import io
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from PIL import Image

import printer_ble
from server.auth import require_login
import server.db as db
from server.services.print_service import (
    dispatch_bitmap_print,
    feed_paper_cmd,
    get_system_printer_status,
    stop_print_job,
)
from server.services.relay_manager import relay_manager

internal_api_router = APIRouter(prefix="/api/internal", dependencies=[Depends(require_login)])


def validate_admin_printer_group() -> tuple[Optional[str], Optional[str]]:
    """
    Mandatory check: Ensures Cloud Relay mode has an assigned Admin Printer group
    before executing jobs from the web test console, preventing prints from routing to other users' printers.
    Returns (target_group, error_message).
    """
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        admin_group = (db.get_setting("admin_printer_group") or "").strip()
        if not admin_group:
            return None, "Admin Printer group is not configured. Please assign an Admin Printer group in Settings before executing test page jobs."
        groups = {g["name"] for g in db.list_client_groups()}
        if admin_group not in groups:
            return None, f"Configured Admin Printer group '{admin_group}' does not exist. Please assign an existing group in Settings."
        return admin_group, None
    return None, None


@internal_api_router.get("/status")
async def internal_status():
    """Probe printer status (local BLE or Cloud Relay scoped strictly to the Admin Printer group)."""
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        admin_group = (db.get_setting("admin_printer_group") or "").strip()
        if not admin_group:
            return {
                "status": "offline",
                "mode": "relay",
                "is_printing": False,
                "printer_name": "Admin Printer Not Configured",
                "address": "Unassigned",
                "active_job_id": None,
                "client_count": 0,
                "group": None,
                "message": "Admin Printer group is not configured. Please assign an Admin Printer group in Settings.",
            }
        return await get_system_printer_status(group=admin_group)
    return await get_system_printer_status()


@internal_api_router.post("/feed")
async def internal_feed():
    """Trigger manual paper feed command (Bluetooth or Cloud Relay scoped to Admin Printer group)."""
    target_group, err = validate_admin_printer_group()
    if err:
        return {"success": False, "error": err}
    success, err_or_msg = await feed_paper_cmd(group=target_group)
    if success:
        return {"success": True, "message": err_or_msg}
    return {"success": False, "error": err_or_msg}


class InternalPrintTextRequest(BaseModel):
    text: str
    font_size: int = 22
    strength: int = 7
    keep_job: bool = True


@internal_api_router.post("/print-text")
async def internal_print_text(payload: InternalPrintTextRequest):
    """Render and print text from the test console."""
    if not payload.text.strip():
        return {"success": False, "message": "Text is empty"}

    target_group, err = validate_admin_printer_group()
    if err:
        return {"success": False, "message": err}

    try:
        bitmap = printer_ble.render_text_to_bitmap(
            payload.text,
            font_size=payload.font_size,
            strength=payload.strength,
        )
        job_id = str(uuid.uuid4())
        db.insert_job(
            job_id=job_id,
            job_type="text",
            status="printing",
            api_key="test_page",
            image=bitmap,
            strength=payload.strength,
            scale=1.0,
            autocrop=True,
            keep_job=payload.keep_job,
        )
        success, msg = await dispatch_bitmap_print(bitmap, strength=payload.strength, job_id=job_id, target_group=target_group)
        final_status = "completed" if success else ("cancelled" if "stop" in msg.lower() or "cancel" in msg.lower() else "failed")
        db.update_job_status(job_id, final_status, error=None if success else msg)
        return {"success": success, "message": msg, "job_id": job_id, "status": final_status}
    except Exception as e:
        return {"success": False, "message": str(e)}


@internal_api_router.post("/stop")
async def internal_stop_print():
    """Stop the currently transmitting print job immediately."""
    active_id = printer_ble.get_active_job_id() or relay_manager.get_active_job_id()
    stopped, msg = await stop_print_job(active_id)
    if active_id:
        db.update_job_status(active_id, "cancelled", error="Stopped by user from test console")
    return {"success": stopped, "message": msg, "job_id": active_id}


@internal_api_router.post("/jobs/{job_id}/stop")
async def internal_stop_job(job_id: str):
    """Stop a specific print job if it is currently printing or pending."""
    active_id = printer_ble.get_active_job_id() or relay_manager.get_active_job_id()
    if active_id == job_id or (printer_ble.is_printing() and not active_id) or (relay_manager.is_printing() and not active_id):
        stopped, msg = await stop_print_job(job_id)
        db.update_job_status(job_id, "cancelled", error="Stopped by user from test console")
        return {"success": True, "message": "Print job stopped successfully"}

    job = db.get_job(job_id)
    if job and job["status"] == "pending":
        db.update_job_status(job_id, "cancelled", error="Cancelled by user before printing")
        return {"success": True, "message": "Pending print job cancelled"}
    elif job and job["status"] == "printing":
        await stop_print_job(job_id)
        db.update_job_status(job_id, "cancelled", error="Stopped by user")
        return {"success": True, "message": "Print job marked stopped"}

    return JSONResponse(status_code=400, content={"success": False, "message": "Job is not currently printing or pending"})


