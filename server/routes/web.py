import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from server.auth import get_current_user, require_login
from server.config import get_admin_password, get_admin_username, templates
import server.db as db
from server.services.relay_manager import relay_manager

web_router = APIRouter()


@web_router.get("/", response_class=RedirectResponse)
async def root_redirect(user: Optional[str] = Depends(get_current_user)):
    """Default redirect to Test page if logged in, else login."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/test", status_code=302)


@web_router.get("/login", response_class=HTMLResponse)
async def login_view(request: Request, user: Optional[str] = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/test", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={},
    )


@web_router.post("/login")
async def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    valid_username = get_admin_username()
    valid_password = get_admin_password()

    if username.strip() == valid_username and password == valid_password:
        response = RedirectResponse(url="/test", status_code=303)
        response.set_cookie("tinypos_session", "admin_authenticated", max_age=86400 * 30, httponly=True)
        return response

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "error": "Invalid username or password.",
        },
        status_code=401,
    )


@web_router.get("/logout")
async def logout_action():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("tinypos_session")
    return response


# --- 1. Test Console (Default Page) ---
@web_router.get("/test", response_class=HTMLResponse)
async def test_view(request: Request, _: str = Depends(require_login)):
    return templates.TemplateResponse(
        request=request,
        name="test/index.html",
        context={
            "active_page": "test",
            "title": "Test | TinyPOS",
        },
    )


# --- 2. API Keys Management ---
@web_router.get("/api-keys", response_class=HTMLResponse)
async def api_keys_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    client_groups = db.list_client_groups()
    counts = db.get_job_counts_by_api_keys()
    for k in keys:
        k["job_count"] = counts.get(k.get("key"), 0)

    mode = db.get_setting("bridge_mode", "bluetooth")
    return templates.TemplateResponse(
        request=request,
        name="api_keys/index.html",
        context={
            "active_page": "api_keys",
            "title": "API Keys | TinyPOS",
            "api_keys": keys,
            "client_groups": client_groups,
            "bridge_mode": mode,
        },
    )


@web_router.get("/api-keys/{key}/history", response_class=HTMLResponse)
async def api_key_history_view(
    request: Request,
    key: str,
    page: int = 1,
    _: str = Depends(require_login),
):
    matched = db.get_api_key(key)
    key_name = matched["name"] if matched else "API Key"

    data = db.get_jobs_paginated(api_key=key, page=page, per_page=50)

    return templates.TemplateResponse(
        request=request,
        name="api_keys/history.html",
        context={
            "active_page": "api_keys",
            "title": f"History: {key_name} | TinyPOS",
            "target_key": key,
            "key_name": key_name,
            "jobs": data["jobs"],
            "total": data["total"],
            "page": data["page"],
            "total_pages": data["total_pages"],
            "has_prev": data["has_prev"],
            "has_next": data["has_next"],
        },
    )


@web_router.post("/api-keys/create")
async def create_api_key_action(
    name: str = Form(...),
    key: str = Form(...),
    group_name: Optional[str] = Form(None),
    _: str = Depends(require_login),
):
    clean_key = key.strip()
    if not clean_key:
        clean_key = "sk_live_" + secrets.token_hex(16)

    clean_name = name.strip() or "Unnamed Key"
    clean_group = (group_name or "").strip() or None
    db.insert_api_key(clean_key, clean_name, group_name=clean_group)
    return RedirectResponse(url="/api-keys", status_code=303)


@web_router.post("/api-keys/delete")
async def delete_api_key_action(
    key_to_delete: str = Form(...),
    _: str = Depends(require_login),
):
    db.delete_api_key(key_to_delete)
    return RedirectResponse(url="/api-keys", status_code=303)


@web_router.post("/api-keys/assign-group")
async def assign_api_key_group_action(
    key: str = Form(...),
    group_name: Optional[str] = Form(None),
    _: str = Depends(require_login),
):
    clean_key = key.strip()
    clean_group = (group_name or "").strip() or None
    if clean_key:
        db.assign_api_key_to_group(clean_key, clean_group)
    return RedirectResponse(url="/api-keys", status_code=303)


@web_router.post("/api-keys/remove-group")
async def remove_api_key_group_action(
    key: str = Form(...),
    _: str = Depends(require_login),
):
    clean_key = key.strip()
    if clean_key:
        db.assign_api_key_to_group(clean_key, None)
    return RedirectResponse(url="/api-keys", status_code=303)


def get_request_base_url(request: Request) -> str:
    """
    Dynamically resolves the public base URL, respecting reverse proxy headers
    (such as Cloudflare Tunnel, Nginx, or Caddy) if present.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


