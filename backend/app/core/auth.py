from hmac import compare_digest

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def require_admin_auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> None:
    """Require a configured admin bearer token for sensitive API routes."""
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication is not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not compare_digest(credentials.credentials, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _request_host(request: Request) -> str:
    """Return a normalized Host header value without any port suffix."""
    host = request.headers.get("host", "").split(":", maxsplit=1)[0]
    return host.strip().rstrip(".").lower()


def homepage_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Allow configured hosts to read the homepage payload without admin auth."""
    if _request_host(request) in settings.homepage_allowed_hosts:
        return
    require_admin_auth(credentials)