@internal_api_router.post("/preview-text")
async def internal_preview_text(payload: InternalPrintTextRequest):
    """Generate 384px PNG preview for text."""
    bitmap = printer_ble.render_text_to_bitmap(
        payload.text,
        font_size=payload.font_size,
        strength=payload.strength,
    )
    buf = io.BytesIO()
    bitmap.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


class InternalPrintQRRequest(BaseModel):
    content: str
    header: Optional[str] = None
    footer: Optional[str] = None
    qr_size: int = 280
    strength: int = 7
    keep_job: bool = True


@internal_api_router.post("/preview-qr")
async def internal_preview_qr(payload: InternalPrintQRRequest):
    """Generate 384px PNG preview for QR code."""
    if not payload.content.strip():
        payload.content = "https://sajjadamin.com"
    bitmap = printer_ble.render_qr_to_bitmap(
        content=payload.content,
        header_text=payload.header,
        footer_text=payload.footer,
        qr_size=payload.qr_size,
        strength=payload.strength,
    )
    buf = io.BytesIO()
    bitmap.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@internal_api_router.post("/print-qr")
async def internal_print_qr(payload: InternalPrintQRRequest):
    """Render and print QR code from the test console."""
    if not payload.content.strip():
        return {"success": False, "message": "QR content cannot be empty"}

    target_group, err = validate_admin_printer_group()
    if err:
        return {"success": False, "message": err}

    try:
        bitmap = printer_ble.render_qr_to_bitmap(
            content=payload.content,
            header_text=payload.header,
            footer_text=payload.footer,
            qr_size=payload.qr_size,
            strength=payload.strength,
        )
        job_id = str(uuid.uuid4())
        db.insert_job(
            job_id=job_id,
            job_type="qr",
            status="printing",
            api_key="test_page",
            image=bitmap,
            strength=payload.strength,
            scale=1.0,
            autocrop=False,
            keep_job=payload.keep_job,
        )
        success, msg = await dispatch_bitmap_print(bitmap, strength=payload.strength, job_id=job_id, target_group=target_group)
        final_status = "completed" if success else ("cancelled" if "stop" in msg.lower() or "cancel" in msg.lower() else "failed")
        db.update_job_status(job_id, final_status, error=None if success else msg)
        return {"success": success, "message": msg, "job_id": job_id, "status": final_status}
    except Exception as e:
        return {"success": False, "message": str(e)}


@internal_api_router.post("/print-file")
async def internal_print_file(
    file: UploadFile = File(...),
    strength: int = Form(7),
    scale: float = Form(1.0),
    autocrop: bool = Form(True),
    keep_job: bool = Form(True),
    mode: str = Form("text"),
    dither: Optional[bool] = Form(None),
):
    """Process and print uploaded PDF/image from the test console."""
    content = await file.read()
    if not content:
        return {"success": False, "message": "File is empty"}

    target_group, err = validate_admin_printer_group()
    if err:
        return {"success": False, "message": err}

    use_photo_mode = (str(mode).lower() == "photo") or bool(dither)
    active_mode = "photo" if use_photo_mode else "text"
    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".pdf") or file.content_type == "application/pdf":
            bitmap = printer_ble.render_pdf_to_bitmap(
                content, scale=scale, autocrop=autocrop, strength=strength, mode=active_mode, dither=use_photo_mode
            )
            job_type = "pdf"
        else:
            raw_img = Image.open(io.BytesIO(content))
            bitmap = printer_ble.convert_image_to_bitmap(
                raw_img, scale=scale, autocrop=autocrop, strength=strength, mode=active_mode, dither=use_photo_mode
            )
            job_type = "image"

        job_id = str(uuid.uuid4())
        db.insert_job(
            job_id=job_id,
            job_type=job_type,
            status="printing",
            api_key="test_page",
            image=bitmap,
            strength=strength,
            scale=scale,
            autocrop=autocrop,
            keep_job=keep_job,
        )
        success, msg = await dispatch_bitmap_print(bitmap, strength=strength, job_id=job_id, target_group=target_group)
        final_status = "completed" if success else ("cancelled" if "stop" in msg.lower() or "cancel" in msg.lower() else "failed")
        db.update_job_status(job_id, final_status, error=None if success else msg)
        return {"success": success, "message": msg, "job_id": job_id, "status": final_status, "mode": active_mode}
    except Exception as e:
        return {"success": False, "message": str(e)}


