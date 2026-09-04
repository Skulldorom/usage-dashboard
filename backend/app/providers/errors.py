"""Normalized provider error model, sanitization, and structured logging.

Provider adapters and the polling layer share this so failures are classified
into stable categories and logged with safe, actionable context — without ever
leaking credentials, bearer/refresh tokens, API keys, cookies, or sensitive
request/response payloads.

Categories are deliberately coarse so a caller can distinguish authentication,
rate-limit, network, upstream, and parsing/schema failures without parsing raw
exception strings.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger("usage_dashboard.providers")

# Stable error categories.
AUTHENTICATION = "authentication"
RATE_LIMIT = "rate_limit"
NETWORK = "network"
TIMEOUT = "timeout"
UPSTREAM_HTTP = "upstream_http"
INVALID_RESPONSE = "invalid_response"
SCHEMA_CHANGED = "schema_changed"
PARSE_ERROR = "parse_error"
CONFIGURATION = "configuration"
UNKNOWN = "unknown"

ERROR_CATEGORIES = frozenset(
    {
        AUTHENTICATION,
        RATE_LIMIT,
        NETWORK,
        TIMEOUT,
        UPSTREAM_HTTP,
        INVALID_RESPONSE,
        SCHEMA_CHANGED,
        PARSE_ERROR,
        CONFIGURATION,
        UNKNOWN,
    }
)

# HTTP status -> (category, retryable).
_STATUS_CATEGORIES: dict[int, tuple[str, bool]] = {
    400: (CONFIGURATION, False),
    401: (AUTHENTICATION, False),
    403: (AUTHENTICATION, False),
    404: (UPSTREAM_HTTP, False),
    408: (TIMEOUT, True),
    429: (RATE_LIMIT, True),
}

# Maximum characters of an upstream response body we retain for diagnostics.
MAX_BODY_LENGTH = 1024

# Regexes for secret-bearing material. Applied to any text destined for logs or
# the API so tokens/keys/cookies never leak even when embedded in URLs, bodies,
# or error messages.
_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)\b(bearer\s+)[a-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(?i)\b(access[_-]?token|refresh[_-]?token|id[_-]?token|api[_-]?key|apikey|auth[_-]?token)\b\s*[:=]\s*[\"']?[a-z0-9._~+/=-]{6,}", re.IGNORECASE),
    re.compile(r"(?i)(sk-[a-z0-9]{8,})"),
    re.compile(r"(?i)(sk-ant-[a-z0-9]{8,})"),
    re.compile(r"(?i)(fc-[a-z0-9]{8,})"),
    re.compile(r"(?i)(eyj[a-z0-9._-]{8,})"),  # JWT (access/id tokens)
    re.compile(r"(?i)(cookies?|cookie)\s*[:=]\s*[\"']?[a-z0-9._~+/=-]{4,}", re.IGNORECASE),
]


@dataclass
class ProviderError(Exception):
    """A classified, sanitized provider failure.

    The raw exception may be attached (``cause``) for internal debugging, but
    ``message`` and everything surfaced through ``to_dict``/``to_log_fields`` is
    sanitized and safe for logs and the API.
    """

    category: str = UNKNOWN
    message: str = "Provider request failed"
    http_status: int | None = None
    stage: str | None = None
    retryable: bool | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    method: str | None = None
    endpoint: str | None = None
    response_content_type: str | None = None
    response_body: str | None = None

    def __post_init__(self) -> None:
        if self.category not in ERROR_CATEGORIES:
            self.category = UNKNOWN
        self.message = redact_text(str(self.message or "Provider request failed"))
        self.endpoint = sanitize_url(self.endpoint)
        if self.response_body is not None:
            self.response_body = truncate(redact_text(self.response_body))

    def to_dict(self) -> dict:
        """Sanitized, API-safe representation. Never includes raw payloads."""
        return {
            "category": self.category,
            "message": self.message,
            "http_status": self.http_status,
            "stage": self.stage,
            "retryable": self.retryable,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }

    def to_log_fields(self) -> dict:
        """Safe key=value fields for a structured log line."""
        fields = {
            "stage": self.stage or "unknown",
            "method": self.method,
            "endpoint": self.endpoint,
            "status_code": self.http_status,
            "error_type": type(self.__cause__).__name__ if self.__cause__ else None,
            "response_content_type": self.response_content_type,
            "response_body": self.response_body,
        }
        return {k: v for k, v in fields.items() if v is not None}

    @classmethod
    def from_response(
        cls,
        response: httpx.Response,
        *,
        category: str | None = None,
        message: str | None = None,
        stage: str | None = None,
        retryable: bool | None = None,
    ) -> "ProviderError":
        """Build a classified error from an httpx.Response, preserving safe context."""
        resolved_category = category or classify_http_status(response.status_code)[0]
        if retryable is None:
            retryable = classify_http_status(response.status_code)[1]
        return cls(
            category=resolved_category,
            message=message or _public_message(resolved_category, response.status_code),
            http_status=response.status_code,
            stage=stage,
            retryable=retryable,
            method=response.request.method if response.request else None,
            endpoint=str(response.request.url) if response.request else None,
            response_content_type=response.headers.get("content-type"),
            response_body=_safe_response_body(response),
        )


def sanitize_url(url: str | None) -> str | None:
    """Redact query-string secrets from a URL, then apply token redaction."""
    if not url:
        return None
    value = str(url)
    value = _redact_query_params(value)
    return redact_text(value)


def redact_text(text: Any) -> str:
    """Strip token/key/cookie material from arbitrary text."""
    if text is None:
        return ""
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(_redact_match, value)
    return value


def _redact_match(match: re.Match) -> str:
    text = match.group(0)
    # Preserve a known label ("Bearer ", "api_key=", "cookie=", ...) so the log
    # keeps useful context while the secret itself is fully redacted.
    for label in (
        "bearer",
        "access_token",
        "access token",
        "refresh_token",
        "refresh token",
        "id_token",
        "id token",
        "api_key",
        "api key",
        "apikey",
        "auth_token",
        "cookie",
        "cookies",
    ):
        prefix = re.match(rf"(?i)({re.escape(label)}\s*[:=]?\s*[\"']?)", text)
        if prefix:
            return prefix.group(1) + "[REDACTED]"
    return "[REDACTED]"


def _redact_query_params(url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    safe = "&".join(f"{key}=[REDACTED]" for key in _query_keys(parts.query))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, safe, parts.fragment))


def _query_keys(query: str) -> list[str]:
    from urllib.parse import parse_qsl, unquote_plus

    try:
        return [unquote_plus(k) for k, _ in parse_qsl(query, keep_blank_values=True)]
    except ValueError:
        return ["[REDACTED]"]


def truncate(text: str | None, limit: int = MAX_BODY_LENGTH) -> str:
    if text is None:
        return ""
    value = str(text)
    if len(value) <= limit:
        return value
    return value[:limit] + f"... [truncated {len(value) - limit} chars]"


def sanitize_headers(headers: dict | None) -> dict:
    """Return a header dict safe to log (drops authorization/cookie entirely)."""
    if not headers:
        return {}
    blocked = {"authorization", "cookie", "set-cookie", "proxy-authorization"}
    return {k: ("[REDACTED]" if k.lower() in blocked else v) for k, v in headers.items()}


def classify_http_status(status: int) -> tuple[str, bool]:
    """Map an HTTP status to (category, retryable)."""
    if status in _STATUS_CATEGORIES:
        return _STATUS_CATEGORIES[status]
    if 500 <= status < 600:
        return UPSTREAM_HTTP, True
    return UPSTREAM_HTTP, False


def classify_exception(exc: BaseException, *, stage: str | None = None) -> ProviderError:
    """Classify an arbitrary exception into a ProviderError, preserving safe context.

    ``stage`` labels the operation (``fetch_usage``, ``oauth_refresh``,
    ``config_test``, ``parse_response``). HTTP errors keep their status, content
    type, and a truncated/sanitized body; connection/timeout/JSON errors map to
    the corresponding category.
    """
    if isinstance(exc, ProviderError):
        if stage and not exc.stage:
            exc.stage = stage
        return exc

    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        category, retryable = classify_http_status(response.status_code)
        body = _safe_response_body(response)
        return ProviderError(
            category=category,
            message=_public_message(category, response.status_code),
            http_status=response.status_code,
            stage=stage,
            retryable=retryable,
            method=response.request.method if response.request else None,
            endpoint=str(response.request.url) if response.request else None,
            response_content_type=response.headers.get("content-type"),
            response_body=body,
        )

    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(category=TIMEOUT, message="Provider request timed out", stage=stage, retryable=True)

    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, httpx.TransportError)):
        return ProviderError(category=NETWORK, message="Network error reaching provider", stage=stage, retryable=True)

    if isinstance(exc, json.JSONDecodeError):
        return ProviderError(category=PARSE_ERROR, message="Provider returned malformed JSON", stage=stage or "parse_response", retryable=False)

    # Fallback: treat as an unknown provider error with a sanitized message.
    return ProviderError(category=UNKNOWN, message=str(exc) or "Provider request failed", stage=stage, retryable=None)


def _safe_response_body(response: httpx.Response) -> str | None:
    try:
        text = response.text
    except Exception:  # noqa: BLE001 - best-effort body capture
        return None
    if not text:
        return None
    return truncate(redact_text(text))


def _public_message(category: str, status: int) -> str:
    if category == AUTHENTICATION:
        return "Authentication rejected by provider"
    if category == RATE_LIMIT:
        return "Provider rate limit exceeded"
    if category == TIMEOUT:
        return "Provider request timed out"
    if status == 404:
        return "Provider endpoint not found or changed"
    if category == UPSTREAM_HTTP:
        return "Provider upstream error"
    if category == CONFIGURATION:
        return "Provider configuration rejected the request"
    return "Provider request failed"


def log_provider_failure(
    *,
    provider: str,
    config_id: int | None,
    error: ProviderError,
    last_success_at: datetime | None = None,
) -> None:
    """Emit one actionable structured log entry for a provider failure.

    The log line is useful at normal (INFO/WARNING) production level; debug
    logging is never required to diagnose a failure.
    """
    fields = error.to_log_fields()
    parts = [
        f"provider={provider}",
        f"config_id={config_id}",
        f"stage={fields['stage']}",
        f"category={error.category}",
        f"occurred_at={error.occurred_at.isoformat()}",
    ]
    for key in ("method", "endpoint", "status_code", "error_type", "response_content_type", "response_body"):
        if fields.get(key) is not None:
            parts.append(f"{key}={fields[key]}")
    if last_success_at is not None:
        parts.append(f"last_success_at={last_success_at.isoformat()}")
    logger.warning("Provider request failed %s", " ".join(parts))
