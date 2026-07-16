from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.providers.base import Metric, ProviderAdapter, ProviderUsage

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens", "num_requests")

class AnthropicAdapter(ProviderAdapter):
    id = "anthropic"
    name = "Anthropic / Claude"
    description = "Claude Usage & Cost Admin API message usage. Requires an Anthropic Admin API key."
    default_base_url = "https://api.anthropic.com"
    metric_names = list(TOKEN_FIELDS)

    async def fetch_usage(self) -> ProviderUsage:
        end = datetime.now(UTC)
        start = end - timedelta(hours=24)
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        }
        params = {"starting_at": start.isoformat(), "ending_at": end.isoformat(), "bucket_width": "1h"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/v1/organizations/usage_report/messages", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        return self.parse_usage(data)

    @staticmethod
    def _walk_records(value: Any):
        if isinstance(value, dict):
            if any(field in value for field in TOKEN_FIELDS):
                yield value
            for child in value.values():
                yield from AnthropicAdapter._walk_records(child)
        elif isinstance(value, list):
            for child in value:
                yield from AnthropicAdapter._walk_records(child)

    @staticmethod
    def parse_usage(data: dict) -> ProviderUsage:
        totals = {field: 0 for field in TOKEN_FIELDS}
        records = list(AnthropicAdapter._walk_records(data))
        for record in records:
            for field in TOKEN_FIELDS:
                value = record.get(field)
                if isinstance(value, (int, float)):
                    totals[field] += value
        metrics = [Metric(label, value, "tokens" if label.endswith("tokens") else "requests") for label, value in totals.items()]
        requests = totals["num_requests"]
        total_tokens = sum(totals[field] for field in TOKEN_FIELDS if field.endswith("tokens"))
        summary = f"{total_tokens:,} tokens across {requests:,} requests in last 24h"
        return ProviderUsage(status="healthy", summary=summary, metrics=metrics, raw=data)
