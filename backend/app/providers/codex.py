import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.analytics.capabilities import analytics_spec, metric_spec
from app.providers.base import Metric, ProviderAdapter, ProviderUsage

OPENAI_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
REFRESH_LEAD = timedelta(minutes=5)


@dataclass(slots=True)
class CodexCredentials:
    access_token: str
    refresh_token: str
    expires_at: datetime | None = None
    account_id: str | None = None

    @classmethod
    def from_secret_json(cls, secret: str, extra: dict[str, Any] | None = None) -> "CodexCredentials":
        if extra and any(key in extra for key in ("access_token", "refresh_token", "id_token")):
            raise ValueError("Codex OAuth tokens must be stored encrypted, not in plaintext extra")
        try:
            payload = json.loads(secret)
        except json.JSONDecodeError as exc:
            raise ValueError("Codex api_key must be an encrypted JSON OAuth token bundle") from exc
        if not isinstance(payload, dict):
            raise ValueError("Codex api_key must be an encrypted JSON OAuth token bundle")
        access_token = _clean_string(payload.get("access_token"))
        refresh_token = _clean_string(payload.get("refresh_token"))
        if not access_token:
            raise ValueError("Codex OAuth token bundle is missing access_token")
        if not refresh_token:
            raise ValueError("Codex OAuth token bundle is missing refresh_token")
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=_parse_datetime(payload.get("expires_at")),
            account_id=_clean_string(payload.get("account_id") or payload.get("workspace_id") or payload.get("chatgpt_account_id")),
        )

    def to_secret_json(self) -> str:
        payload = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.astimezone(UTC).isoformat() if self.expires_at else None,
            "account_id": self.account_id,
        }
        return json.dumps({key: value for key, value in payload.items() if value is not None}, separators=(",", ":"), sort_keys=True)

    def needs_refresh(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (now or datetime.now(UTC)) + REFRESH_LEAD


class CodexAdapter(ProviderAdapter):
    id = "codex"
    name = "OpenAI Codex"
    description = "ChatGPT OAuth Codex rate-limit windows from the wham usage endpoint. Store access + refresh tokens encrypted."
    default_base_url = "https://chatgpt.com"
    metric_names = [
        "plan_type",
        "session_remaining_percent",
        "session_reset_at",
        "weekly_remaining_percent",
        "weekly_reset_at",
        "limit_reached",
        "reset_credits_available",
        "review_session_remaining_percent",
        "review_weekly_remaining_percent",
    ]
    alert_metrics = [
        {"metric": "session_remaining_percent", "label": "Session remaining", "unit": "%", "direction": "decreasing"},
        {"metric": "weekly_remaining_percent", "label": "Weekly remaining", "unit": "%", "direction": "decreasing"},
        {"metric": "review_session_remaining_percent", "label": "Review session remaining", "unit": "%", "direction": "decreasing"},
        {"metric": "review_weekly_remaining_percent", "label": "Review weekly remaining", "unit": "%", "direction": "decreasing"},
        {"metric": "reset_credits_available", "label": "Reset credits available", "unit": "credits", "direction": "decreasing"},
    ]
    analytics = analytics_spec(
        supported=True,
        native_history=False,
        metrics={
            "session_remaining_percent": metric_spec(type_="remaining", unit="%", direction="decreasing", maximum=100, reset_metric="session_reset_at", window="session", utilization=True),
            "weekly_remaining_percent": metric_spec(type_="remaining", unit="%", direction="decreasing", maximum=100, reset_metric="weekly_reset_at", window="week", utilization=True, overview=True),
            "review_session_remaining_percent": metric_spec(type_="remaining", unit="%", direction="decreasing", maximum=100, reset_metric="review_session_reset_at", window="session"),
            "review_weekly_remaining_percent": metric_spec(type_="remaining", unit="%", direction="decreasing", maximum=100, reset_metric="review_weekly_reset_at", window="week"),
            "reset_credits_available": metric_spec(type_="balance", unit="credits", direction="decreasing"),
        },
    )

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 20.0,
        extra: dict[str, Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        super().__init__(api_key, base_url=base_url, timeout=timeout, extra=extra)
        self.credentials = CodexCredentials.from_secret_json(api_key, self.extra)
        self._transport = transport
        self.updated_secret: str | None = None

    async def fetch_usage(self) -> ProviderUsage:
        if self.credentials.needs_refresh():
            await self.refresh_access_token()
        headers = {
            "Authorization": f"Bearer {self.credentials.access_token}",
            "Accept": "application/json",
            "OpenAI-Beta": "codex-1",
            "originator": "codex_cli_rs",
        }
        if self.credentials.account_id:
            headers["ChatGPT-Account-ID"] = self.credentials.account_id
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            response = await client.get(f"{self.base_url}/backend-api/wham/usage", headers=headers)
            if response.status_code in (401, 403):
                raise ValueError("Codex token expired or was rejected - re-authorize the Codex provider")
            response.raise_for_status()
            data = response.json()
        return self.parse_usage(data)

    async def refresh_access_token(self) -> None:
        payload = {"grant_type": "refresh_token", "refresh_token": self.credentials.refresh_token}
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            response = await client.post(OPENAI_OAUTH_TOKEN_URL, data=payload, headers={"Accept": "application/json"})
            if response.status_code in (400, 401, 403):
                raise ValueError("Codex refresh token expired or was rejected - re-authorize the Codex provider")
            response.raise_for_status()
            data = response.json()
        access_token = _clean_string(data.get("access_token"))
        if not access_token:
            raise ValueError("Codex token refresh response did not include an access_token")
        refresh_token = _clean_string(data.get("refresh_token")) or self.credentials.refresh_token
        expires_at = _expires_at_from_response(data) or self.credentials.expires_at
        self.credentials = CodexCredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            account_id=self.credentials.account_id,
        )
        self.updated_secret = self.credentials.to_secret_json()

    @staticmethod
    def parse_usage(data: dict[str, Any]) -> ProviderUsage:
        plan = _clean_string(data.get("plan_type") or _deep_get(data, "summary", "plan")) or "Codex"
        codex_limit = _find_limit(data, "codex") or data.get("rate_limit") or data.get("rate_limits") or {}
        review_limit = _find_limit(data, "code_review") or _find_review_limit(data) or {}
        session = _window(codex_limit, "primary_window")
        weekly = _window(codex_limit, "secondary_window")
        review_session = _window(review_limit, "primary_window")
        review_weekly = _window(review_limit, "secondary_window")
        metrics = [Metric("plan_type", plan)]
        if session["used_percent"] is not None:
            metrics.append(Metric("session_remaining_percent", _remaining_percent(session["used_percent"]), "%", 100))
        if session["reset_at"]:
            metrics.append(Metric("session_reset_at", session["reset_at"]))
        if weekly["used_percent"] is not None:
            metrics.append(Metric("weekly_remaining_percent", _remaining_percent(weekly["used_percent"]), "%", 100))
        if weekly["reset_at"]:
            metrics.append(Metric("weekly_reset_at", weekly["reset_at"]))
        metrics.append(Metric("limit_reached", bool(codex_limit.get("limit_reached"))))
        reset_credits = _reset_credits(data, codex_limit)
        if reset_credits is not None:
            metrics.append(Metric("reset_credits_available", reset_credits))
        if review_limit:
            metrics.append(Metric("review_limit_reached", bool(review_limit.get("limit_reached"))))
            if review_session["used_percent"] is not None:
                metrics.append(Metric("review_session_remaining_percent", _remaining_percent(review_session["used_percent"]), "%", 100))
            if review_session["reset_at"]:
                metrics.append(Metric("review_session_reset_at", review_session["reset_at"]))
            if review_weekly["used_percent"] is not None:
                metrics.append(Metric("review_weekly_remaining_percent", _remaining_percent(review_weekly["used_percent"]), "%", 100))
            if review_weekly["reset_at"]:
                metrics.append(Metric("review_weekly_reset_at", review_weekly["reset_at"]))
        summary_parts = []
        if session["used_percent"] is not None:
            summary_parts.append(f"{_format_number(_remaining_percent(session['used_percent']))}% session left")
        if weekly["used_percent"] is not None:
            summary_parts.append(f"{_format_number(_remaining_percent(weekly['used_percent']))}% weekly left")
        summary = f"{plan} - {', '.join(summary_parts)}" if summary_parts else f"{plan} Codex usage available"
        return ProviderUsage(status="healthy", summary=summary, metrics=metrics, raw=data)


def _remaining_percent(used_percent: float | int) -> float | int:
    remaining = max(0, min(100, 100 - used_percent))
    if isinstance(used_percent, int) or remaining.is_integer():
        return int(remaining)
    return remaining


def _clean_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _expires_at_from_response(data: dict[str, Any]) -> datetime | None:
    expires_at = _parse_datetime(data.get("expires_at"))
    if expires_at:
        return expires_at
    expires_in = data.get("expires_in")
    if isinstance(expires_in, int | float) and expires_in > 0:
        return datetime.now(UTC) + timedelta(seconds=float(expires_in))
    return None


def _deep_get(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _find_limit(data: dict[str, Any], limit_id: str) -> dict[str, Any] | None:
    by_id = data.get("rate_limits_by_limit_id")
    if isinstance(by_id, dict) and isinstance(by_id.get(limit_id), dict):
        return by_id[limit_id]
    return None


def _find_review_limit(data: dict[str, Any]) -> dict[str, Any] | None:
    direct = data.get("code_review_rate_limit")
    if isinstance(direct, dict):
        return direct
    for item in data.get("additional_rate_limits") or []:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(str(item.get(key, "")) for key in ("id", "name", "label", "quotaFamily", "quota_family")).lower()
        if "review" in haystack:
            return item
    return None


def _coerce_percent(value: Any) -> float | int | None:
    if isinstance(value, str):
        cleaned = value.strip().removesuffix("%").strip()
        try:
            value = float(cleaned)
        except ValueError:
            return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    value = max(0, min(100, value))
    if isinstance(value, int) or float(value).is_integer():
        return int(value)
    return float(value)


def _window_candidates(limit: dict[str, Any], key: str) -> list[Any]:
    if key == "primary_window":
        aliases = ("primary_window", "session_window", "current_window", "primary", "session")
        tokens = ("primary", "session", "current")
    else:
        aliases = ("secondary_window", "weekly_window", "week_window", "weekly", "week", "secondary")
        tokens = ("secondary", "weekly", "week")
    candidates = [limit.get(alias) for alias in aliases]
    for collection_key in ("windows", "rate_limit_windows", "rateLimitWindows"):
        windows = limit.get(collection_key)
        if not isinstance(windows, list):
            continue
        for item in windows:
            if not isinstance(item, dict):
                continue
            haystack = " ".join(str(item.get(name, "")) for name in ("id", "key", "name", "label", "type", "window", "window_type", "windowType")).lower()
            if any(token in haystack for token in tokens):
                candidates.append(item)
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _normalize_reset_at(value: Any) -> str | None:
    """Normalize a provider reset timestamp to a UTC ISO-8601 string.

    Preserves provider-supplied ISO strings verbatim, converts numeric Unix
    timestamps (seconds since epoch) to a UTC ISO-8601 string, and returns
    ``None`` for anything unusable (missing, boolean, or non-finite/out-of-range
    numbers) so callers never fabricate a reset time.
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(timestamp):
            return None
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _window(limit: Any, key: str) -> dict[str, float | int | str | None]:
    if not isinstance(limit, dict):
        return {"used_percent": None, "reset_at": None}
    for window in _window_candidates(limit, key):
        used = None
        for used_key in ("used_percent", "percent_used", "usage_percent", "used_pct", "usedPct", "usagePct"):
            used = _coerce_percent(window.get(used_key))
            if used is not None:
                break
        if used is None:
            for remaining_key in ("remaining_percent", "percent_remaining", "remaining_pct", "remainingPct"):
                remaining = _coerce_percent(window.get(remaining_key))
                if remaining is not None:
                    used = 100 - remaining
                    break
        reset_at = _normalize_reset_at(
            window.get("reset_at") or window.get("resets_at") or window.get("resetAt") or window.get("reset_time")
        )
        if used is not None or reset_at is not None:
            return {"used_percent": used, "reset_at": reset_at}
    return {"used_percent": None, "reset_at": None}


def _reset_credits(data: dict[str, Any], codex_limit: Any) -> int | None:
    for source in (codex_limit, data):
        if not isinstance(source, dict):
            continue
        credits = source.get("rate_limit_reset_credits")
        if isinstance(credits, dict) and isinstance(credits.get("available_count"), int):
            return credits["available_count"]
    return None


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:g}" if isinstance(value, int | float) else str(value)
