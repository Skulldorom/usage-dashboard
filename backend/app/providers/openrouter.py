import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

from app.analytics.normalizer import parse_time

from app.analytics.capabilities import analytics_spec, metric_spec
from app.providers.base import Metric, ProviderAdapter, ProviderUsage


class OpenRouterAdapter(ProviderAdapter):
    _analytics_origin = "https://openrouter.ai/api/v1"
    _analytics_days = 30
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
        "openrouter_account_spend",
        "openrouter_account_requests",
        "openrouter_account_prompt_tokens",
        "openrouter_account_completion_tokens",
        "openrouter_account_reasoning_tokens",
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
        native_history=True,
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
            # Account-wide activity is intentionally scoped, never global: the
            # same spend may already be represented by individual keys or Hermes.
            "openrouter_account_spend": metric_spec(
                type_="counter", unit="USD", direction="increasing", aggregations=["daily"]
            ),
            "openrouter_account_requests": metric_spec(
                type_="counter", unit="requests", direction="increasing", aggregations=["daily"]
            ),
            "openrouter_account_prompt_tokens": metric_spec(
                type_="counter", unit="tokens", direction="increasing", aggregations=["daily"]
            ),
            "openrouter_account_completion_tokens": metric_spec(
                type_="counter", unit="tokens", direction="increasing", aggregations=["daily"]
            ),
            "openrouter_account_reasoning_tokens": metric_spec(
                type_="counter", unit="tokens", direction="increasing", aggregations=["daily"]
            ),
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._validate_endpoint()

    @property
    def account_wide(self) -> bool:
        mode = self.extra.get("monitoring_mode", "individual_key")
        if mode not in {"individual_key", "account_wide"}:
            raise ValueError("OpenRouter monitoring_mode must be individual_key or account_wide")
        return mode == "account_wide"

    @staticmethod
    def validate_config(base_url: str | None, extra: dict | None) -> None:
        if not isinstance(extra, dict):
            raise ValueError("OpenRouter monitoring configuration must be an object")
        mode = extra.get("monitoring_mode", "individual_key")
        if not isinstance(mode, str) or mode not in {"individual_key", "account_wide"}:
            raise ValueError("OpenRouter monitoring_mode must be individual_key or account_wide")
        if mode != "account_wide":
            return
        try:
            parsed = urlparse((base_url or "https://openrouter.ai/api/v1").rstrip("/"))
            port = parsed.port
        except ValueError as exc:
            raise ValueError(
                "OpenRouter Management credentials may only be sent to https://openrouter.ai/api/v1"
            ) from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != "openrouter.ai"
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
            or parsed.path != "/api/v1"
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OpenRouter Management credentials may only be sent to https://openrouter.ai/api/v1")

    def _validate_endpoint(self) -> None:
        self.validate_config(self.base_url, self.extra)

    async def fetch_usage(self) -> ProviderUsage:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if not self.account_wide:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                resp = await client.get(f"{self.base_url}/key", headers=headers)
                resp.raise_for_status()
                return self.parse_usage(resp.json())

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            credits_resp = await client.get(f"{self._analytics_origin}/credits", headers=headers)
            credits_resp.raise_for_status()
            credits = credits_resp.json()
            analytics = None
            activity = None
            analytics_status = "failed"
            analytics_error = None
            try:
                analytics = await self._fetch_analytics(client, headers)
                analytics_status = "success" if analytics["account"]["data"] else "empty"
            except httpx.HTTPStatusError as exc:
                analytics_error = (
                    "permission_or_upstream_error" if exc.response.status_code in {401, 403, 404} else "upstream_error"
                )
            except (httpx.HTTPError, ValueError):
                analytics_error = "malformed_or_network_error"
            if analytics is None:
                try:
                    activity_resp = await client.get(f"{self._analytics_origin}/activity", headers=headers)
                    activity_resp.raise_for_status()
                    activity = self._sanitize_activity(activity_resp.json())
                    analytics_status = "success" if activity["data"] else "empty"
                    analytics_error = None
                except httpx.HTTPStatusError as exc:
                    analytics_error = (
                        "permission_or_upstream_error"
                        if exc.response.status_code in {401, 403, 404}
                        else "upstream_error"
                    )
                except (httpx.HTTPError, ValueError):
                    analytics_error = "malformed_or_network_error"
        usage = self.parse_account_usage(credits)
        usage.analytics_status = analytics_status
        usage.analytics_error = analytics_error
        usage.raw["analytics"] = {"status": analytics_status, "error": analytics_error}
        if analytics is not None:
            usage.raw["analytics_query"] = analytics
        elif activity is not None:
            usage.raw["activity"] = activity
        return usage

    _analytics_metric_aliases = {
        "openrouter_account_spend": ("usage", "spend", "cost"),
        "openrouter_account_requests": ("request_count",),
        "openrouter_account_prompt_tokens": ("prompt_tokens", "input_tokens"),
        "openrouter_account_completion_tokens": ("completion_tokens", "output_tokens"),
        "openrouter_account_reasoning_tokens": ("reasoning_tokens",),
    }
    _analytics_group_dimensions = ("workspace", "model", "provider")

    async def _fetch_analytics(self, client: httpx.AsyncClient, headers: dict[str, str]) -> dict:
        meta_response = await client.get(f"{self._analytics_origin}/analytics/meta", headers=headers)
        meta_response.raise_for_status()
        meta = self._sanitize_analytics_meta(meta_response.json())
        metric_by_name = {metric["name"]: metric for metric in meta["metrics"]}
        granularities = {item["name"] for item in meta["granularities"]}
        if "day" not in granularities:
            raise ValueError("OpenRouter analytics metadata lacks daily granularity")
        metrics = self._supported_metrics(metric_by_name)
        if not metrics:
            raise ValueError("OpenRouter analytics metadata lacks supported account metrics")
        time_range = self._analytics_time_range()
        account = await self._query_analytics(client, headers, metrics, time_range)
        groups = {}
        supported_dimensions = {item["name"] for item in meta["dimensions"]}
        for dimension in self._analytics_group_dimensions:
            if dimension not in supported_dimensions:
                continue
            try:
                groups[dimension] = await self._query_analytics(
                    client, headers, metrics, time_range, dimensions=[dimension]
                )
            except (httpx.HTTPError, ValueError):
                # The ungrouped query remains authoritative. A failed or incomplete
                # breakdown is unavailable, never substituted into its total.
                continue
        return {"account": account, "groups": groups, "meta": meta, "metric_map": metrics}

    @classmethod
    def _supported_metrics(cls, metric_by_name: dict[str, dict]) -> dict[str, str]:
        selected = {}
        for native_metric, aliases in cls._analytics_metric_aliases.items():
            name = next((alias for alias in aliases if alias in metric_by_name), None)
            if name:
                selected[native_metric] = name
        return selected

    async def _query_analytics(
        self,
        client,
        headers: dict[str, str],
        metric_map: dict[str, str],
        time_range: dict[str, str],
        dimensions: list[str] | None = None,
    ) -> dict:
        payload = {
            "metrics": list(metric_map.values()),
            "granularity": "day",
            "time_range": time_range,
            "limit": 1000,
            "order_by": {"field": "date", "direction": "asc"},
        }
        if dimensions:
            if len(dimensions) > 2:
                raise ValueError("OpenRouter supports at most two analytics dimensions")
            payload["dimensions"] = dimensions
        response = await client.post(f"{self._analytics_origin}/analytics/query", headers=headers, json=payload)
        response.raise_for_status()
        return self._sanitize_analytics_query(response.json(), metric_map, dimensions or [])

    @classmethod
    def _analytics_time_range(cls) -> dict[str, str]:
        end = datetime.now(UTC).replace(microsecond=0)
        start = (end - timedelta(days=cls._analytics_days)).replace(hour=0, minute=0, second=0)
        return {"start": start.isoformat().replace("+00:00", "Z"), "end": end.isoformat().replace("+00:00", "Z")}

    @staticmethod
    def _sanitize_analytics_meta(data: object) -> dict:
        info = data.get("data") if isinstance(data, dict) else None
        if not isinstance(info, dict):
            raise ValueError("OpenRouter analytics metadata response must contain data")
        required = {
            "metrics": ("name", "display_label", "display_format", "is_rate"),
            "dimensions": ("name", "display_label"),
            "granularities": ("name", "display_label"),
            "operators": ("name", "value_type"),
        }
        result = {}
        for field, keys in required.items():
            values = info.get(field)
            if not isinstance(values, list):
                raise ValueError(f"OpenRouter analytics metadata {field} must be a list")
            normalized = []
            for value in values:
                if not isinstance(value, dict) or any(
                    not isinstance(value.get(key), str) and key != "is_rate" for key in keys
                ):
                    raise ValueError(f"OpenRouter analytics metadata {field} contains an invalid entry")
                if not isinstance(value.get("name"), str) or not value["name"].strip():
                    raise ValueError(f"OpenRouter analytics metadata {field} contains an invalid name")
                item = {key: value[key] for key in keys}
                if field == "metrics" and not isinstance(item["is_rate"], bool):
                    raise ValueError("OpenRouter analytics metric is_rate must be boolean")
                normalized.append(item)
            result[field] = normalized
        return result

    @staticmethod
    def _sanitize_analytics_query(
        data: object, metric_map: dict[str, str] | list[str], dimensions: list[str] | None = None
    ) -> dict:
        if isinstance(metric_map, list):
            metric_map = {metric: metric for metric in metric_map}
        dimensions = dimensions or []
        outer = data.get("data") if isinstance(data, dict) else None
        if (
            not isinstance(outer, dict)
            or not isinstance(outer.get("data"), list)
            or not isinstance(outer.get("metadata"), dict)
        ):
            raise ValueError("OpenRouter analytics query response must contain data and metadata")
        metadata = outer["metadata"]
        if (
            isinstance(metadata.get("query_time_ms"), bool)
            or not isinstance(metadata.get("query_time_ms"), (int, float))
            or isinstance(metadata.get("row_count"), bool)
            or not isinstance(metadata.get("row_count"), int)
            or not isinstance(metadata.get("truncated"), bool)
            or metadata["row_count"] < 0
        ):
            raise ValueError("OpenRouter analytics query metadata is invalid")
        if metadata["truncated"] or metadata["row_count"] != len(outer["data"]):
            raise ValueError("OpenRouter analytics query results are incomplete")
        rows = []
        for row in outer["data"]:
            date = row.get("date__day") if isinstance(row, dict) else None
            if parse_time(date) is None:
                raise ValueError("OpenRouter analytics query contains an invalid UTC daily row")
            item = {"date": date}
            for dimension in dimensions:
                value = row.get(dimension)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("OpenRouter analytics query contains an invalid dimension")
                item[dimension] = value.strip()
            for native_metric, upstream_metric in metric_map.items():
                if upstream_metric not in row:
                    continue
                value = OpenRouterAdapter._number(row[upstream_metric])
                if value is None or value < 0:
                    raise ValueError("OpenRouter analytics query contains an invalid metric")
                item[native_metric] = value
            if any(metric in item for metric in metric_map):
                rows.append(item)
        warnings = outer.get("warnings", [])
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            raise ValueError("OpenRouter analytics query warnings are invalid")
        cached_at = outer.get("cachedAt")
        if cached_at is not None and OpenRouterAdapter._number(cached_at) is None:
            raise ValueError("OpenRouter analytics query cachedAt is invalid")
        return {
            "data": rows,
            "metadata": metadata,
            "warnings": warnings,
            "cached_at": cached_at,
            "dimensions": dimensions,
        }

    @staticmethod
    def _sanitize_activity(data: object) -> dict:
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ValueError("OpenRouter activity response must contain a data list")
        rows, rejected = [], 0
        numeric = {
            "usage": "spend",
            "requests": "count",
            "prompt_tokens": "count",
            "completion_tokens": "count",
            "reasoning_tokens": "count",
        }
        for row in data["data"]:
            if not isinstance(row, dict) or parse_time(row.get("date")) is None:
                rejected += 1
                continue
            item = {"date": row["date"]}
            valid = True
            for key, kind in numeric.items():
                if key not in row:
                    continue
                value = OpenRouterAdapter._decimal(row[key])
                if (
                    value is None
                    or (kind == "count" and (value < 0 or value != value.to_integral_value()))
                    or (kind == "spend" and value < 0)
                ):
                    valid = False
                    break
                converted = int(value) if kind == "count" else OpenRouterAdapter._number(value)
                if converted is None:
                    valid = False
                    break
                item[key] = converted
            for key in ("workspace_id", "model", "provider_name"):
                if key in row and isinstance(row[key], str) and row[key].strip():
                    item[key] = row[key].strip()
            if valid and any(key in item for key in numeric):
                rows.append(item)
            else:
                rejected += 1
        if rejected and rows:
            raise ValueError("OpenRouter activity response contained malformed rows")
        if rejected and not rows and data["data"]:
            raise ValueError("OpenRouter activity response contained no valid rows")
        return {"data": rows}

    @staticmethod
    def native_observations(raw: dict) -> list[dict]:
        """Persist completed account rows and non-authoritative grouped rows separately."""
        if not isinstance(raw, dict):
            return []
        query = raw.get("analytics_query")
        activity = raw.get("activity")
        sources = []
        if isinstance(query, dict):
            account = query.get("account")
            if isinstance(account, dict):
                sources.append((account.get("data"), "native", None))
            for dimension, grouped in (query.get("groups") or {}).items():
                if isinstance(grouped, dict):
                    sources.append((grouped.get("data"), "native_grouped", dimension))
        elif isinstance(activity, dict):
            sources.append((activity.get("data"), "native", None))
        observations = []
        for rows, source, group_dimension in sources:
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                day = parse_time(row.get("date"))
                if day is None:
                    continue
                start = day.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
                if end > datetime.now(UTC):
                    continue
                scope = row.get("workspace") or row.get("workspace_id")
                model = row.get("model")
                upstream = row.get("provider") or row.get("provider_name")
                for metric, unit, legacy in (
                    ("openrouter_account_spend", "USD", "usage"),
                    ("openrouter_account_requests", "requests", "requests"),
                    ("openrouter_account_prompt_tokens", "tokens", "prompt_tokens"),
                    ("openrouter_account_completion_tokens", "tokens", "completion_tokens"),
                    ("openrouter_account_reasoning_tokens", "tokens", "reasoning_tokens"),
                ):
                    number = OpenRouterAdapter._number(row.get(metric, row.get(legacy)))
                    if number is None:
                        continue
                    observations.append(
                        {
                            "metric": metric,
                            "value": number,
                            "unit": unit,
                            "observed_at": start,
                            "window_start": start,
                            "window_end": end,
                            "kind": "delta",
                            "source": source,
                            "scope": scope,
                            "model": model,
                            "provider_mapping": upstream,
                            "group_dimension": group_dimension,
                        }
                    )
        return observations

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return result if result.is_finite() else None

    @staticmethod
    def _number(value):
        number = OpenRouterAdapter._decimal(value)
        if number is None:
            return None
        try:
            converted = float(number)
        except (OverflowError, ValueError):
            return None
        return converted if math.isfinite(converted) else None

    @staticmethod
    def _object(data, context):
        if not isinstance(data, dict):
            raise ValueError(f"OpenRouter {context} response must be an object")
        info = data.get("data", data)
        if not isinstance(info, dict):
            raise ValueError(f"OpenRouter {context} response data must be an object")
        return info

    @staticmethod
    def parse_usage(data: dict) -> ProviderUsage:
        info = OpenRouterAdapter._object(data, "key")
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
        info = OpenRouterAdapter._object(data, "credits")
        purchased = OpenRouterAdapter._decimal(info.get("total_credits"))
        used = OpenRouterAdapter._decimal(info.get("total_usage"))
        if purchased is None or used is None:
            raise ValueError("OpenRouter credits response is missing finite total_credits or total_usage")
        try:
            balance = purchased - used
            values = [float(item) for item in (balance, used, purchased)]
        except (ArithmeticError, OverflowError, ValueError):
            raise ValueError("OpenRouter credits response contains an unsupported numeric value") from None
        if not all(math.isfinite(item) for item in values):
            raise ValueError("OpenRouter credits response contains an unsupported numeric value")
        balance_value, used_value, purchased_value = values
        metrics = [
            Metric("account_credit_balance", balance_value, "credits"),
            Metric("account_credits_used", used_value, "credits"),
            Metric("account_credits_purchased", purchased_value, "credits"),
        ]
        return ProviderUsage(
            status="healthy",
            summary=f"{balance} account credits available",
            metrics=metrics,
            raw={"credits": {"total_credits": purchased_value, "total_usage": used_value}},
        )
