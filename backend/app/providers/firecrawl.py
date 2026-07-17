from datetime import datetime
import httpx
from app.providers.base import Metric, ProviderAdapter, ProviderUsage


class FirecrawlAdapter(ProviderAdapter):
    id = "firecrawl"
    name = "Firecrawl"
    description = "Firecrawl team credit usage."
    default_base_url = "https://api.firecrawl.dev/v2"
    metric_names = ["credits_remaining", "credits_used", "usage_percent", "plan_credits", "billing_period_end"]

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            credit_resp = await client.get(f"{self.base_url}/team/credit-usage", headers=headers)
            credit_resp.raise_for_status()
            credit_data = credit_resp.json()
            historical_resp = await client.get(f"{self.base_url}/team/credit-usage/historical", headers=headers)
            historical_resp.raise_for_status()
            historical_data = historical_resp.json()
        return self.parse_usage(credit_data, historical_data)

    @staticmethod
    def _payload(data: dict | None) -> dict:
        if not isinstance(data, dict):
            return {}
        payload = data.get("data", data)
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _first_number(*values):
        for value in values:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value
            if isinstance(value, str):
                try:
                    return float(value) if "." in value else int(value)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _first_text(*values):
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _format_date(value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.strftime("%b %-d, %Y")

    @staticmethod
    def parse_usage(credit_data: dict, historical_data: dict | None = None) -> ProviderUsage:
        credit_payload = FirecrawlAdapter._payload(credit_data)
        periods = (historical_data or {}).get("periods") or []
        latest_period = periods[-1] if isinstance(periods, list) and periods else {}
        if not isinstance(latest_period, dict):
            latest_period = {}

        credits_remaining = FirecrawlAdapter._first_number(
            credit_payload.get("remainingCredits"),
            credit_payload.get("remaining_credits"),
            credit_payload.get("creditsRemaining"),
            credit_payload.get("credits_remaining"),
        )
        plan_credits = FirecrawlAdapter._first_number(
            credit_payload.get("planCredits"),
            credit_payload.get("plan_credits"),
            credit_payload.get("creditLimit"),
            credit_payload.get("credit_limit"),
        )
        credits_used = FirecrawlAdapter._first_number(
            credit_payload.get("creditsUsed"),
            credit_payload.get("credits_used"),
            credit_payload.get("usedCredits"),
            credit_payload.get("used_credits"),
            latest_period.get("totalCredits"),
            latest_period.get("total_credits"),
        )
        if credits_used is None and isinstance(plan_credits, (int, float)) and isinstance(credits_remaining, (int, float)):
            credits_used = max(plan_credits - credits_remaining, 0)

        usage_percent = None
        if isinstance(credits_used, (int, float)) and isinstance(plan_credits, (int, float)) and plan_credits > 0:
            usage_percent = round((credits_used / plan_credits) * 100, 1)

        billing_period_end = FirecrawlAdapter._first_text(
            credit_payload.get("billingPeriodEnd"),
            credit_payload.get("billing_period_end"),
            credit_payload.get("nextRefreshAt"),
            credit_payload.get("next_refresh_at"),
        )
        plan_name = FirecrawlAdapter._first_text(
            credit_payload.get("plan"),
            credit_payload.get("planName"),
            credit_payload.get("plan_name"),
        )

        metrics = [
            Metric("credits_remaining", credits_remaining, "credits"),
            Metric("credits_used", credits_used, "credits", plan_credits if isinstance(plan_credits, (int, float)) else None),
            Metric("usage_percent", usage_percent, "%"),
            Metric("plan_credits", plan_credits, "credits"),
            Metric("billing_period_end", billing_period_end),
        ]
        metrics = [metric for metric in metrics if metric.value is not None]

        status = "healthy" if credit_data.get("success", True) and (historical_data or {}).get("success", True) else "degraded"
        if isinstance(credits_remaining, (int, float)):
            summary = f"{credits_remaining:,.0f} credits remaining"
        else:
            summary = "Firecrawl credit usage fetched"

        if isinstance(plan_credits, (int, float)) and billing_period_end:
            plan_label = f"{plan_name} plan" if plan_name else "Plan"
            summary = f"{summary}. {plan_label}: {plan_credits:,.0f} credits being refreshed on {FirecrawlAdapter._format_date(billing_period_end)}"

        return ProviderUsage(status=status, summary=summary, metrics=metrics, raw={"credit_usage": credit_data, "historical_credit_usage": historical_data or {}})