# --- 3. Documentation Routes ---
@web_router.get("/documentation", response_class=HTMLResponse)
@web_router.get("/documentation/overview", response_class=HTMLResponse)
async def documentation_overview_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    base_url = get_request_base_url(request)
    return templates.TemplateResponse(
        request=request,
        name="documentation/index.html",
        context={
            "active_page": "documentation",
            "active_subpage": "overview",
            "title": "Documentation & Quickstart | TinyPOS",
            "api_keys": keys,
            "request_url_base": base_url,
        },
    )


@web_router.get("/documentation/qr", response_class=HTMLResponse)
async def documentation_qr_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    base_url = get_request_base_url(request)
    return templates.TemplateResponse(
        request=request,
        name="documentation/qr.html",
        context={
            "active_page": "documentation",
            "active_subpage": "qr",
            "title": "QR Code API | TinyPOS",
            "api_keys": keys,
            "request_url_base": base_url,
        },
    )


@web_router.get("/documentation/photo", response_class=HTMLResponse)
async def documentation_photo_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    base_url = get_request_base_url(request)
    return templates.TemplateResponse(
        request=request,
        name="documentation/photo.html",
        context={
            "active_page": "documentation",
            "active_subpage": "photo",
            "title": "Photo Studio API | TinyPOS",
            "api_keys": keys,
            "request_url_base": base_url,
        },
    )


@web_router.get("/documentation/documents", response_class=HTMLResponse)
async def documentation_documents_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    base_url = get_request_base_url(request)
    return templates.TemplateResponse(
        request=request,
        name="documentation/documents.html",
        context={
            "active_page": "documentation",
            "active_subpage": "documents",
            "title": "Invoices & PDFs API | TinyPOS",
            "api_keys": keys,
            "request_url_base": base_url,
        },
    )


@web_router.get("/documentation/text", response_class=HTMLResponse)
async def documentation_text_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    base_url = get_request_base_url(request)
    return templates.TemplateResponse(
        request=request,
        name="documentation/text.html",
        context={
            "active_page": "documentation",
            "active_subpage": "text",
            "title": "Multilingual Text API | TinyPOS",
            "api_keys": keys,
            "request_url_base": base_url,
        },
    )


@web_router.get("/documentation/control", response_class=HTMLResponse)
async def documentation_control_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    base_url = get_request_base_url(request)
    return templates.TemplateResponse(
        request=request,
        name="documentation/control.html",
        context={
            "active_page": "documentation",
            "active_subpage": "control",
            "title": "Job Control & Status API | TinyPOS",
            "api_keys": keys,
            "request_url_base": base_url,
        },
    )


