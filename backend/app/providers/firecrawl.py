import httpx
from app.providers.base import Metric, ProviderAdapter, ProviderUsage

class FirecrawlAdapter(ProviderAdapter):
    id = "firecrawl"
    name = "Firecrawl"
    description = "Firecrawl team token and credit usage."
    default_base_url = "https://api.firecrawl.dev/v2"
    metric_names = ["remaining_tokens", "plan_tokens", "credits_this_period"]
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
    def parse_usage(token_data: dict, credit_data: dict | None = None) -> ProviderUsage:
        data = token_data.get("data", token_data)
        remaining = data.get("remainingTokens")
        plan = data.get("planTokens")
        used = (plan - remaining) if isinstance(plan, (int, float)) and isinstance(remaining, (int, float)) else None
        periods = (credit_data or {}).get("periods") or []
        credits = (periods[-1] if periods else {}).get("totalCredits")
        metrics = [Metric("remaining_tokens", remaining, "tokens", plan if isinstance(plan, (int, float)) else None), Metric("used_tokens", used, "tokens", plan if isinstance(plan, (int, float)) else None), Metric("plan_tokens", plan, "tokens"), Metric("credits_this_period", credits, "credits")]
        status = "healthy" if token_data.get("success", True) else "degraded"
        summary = f"{remaining:,} tokens remaining" if isinstance(remaining, int) else "Firecrawl usage fetched"
        return ProviderUsage(status=status, summary=summary, metrics=metrics, raw={"token_usage": token_data, "credit_usage": credit_data or {}})