@internal_api_router.post("/preview-file")
async def internal_preview_file(
    file: UploadFile = File(...),
    strength: int = Form(7),
    scale: float = Form(1.0),
    autocrop: bool = Form(True),
    mode: str = Form("text"),
    dither: Optional[bool] = Form(None),
):
    """Generate 384px PNG thermal preview for uploaded file with scale, autocrop, and dithering."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    use_photo_mode = (str(mode).lower() == "photo") or bool(dither)
    active_mode = "photo" if use_photo_mode else "text"
    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".pdf") or file.content_type == "application/pdf":
            bitmap = printer_ble.render_pdf_to_bitmap(
                content, scale=scale, autocrop=autocrop, strength=strength, mode=active_mode, dither=use_photo_mode
            )
        else:
            raw_img = Image.open(io.BytesIO(content))
            bitmap = printer_ble.convert_image_to_bitmap(
                raw_img, scale=scale, autocrop=autocrop, strength=strength, mode=active_mode, dither=use_photo_mode
            )

        buf = io.BytesIO()
        bitmap.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@internal_api_router.post("/print-photo")
async def internal_print_photo(
    file: UploadFile = File(...),
    preset: str = Form("portrait"),
    dither_algo: Optional[str] = Form(None),
    sharpness: Optional[float] = Form(None),
    contrast: Optional[float] = Form(None),
    brightness: Optional[float] = Form(None),
    strength: int = Form(7),
    scale: float = Form(1.0),
    autocrop: bool = Form(True),
    keep_job: bool = Form(True),
):
    """Process and print uploaded photo with advanced quality and dithering controls."""
    content = await file.read()
    if not content:
        return {"success": False, "message": "Uploaded photo file is empty"}

    target_group, err = validate_admin_printer_group()
    if err:
        return {"success": False, "message": err}

    try:
        raw_img = Image.open(io.BytesIO(content))
        bitmap = printer_ble.render_photo_to_bitmap(
            raw_img,
            scale=scale,
            autocrop=autocrop,
            strength=strength,
            preset=preset,
            dither_algo=dither_algo,
            sharpness=sharpness,
            contrast=contrast,
            brightness=brightness,
        )

        job_id = str(uuid.uuid4())
        db.insert_job(
            job_id=job_id,
            job_type="photo",
            status="printing",
            api_key="test_page",
            image=bitmap,
            strength=strength,
            scale=scale,
            autocrop=autocrop,
            keep_job=keep_job,
        )
        success, msg = await dispatch_bitmap_print(bitmap, strength=strength, job_id=job_id, target_group=target_group)
        final_status = "completed" if success else ("cancelled" if "stop" in msg.lower() or "cancel" in msg.lower() else "failed")
        db.update_job_status(job_id, final_status, error=None if success else msg)
        return {"success": success, "message": msg, "job_id": job_id, "status": final_status, "preset": preset}
    except Exception as e:
        return {"success": False, "message": str(e)}


@internal_api_router.post("/preview-photo")
async def internal_preview_photo(
    file: UploadFile = File(...),
    preset: str = Form("portrait"),
    dither_algo: Optional[str] = Form(None),
    sharpness: Optional[float] = Form(None),
    contrast: Optional[float] = Form(None),
    brightness: Optional[float] = Form(None),
    strength: int = Form(7),
    scale: float = Form(1.0),
    autocrop: bool = Form(True),
):
    """Generate 384px PNG thermal preview for uploaded photo with quality controls."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded photo is empty")

    try:
        raw_img = Image.open(io.BytesIO(content))
        bitmap = printer_ble.render_photo_to_bitmap(
            raw_img,
            scale=scale,
            autocrop=autocrop,
            strength=strength,
            preset=preset,
            dither_algo=dither_algo,
            sharpness=sharpness,
            contrast=contrast,
            brightness=brightness,
        )

        buf = io.BytesIO()
        bitmap.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@internal_api_router.get("/queue")
async def internal_queue(
    page: int = 1,
    per_page: int = 50,
    api_key: Optional[str] = None,
):
    """Retrieve paginated jobs for the web dashboard (default: 50/page)."""
    return db.get_jobs_paginated(api_key=api_key, page=page, per_page=per_page)


@internal_api_router.delete("/jobs/{job_id}")
async def internal_delete_job(job_id: str):
    """Delete a single job and its preview raster from SQLite."""
    deleted = db.delete_job(job_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"success": False, "message": "Job not found"})
    return {"success": True, "message": "Job deleted successfully"}


@internal_api_router.post("/jobs/clear")
async def internal_clear_jobs(api_key: Optional[str] = Form(None)):
    """Bulk delete jobs, optionally filtered by api_key."""
    count = db.delete_jobs_by_filter(api_key=api_key)
    return {"success": True, "count": count, "message": f"Successfully deleted {count} jobs"}


# ==========================================
# Settings & Cloud Relay Control
# ==========================================

class UpdateModeRequest(BaseModel):
    mode: str


