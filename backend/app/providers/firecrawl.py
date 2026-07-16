from datetime import datetime
import httpx
from app.providers.base import Metric, ProviderAdapter, ProviderUsage


class FirecrawlAdapter(ProviderAdapter):
    id = "firecrawl"
    name = "Firecrawl"
    description = "Firecrawl team token and credit usage."
    default_base_url = "https://api.firecrawl.dev/v2"
    metric_names = ["credits_remaining", "credits_used", "plan_credits", "refresh_date", "remaining_tokens", "used_tokens"]

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token_resp = await client.get(f"{self.base_url}/team/token-usage", headers=headers)
            token_resp.raise_for_status()
            token_data = token_resp.json()
            credit_resp = await client.get(f"{self.base_url}/team/credit-usage/historical", headers=headers)
            credit_resp.raise_for_status()
            credit_data = credit_resp.json()
        return self.parse_usage(token_data, credit_data)

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
    def parse_usage(token_data: dict, credit_data: dict | None = None) -> ProviderUsage:
        token_payload = FirecrawlAdapter._payload(token_data)
        credit_payload = FirecrawlAdapter._payload(credit_data)
        periods = credit_payload.get("periods") or credit_payload.get("data") or []
        latest_period = periods[-1] if isinstance(periods, list) and periods else {}
        if not isinstance(latest_period, dict):
            latest_period = {}

        remaining_tokens = FirecrawlAdapter._first_number(token_payload.get("remainingTokens"), token_payload.get("remaining_tokens"))
        plan_tokens = FirecrawlAdapter._first_number(token_payload.get("planTokens"), token_payload.get("plan_tokens"))
        used_tokens = (plan_tokens - remaining_tokens) if isinstance(plan_tokens, (int, float)) and isinstance(remaining_tokens, (int, float)) else None

        credits_remaining = FirecrawlAdapter._first_number(
            credit_payload.get("creditsRemaining"),
            credit_payload.get("credits_remaining"),
            credit_payload.get("remainingCredits"),
            credit_payload.get("remaining_credits"),
            token_payload.get("creditsRemaining"),
            token_payload.get("credits_remaining"),
        )
        plan_credits = FirecrawlAdapter._first_number(
            credit_payload.get("planCredits"),
            credit_payload.get("plan_credits"),
            credit_payload.get("creditLimit"),
            credit_payload.get("credit_limit"),
            credit_payload.get("totalCredits"),
            credit_payload.get("total_credits"),
            token_payload.get("planCredits"),
            token_payload.get("plan_credits"),
        )
        credits_used = FirecrawlAdapter._first_number(
            credit_payload.get("creditsUsed"),
            credit_payload.get("credits_used"),
            credit_payload.get("usedCredits"),
            credit_payload.get("used_credits"),
            latest_period.get("usedCredits"),
            latest_period.get("used_credits"),
            latest_period.get("totalCredits"),
            latest_period.get("total_credits"),
        )
        if credits_used is None and isinstance(plan_credits, (int, float)) and isinstance(credits_remaining, (int, float)):
            credits_used = max(plan_credits - credits_remaining, 0)

        refresh_date = FirecrawlAdapter._first_text(
            credit_payload.get("refreshDate"),
            credit_payload.get("refresh_date"),
            credit_payload.get("refreshesAt"),
            credit_payload.get("refreshes_at"),
            credit_payload.get("nextRefreshAt"),
            credit_payload.get("next_refresh_at"),
            token_payload.get("refreshDate"),
            token_payload.get("refresh_date"),
            token_payload.get("nextRefreshAt"),
            token_payload.get("next_refresh_at"),
        )
        plan_name = FirecrawlAdapter._first_text(
            credit_payload.get("plan"),
            credit_payload.get("planName"),
            credit_payload.get("plan_name"),
            token_payload.get("plan"),
            token_payload.get("planName"),
            token_payload.get("plan_name"),
        )

        metrics = [
            Metric("credits_remaining", credits_remaining, "credits", plan_credits if isinstance(plan_credits, (int, float)) else None),
            Metric("credits_used", credits_used, "credits", plan_credits if isinstance(plan_credits, (int, float)) else None),
            Metric("plan_credits", plan_credits, "credits"),
            Metric("refresh_date", refresh_date),
            Metric("remaining_tokens", remaining_tokens, "tokens", plan_tokens if isinstance(plan_tokens, (int, float)) else None),
            Metric("used_tokens", used_tokens, "tokens", plan_tokens if isinstance(plan_tokens, (int, float)) else None),
        ]
        metrics = [metric for metric in metrics if metric.value is not None]

        status = "healthy" if token_data.get("success", True) and (credit_data or {}).get("success", True) else "degraded"
        if isinstance(credits_remaining, (int, float)):
            summary = f"{credits_remaining:,.0f} credits remaining"
        elif isinstance(remaining_tokens, (int, float)):
            summary = f"{remaining_tokens:,.0f} tokens remaining"
        else:
            summary = "Firecrawl usage fetched"

        if isinstance(plan_credits, (int, float)) and refresh_date:
            plan_label = f"{plan_name} plan" if plan_name else "Plan"
            summary = f"{summary}. {plan_label}: {plan_credits:,.0f} credits being refreshed on {FirecrawlAdapter._format_date(refresh_date)}"

        return ProviderUsage(status=status, summary=summary, metrics=metrics, raw={"token_usage": token_data, "credit_usage": credit_data or {}})
