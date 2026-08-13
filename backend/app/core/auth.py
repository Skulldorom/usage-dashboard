import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from hmac import compare_digest

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_session
from app.models import AdminCredential

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_secret(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return digest


def _password_hash(password: str, *, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 390_000)
    return f"pbkdf2_sha256$390000${salt}${base64.b64encode(key).decode('ascii')}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", maxsplit=3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    candidate = base64.b64encode(key).decode("ascii")
    return compare_digest(candidate, expected)


def _expiry(hours: int) -> datetime:
    return _now() + timedelta(hours=hours)


def _code_expiry() -> datetime:
    return _now() + timedelta(minutes=settings.admin_recovery_code_expire_minutes)


def _session_payload(token: str, expires_at: datetime) -> dict[str, str]:
    return {"token_hash": _hash_secret(token), "expires_at": expires_at.isoformat()}


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _code_is_valid(code: str, code_hash: str | None, expires_at: datetime | None) -> bool:
    expires_at = _as_aware(expires_at)
    if not code_hash or not expires_at or expires_at <= _now():
        return False
    return compare_digest(_hash_secret(code), code_hash)


async def get_admin_credential(session: AsyncSession) -> AdminCredential | None:
    return (await session.execute(select(AdminCredential).order_by(AdminCredential.id).limit(1))).scalar_one_or_none()


async def ensure_setup_code(session: AsyncSession) -> AdminCredential | None:
    credential = await get_admin_credential(session)
    if credential and credential.password_hash:
        return credential
    code = secrets.token_urlsafe(18)
    expires_at = _code_expiry()
    if credential is None:
        credential = AdminCredential(password_hash="pending", setup_code_hash=_hash_secret(code), setup_code_expires_at=expires_at)
        session.add(credential)
    else:
        credential.setup_code_hash = _hash_secret(code)
        credential.setup_code_expires_at = expires_at
    await session.commit()
    logger.warning("Admin setup code: %s", code)
    return credential


async def auth_status(session: AsyncSession) -> dict[str, bool]:
    credential = await ensure_setup_code(session)
    is_configured = bool(credential and credential.password_hash != "pending")
    return {"is_configured": is_configured, "setup_required": not is_configured}


async def create_session(credential: AdminCredential, session: AsyncSession) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = _expiry(settings.admin_session_expire_hours)
    active = [item for item in (credential.session_tokens or []) if _parse_expiry(item.get("expires_at")) and _parse_expiry(item.get("expires_at")) > _now()]
    active.append(_session_payload(token, expires_at))
    credential.session_tokens = active
    await session.commit()
    return token, expires_at


async def setup_admin_password(code: str, password: str, session: AsyncSession) -> tuple[str, datetime]:
    credential = await get_admin_credential(session)
    if credential and credential.password_hash != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin password is already configured")
    if credential is None:
        credential = await ensure_setup_code(session)
    if not _code_is_valid(code, credential.setup_code_hash, credential.setup_code_expires_at):
        raise HTTPException(status_code=400, detail="Invalid or expired setup code")
    credential.password_hash = _password_hash(password)
    credential.setup_code_hash = None
    credential.setup_code_expires_at = None
    credential.session_tokens = []
    return await create_session(credential, session)


async def login_admin(password: str, session: AsyncSession) -> tuple[str, datetime]:
    credential = await get_admin_credential(session)
    if not credential or credential.password_hash == "pending" or not _verify_password(password, credential.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    return await create_session(credential, session)


async def request_password_reset(session: AsyncSession) -> None:
    credential = await get_admin_credential(session)
    if not credential or credential.password_hash == "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin password is not configured")
    code = secrets.token_urlsafe(18)
    credential.reset_code_hash = _hash_secret(code)
    credential.reset_code_expires_at = _code_expiry()
    await session.commit()
    logger.warning("Admin password reset code: %s", code)


async def reset_admin_password(code: str, password: str, session: AsyncSession) -> tuple[str, datetime]:
    credential = await get_admin_credential(session)
    if not credential or credential.password_hash == "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin password is not configured")
    if not _code_is_valid(code, credential.reset_code_hash, credential.reset_code_expires_at):
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
    credential.password_hash = _password_hash(password)
    credential.reset_code_hash = None
    credential.reset_code_expires_at = None
    credential.session_tokens = []
    return await create_session(credential, session)


async def revoke_admin_session(token: str, session: AsyncSession) -> None:
    credential = await get_admin_credential(session)
    if not credential:
        return
    token_hash = _hash_secret(token)
    credential.session_tokens = [item for item in (credential.session_tokens or []) if item.get("token_hash") != token_hash]
    await session.commit()


async def validate_admin_session_token(token: str, session: AsyncSession) -> bool:
    credential = await get_admin_credential(session)
    if not credential:
        return False
    token_hash = _hash_secret(token)
    current = _now()
    active = []
    valid = False
    for item in credential.session_tokens or []:
        expires_at = _parse_expiry(item.get("expires_at"))
        if expires_at and expires_at > current:
            active.append(item)
            if compare_digest(item.get("token_hash", ""), token_hash):
                valid = True
    if active != (credential.session_tokens or []):
        credential.session_tokens = active
        await session.commit()
    return valid


def _request_host(request: Request) -> str:
    """Return a normalized Host header value without any port suffix."""
    host = request.headers.get("host", "").split(":", maxsplit=1)[0]
    return host.strip().rstrip(".").lower()


async def require_admin_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Require admin bearer auth for sensitive API routes."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    if settings.admin_token and compare_digest(token, settings.admin_token):
        return
    if await validate_admin_session_token(token, session):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def homepage_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Allow configured hosts to read the homepage payload without admin auth."""
    if _request_host(request) in settings.homepage_allowed_hosts:
        return
    await require_admin_auth(credentials, session)
