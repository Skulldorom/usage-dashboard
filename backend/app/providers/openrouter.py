import math
from datetime import UTC, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

from app.analytics.normalizer import parse_time

from app.analytics.capabilities import analytics_spec, metric_spec
from app.providers.base import Metric, ProviderAdapter, ProviderUsage


class OpenRouterAdapter(ProviderAdapter):
    id = "openrouter"
    name = "OpenRouter"
    description = "OpenRouter API key limits or account-wide credit balances."
    default_base_url = "https://openrouter.ai/api/v1"
    metric_names = [
        "limit_remaining",
        "usage_daily",
        "usage_weekly",
        "usage_monthly",
        "limit",
        "account_credit_balance",
        "account_credits_used",
        "account_credits_purchased",
        "openrouter_account_spend",
        "openrouter_account_requests",
        "openrouter_account_prompt_tokens",
        "openrouter_account_completion_tokens",
        "openrouter_account_reasoning_tokens",
    ]
    alert_metrics = [
        {"metric": "limit_remaining", "label": "Limit remaining", "unit": "credits", "direction": "decreasing"},
        {
            "metric": "account_credit_balance",
            "label": "Available account credits",
            "unit": "credits",
            "direction": "decreasing",
        },
        {"metric": "usage_daily", "label": "Daily usage", "unit": "credits", "direction": "increasing"},
        {"metric": "usage_weekly", "label": "Weekly usage", "unit": "credits", "direction": "increasing"},
        {"metric": "usage_monthly", "label": "Monthly usage", "unit": "credits", "direction": "increasing"},
    ]
    analytics = analytics_spec(
        supported=True,
        native_history=True,
        metrics={
            "limit_remaining": metric_spec(
                type_="remaining", unit="credits", direction="decreasing", capacity_metric="limit", utilization=True
            ),
            "usage_daily": metric_spec(type_="counter", unit="credits", direction="increasing", window="24h"),
            "usage_weekly": metric_spec(type_="counter", unit="credits", direction="increasing", window="7d"),
            "usage_monthly": metric_spec(
                type_="counter", unit="credits", direction="increasing", window="30d", overview=True
            ),
            "limit": metric_spec(type_="gauge", unit="credits", direction="increasing", deltas=False),
            # Account credits are financial state, not workload or provider-spend history.
            # Gauges deliberately prevent aggregation with individual-key windows.
            "account_credit_balance": metric_spec(
                type_="balance", unit="credits", direction="decreasing", deltas=False
            ),
            "account_credits_used": metric_spec(type_="gauge", unit="credits", direction="increasing", deltas=False),
            "account_credits_purchased": metric_spec(
                type_="gauge", unit="credits", direction="increasing", deltas=False
            ),
            "openrouter_account_spend": metric_spec(
                type_="counter", unit="USD", direction="increasing", aggregations=["daily"], overview=True
            ),
            "openrouter_account_requests": metric_spec(
                type_="counter", unit="requests", direction="increasing", aggregations=["daily"]
            ),
            "openrouter_account_prompt_tokens": metric_spec(
                type_="counter", unit="tokens", direction="increasing", aggregations=["daily"]
            ),
            "openrouter_account_completion_tokens": metric_spec(
                type_="counter", unit="tokens", direction="increasing", aggregations=["daily"]
            ),
            "openrouter_account_reasoning_tokens": metric_spec(
                type_="counter", unit="tokens", direction="increasing", aggregations=["daily"]
            ),
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._validate_endpoint()

    @property
    def account_wide(self) -> bool:
        mode = self.extra.get("monitoring_mode", "individual_key")
        if mode not in {"individual_key", "account_wide"}:
            raise ValueError("OpenRouter monitoring_mode must be individual_key or account_wide")
        return mode == "account_wide"

    def _validate_endpoint(self) -> None:
        if not self.account_wide:
            return
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "openrouter.ai"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.path.rstrip("/") != "/api/v1"
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OpenRouter Management credentials may only be sent to https://openrouter.ai/api/v1")

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if not self.account_wide:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                resp = await client.get(f"{self.base_url}/key", headers=headers)
                resp.raise_for_status()
                return self.parse_usage(resp.json())

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            credits_resp = await client.get("https://openrouter.ai/api/v1/credits", headers=headers)
            credits_resp.raise_for_status()
            credits = credits_resp.json()
            activity = None
            try:
                params = {}
                workspace_id = self.extra.get("workspace_id")
                if workspace_id:
                    params["workspace_id"] = workspace_id
                if self.extra.get("activity_group_by_workspace"):
                    params["group_by"] = "workspace"
                activity_resp = await client.get(
                    "https://openrouter.ai/api/v1/activity", headers=headers, params=params or None
                )
                activity_resp.raise_for_status()
                parsed = activity_resp.json()
                if isinstance(parsed, dict):
                    activity = parsed
            except (httpx.HTTPError, ValueError):
                # Credits remain authoritative when the optional activity API is unavailable.
                activity = None
        usage = self.parse_account_usage(credits)
        if activity is not None:
            usage.raw["activity"] = activity
        return usage

    @staticmethod
    def native_observations(raw: dict) -> list[dict]:
        """Normalize documented, completed UTC activity rows into observations."""
        activity = raw.get("activity") if isinstance(raw, dict) else None
        rows = activity.get("data") if isinstance(activity, dict) else None
        if not isinstance(rows, list):
            return []
        observations = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = parse_time(row.get("date"))
            if day is None:
                continue
            start = day.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            dimensions = {
                "openrouter_account_spend": (row.get("usage"), "USD"),
                "openrouter_account_requests": (row.get("requests"), "requests"),
                "openrouter_account_prompt_tokens": (row.get("prompt_tokens"), "tokens"),
                "openrouter_account_completion_tokens": (row.get("completion_tokens"), "tokens"),
                "openrouter_account_reasoning_tokens": (row.get("reasoning_tokens"), "tokens"),
            }
            scope = row.get("workspace_id")
            for metric, (value, unit) in dimensions.items():
                number = OpenRouterAdapter._number(value)
                if number is None:
                    continue
                observations.append(
                    {
                        "metric": metric,
                        "value": number,
                        "unit": unit,
                        "observed_at": start,
                        "window_start": start,
                        "window_end": end,
                        "kind": "delta",
                        "scope": scope,
                        "model": row.get("model"),
                        "provider_mapping": row.get("provider_name"),
                    }
                )
        return observations

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return result if result.is_finite() else None

    @staticmethod
    def _number(value):
        number = OpenRouterAdapter._decimal(value)
        if number is None:
            return None
        try:
            converted = float(number)
        except (OverflowError, ValueError):
            return None
        return converted if math.isfinite(converted) else None

    @staticmethod
    def _object(data, context):
        if not isinstance(data, dict):
            raise ValueError(f"OpenRouter {context} response must be an object")
        info = data.get("data", data)
        if not isinstance(info, dict):
            raise ValueError(f"OpenRouter {context} response data must be an object")
        return info

    @staticmethod
    def parse_usage(data: dict) -> ProviderUsage:
        info = OpenRouterAdapter._object(data, "key")
        remaining = OpenRouterAdapter._number(info.get("limit_remaining"))
        limit = OpenRouterAdapter._number(info.get("limit"))
        metrics = [
            Metric("limit_remaining", remaining, "credits", limit),
            Metric("usage_daily", OpenRouterAdapter._number(info.get("usage_daily")), "credits"),
            Metric("usage_weekly", OpenRouterAdapter._number(info.get("usage_weekly")), "credits"),
            Metric("usage_monthly", OpenRouterAdapter._number(info.get("usage_monthly")), "credits"),
            Metric("limit", limit, "credits"),
        ]
        label = info.get("label") or "OpenRouter key"
        summary = f"{remaining} credits remaining" if remaining is not None else f"{label} usage fetched"
        return ProviderUsage(status="healthy", summary=summary, metrics=metrics, raw=data)

    @staticmethod
    def parse_account_usage(data: dict) -> ProviderUsage:
        info = OpenRouterAdapter._object(data, "credits")
        purchased = OpenRouterAdapter._decimal(info.get("total_credits"))
        used = OpenRouterAdapter._decimal(info.get("total_usage"))
        if purchased is None or used is None:
            raise ValueError("OpenRouter credits response is missing finite total_credits or total_usage")
        try:
            balance = purchased - used
            values = [float(item) for item in (balance, used, purchased)]
        except (ArithmeticError, OverflowError, ValueError):
            raise ValueError("OpenRouter credits response contains an unsupported numeric value") from None
        if not all(math.isfinite(item) for item in values):
            raise ValueError("OpenRouter credits response contains an unsupported numeric value")
        balance_value, used_value, purchased_value = values
        metrics = [
            Metric("account_credit_balance", balance_value, "credits"),
            Metric("account_credits_used", used_value, "credits"),
            Metric("account_credits_purchased", purchased_value, "credits"),
        ]
        return ProviderUsage(
            status="healthy",
            summary=f"{balance} account credits available",
            metrics=metrics,
            raw={"credits": {"total_credits": purchased_value, "total_usage": used_value}},
        )