@internal_api_router.get("/settings")
async def internal_get_settings():
    """Retrieve system bridge settings and relay connection state."""
    settings = db.get_all_settings()
    mode = settings.get("bridge_mode", "bluetooth")
    client_key = settings.get("client_api_key", "any")
    admin_group = settings.get("admin_printer_group", "default")
    clients = relay_manager.get_connected_clients_summary(group=admin_group if mode == "relay" else None)
    active_client = relay_manager.get_active_printing_client(group=admin_group if mode == "relay" else None)
    return {
        "bridge_mode": mode,
        "client_api_key": client_key,
        "admin_printer_group": admin_group,
        "client_count": len(clients),
        "clients": clients,
        "active_client": active_client,
        "is_client_connected": len(clients) > 0,
        "is_printer_online": active_client is not None,
    }


@internal_api_router.post("/settings/mode")
async def internal_set_mode(payload: UpdateModeRequest):
    """Switch operating bridge mode ('bluetooth' or 'relay')."""
    cleaned = payload.mode.lower().strip()
    if cleaned not in ("bluetooth", "relay"):
        return JSONResponse(status_code=400, content={"success": False, "message": "Mode must be 'bluetooth' or 'relay'"})
    db.set_setting("bridge_mode", cleaned)
    return {"success": True, "mode": cleaned, "message": f"Bridge mode switched to {cleaned}"}


class UpdateAdminGroupRequest(BaseModel):
    admin_printer_group: str


@internal_api_router.post("/settings/admin-group")
async def internal_set_admin_group(payload: UpdateAdminGroupRequest):
    """Assign which client terminal group can print admin jobs from the web test page."""
    group_name = payload.admin_printer_group.strip()
    groups = {g["name"] for g in db.list_client_groups()}
    if group_name not in groups:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Group '{group_name}' does not exist."}
        )
    db.set_setting("admin_printer_group", group_name)
    return {
        "success": True,
        "admin_printer_group": group_name,
        "message": f"Admin Printer assigned strictly to group '{group_name}'"
    }


class UpdateClientKeyRequest(BaseModel):
    client_api_key: str


class CreateClientKeyRequest(BaseModel):
    name: str
    key: Optional[str] = None


@internal_api_router.get("/client-keys")
async def internal_list_client_keys():
    """List all dedicated client terminal keys and their live connection status."""
    keys = db.list_client_api_keys()
    connected_keys = relay_manager.get_connected_api_keys()
    result = []
    for k in keys:
        key_str = k["key"]
        conn_info = connected_keys.get(key_str)
        result.append({
            "key": key_str,
            "name": k["name"],
            "group_name": k.get("group_name"),
            "created_at": k["created_at"],
            "is_connected": conn_info is not None,
            "client": conn_info,
        })
    return {"success": True, "client_keys": result}


@internal_api_router.post("/client-keys")
async def internal_create_client_key(payload: CreateClientKeyRequest):
    """Create a new authorized Client API Key for store PC terminals."""
    name = (payload.name or "").strip() or "Store Terminal"
    key = (payload.key or "").strip()
    if not key:
        import secrets
        key = "sk_client_" + secrets.token_hex(12)
    created = db.insert_client_api_key(key, name)
    return {"success": True, "client_key": created}


@internal_api_router.delete("/client-keys/{key}")
async def internal_delete_client_key(key: str):
    """Delete a Client API Key and disconnect any active terminal using it."""
    clean_key = (key or "").strip()
    if not clean_key:
        return JSONResponse(status_code=400, content={"success": False, "message": "Key is required"})
    await relay_manager.disconnect_by_api_key(clean_key)
    deleted = db.delete_client_api_key(clean_key)
    return {"success": deleted, "message": f"Client key '{clean_key}' deleted"}


@internal_api_router.post("/settings/client-key")
async def internal_set_client_key(payload: UpdateClientKeyRequest):
    """Set the API key authorized for store client connection (backward compatibility)."""
    key = payload.client_api_key.strip()
    db.set_setting("client_api_key", key)
    return {"success": True, "client_api_key": key, "message": "Client API key authorization updated"}


@internal_api_router.get("/relay/status")
async def internal_relay_status():
    """Live status probe of Cloud Relay WebSocket client terminals & roaming presence."""
    client_count = relay_manager.get_client_count()
    clients = relay_manager.get_connected_clients_summary()
    active_client = relay_manager.get_active_printing_client()
    is_printer_online = active_client is not None
    return {
        "connected": client_count > 0,
        "client_count": client_count,
        "clients": clients,
        "active_client": active_client,
        "is_printer_online": is_printer_online,
        "is_printing": relay_manager.is_printing(),
        "active_job_id": relay_manager.get_active_job_id(),
        # Backward compatibility with existing UI
        "client": active_client or (clients[0] if clients else None),
    }
