import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app import updates
from app.core.config import settings

NOW = datetime(2026, 11, 12, tzinfo=UTC)
RELEASE = {
    "tag_name": "v1.3.0",
    "html_url": updates.RELEASE_BASE + "v1.3.0",
    "draft": False,
    "prerelease": False,
    "published_at": "2026-11-11T00:00:00Z",
    "name": "Release 1.3",
}


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    updates.reset_cache()
    monkeypatch.setattr(settings, "app_version", "v1.2.0")


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        updates.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)
    )


@pytest.mark.parametrize(
    "current,latest,expected",
    [
        ("1.2.0", "1.2.1", True),
        ("v1.2.0", "v1.3.0", True),
        ("1.2.0", "2.0.0", True),
        ("1.3.0", "1.3.0", False),
        ("1.4.0", "1.3.0", False),
        ("1.10.0", "1.9.0", False),
        ("invalid", "1.3.0", False),
        ("unknown", "1.3.0", False),
        ("1.3.0-rc.1", "1.3.0", True),
        ("1.4.0-dev", "1.3.0", False),
        ("1.2", "1.3.0", False),
        ("1.2.0", "1.2.0+build", False),
        ("1.2.0-alpha.01", "1.3.0", False),
    ],
)
def test_semver(current, latest, expected):
    assert updates.is_newer(current, latest) is expected


@pytest.mark.asyncio
async def test_cache_concurrent_etag_and_failure_backoff(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=RELEASE, headers={"etag": '"release"'})
        if len(requests) == 2:
            assert request.headers["If-None-Match"] == '"release"'
            return httpx.Response(304)
        return httpx.Response(429)

    transport(monkeypatch, handler)
    results = await asyncio.gather(*(updates.check_for_update(now=NOW) for _ in range(8)))
    assert len(requests) == 1
    assert all(result.update_available for result in results)
    assert results[0].checked_at == NOW
    refreshed = await updates.check_for_update(now=NOW + timedelta(hours=7))
    assert refreshed.checked_at == NOW + timedelta(hours=7)
    stale = await updates.check_for_update(now=NOW + timedelta(hours=14))
    assert stale.status == "check_failed" and stale.cache_status == "stale"
    assert stale.latest_version == "v1.3.0" and not stale.update_available
    assert stale.checked_at == refreshed.checked_at
    await updates.check_for_update(now=NOW + timedelta(hours=14, minutes=1))
    assert len(requests) == 3


@pytest.mark.parametrize(
    "patch",
    [
        {"tag_name": None},
        {"html_url": None},
        {"html_url": "http://github.com/Skulldorom/usage-dashboard/releases/tag/v1.3.0"},
        {"html_url": "https://github.com/evil/repo/releases/tag/v1.3.0"},
        {"html_url": updates.RELEASE_BASE + "v9.0.0"},
        {"draft": True},
        {"prerelease": True},
        {"tag_name": "main"},
        {"published_at": None},
        {"tag_name": "v1.3.0-rc.1"},
        {"published_at": "2027-01-01T00:00:00Z"},
    ],
)
@pytest.mark.asyncio
async def test_invalid_releases(monkeypatch, patch):
    transport(monkeypatch, lambda _: httpx.Response(200, json={**RELEASE, **patch}))
    result = await updates.check_for_update(now=NOW)
    assert result.status == "check_failed" and result.latest_version is None


@pytest.mark.parametrize("code", [403, 404, 429, 500])
@pytest.mark.asyncio
async def test_http_failures_do_not_storm(monkeypatch, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(code)

    transport(monkeypatch, handler)
    for _ in range(5):
        result = await updates.check_for_update(now=NOW)
        assert result.status == "check_failed"
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"not json", b"[]", b"{}", b"x" * (updates.MAX_RESPONSE_BYTES + 1)])
@pytest.mark.asyncio
async def test_invalid_json_and_empty_history(monkeypatch, body):
    transport(monkeypatch, lambda _: httpx.Response(200, content=body))
    assert (await updates.check_for_update(now=NOW)).status == "check_failed"


@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
@pytest.mark.asyncio
async def test_network_failures(monkeypatch, exception):
    def handler(request):
        raise exception("offline", request=request)

    transport(monkeypatch, handler)
    assert (await updates.check_for_update(now=NOW)).status == "check_failed"


@pytest.mark.parametrize("version", ["unknown", "main", "v1.4.0-dev"])
@pytest.mark.asyncio
async def test_unknown_and_development_never_advertise(monkeypatch, version):
    monkeypatch.setattr(settings, "app_version", version)
    transport(monkeypatch, lambda _: httpx.Response(200, json=RELEASE))
    result = await updates.check_for_update(now=NOW)
    assert result.status == "unknown" and not result.update_available
