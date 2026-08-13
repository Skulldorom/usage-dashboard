import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.providers.codex import CodexCredentials

OPENAI_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_OAUTH_SCOPE = "openid profile email offline_access"
OPENAI_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_OAUTH_DEVICE_CODE_URL = "https://auth.openai.com/oauth/device/code"
CODEX_DEVICE_AUTH_SETTINGS_URL = "https://chatgpt.com/codex/settings/general#settings/Security"
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


@dataclass(slots=True)
class CodexDeviceStart:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_at: datetime
    interval_seconds: int


def public_device_payload(flow_id: str, device: CodexDeviceStart) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "user_code": device.user_code,
        "verification_uri": device.verification_uri,
        "verification_uri_complete": device.verification_uri_complete,
        "expires_at": device.expires_at.astimezone(UTC).isoformat(),
        "interval_seconds": device.interval_seconds,
    }


async def start_device_authorization(*, timeout: float = 20.0) -> CodexDeviceStart:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            OPENAI_OAUTH_DEVICE_CODE_URL,
            data={"client_id": OPENAI_OAUTH_CLIENT_ID, "scope": OPENAI_OAUTH_SCOPE},
            headers={"Accept": "application/json"},
        )
    if not response.is_success:
        raise ValueError(f"Codex device authorization failed: {_safe_oauth_error(response)}")
    data = response.json()
    device_code = _clean_string(data.get("device_code"))
    user_code = _clean_string(data.get("user_code"))
    verification_uri = _clean_string(data.get("verification_uri")) or "https://auth.openai.com/codex/device"
    verification_uri_complete = _clean_string(data.get("verification_uri_complete"))
    expires_in = _positive_int(data.get("expires_in")) or 900
    interval = _positive_int(data.get("interval")) or 5
    if not device_code or not user_code:
        raise ValueError("Codex device authorization response was missing a device or user code")
    return CodexDeviceStart(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        interval_seconds=interval,
    )


async def poll_device_authorization(device_code: str, *, timeout: float = 20.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            OPENAI_OAUTH_TOKEN_URL,
            data={
                "grant_type": DEVICE_GRANT_TYPE,
                "device_code": device_code,
                "client_id": OPENAI_OAUTH_CLIENT_ID,
            },
            headers={"Accept": "application/json"},
        )
    if response.is_success:
        secret = _secret_from_token_response(response.json())
        return {"status": "completed", "secret": secret}

    error_payload = _oauth_error_payload(response)
    oauth_error = error_payload.get("error")
    if oauth_error == "authorization_pending":
        return {"status": "pending", "interval_seconds": _positive_int(error_payload.get("interval")) or 5}
    if oauth_error == "slow_down":
        return {"status": "slow_down", "interval_seconds": _positive_int(error_payload.get("interval")) or 10}
    if oauth_error == "expired_token":
        return {"status": "expired", "error": "Codex device code expired. Start a new connection."}
    if oauth_error == "access_denied":
        return {"status": "failed", "error": "Codex device authorization was denied."}
    return {"status": "failed", "error": f"Codex device authorization failed: {_safe_oauth_error(response)}"}


def _secret_from_token_response(data: dict[str, Any]) -> str:
    access_token = _clean_string(data.get("access_token"))
    refresh_token = _clean_string(data.get("refresh_token"))
    if not access_token or not refresh_token:
        raise ValueError("Codex token response did not include access and refresh tokens")
    expires_at = _expires_at(data)
    id_token = _clean_string(data.get("id_token"))
    account_id = _extract_account_id(id_token) if id_token else None
    return CodexCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        account_id=account_id,
    ).to_secret_json()


def _expires_at(data: dict[str, Any]) -> datetime | None:
    expires_in = _positive_int(data.get("expires_in"))
    if not expires_in:
        return None
    return datetime.now(UTC) + timedelta(seconds=expires_in)


def _extract_account_id(id_token: str) -> str | None:
    parts = id_token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return None
    for key in ("chatgpt_account_id", "account_id", "workspace_id"):
        value = _clean_string(claims.get(key))
        if value:
            return value
    for namespace in ("https://api.openai.com/auth", "https://auth.openai.com/auth_info"):
        nested = claims.get(namespace)
        if isinstance(nested, dict):
            value = _clean_string(nested.get("chatgpt_account_id") or nested.get("account_id"))
            if value:
                return value
    return None


def _oauth_error_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _safe_oauth_error(response: httpx.Response) -> str:
    if response.status_code == 403:
        return (
            "HTTP 403. Enable device code authentication for Codex in ChatGPT security settings "
            f"({CODEX_DEVICE_AUTH_SETTINGS_URL}), then start a new Codex device login. "
            "For workspace accounts, an admin may need to allow device code authentication."
        )
    data = _oauth_error_payload(response)
    description = _clean_string(data.get("error_description"))
    oauth_error = _clean_string(data.get("error"))
    if description:
        return _truncate(description)
    if oauth_error:
        return _truncate(oauth_error)
    return f"HTTP {response.status_code}"


def _truncate(value: str, max_length: int = 240) -> str:
    return value if len(value) <= max_length else f"{value[:max_length]}..."


def _clean_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
