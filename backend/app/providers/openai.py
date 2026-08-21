from datetime import UTC, datetime, timedelta
import httpx

from app.analytics.capabilities import analytics_spec, metric_spec
from app.analytics.normalizer import parse_time
from app.providers.base import Metric, ProviderAdapter, ProviderUsage

class OpenAIAdapter(ProviderAdapter):
    id = "openai"
    name = "OpenAI"
    description = "OpenAI organization costs over the last 30 days. Requires an organization admin key."
    default_base_url = "https://api.openai.com/v1"
    metric_names = ["cost_30d", "currency", "buckets"]
    alert_metrics = [
        {"metric": "cost_30d", "label": "30-day cost", "unit": "USD", "direction": "increasing"},
    ]
    analytics = analytics_spec(
        supported=True,
        native_history=True,
        metrics={
            "cost_30d": metric_spec(
                type_="rolling_total", unit="USD", direction="increasing",
                aggregations=["daily"], deltas=False, window="30d",
            ),
            "daily_cost": metric_spec(
                type_="counter", unit="USD", direction="increasing", aggregations=["daily"], overview=True,
            ),
        },
    )
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

    @staticmethod
    def native_observations(raw: dict) -> list[dict]:
        """Expand daily cost buckets from the organization costs response."""
        observations: list[dict] = []
        for bucket in raw.get("data") or []:
            if not isinstance(bucket, dict):
                continue
            start = parse_time(bucket.get("start_time"))
            end = parse_time(bucket.get("end_time"))
            if start is None:
                continue
            total = 0.0
            currency = None
            for result in bucket.get("results") or []:
                amount = (result or {}).get("amount") or {}
                value = amount.get("value")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    total += float(value)
                currency = amount.get("currency") or currency
            if total > 0:
                observations.append(
                    {
                        "metric": "daily_cost",
                        "value": round(total, 6),
                        "unit": (currency or "usd").upper(),
                        "observed_at": start,
                        "window_start": start,
                        "window_end": end,
                        "kind": "delta",
                    }
                )
        return observations
