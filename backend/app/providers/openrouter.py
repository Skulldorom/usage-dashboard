from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

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
        native_history=False,
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
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._validate_base_url()

    @property
    def account_wide(self) -> bool:
        return (self.extra.get("monitoring_mode") or "individual_key") == "account_wide"

    def _validate_base_url(self) -> None:
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "openrouter.ai"
            or parsed.port is not None
            or parsed.path.rstrip("/") != "/api/v1"
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OpenRouter credentials may only be sent to https://openrouter.ai/api/v1")

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        endpoint = "credits" if self.account_wide else "key"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            resp = await client.get(f"{self.base_url}/{endpoint}", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return self.parse_account_usage(data) if self.account_wide else self.parse_usage(data)

    @staticmethod
    def _number(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def parse_usage(data: dict) -> ProviderUsage:
        info = data.get("data") or data
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
        info = data.get("data") or data
        purchased = OpenRouterAdapter._number(info.get("total_credits"))
        used = OpenRouterAdapter._number(info.get("total_usage"))
        if purchased is None or used is None:
            raise ValueError("OpenRouter credits response is missing total_credits or total_usage")
        balance = purchased - used
        metrics = [
            Metric("account_credit_balance", balance, "credits"),
            Metric("account_credits_used", used, "credits"),
            Metric("account_credits_purchased", purchased, "credits"),
        ]
        return ProviderUsage(
            status="healthy",
            summary=f"{balance} account credits available",
            metrics=metrics,
            raw={"credits": {"total_credits": purchased, "total_usage": used}},
        )
