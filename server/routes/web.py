import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from server.auth import get_current_user, require_login
from server.config import get_admin_password, get_admin_username, templates
import server.db as db

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
    counts = db.get_job_counts_by_api_keys()
    for k in keys:
        k["job_count"] = counts.get(k.get("key"), 0)

    return templates.TemplateResponse(
        request=request,
        name="api_keys/index.html",
        context={
            "active_page": "api_keys",
            "title": "API Keys | TinyPOS",
            "api_keys": keys,
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
    _: str = Depends(require_login),
):
    clean_key = key.strip()
    if not clean_key:
        clean_key = "sk_live_" + secrets.token_hex(16)

    clean_name = name.strip() or "Unnamed Key"
    db.insert_api_key(clean_key, clean_name)
    return RedirectResponse(url="/api-keys", status_code=303)


@web_router.post("/api-keys/delete")
async def delete_api_key_action(
    key_to_delete: str = Form(...),
    _: str = Depends(require_login),
):
    db.delete_api_key(key_to_delete)
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

