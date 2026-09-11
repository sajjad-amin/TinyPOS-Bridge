from typing import Optional
from fastapi import Cookie, Header, HTTPException, Request, status

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


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """
    Dependency to enforce valid X-API-Key on all external API routes.
    In Cloud Relay mode: Enforces that the key is bound to an authorized client terminal group.
    In Local Bluetooth mode: Allows direct printing to local BLE printer without requiring a relay group.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Missing X-API-Key header",
        )
    key_data = get_api_key(x_api_key)
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid X-API-Key",
        )

    mode = get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        group_name = (key_data.get("group_name") or "").strip()
        if not group_name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: In Cloud Relay mode, API key must be bound to a client terminal group. Please bind this key to a client group in settings.",
            )

    return x_api_key
