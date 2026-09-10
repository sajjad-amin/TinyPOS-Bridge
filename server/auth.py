from typing import Optional
from fastapi import Cookie, Header, HTTPException, Request, status

from server.config import get_admin_username
from server.db import is_valid_api_key


def get_current_user(tinypos_session: Optional[str] = Cookie(None)) -> Optional[str]:
    """Check session cookie for logged in user."""
    if tinypos_session != "admin_authenticated":
        return None
    return get_admin_username()


def require_login(request: Request, tinypos_session: Optional[str] = Cookie(None)) -> str:
    """Dependency that redirects unauthenticated users to /login."""
    if tinypos_session != "admin_authenticated":
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return get_admin_username()


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """Dependency to enforce valid X-API-Key stored in SQLite on all external API routes."""
    if not x_api_key or not is_valid_api_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or missing X-API-Key header",
        )
    return x_api_key
