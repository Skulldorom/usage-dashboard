"""Official 9Router dashboard request-telemetry adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

import httpx

from app.datasources.base import DataSource, DataSourceFetchResult, DataSourceRetryError

_OVERLAP = timedelta(minutes=10)
_PAGE_SIZE = 100
_MAX_PAGINATION_ATTEMPTS = 2
_AUTH_FAILURE_RETRY_SECONDS = 15 * 60
_ACCESS_FAILURE_RETRY_SECONDS = 30 * 60
_RETRY_AFTER_FALLBACK_SECONDS = 10 * 60


class _UnstablePaginationError(Exception):
    pass


class NineRouterDataSource(DataSource):
    id = "9router"
    name = "9Router"
    description = "Observed request and token telemetry from an official 9Router dashboard."
    default_poll_interval_minutes = 1

    async def fetch_observations(
        self,
        base_url: str | None,
        token: str | None,
        extra: dict[str, Any],
        timeout: float,
    ) -> DataSourceFetchResult:
        if not base_url:
            raise ValueError("9Router base URL is required")
        if not token:
            raise ValueError("9Router dashboard password is required")

        base = base_url.rstrip("/")
        sync_end = datetime.now(UTC)
        params: dict[str, str | int] = {
            "page": 1,
            "pageSize": _PAGE_SIZE,
            "endDate": sync_end.isoformat(),
        }
        watermark = _parse_cursor(extra.get("cursor"))
        if watermark is not None:
            params["startDate"] = (watermark - _OVERLAP).isoformat()

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                login = await client.post(f"{base}/api/auth/login", json={"password": token})
                _validate_login(login, client)

                for attempt in range(_MAX_PAGINATION_ATTEMPTS):
                    try:
                        records = await _fetch_window(client, base, params)
                        return DataSourceFetchResult(records=records, cursor=sync_end.isoformat())
                    except _UnstablePaginationError:
                        if attempt + 1 == _MAX_PAGINATION_ATTEMPTS:
                            raise ValueError(
                                "9Router request-details changed during pagination; retry the sync after traffic settles"
                            ) from None
        except httpx.HTTPError as exc:
            raise ValueError(f"9Router connection failed: {exc}") from exc

        raise AssertionError("unreachable")


def _validate_login(response: httpx.Response, client: httpx.AsyncClient) -> None:
    if response.status_code == 401:
        raise DataSourceRetryError(
            "9Router dashboard authentication failed. Check the configured dashboard password.",
            _AUTH_FAILURE_RETRY_SECONDS,
        )
    if response.status_code == 403:
        raise DataSourceRetryError(
            "9Router dashboard access was denied. Check dashboard access settings and authentication requirements.",
            _ACCESS_FAILURE_RETRY_SECONDS,
        )
    if response.status_code == 429:
        retry_after = _retry_after_seconds(response)
        raise DataSourceRetryError(
            f"9Router dashboard login is temporarily locked. Retry after {retry_after} seconds.", retry_after
        )
    if response.status_code != 200:
        raise ValueError(f"9Router dashboard login returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("9Router dashboard login returned a non-JSON response") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("9Router dashboard login failed")
    if not _has_dashboard_cookie(client):
        raise ValueError("9Router dashboard login did not establish a session")


def _retry_after_seconds(response: httpx.Response) -> int:
    value = getattr(response, "headers", {}).get("Retry-After")
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return _RETRY_AFTER_FALLBACK_SECONDS
    return seconds if seconds >= 0 else _RETRY_AFTER_FALLBACK_SECONDS


def _has_dashboard_cookie(client: httpx.AsyncClient) -> bool:
    return any(cookie.name == "auth_token" and cookie.value for cookie in client.cookies.jar)


async def _fetch_window(
    client: httpx.AsyncClient,
    base: str,
    window_params: dict[str, str | int],
) -> list[dict]:
    params = dict(window_params)
    expected_total: int | None = None
    records: list[dict] = []

    while True:
        response = await client.get(f"{base}/api/usage/request-details", params=params)
        if response.status_code != 200:
            raise ValueError(f"9Router request-details returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("9Router request-details returned a non-JSON response") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("details"), list):
            raise ValueError("9Router returned an invalid request-details payload")

        pagination = _validate_pagination(payload.get("pagination"), params)
        total_items = pagination["totalItems"]
        if expected_total is None:
            expected_total = total_items
        elif total_items != expected_total:
            raise _UnstablePaginationError

        records.extend(_normalize_detail(detail) for detail in payload["details"])
        if not pagination["hasNext"]:
            return records
        params["page"] = int(params["page"]) + 1


def _validate_pagination(pagination: Any, params: dict[str, str | int]) -> dict[str, int | bool]:
    if not isinstance(pagination, dict):
        raise ValueError("9Router returned invalid request-details pagination")
    page = pagination.get("page")
    page_size = pagination.get("pageSize")
    total_items = pagination.get("totalItems")
    total_pages = pagination.get("totalPages")
    has_next = pagination.get("hasNext")
    if (
        not isinstance(page, int)
        or page != params["page"]
        or not isinstance(page_size, int)
        or page_size != _PAGE_SIZE
        or not isinstance(total_items, int)
        or total_items < 0
        or not isinstance(total_pages, int)
        or total_pages < 0
        or not isinstance(has_next, bool)
    ):
        raise ValueError("9Router returned invalid request-details pagination")
    if total_pages != (total_items + _PAGE_SIZE - 1) // _PAGE_SIZE or has_next != (page < total_pages):
        raise ValueError("9Router returned invalid request-details pagination")
    return {"totalItems": total_items, "hasNext": has_next}


def _parse_cursor(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("9Router sync cursor is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("9Router sync cursor is invalid")
    return parsed.astimezone(UTC)


def _normalize_detail(detail: Any) -> dict:
    if not isinstance(detail, dict):
        raise ValueError("9Router returned a malformed request detail")
    event_id = detail.get("id")
    timestamp = detail.get("timestamp")
    if not isinstance(event_id, str) or not event_id.strip() or not isinstance(timestamp, str) or not timestamp:
        raise ValueError("9Router returned a malformed request detail")

    record = {
        "id": event_id,
        "timestamp": timestamp,
        "provider": detail.get("provider"),
        "model": detail.get("model"),
        "requests": 1,
    }
    tokens = detail.get("tokens")
    if isinstance(tokens, dict):
        _copy_positive_token(record, "input_tokens", tokens, "prompt_tokens", "input_tokens")
        _copy_positive_token(record, "output_tokens", tokens, "completion_tokens", "output_tokens")
        _copy_positive_token(record, "cache_read_tokens", tokens, "cached_tokens", "cache_read_input_tokens")
        _copy_positive_token(record, "cache_write_tokens", tokens, "cache_creation_input_tokens")
        _copy_positive_token(record, "reasoning_tokens", tokens, "reasoning_tokens")
    return record


def _copy_positive_token(record: dict, field: str, tokens: dict, *keys: str) -> None:
    for key in keys:
        value = tokens.get(key)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if isfinite(numeric) and numeric > 0:
            record[field] = value
            return
