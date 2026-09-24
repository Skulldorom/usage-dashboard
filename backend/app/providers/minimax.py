from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.analytics.capabilities import analytics_spec, metric_spec
from app.providers.base import Metric, ProviderAdapter, ProviderUsage
from app.providers.errors import (
    AUTHENTICATION,
    CONFIGURATION,
    INVALID_RESPONSE,
    RATE_LIMIT,
    SCHEMA_CHANGED,
    ProviderError,
    classify_exception,
)


class MiniMaxAdapter(ProviderAdapter):
    """MiniMax Token Plan quota adapter; this does not query PAYG billing."""

    id = "minimax"
    name = "MiniMax"
    description = "MiniMax Token Plan subscription quota. Requires a Token Plan Subscription Key, not a PAYG API key."
    default_base_url = "https://www.minimax.io"
    metric_names = [
        "five_hour_used_percent", "five_hour_remaining_percent", "five_hour_reset_at",
        "weekly_used_percent", "weekly_remaining_percent", "weekly_reset_at",
        "exhausted", "resource_groups",
    ]
    alert_metrics = [
        {"metric": "five_hour_used_percent", "label": "5-hour usage", "unit": "%", "direction": "increasing"},
        {"metric": "weekly_used_percent", "label": "Weekly usage", "unit": "%", "direction": "increasing"},
    ]
    analytics = analytics_spec(
        supported=True,
        native_history=False,
        metrics={
            "five_hour_used_percent": metric_spec(type_="gauge", unit="%", direction="increasing", maximum=100, reset_metric="five_hour_reset_at", window="5h", utilization=True, deltas=False),
            "weekly_used_percent": metric_spec(type_="gauge", unit="%", direction="increasing", maximum=100, reset_metric="weekly_reset_at", window="week", utilization=True, overview=True, deltas=False),
            "five_hour_remaining_percent": metric_spec(type_="remaining", unit="%", direction="decreasing", maximum=100, reset_metric="five_hour_reset_at", window="5h", utilization=True),
            "weekly_remaining_percent": metric_spec(type_="remaining", unit="%", direction="decreasing", maximum=100, reset_metric="weekly_reset_at", window="week", utilization=True),
        },
    )

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/v1/token_plan/remains", headers=headers)
        except httpx.HTTPError as exc:
            raise classify_exception(exc, stage="fetch_usage") from exc
        if response.status_code in (401, 403):
            raise ProviderError.from_response(response, category=AUTHENTICATION, message="MiniMax rejected the Token Plan Subscription Key", stage="fetch_usage", retryable=False)
        if response.status_code == 429:
            raise ProviderError.from_response(response, category=RATE_LIMIT, message="MiniMax Token Plan rate limit exceeded", stage="fetch_usage", retryable=True)
        if response.is_error:
            response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(category=INVALID_RESPONSE, message="MiniMax returned malformed JSON", stage="parse_response", retryable=False) from exc
        return self.parse_usage(data)

    @staticmethod
    def parse_usage(data: dict[str, Any]) -> ProviderUsage:
        if not isinstance(data, dict):
            raise ProviderError(category=SCHEMA_CHANGED, message="MiniMax returned an unusable Token Plan response", stage="parse_response", retryable=False)
        base_resp = data.get("base_resp")
        if not isinstance(base_resp, dict):
            raise ProviderError(category=SCHEMA_CHANGED, message="MiniMax response is missing subscription status", stage="parse_response", retryable=False)
        status_code = base_resp.get("status_code")
        if status_code != 0:
            raise _business_error(status_code, base_resp.get("status_msg"))
        entries = data.get("model_remains")
        if not isinstance(entries, list):
            raise ProviderError(category=SCHEMA_CHANGED, message="MiniMax response is missing resource group quota data", stage="parse_response", retryable=False)
        groups = [_resource_group(entry) for entry in entries if isinstance(entry, dict)]
        valid_groups = [
            group for group in groups
            if group["model"] and any(
                group[f"{prefix}_{field}"] is not None
                for prefix in ("five_hour", "weekly")
                for field in ("remaining_percent", "status", "reset_at")
            )
        ]
        if not valid_groups:
            raise ProviderError(category=SCHEMA_CHANGED, message="MiniMax response contains no usable resource group quota data", stage="parse_response", retryable=False)

        primary = next((group for group in valid_groups if group["model"] == "general"), valid_groups[0])
        metrics: list[Metric] = [Metric("resource_groups", valid_groups)]
        summary_parts: list[str] = []
        exhausted = _is_exhausted(primary)
        for prefix, title in (("five_hour", "5h"), ("weekly", "weekly")):
            remaining = primary[f"{prefix}_remaining_percent"]
            used = primary[f"{prefix}_used_percent"]
            reset = primary[f"{prefix}_reset_at"]
            if used is not None:
                metrics.append(Metric(f"{prefix}_used_percent", used, "%", 100))
                summary_parts.append(f"{used:g}% {title}")
            if remaining is not None:
                metrics.append(Metric(f"{prefix}_remaining_percent", remaining, "%", 100))
            if reset:
                metrics.append(Metric(f"{prefix}_reset_at", reset))
        metrics.append(Metric("exhausted", exhausted))
        return ProviderUsage(
            status="degraded" if exhausted else "healthy",
            summary=", ".join(summary_parts) or f"MiniMax {primary['model']} Token Plan quota fetched",
            metrics=metrics,
            raw=data,
        )


def _business_error(status_code: Any, status_msg: Any) -> ProviderError:
    message = str(status_msg or "MiniMax Token Plan request failed")
    lowered = message.lower()
    if "subscription" in lowered and ("no active" in lowered or "not" in lowered):
        category, public = CONFIGURATION, "MiniMax has no active Token Plan subscription"
    elif any(token in lowered for token in ("key", "auth", "credential", "permission")):
        category, public = AUTHENTICATION, "MiniMax rejected the Token Plan Subscription Key"
    elif any(token in lowered for token in ("rate", "limit", "too many")):
        category, public = RATE_LIMIT, "MiniMax Token Plan rate limit exceeded"
    else:
        category, public = INVALID_RESPONSE, f"MiniMax Token Plan error ({status_code})"
    return ProviderError(category=category, message=public, stage="provider_status", retryable=category == RATE_LIMIT)


def _resource_group(entry: dict[str, Any]) -> dict[str, Any]:
    model = entry.get("model_name")
    group = {"model": str(model) if model is not None else ""}
    for prefix, remaining_key, status_key, reset_key in (
        ("five_hour", "current_interval_remaining_percent", "current_interval_status", "end_time"),
        ("weekly", "current_weekly_remaining_percent", "current_weekly_status", "weekly_end_time"),
    ):
        remaining = _percent(entry.get(remaining_key))
        group[f"{prefix}_remaining_percent"] = remaining
        group[f"{prefix}_used_percent"] = 100 - remaining if remaining is not None else None
        group[f"{prefix}_status"] = _integer(entry.get(status_key))
        group[f"{prefix}_reset_at"] = _timestamp(entry.get(reset_key))
    return group


def _percent(value: Any) -> float | int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= number <= 100:
        return None
    return int(number) if number.is_integer() else number


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> str | None:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000, UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _is_exhausted(group: dict[str, Any]) -> bool:
    for prefix in ("five_hour", "weekly"):
        status = group[f"{prefix}_status"]
        remaining = group[f"{prefix}_remaining_percent"]
        if status == 2:
            return True
        if status != 3 and remaining == 0:
            return True
    return False
