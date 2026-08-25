"""Hermes Agent data source - read-only usage telemetry over HTTP.

Hermes does not expose a documented REST usage endpoint today, so this adapter
implements a clean HTTP seam: it GETs ``{base_url}/usage`` and expects a JSON
payload that conforms to the observation contract documented in
``app.datasources.base`` (either ``{"observations": [record, ...]}`` or a bare
list of records). The concrete byte-source on the Hermes side (a small read-only
plugin/endpoint serving that contract, or a direct ``state.db`` reader) is wired
separately; this adapter is agnostic to it.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.datasources.base import DataSource


class HermesDataSource(DataSource):
    id = "hermes"
    name = "Hermes Agent"
    description = "Observed usage telemetry from a Hermes Agent installation."

    async def fetch_observations(
        self,
        base_url: str | None,
        token: str | None,
        extra: dict[str, Any],
        timeout: float,
    ) -> list[dict]:
        if not base_url:
            raise ValueError("Hermes base URL is required")
        url = base_url.rstrip("/") + "/usage"
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise ValueError(f"Hermes returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Hermes returned a non-JSON response") from exc
        records = payload.get("observations") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("Hermes payload must be a list or {\"observations\": [...]}")
        return records
