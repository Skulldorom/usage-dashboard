import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import settings

_SEMVER = re.compile(
    r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
GITHUB_API_URL = "https://api.github.com/repos/Skulldorom/usage-dashboard/releases/latest"
RELEASE_BASE = "https://github.com/Skulldorom/usage-dashboard/releases/tag/"
MAX_RESPONSE_BYTES = 262144


@dataclass(frozen=True)
class UpdateResult:
    status: str
    current_version: str | None
    latest_version: str | None = None
    release_url: str | None = None
    release_name: str | None = None
    published_at: datetime | None = None
    checked_at: datetime | None = None
    cache_status: str = "empty"
    update_available: bool = False


@dataclass
class _Cache:
    checked_at: datetime
    tag: str
    url: str
    name: str | None
    published_at: datetime
    etag: str | None = None


_cache: _Cache | None = None
_next_check: datetime | None = None
_failed = False
_lock = asyncio.Lock()


def _version(value: str) -> tuple | None:
    if not isinstance(value, str) or len(value) > 128:
        return None
    match = _SEMVER.fullmatch(value)
    if not match:
        return None
    parts = (match.group(4) or "").split(".") if match.group(4) else []
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in parts):
        return None
    prerelease = tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts)
    return int(match[1]), int(match[2]), int(match[3]), prerelease


def is_newer(current: str, latest: str) -> bool:
    current_parsed, latest_parsed = _version(current), _version(latest)
    if not current_parsed or not latest_parsed:
        return False
    if current_parsed[:3] != latest_parsed[:3]:
        return current_parsed[:3] < latest_parsed[:3]
    if not current_parsed[3]:
        return False
    if not latest_parsed[3]:
        return True
    return current_parsed[3] < latest_parsed[3]


def _result() -> UpdateResult:
    current = settings.app_version
    parsed = _version(current)
    current = current if parsed else None
    status = "check_failed" if _failed else "unknown"
    available = False
    if not _failed and _cache and parsed and not parsed[3]:
        available = is_newer(current, _cache.tag)
        status = "update_available" if available else "up_to_date"
    return UpdateResult(
        status=status,
        current_version=current,
        latest_version=_cache.tag if _cache else None,
        release_url=_cache.url if _cache else None,
        release_name=_cache.name if _cache else None,
        published_at=_cache.published_at if _cache else None,
        checked_at=_cache.checked_at if _cache else None,
        cache_status=("stale" if _failed else "fresh") if _cache else "empty",
        update_available=available,
    )


def _release(payload: object, now: datetime, etag: str | None) -> _Cache:
    if not isinstance(payload, dict):
        raise ValueError("invalid release")
    tag, url = payload.get("tag_name"), payload.get("html_url")
    parsed = _version(tag)
    if (
        not parsed
        or parsed[3]
        or payload.get("draft") is not False
        or payload.get("prerelease") is not False
        or url != RELEASE_BASE + tag
    ):
        raise ValueError("not a published stable release")
    published = payload.get("published_at")
    if not isinstance(published, str):
        raise ValueError("missing publication time")
    published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
    if published_at.tzinfo is None or published_at > now:
        raise ValueError("invalid publication time")
    name = payload.get("name")
    if name is not None and (not isinstance(name, str) or len(name) > 256):
        raise ValueError("invalid release name")
    return _Cache(now, tag, url, name, published_at, etag)


async def check_for_update(*, now: datetime | None = None) -> UpdateResult:
    global _cache, _next_check, _failed
    async with _lock:
        now = now or datetime.now(UTC)
        if _next_check and now < _next_check:
            return _result()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "usage-dashboard-update-checker",
        }
        if _cache and _cache.etag:
            headers["If-None-Match"] = _cache.etag
        try:
            async with asyncio.timeout(settings.update_request_timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=settings.update_request_timeout_seconds, follow_redirects=False
                ) as client:
                    async with client.stream("GET", GITHUB_API_URL, headers=headers) as response:
                        if response.status_code == 304 and _cache:
                            _cache.checked_at = now
                        else:
                            response.raise_for_status()
                            body = bytearray()
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if len(body) > MAX_RESPONSE_BYTES:
                                    raise ValueError("oversized release response")
                            _cache = _release(json.loads(body), now, response.headers.get("etag"))
            _failed = False
            _next_check = now + timedelta(seconds=settings.update_cache_seconds)
        except (httpx.HTTPError, ValueError, UnicodeError, TimeoutError):
            _failed = True
            _next_check = now + timedelta(minutes=15)
        return _result()


def reset_cache() -> None:
    global _cache, _next_check, _failed, _lock
    _cache, _next_check, _failed = None, None, False
    _lock = asyncio.Lock()
