from datetime import datetime
import httpx

from app.analytics.capabilities import analytics_spec, metric_spec
from app.analytics.normalizer import parse_time
from app.providers.base import Metric, ProviderAdapter, ProviderUsage


class FirecrawlAdapter(ProviderAdapter):
    id = "firecrawl"
    name = "Firecrawl"
    description = "Firecrawl team credit usage."
    default_base_url = "https://api.firecrawl.dev/v2"
    metric_names = ["credits_remaining", "credits_used", "usage_percent", "plan_credits", "billing_period_end"]
    alert_metrics = [
        {"metric": "usage_percent", "label": "Usage", "unit": "%", "direction": "increasing"},
        {"metric": "credits_remaining", "label": "Credits remaining", "unit": "credits", "direction": "decreasing"},
        {"metric": "credits_used", "label": "Credits used", "unit": "credits", "direction": "increasing"},
    ]
    analytics = analytics_spec(
        supported=True,
        native_history=True,
        metrics={
            "credits_remaining": metric_spec(type_="remaining", unit="credits", direction="decreasing"),
            "credits_used": metric_spec(type_="counter", unit="credits", direction="increasing", reset_metric="billing_period_end", window="billing", overview=True),
            "usage_percent": metric_spec(type_="counter", unit="%", direction="increasing", maximum=100, reset_metric="billing_period_end", window="billing", utilization=True),
            "plan_credits": metric_spec(type_="gauge", unit="credits", direction="increasing", deltas=False),
        },
    )

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

    @staticmethod
    def native_observations(raw: dict) -> list[dict]:
        """Expand per-period credit usage from the historical credit response.

        Tolerantly reads a handful of common period field names and skips
        periods that cannot be placed in time, so schema drift degrades to
        snapshot-derived analytics rather than fabricating buckets.
        """
        historical = raw.get("historical_credit_usage") or {}
        periods = historical.get("periods") or []
        if not isinstance(periods, list):
            return []
        observations: list[dict] = []
        for period in periods:
            if not isinstance(period, dict):
                continue
            start = _first_time(period, ("startDate", "start_date", "from", "date", "periodStart", "period_start"))
            end = _first_time(period, ("endDate", "end_date", "to", "periodEnd", "period_end"))
            if start is None and end is None:
                continue
            used = FirecrawlAdapter._first_number(
                period.get("totalCredits"),
                period.get("total_credits"),
                period.get("creditsUsed"),
                period.get("credits_used"),
                period.get("usedCredits"),
            )
            if used is None:
                continue
            observations.append(
                {
                    "metric": "credits_used",
                    "value": used,
                    "unit": "credits",
                    "observed_at": start or end,
                    "window_start": start,
                    "window_end": end,
                    "kind": "delta",
                }
            )
        return observations


def _first_time(record: dict, keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        parsed = parse_time(record.get(key))
        if parsed is not None:
            return parsed
    return None
