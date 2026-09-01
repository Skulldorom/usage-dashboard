from datetime import UTC, datetime
from typing import Any

import httpx

from app.analytics.capabilities import analytics_spec, metric_spec
from app.providers.base import Metric, ProviderAdapter, ProviderUsage


# Static model identifiers and default per-window request limits published in the
# OpenCode Go documentation. These are used to enrich snapshots when the API
# response omits per-model limits but includes a model usage count.
MODEL_ID_ALIASES: dict[str, tuple[str, ...]] = {
    "grok-4.6": ("grok-4.6",),
    "gpt-5.6-luna": ("gpt-5.6-luna", "gpt5.6luna"),
    "glm-5.3-flash": ("glm-5.3-flash", "glm5.3flash"),
    "glm-5.3": ("glm-5.3", "glm5.3"),
    "glm-5.2": ("glm-5.2", "glm5.2"),
    "glm-5.1": ("glm-5.1", "glm5.1"),
    "kimi-k3": ("kimi-k3", "kimik3"),
    "kimi-k2.7-code": ("kimi-k2.7-code", "kimi-k2.7code", "k2.7-code"),
    "kimi-k2.6": ("kimi-k2.6", "k2.6"),
    "kimi-k2.5": ("kimi-k2.5", "k2.5"),
    "longcat-2.0": ("longcat-2.0", "longcat2.0"),
    "mimo-v2.5": ("mimo-v2.5", "mimov2.5"),
    "mimo-v2.5-pro": ("mimo-v2.5-pro", "mimov2.5pro"),
    "minimax-m3": ("minimax-m3", "minimaxm3"),
    "minimax-m2.7": ("minimax-m2.7", "minimaxm2.7", "minimax-m2.5"),
    "muse-spark-1.2-contributor": ("muse-spark-1.2-contributor", "musespark1.2"),
    "qwen3.8-max": ("qwen3.8-max", "qwen38max"),
    "qwen3.8-flash": ("qwen3.8-flash", "qwen38flash"),
    "qwen3.7-max": ("qwen3.7-max", "qwen37max"),
    "qwen3.7-plus": ("qwen3.7-plus", "qwen37plus"),
    "qwen3.6-plus": ("qwen3.6-plus", "qwen36plus"),
    "qwen3.5-plus": ("qwen3.5-plus", "qwen35plus"),
    "deepseek-v4-pro": ("deepseek-v4-pro", "deepseekv4pro"),
    "deepseek-v4-flash": ("deepseek-v4-flash", "deepseekv4flash"),
    "deepseek-v4-flash-vision-exp": ("deepseek-v4-flash-vision-exp", "deepseekv4flashvisionexp"),
    "hy4-preview": ("hy4-preview", "hy4preview"),
    "hy3": ("hy3",),
}

# Canonical model ID -> (5h, weekly, monthly) request limits as documented.
MODEL_REQUEST_LIMITS: dict[str, tuple[int | None, int | None, int | None]] = {
    "grok-4.6": (169, 423, 845),
    "gpt-5.6-luna": (2050, 5100, 10250),
    "glm-5.3-flash": (1580, 3950, 7900),
    "glm-5.3": (220, 540, 1080),
    "glm-5.2": (880, 2150, 4300),
    "glm-5.1": (880, 2150, 4300),
    "kimi-k3": (110, 250, 490),
    "kimi-k2.7-code": (1350, 3380, 6750),
    "kimi-k2.6": (1150, 2880, 5750),
    "kimi-k2.5": (None, None, None),
    "longcat-2.0": (11400, 28600, 57200),
    "mimo-v2.5": (30100, 75200, 150400),
    "mimo-v2.5-pro": (3250, 8150, 16300),
    "minimax-m3": (3200, 8000, 16000),
    "minimax-m2.7": (3400, 8500, 17000),
    "muse-spark-1.2-contributor": (45300, 113300, 226600),
    "qwen3.8-max": (160, 400, 810),
    "qwen3.8-flash": (5400, 13500, 27000),
    "qwen3.7-max": (340, 840, 1690),
    "qwen3.7-plus": (4300, 10800, 21600),
    "qwen3.6-plus": (3300, 8200, 16300),
    "qwen3.5-plus": (None, None, None),
    "deepseek-v4-pro": (1050, 2600, 5200),
    "deepseek-v4-flash": (7600, 18900, 37800),
    "deepseek-v4-flash-vision-exp": (3800, 9450, 18900),
    "hy4-preview": (1350, 3380, 6770),
    "hy3": (4300, 10750, 21500),
}