def get_websocket_url(request: Request, api_key: str = "") -> str:
    """Construct WebSocket connection URL respecting reverse proxy scheme and host."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    ws_proto = "wss" if proto == "https" else "ws"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not host:
        host = f"{request.url.hostname}:{request.url.port}" if request.url.port else (request.url.hostname or "localhost")
    url = f"{ws_proto}://{host}/ws/client"
    if api_key:
        url += f"?api_key={api_key}"
    return url


# --- 4. Settings Routes ---
@web_router.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request, _: str = Depends(require_login)):
    keys = db.list_api_keys()
    client_keys = db.list_client_api_keys()
    client_groups = db.list_client_groups()
    connected_keys = relay_manager.get_connected_api_keys()

    # Enrich client keys with live connection info & WebSocket URL
    for ck in client_keys:
        k = ck["key"]
        conn_info = connected_keys.get(k)
        ck["is_connected"] = conn_info is not None
        ck["connected_client"] = conn_info
        ck["ws_url"] = get_websocket_url(request, api_key=k)

    # Group client keys by group
    grouped_client_keys = []
    for g in client_groups:
        g_name = g["name"]
        keys_in_group = [ck for ck in client_keys if ck.get("group_name") == g_name]
        grouped_client_keys.append({
            "name": g_name,
            "created_at": g.get("created_at"),
            "key_count": len(keys_in_group),
            "connected_count": sum(1 for k in keys_in_group if k["is_connected"]),
            "terminal_keys": keys_in_group,
        })

    # Keys that are not assigned to any group
    unassigned_client_keys = [ck for ck in client_keys if not ck.get("group_name")]

    settings = db.get_all_settings()
    bridge_mode = settings.get("bridge_mode", "bluetooth")

    base_url = get_request_base_url(request)
    first_client_key = client_keys[0]["key"] if client_keys else ""
    ws_url = get_websocket_url(request, api_key=first_client_key)

    is_client_connected = relay_manager.is_any_client_connected()
    client_info = relay_manager.get_client_info()
    admin_printer_group = db.get_setting("admin_printer_group", "default")
    clients = relay_manager.get_connected_clients_summary(group=admin_printer_group if bridge_mode == "relay" else None)
    active_client = relay_manager.get_active_printing_client(group=admin_printer_group if bridge_mode == "relay" else None)

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "active_page": "settings",
            "title": "Settings | TinyPOS",
            "bridge_mode": bridge_mode,
            "admin_printer_group": admin_printer_group,
            "client_keys": client_keys,
            "client_groups": client_groups,
            "grouped_client_keys": grouped_client_keys,
            "unassigned_client_keys": unassigned_client_keys,
            "api_keys": keys,
            "request_url_base": base_url,
            "ws_url": ws_url,
            "is_client_connected": is_client_connected,
            "client_info": client_info,
            "clients": clients,
            "active_client": active_client,
            "client_count": len(clients),
        },
    )


@web_router.post("/settings/mode")
async def settings_mode_action(
    mode: str = Form(...),
    _: str = Depends(require_login),
):
    cleaned = mode.lower().strip()
    if cleaned in ("bluetooth", "relay"):
        db.set_setting("bridge_mode", cleaned)
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/settings/admin-group")
async def settings_admin_group_action(
    admin_printer_group: str = Form(...),
    _: str = Depends(require_login),
):
    clean_group = admin_printer_group.strip()
    if clean_group:
        db.set_setting("admin_printer_group", clean_group)
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/settings/client-keys/create")
async def settings_create_client_key_action(
    name: str = Form(...),
    key: Optional[str] = Form(None),
    group_name: Optional[str] = Form(None),
    _: str = Depends(require_login),
):
    clean_name = name.strip() or "Store Terminal"
    clean_key = (key or "").strip()
    if not clean_key:
        clean_key = "sk_client_" + secrets.token_hex(12)
    clean_group = (group_name or "").strip() or None
    db.insert_client_api_key(clean_key, clean_name, group_name=clean_group)
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/settings/client-keys/delete")
async def settings_delete_client_key_action(
    key_to_delete: str = Form(...),
    _: str = Depends(require_login),
):
    clean_key = key_to_delete.strip()
    if clean_key:
        await relay_manager.disconnect_by_api_key(clean_key)
        db.delete_client_api_key(clean_key)
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/settings/groups/create")
async def settings_create_group_action(
    request: Request,
    name: str = Form(...),
    _: str = Depends(require_login),
):
    form = await request.form()
    clean_name = name.strip()
    key_list = form.getlist("keys")
    if clean_name:
        db.create_client_group(clean_name, key_list=key_list)
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/settings/groups/delete")
async def settings_delete_group_action(
    group_to_delete: str = Form(...),
    _: str = Depends(require_login),
):
    clean_group = group_to_delete.strip()
    if clean_group:
        db.delete_client_group(clean_group)
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/settings/client-keys/remove-group")
async def settings_remove_client_key_group_action(
    key: str = Form(...),
    _: str = Depends(require_login),
):
    clean_key = key.strip()
    if clean_key:
        db.remove_client_key_from_group(clean_key)
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/settings/client-keys/assign-group")
async def settings_assign_client_key_group_action(
    key: str = Form(...),
    group_name: str = Form(...),
    _: str = Depends(require_login),
):
    clean_key = key.strip()
    clean_group = group_name.strip()
    if clean_key and clean_group:
        db.assign_client_key_to_group(clean_key, clean_group)
    return RedirectResponse(url="/settings", status_code=303)



