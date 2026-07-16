import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.base import Metric, ProviderAdapter, ProviderUsage

_PATH_TOKEN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)(?:\[(\d+)\])?")

class CustomHTTPAdapter(ProviderAdapter):
    id = "custom_http"
    name = "Custom HTTP"
    description = "User-defined HTTP endpoint with JSON path metric extraction."
    default_base_url = "https://example.invalid"
    metric_names = ["custom_metrics"]

    async def fetch_usage(self) -> ProviderUsage:
        config = self._validated_config(self.extra, self.base_url)
        headers = {"Accept": "application/json"}
        auth_header_name = config.get("auth_header_name") or "Authorization"
        auth_template = config.get("auth_header_template") or "Bearer {api_key}"
        if self.api_key:
            headers[auth_header_name] = auth_template.format(api_key=self.api_key)
        for key, value in (config.get("headers") or {}).items():
            if isinstance(key, str) and isinstance(value, str):
                headers[key] = value
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.request(config["method"], config["url"], headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return self.parse_usage(data, config)

    @staticmethod
    def _validated_config(extra: dict[str, Any], base_url: str) -> dict[str, Any]:
        method = str(extra.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            raise ValueError("Custom HTTP method must be GET or POST")
        path = str(extra.get("path") or "")
        parsed_base = urlsplit(base_url)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ValueError("Custom HTTP base URL must be an absolute http(s) URL")
        if parsed_base.username or parsed_base.password or "@" in parsed_base.netloc:
            raise ValueError("Do not store credentials in the custom provider URL")
        if urlsplit(path).scheme or urlsplit(path).netloc:
            raise ValueError("Custom HTTP path must be relative; put the host in Base URL")
        if "api_key=" in path.lower() or "token=" in path.lower():
            raise ValueError("Do not store credentials in the custom provider path")
        metric_paths = extra.get("metrics") or []
        if not isinstance(metric_paths, list) or not metric_paths:
            raise ValueError("Custom HTTP provider requires at least one metric path")
        base = base_url.rstrip("/")
        clean_path = path if path.startswith("/") else f"/{path}"
        return {**extra, "method": method, "url": f"{base}{clean_path}", "metrics": metric_paths}

    @staticmethod
    def extract_json_path(data: Any, path: str) -> Any:
        if not path.startswith("$"):
            raise ValueError(f"JSON path must start with $: {path}")
        current = data
        remainder = path[1:]
        while remainder:
            if not remainder.startswith("."):
                raise ValueError(f"Unsupported JSON path syntax: {path}")
            remainder = remainder[1:]
            match = _PATH_TOKEN_RE.match(remainder)
            if not match:
                raise ValueError(f"Unsupported JSON path syntax: {path}")
            key, index = match.groups()
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
            if index is not None:
                if not isinstance(current, list):
                    return None
                idx = int(index)
                current = current[idx] if idx < len(current) else None
            remainder = remainder[match.end():]
        return current

    @staticmethod
    def parse_usage(data: dict, config: dict[str, Any]) -> ProviderUsage:
        metrics = []
        for item in config.get("metrics") or []:
            if not isinstance(item, dict):
                raise ValueError("Custom metric config entries must be objects")
            label = item.get("label") or item.get("path")
            path = item.get("path")
            if not label or not path:
                raise ValueError("Custom metric config requires label and path")
            value = CustomHTTPAdapter.extract_json_path(data, path)
            maximum = CustomHTTPAdapter.extract_json_path(data, item["maximum_path"]) if item.get("maximum_path") else None
            metrics.append(Metric(str(label), value, item.get("unit") or None, maximum if isinstance(maximum, (int, float)) else None))
        healthy = any(metric.value is not None for metric in metrics)
        summary = f"{len(metrics)} custom metrics fetched" if healthy else "Custom HTTP response did not match configured paths"
        return ProviderUsage(status="healthy" if healthy else "degraded", summary=summary, metrics=metrics, raw=data)