# Known subscription usage limits in USD.
DEFAULT_LIMITS = {
    "five_hour": 12.0,
    "weekly": 30.0,
    "monthly": 60.0,
}

_WINDOW_KEYS = {
    "five_hour": ("five_hour", "5_hour", "five_hr", "5hr", "hour", "session"),
    "weekly": ("weekly", "week", "7_day"),
    "monthly": ("monthly", "month", "30_day"),
}


class OpenCodeGoAdapter(ProviderAdapter):
    id = "opencode-go"
    name = "OpenCode Go"
    description = "OpenCode Go subscription usage and per-model request limits. Requires a Go API key."
    default_base_url = "https://opencode.ai"
    metric_names = [
        "plan_type",
        "five_hour_usage",
        "five_hour_remaining",
        "five_hour_limit",
        "five_hour_reset_at",
        "weekly_usage",
        "weekly_remaining",
        "weekly_limit",
        "weekly_reset_at",
        "monthly_usage",
        "monthly_remaining",
        "monthly_limit",
        "monthly_reset_at",
        "balance_fallback_enabled",
        "exhausted",
        "models_used",
    ]
    alert_metrics = [
        {"metric": "five_hour_remaining", "label": "5-hour remaining", "unit": "USD", "direction": "decreasing"},
        {"metric": "weekly_remaining", "label": "Weekly remaining", "unit": "USD", "direction": "decreasing"},
        {"metric": "monthly_remaining", "label": "Monthly remaining", "unit": "USD", "direction": "decreasing"},
        {"metric": "five_hour_usage", "label": "5-hour usage", "unit": "USD", "direction": "increasing"},
        {"metric": "weekly_usage", "label": "Weekly usage", "unit": "USD", "direction": "increasing"},
        {"metric": "monthly_usage", "label": "Monthly usage", "unit": "USD", "direction": "increasing"},
    ]
    analytics = analytics_spec(
        supported=True,
        native_history=False,
        metrics={
            "five_hour_remaining": metric_spec(
                type_="remaining",
                unit="USD",
                direction="decreasing",
                capacity_metric="five_hour_limit",
                reset_metric="five_hour_reset_at",
                window="5h",
                utilization=True,
            ),
            "weekly_remaining": metric_spec(
                type_="remaining",
                unit="USD",
                direction="decreasing",
                capacity_metric="weekly_limit",
                reset_metric="weekly_reset_at",
                window="week",
                utilization=True,
                overview=True,
            ),
            "monthly_remaining": metric_spec(
                type_="remaining",
                unit="USD",
                direction="decreasing",
                capacity_metric="monthly_limit",
                reset_metric="monthly_reset_at",
                window="month",
                utilization=True,
            ),
            "five_hour_usage": metric_spec(type_="counter", unit="USD", direction="increasing", window="5h"),
            "weekly_usage": metric_spec(type_="counter", unit="USD", direction="increasing", window="week"),
            "monthly_usage": metric_spec(type_="counter", unit="USD", direction="increasing", window="month"),
            "five_hour_limit": metric_spec(type_="gauge", unit="USD", direction="increasing", deltas=False),
            "weekly_limit": metric_spec(type_="gauge", unit="USD", direction="increasing", deltas=False),
            "monthly_limit": metric_spec(type_="gauge", unit="USD", direction="increasing", deltas=False),
        },
    )

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/zen/go/v1/usage", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return self.parse_usage(data)

    @staticmethod
    def parse_usage(data: dict[str, Any]) -> ProviderUsage:
        payload = data.get("data") or data
        if not isinstance(payload, dict):
            payload = {}

        metrics: list[Metric] = []
        summary_parts: list[str] = []

        plan_type = _first_text(payload.get("plan_type"), payload.get("plan"), payload.get("subscription"))
        if plan_type:
            metrics.append(Metric("plan_type", plan_type))

        balance_fallback = bool(payload.get("use_balance")) or bool(payload.get("balance_fallback_enabled"))

        windows = _extract_windows(payload)
        exhausted = bool(payload.get("exhausted")) or bool(payload.get("limit_reached"))
        for key, title in (
            ("five_hour", "5h"),
            ("weekly", "weekly"),
            ("monthly", "monthly"),
        ):
            window = windows.get(key)
            if window is None:
                continue
            used = window.get("usage")
            limit = window.get("limit")
            remaining = window.get("remaining")
            reset_at = window.get("reset_at")

            if used is not None:
                metrics.append(Metric(f"{key}_usage", used, "USD"))
            if remaining is not None:
                metrics.append(Metric(f"{key}_remaining", remaining, "USD", limit))
            if limit is not None:
                metrics.append(Metric(f"{key}_limit", limit, "USD"))
            if reset_at:
                metrics.append(Metric(f"{key}_reset_at", reset_at))

            if remaining is not None and limit is not None and limit > 0:
                summary_parts.append(f"${remaining:.2f}/{limit:.0f} {title}")
            elif used is not None and limit is not None and limit > 0:
                summary_parts.append(f"${used:.2f}/{limit:.0f} {title}")

            # Treat a fully consumed window as exhausted.
            if remaining is not None and remaining <= 0:
                exhausted = True

        metrics.append(Metric("balance_fallback_enabled", balance_fallback))

        # Per-model request usage and limits.
        model_usage = _extract_model_usage(payload)
        models_used: list[dict[str, Any]] = []
        exhausted_models: list[str] = []
        for model_id, used in model_usage.items():
            canonical = _canonical_model_id(model_id)
            limits = MODEL_REQUEST_LIMITS.get(canonical) or (None, None, None)
            five_h_limit, week_limit, month_limit = limits
            remaining_month = (month_limit - used) if isinstance(month_limit, int) and isinstance(used, int) else None
            model_metric_value: dict[str, Any] = {
                "model": canonical or model_id,
                "used": used,
            }
            if five_h_limit is not None:
                model_metric_value["five_hour_limit"] = five_h_limit
            if week_limit is not None:
                model_metric_value["weekly_limit"] = week_limit
            if month_limit is not None:
                model_metric_value["monthly_limit"] = month_limit
                model_metric_value["monthly_remaining"] = remaining_month
            if isinstance(remaining_month, int) and remaining_month <= 0:
                exhausted_models.append(canonical or model_id)
            models_used.append(model_metric_value)

        if models_used:
            metrics.append(Metric("models_used", models_used))

        if exhausted_models and not exhausted:
            exhausted = True
        metrics.append(Metric("exhausted", exhausted))

        status = "healthy"
        if exhausted:
            status = "degraded"

        if summary_parts:
            summary = "OpenCode Go - " + ", ".join(summary_parts)
        elif model_usage:
            summary = f"OpenCode Go - {len(model_usage)} model(s) tracked"
        else:
            summary = "OpenCode Go usage fetched"

        return ProviderUsage(status=status, summary=summary, metrics=metrics, raw=data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
        if parsed.is_integer():
            return int(parsed)
        return parsed
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_reset_at(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        if not timestamp or timestamp < 0:
            return None
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _extract_windows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract the three canonical usage windows from the API payload.

    Tolerates a variety of nesting and naming conventions so the adapter keeps
    working if OpenCode tweaks the response schema.
    """
    windows: dict[str, dict[str, Any]] = {}
    raw_windows: dict[str, Any] = {}

    # Top-level window collections.
    for collection_key in ("windows", "limits", "usage_windows", "rate_limits"):
        collection = payload.get(collection_key)
        if isinstance(collection, dict):
            raw_windows.update(collection)
        elif isinstance(collection, list):
            for item in collection:
                if isinstance(item, dict):
                    name = _first_text(item.get("id"), item.get("key"), item.get("name"), item.get("label"), item.get("window"))
                    if name:
                        raw_windows[name] = item

    # Flat keys directly on the payload.
    for canonical, aliases in _WINDOW_KEYS.items():
        for alias in aliases:
            for suffix in ("", "_window", "_limit", "_usage"):
                key = f"{alias}{suffix}"
                if key in payload:
                    raw_windows.setdefault(canonical, {}).update({"id": canonical, key: payload[key]})

    for canonical in ("five_hour", "weekly", "monthly"):
        window = _coerce_window(raw_windows, canonical)
        if window is None:
            # Try a flat fallback using known default limits.
            usage = _number(payload.get(f"{canonical}_usage"))
            limit = _number(payload.get(f"{canonical}_limit"))
            if usage is not None or limit is not None:
                window = {
                    "usage": usage,
                    "limit": limit or DEFAULT_LIMITS.get(canonical),
                    "remaining": _number(payload.get(f"{canonical}_remaining")),
                    "reset_at": _normalize_reset_at(payload.get(f"{canonical}_reset_at")),
                }
        if window is None and canonical == "monthly" and ("usage" in payload or "limit" in payload):
            # Ultra-flat single-window response.
            usage = _number(payload.get("usage"))
            limit = _number(payload.get("limit"))
            if usage is not None or limit is not None:
                window = {"usage": usage, "limit": limit, "remaining": _number(payload.get("remaining")), "reset_at": _normalize_reset_at(payload.get("reset_at"))}
        if window is not None:
            windows[canonical] = window

    # Fill missing limits with documented defaults.
    for canonical in ("five_hour", "weekly", "monthly"):
        window = windows.get(canonical)
        if window is None:
            continue
        if window.get("limit") is None:
            window["limit"] = DEFAULT_LIMITS.get(canonical)
        if window.get("remaining") is None and isinstance(window.get("usage"), (int, float)) and isinstance(window["limit"], (int, float)):
            window["remaining"] = max(0, round(window["limit"] - window["usage"], 4))

    return windows


def _coerce_window(raw_windows: dict[str, Any], canonical: str) -> dict[str, Any] | None:
    candidates: list[tuple[str, Any]] = []
    for key, value in raw_windows.items():
        normalized = key.lower().replace(" ", "_").replace("-", "_")
        if normalized == canonical or normalized in _WINDOW_KEYS.get(canonical, ()):
            candidates.append((key, value))

    for key, value in candidates:
        if isinstance(value, dict):
            usage = _number(value.get("usage") or value.get("used") or value.get("current"))
            limit = _number(value.get("limit") or value.get("max") or value.get("maximum") or value.get("cap"))
            remaining = _number(value.get("remaining") or value.get("left") or value.get("available"))
            reset_at = _normalize_reset_at(
                value.get("reset_at") or value.get("resets_at") or value.get("reset_time") or value.get("reset")
            )
            if usage is not None or limit is not None or remaining is not None or reset_at is not None:
                return {
                    "usage": usage,
                    "limit": limit,
                    "remaining": remaining,
                    "reset_at": reset_at,
                }
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            return {"usage": _number(value), "limit": DEFAULT_LIMITS.get(canonical), "remaining": None, "reset_at": None}

    return None


def _extract_model_usage(payload: dict[str, Any]) -> dict[str, int]:
    """Extract per-model request usage counts from the payload.

    Returns a dict of raw model ID -> used requests. Unknown model IDs are
    preserved so callers can still surface them.
    """
    result: dict[str, int] = {}
    for collection_key in ("models", "model_usage", "per_model", "models_used"):
        collection = payload.get(collection_key)
        if isinstance(collection, dict):
            for model_id, value in collection.items():
                used = _model_used(value)
                if used is not None:
                    result[model_id] = used
        elif isinstance(collection, list):
            for item in collection:
                if not isinstance(item, dict):
                    continue
                model_id = _first_text(
                    item.get("id"),
                    item.get("model"),
                    item.get("model_id"),
                    item.get("name"),
                )
                if not model_id:
                    continue
                used = _model_used(item.get("usage") or item.get("used") or item.get("requests"))
                if used is not None:
                    result[model_id] = used
    return result


def _model_used(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, dict):
        return _model_used(value.get("requests") or value.get("used") or value.get("usage") or value.get("count"))
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def _canonical_model_id(model_id: str) -> str | None:
    normalized = model_id.lower().replace(" ", "_").replace("-", "_")
    for canonical, aliases in MODEL_ID_ALIASES.items():
        if normalized == canonical.replace("-", "_"):
            return canonical
        for alias in aliases:
            if normalized == alias.replace("-", "_"):
                return canonical
    return None
