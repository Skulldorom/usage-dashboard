import httpx

from app.providers.base import Metric, ProviderAdapter, ProviderUsage

class OpenRouterAdapter(ProviderAdapter):
    id = "openrouter"
    name = "OpenRouter"
    description = "OpenRouter API key credit usage and limits."
    default_base_url = "https://openrouter.ai/api/v1"
    metric_names = ["limit_remaining", "usage_daily", "usage_weekly", "usage_monthly", "limit"]

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/key", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return self.parse_usage(data)

    @staticmethod
    def _number(value):
        if value is None:
            return None
        return float(value) if isinstance(value, str) else value

    @staticmethod
    def parse_usage(data: dict) -> ProviderUsage:
        info = data.get("data") or data
        remaining = OpenRouterAdapter._number(info.get("limit_remaining"))
        limit = OpenRouterAdapter._number(info.get("limit"))
        metrics = [
            Metric("limit_remaining", remaining, "credits", limit if isinstance(limit, (int, float)) else None),
            Metric("usage_daily", OpenRouterAdapter._number(info.get("usage_daily")), "credits"),
            Metric("usage_weekly", OpenRouterAdapter._number(info.get("usage_weekly")), "credits"),
            Metric("usage_monthly", OpenRouterAdapter._number(info.get("usage_monthly")), "credits"),
            Metric("limit", limit, "credits"),
        ]
        label = info.get("label") or "OpenRouter key"
        summary = f"{remaining} credits remaining" if remaining is not None else f"{label} usage fetched"
        return ProviderUsage(status="healthy", summary=summary, metrics=metrics, raw=data)
