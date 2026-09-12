from typing import Optional
from fastapi import Cookie, Header, HTTPException, Query, Request, status

from server.config import get_admin_username
from server.db import get_api_key, get_setting, is_valid_api_key


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


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, alias="api_key"),
    key: Optional[str] = Query(None, alias="key"),
) -> str:
    """
    Dependency to enforce authentication on all transactional public API routes.
    Accepts credentials via:
      1. 'X-API-Key' HTTP Header (standard for REST API integrations)
      2. 'api_key' or 'key' URL query parameter
    In Cloud Relay mode: Enforces that external API keys are bound to an authorized client terminal group.
    In Local Bluetooth mode: Allows direct printing without requiring a relay group.
    Does NOT accept ambient session cookies to prevent cross-site request forgery (CSRF).
    """
    effective_key = (x_api_key or api_key or key or "").strip()
    if not effective_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Missing API key. Provide via 'X-API-Key' header or '?api_key=' parameter.",
        )

    key_data = get_api_key(effective_key)
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid API key",
        )

    mode = get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        group_name = (key_data.get("group_name") or "").strip()
        if not group_name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: In Cloud Relay mode, API key must be bound to a client terminal group. Please bind this key to a client group in settings.",
            )

    return effective_key


async def verify_media_access(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, alias="api_key"),
    key: Optional[str] = Query(None, alias="key"),
    tinypos_session: Optional[str] = Cookie(None),
) -> str:
    """
    Dependency for media/preview endpoints (GET /api/print/preview/{job_id} and GET/POST /api/qr/generate).
    Allows authentication via:
      1. Active admin session cookie ('tinypos_session=admin_authenticated') for internal dashboard views
      2. 'X-API-Key' HTTP Header
      3. 'api_key' or 'key' URL query parameter (for <img> tags, downloads, and direct links)
    """
    # 1. Allow authenticated admin session
    if tinypos_session == "admin_authenticated":
        return "admin_session"

    # 2. Extract key from header or query param
    effective_key = (x_api_key or api_key or key or "").strip()
    if not effective_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Missing API key. Provide via 'X-API-Key' header or '?api_key=' parameter.",
        )

    if not is_valid_api_key(effective_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid API key",
        )

    return effective_key
