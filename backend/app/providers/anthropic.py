from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.analytics.capabilities import analytics_spec, metric_spec
from app.analytics.normalizer import parse_time
from app.providers.base import Metric, ProviderAdapter, ProviderUsage

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens", "num_requests")
_TIME_START_KEYS = ("start_time", "bucket_start", "starting_at", "start")
_TIME_END_KEYS = ("end_time", "bucket_end", "ending_at", "end")

class AnthropicAdapter(ProviderAdapter):
    id = "anthropic"
    name = "Anthropic / Claude"
    description = "Claude Usage & Cost Admin API message usage. Requires an Anthropic Admin API key."
    default_base_url = "https://api.anthropic.com"
    metric_names = list(TOKEN_FIELDS)
    alert_metrics = [
        {"metric": "input_tokens", "label": "Input tokens", "unit": "tokens", "direction": "increasing"},
        {"metric": "output_tokens", "label": "Output tokens", "unit": "tokens", "direction": "increasing"},
        {"metric": "cache_creation_tokens", "label": "Cache creation tokens", "unit": "tokens", "direction": "increasing"},
        {"metric": "cache_read_tokens", "label": "Cache read tokens", "unit": "tokens", "direction": "increasing"},
        {"metric": "num_requests", "label": "Requests", "unit": "requests", "direction": "increasing"},
    ]
    analytics = analytics_spec(
        supported=True,
        native_history=True,
        metrics={
            "input_tokens": metric_spec(type_="counter", unit="tokens", direction="increasing", overview=True),
            "output_tokens": metric_spec(type_="counter", unit="tokens", direction="increasing"),
            "cache_creation_tokens": metric_spec(type_="counter", unit="tokens", direction="increasing"),
            "cache_read_tokens": metric_spec(type_="counter", unit="tokens", direction="increasing"),
            "num_requests": metric_spec(type_="counter", unit="requests", direction="increasing"),
        },
    )

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

    @staticmethod
    def native_observations(raw: dict[str, Any]) -> list[dict]:
        """Extract per-bucket token/request usage from the raw usage report.

        Walks the response carrying time context down from ancestor objects so
        both flat records (bucket + token fields on one object) and nested
        records (time on a parent) are normalized into hourly observations.
        """
        observations: list[dict] = []

        def walk(node: Any, start: datetime | None, end: datetime | None) -> None:
            if isinstance(node, dict):
                node_start = _first_time(node, _TIME_START_KEYS) or start
                node_end = _first_time(node, _TIME_END_KEYS) or end
                if any(field in node for field in TOKEN_FIELDS) and (node_start or node_end):
                    observed = node_start or node_end
                    for field in TOKEN_FIELDS:
                        value = node.get(field)
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            observations.append(
                                {
                                    "metric": field,
                                    "value": value,
                                    "unit": "tokens" if field.endswith("tokens") else "requests",
                                    "observed_at": observed,
                                    "window_start": node_start,
                                    "window_end": node_end,
                                    "kind": "delta",
                                }
                            )
                for child in node.values():
                    walk(child, node_start, node_end)
            elif isinstance(node, list):
                for child in node:
                    walk(child, start, end)

        walk(raw, None, None)
        return observations


def _first_time(record: dict, keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        parsed = parse_time(record.get(key))
        if parsed is not None:
            return parsed
    return None
