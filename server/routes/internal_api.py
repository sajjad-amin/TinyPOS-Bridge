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

internal_api_router = APIRouter(prefix="/api/internal", dependencies=[Depends(require_login)])


@internal_api_router.get("/status")
async def internal_status():
    """Probe BLE thermal printer online/offline status."""
    return await printer_ble.get_printer_status()


@internal_api_router.post("/feed")
async def internal_feed():
    """Trigger manual paper feed command."""
    try:
        device = await printer_ble.scan_for_printer(timeout=4.0)
        if not device:
            return {"success": False, "error": "Printer not found"}

        from bleak import BleakClient
        async with BleakClient(device) as client:
            tx_char = "0000ae01-0000-1000-8000-00805f9b34fb"
            await client.write_gatt_char(tx_char, printer_ble.CMD_FEED_PAPER, response=False)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
        success, msg = await printer_ble.send_bitmap_to_printer(bitmap, strength=payload.strength, job_id=job_id)
        final_status = "completed" if success else ("cancelled" if "stop" in msg.lower() or "cancel" in msg.lower() else "failed")
        db.update_job_status(job_id, final_status, error=None if success else msg)
        return {"success": success, "message": msg, "job_id": job_id, "status": final_status}
    except Exception as e:
        return {"success": False, "message": str(e)}


@internal_api_router.post("/stop")
async def internal_stop_print():
    """Stop the currently transmitting print job immediately."""
    active_id = printer_ble.get_active_job_id()
    stopped, msg = printer_ble.stop_printing()
    if active_id:
        db.update_job_status(active_id, "cancelled", error="Stopped by user from test console")
    return {"success": stopped, "message": msg, "job_id": active_id}


@internal_api_router.post("/jobs/{job_id}/stop")
async def internal_stop_job(job_id: str):
    """Stop a specific print job if it is currently printing or pending."""
    active_id = printer_ble.get_active_job_id()
    if active_id == job_id or (printer_ble.is_printing() and not active_id):
        stopped, msg = printer_ble.stop_printing()
        db.update_job_status(job_id, "cancelled", error="Stopped by user from test console")
        return {"success": True, "message": "Print job stopped successfully"}

    job = db.get_job(job_id)
    if job and job["status"] == "pending":
        db.update_job_status(job_id, "cancelled", error="Cancelled by user before printing")
        return {"success": True, "message": "Pending print job cancelled"}
    elif job and job["status"] == "printing":
        printer_ble.stop_printing()
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
        payload.content = "https://pos.sayem.com"
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
        success, msg = await printer_ble.send_bitmap_to_printer(bitmap, strength=payload.strength, job_id=job_id)
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
        success, msg = await printer_ble.send_bitmap_to_printer(bitmap, strength=strength, job_id=job_id)
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
