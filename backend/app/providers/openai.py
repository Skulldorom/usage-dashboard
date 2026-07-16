from datetime import UTC, datetime, timedelta
import httpx
from app.providers.base import Metric, ProviderAdapter, ProviderUsage

class OpenAIAdapter(ProviderAdapter):
    id = "openai"
    name = "OpenAI / Codex"
    description = "OpenAI organization costs over the last 30 days. Requires an admin key."
    default_base_url = "https://api.openai.com/v1"
    metric_names = ["cost_30d", "currency", "buckets"]
    async def fetch_usage(self) -> ProviderUsage:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        params = {"start_time": int(start.timestamp()), "end_time": int(end.timestamp()), "bucket_width": "1d"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/organization/costs", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        return self.parse_usage(data)
    @staticmethod
    def parse_usage(data: dict) -> ProviderUsage:
        total = 0.0
        currency = "usd"
        buckets = data.get("data") or []
        for bucket in buckets:
            for result in bucket.get("results") or []:
                amount = result.get("amount") or {}
                total += float(amount.get("value") or 0)
                currency = amount.get("currency") or currency
        metrics = [Metric("cost_30d", round(total, 6), currency.upper()), Metric("buckets", len(buckets))]
        return ProviderUsage(status="healthy", summary=f"{total:.2f} {currency.upper()} spent in last 30 days", metrics=metrics, raw=data)
