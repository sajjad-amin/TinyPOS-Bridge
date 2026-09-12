import asyncio
import io
import uuid
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from PIL import Image

import printer_ble
from server.auth import verify_api_key, verify_media_access
import server.db as db
from server.services.print_service import (
    execute_print_job,
    feed_paper_cmd,
    get_system_printer_status,
    schedule_job_cleanup,
)

public_api_router = APIRouter(prefix="/api")


class PrintTextRequest(BaseModel):
    text: str = Field(..., description="Receipt text to print")
    font_size: int = Field(22, ge=10, le=60, description="Font size in points")
    strength: int = Field(7, ge=1, le=7, description="Print strength/darkness 1-7")
    immediate: bool = Field(True, description="When true, directly prints in background without requiring /confirm")
    keep_job: Optional[bool] = Field(None, description="When true, permanently preserves job in database. Default false (temporary, purged after 5 minutes)")
    keepjob: Optional[bool] = Field(None, description="Alias for keep_job")

    def should_keep(self) -> bool:
        if self.keep_job is not None:
            return bool(self.keep_job)
        if self.keepjob is not None:
            return bool(self.keepjob)
        return False


class PrintQRRequest(BaseModel):
    content: Optional[str] = Field(None, description="QR code data payload (URL, text, WiFi, UPI, etc.)")
    text: Optional[str] = Field(None, description="Alias for content")
    header: Optional[str] = Field(None, description="Optional text displayed above the QR code")
    footer: Optional[str] = Field(None, description="Optional text displayed below the QR code")
    qr_size: int = Field(280, ge=64, le=384, description="QR code pixel size (default 280, max 368)")
    size: Optional[int] = Field(None, description="Alias for qr_size")
    strength: int = Field(7, ge=1, le=7, description="Print strength/darkness 1-7")
    immediate: bool = Field(True, description="When true, directly prints in background without requiring /confirm")
    keep_job: Optional[bool] = Field(None, description="When true, permanently preserves job in database. Default false (temporary, purged after 5 minutes)")
    keepjob: Optional[bool] = Field(None, description="Alias for keep_job")

    def get_content(self) -> str:
        return (self.content or self.text or "").strip()

    def get_size(self) -> int:
        if self.size is not None and 64 <= self.size <= 384:
            return self.size
        return self.qr_size

    def should_keep(self) -> bool:
        if self.keep_job is not None:
            return bool(self.keep_job)
        if self.keepjob is not None:
            return bool(self.keepjob)
        return False


class GenerateQRRequest(BaseModel):
    text: Optional[str] = Field(None, description="Text or URL content to encode in QR")
    content: Optional[str] = Field(None, description="Alias for text")
    header: Optional[str] = Field(None, description="Optional text header above QR")
    footer: Optional[str] = Field(None, description="Optional text footer below QR")
    size: Optional[int] = Field(260, ge=64, le=384, description="QR code size in pixels (default 260)")
    qr_size: Optional[int] = Field(None, description="Alias for size")
    strength: int = Field(7, ge=1, le=7, description="Print strength/contrast (default 7)")

    def get_text(self) -> str:
        return (self.text or self.content or "").strip()

    def get_pixel_size(self) -> int:
        if self.qr_size is not None and 64 <= self.qr_size <= 384:
            return self.qr_size
        if self.size is not None and 64 <= self.size <= 384:
            return self.size
        return 260


@public_api_router.get("/status")
async def check_status(api_key: str = Depends(verify_api_key)):
    """Probe thermal printer online/offline status for the authorized API group."""
    key_data = db.get_api_key(api_key)
    target_group = key_data.get("group_name") if key_data else None
    return await get_system_printer_status(group=target_group)


@public_api_router.post("/print/raw")
async def print_raw_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    strength: int = Form(7, description="Print strength 1-7"),
    scale: float = Form(1.0, description="Scale zoom multiplier (e.g. 1.25 for 80mm receipts, 1.5 for A4)"),
    autocrop: bool = Form(True, description="Auto-crop whitespace margins before resizing"),
    mode: str = Form("text", description="Rendering mode: 'text' (default) or 'photo' (Floyd-Steinberg error-diffusion dithering)"),
    dither: Optional[bool] = Form(None, description="Optional boolean flag to enable photo dithering mode (equivalent to mode=photo)"),
    immediate: bool = Form(True, description="Directly execute and print immediately (default: true)"),
    keep_job: Optional[bool] = Form(None, description="When true, permanently preserves job in database. Default false (temporary, purged after 5 minutes)"),
    keepjob: Optional[bool] = Form(None, description="Alias for keep_job"),
    x_api_key: str = Depends(verify_api_key),
):
    """
    Upload and print an invoice PDF or image.
    If immediate=true (default), queues and immediately transmits the job to the printer.
    If keep_job=false (default), the job is temporary and removed from SQLite after 5 minutes.
    Use mode='photo' or dither=true for photographic dithering with smooth shades.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    use_photo_mode = (str(mode).strip().lower() == "photo") or bool(dither)
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")

    job_id = str(uuid.uuid4())
    job_status = "printing" if immediate else "pending"
    preserve = bool(keep_job) or bool(keepjob)

    db.insert_job(
        job_id=job_id,
        job_type=job_type,
        status=job_status,
        api_key=x_api_key,
        image=bitmap,
        strength=max(1, min(7, strength)),
        scale=scale,
        autocrop=autocrop,
        keep_job=preserve,
    )

    if immediate:
        background_tasks.add_task(execute_print_job, job_id)
    elif not preserve:
        # Schedule cleanup in case pending job is never confirmed
        asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))

    return {
        "job_id": job_id,
        "status": job_status,
        "mode": active_mode,
        "immediate": immediate,
        "keep_job": preserve,
        "width": bitmap.width,
        "height": bitmap.height,
        "scale": scale,
        "autocrop": autocrop,
        "preview_url": f"/api/print/preview/{job_id}",
        "confirm_url": f"/api/print/confirm/{job_id}" if not immediate else None,
        "message": (
            "Job dispatched to printer immediately." if immediate else "Job queued. Call /api/print/confirm/{job_id} to print."
        ) + (" (Preserved in database)" if preserve else " (Temporary: auto-removed in 5 minutes)"),
    }


@public_api_router.post("/print/photo")
async def print_photo_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    preset: str = Form("portrait", description="Quality preset: portrait, sharp, balanced, high_contrast, halftone"),
    dither_algo: Optional[str] = Form(None, description="Dithering algorithm: floyd, atkinson, bayer"),
    sharpness: Optional[float] = Form(None, description="Unsharp mask edge sharpening level (0.0 to 3.0)"),
    contrast: Optional[float] = Form(None, description="Contrast multiplier (e.g. 1.15)"),
    brightness: Optional[float] = Form(None, description="Brightness multiplier (e.g. 1.08)"),
    strength: int = Form(7, description="Print strength 1-7"),
    scale: float = Form(1.0, description="Scale multiplier (e.g. 1.0 = 384px fit)"),
    autocrop: bool = Form(True, description="Auto-crop whitespace borders"),
    immediate: bool = Form(True, description="Directly execute and print immediately (default: true)"),
    keep_job: Optional[bool] = Form(None, description="When true, permanently preserves job in database. Default false (temporary, purged after 5 minutes)"),
    keepjob: Optional[bool] = Form(None, description="Alias for keep_job"),
    x_api_key: str = Depends(verify_api_key),
):
    """
    High-fidelity photo and artwork printing with advanced halftoning and quality controls.
    Supports Floyd-Steinberg error diffusion, Atkinson, and Bayer dot-matrix dithering,
    with unsharp mask edge enhancement and tone curve presets (portrait, sharp, balanced, high_contrast, halftone).
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded photo is empty.")

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
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process photo: {str(e)}")

    job_id = str(uuid.uuid4())
    job_status = "printing" if immediate else "pending"
    preserve = bool(keep_job) or bool(keepjob)

    db.insert_job(
        job_id=job_id,
        job_type="photo",
        status=job_status,
        api_key=x_api_key,
        image=bitmap,
        strength=max(1, min(7, strength)),
        scale=scale,
        autocrop=autocrop,
        keep_job=preserve,
    )

    if immediate:
        background_tasks.add_task(execute_print_job, job_id)
    elif not preserve:
        asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))

    return {
        "job_id": job_id,
        "status": job_status,
        "preset": preset,
        "dither_algo": dither_algo or "preset_default",
        "immediate": immediate,
        "keep_job": preserve,
        "width": bitmap.width,
        "height": bitmap.height,
        "preview_url": f"/api/print/preview/{job_id}",
        "confirm_url": f"/api/print/confirm/{job_id}" if not immediate else None,
        "message": (
            "Photo dispatched to printer immediately." if immediate else "Photo queued. Call /api/print/confirm/{job_id} to print."
        ) + (" (Preserved in database)" if preserve else " (Temporary: auto-removed in 5 minutes)"),
    }


@public_api_router.post("/print/text")
async def print_text_job(
    payload: PrintTextRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Depends(verify_api_key),
):
    """
    Queue formatted text for printing.
    If immediate=true (default), queues and immediately transmits the job to the printer.
    If keep_job=false (default), the job is temporary and removed from SQLite after 5 minutes.
    """
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text field cannot be empty.")

    try:
        bitmap = printer_ble.render_text_to_bitmap(
            payload.text,
            font_size=payload.font_size,
            strength=payload.strength,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render text: {str(e)}")

    job_id = str(uuid.uuid4())
    job_status = "printing" if payload.immediate else "pending"
    preserve = payload.should_keep()

    db.insert_job(
        job_id=job_id,
        job_type="text",
        status=job_status,
        api_key=x_api_key,
        image=bitmap,
        strength=payload.strength,
        scale=1.0,
        autocrop=True,
        keep_job=preserve,
    )

    if payload.immediate:
        background_tasks.add_task(execute_print_job, job_id)
    elif not preserve:
        # Schedule cleanup in case pending job is never confirmed
        asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))

    return {
        "job_id": job_id,
        "status": job_status,
        "immediate": payload.immediate,
        "keep_job": preserve,
        "width": bitmap.width,
        "height": bitmap.height,
        "preview_url": f"/api/print/preview/{job_id}",
        "confirm_url": f"/api/print/confirm/{job_id}" if not payload.immediate else None,
        "message": (
            "Job dispatched to printer immediately." if payload.immediate else "Job queued. Call /api/print/confirm/{job_id} to print."
        ) + (" (Preserved in database)" if preserve else " (Temporary: auto-removed in 5 minutes)"),
    }


@public_api_router.get("/qr/generate")
async def generate_qr_image_get(
    text: Optional[str] = None,
    content: Optional[str] = None,
    header: Optional[str] = None,
    footer: Optional[str] = None,
    size: int = 260,
    qr_size: Optional[int] = None,
    strength: int = 7,
    _: str = Depends(verify_media_access),
):
    """
    Generates a 384px-wide thermal-optimized QR code PNG image from query text.
    Protected endpoint: Requires API Key via 'X-API-Key' header, '?api_key=' parameter, or admin session.
    Can be embedded in HTML <img> tags or downloaded.
    """
    qr_text = (text or content or "").strip()
    if not qr_text:
        raise HTTPException(status_code=400, detail="Missing required parameter: provide 'text' or 'content' in query.")

    actual_size = qr_size if qr_size is not None else size
    actual_size = max(64, min(384, actual_size))

    try:
        bitmap = printer_ble.render_qr_to_bitmap(
            content=qr_text,
            header_text=header,
            footer_text=footer,
            qr_size=actual_size,
            strength=strength,
        )
        buf = io.BytesIO()
        bitmap.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render QR code: {str(e)}")


@public_api_router.post("/qr/generate")
async def generate_qr_image_post(
    payload: GenerateQRRequest,
    _: str = Depends(verify_media_access),
):
    """
    Generates a 384px-wide thermal-optimized QR code PNG image from JSON payload.
    Protected endpoint: Requires API Key via 'X-API-Key' header, '?api_key=' parameter, or admin session.
    Returns binary PNG image stream.
    """
    qr_text = payload.get_text()
    if not qr_text:
        raise HTTPException(status_code=400, detail="Missing required field: provide 'text' or 'content'.")

    try:
        bitmap = printer_ble.render_qr_to_bitmap(
            content=qr_text,
            header_text=payload.header,
            footer_text=payload.footer,
            qr_size=payload.get_pixel_size(),
            strength=payload.strength,
        )
        buf = io.BytesIO()
        bitmap.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render QR code: {str(e)}")


@public_api_router.post("/print/qr")
async def print_qr_job(
    payload: PrintQRRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Depends(verify_api_key),
):
    """
    Queue a high-contrast QR code for printing.
    If immediate=true (default), queues and immediately transmits the job to the printer.
    """
    qr_text = payload.get_content()
    if not qr_text:
        raise HTTPException(status_code=400, detail="Content or text field cannot be empty.")

    try:
        bitmap = printer_ble.render_qr_to_bitmap(
            content=qr_text,
            header_text=payload.header,
            footer_text=payload.footer,
            qr_size=payload.get_size(),
            strength=payload.strength,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render QR code: {str(e)}")

    job_id = str(uuid.uuid4())
    job_status = "printing" if payload.immediate else "pending"
    preserve = payload.should_keep()

    db.insert_job(
        job_id=job_id,
        job_type="qr",
        status=job_status,
        api_key=x_api_key,
        image=bitmap,
        strength=payload.strength,
        scale=1.0,
        autocrop=False,
        keep_job=preserve,
    )

    if payload.immediate:
        background_tasks.add_task(execute_print_job, job_id)
    elif not preserve:
        asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))

    return {
        "job_id": job_id,
        "status": job_status,
        "immediate": payload.immediate,
        "keep_job": preserve,
        "width": bitmap.width,
        "height": bitmap.height,
        "preview_url": f"/api/print/preview/{job_id}",
        "confirm_url": f"/api/print/confirm/{job_id}" if not payload.immediate else None,
        "message": (
            "Job dispatched to printer immediately." if payload.immediate else "Job queued. Call /api/print/confirm/{job_id} to print."
        ) + (" (Preserved in database)" if preserve else " (Temporary: auto-removed in 5 minutes)"),
    }


@public_api_router.post("/print/confirm/{job_id}")
async def confirm_print_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
):
    """Trigger background transmission of a pending queued job to printer."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found.")

    if job["status"] == "printing":
        return {"job_id": job_id, "status": "printing", "message": "Job is already being printed."}
    if job["status"] == "completed":
        return {"job_id": job_id, "status": "completed", "message": "Job was already completed."}

    db.update_job_status(job_id, "printing")
    background_tasks.add_task(execute_print_job, job_id)

    return {
        "job_id": job_id,
        "status": "printing",
        "message": "Print job confirmed and queued for transmission.",
    }


@public_api_router.post("/print/feed")
@public_api_router.post("/printer/feed")
async def feed_printer_paper(api_key: str = Depends(verify_api_key)):
    """
    Advance/feed paper on the thermal printer associated with the authorized API key.
    Sends standard ESC/POS paper feed byte sequence to the printer.
    """
    key_data = db.get_api_key(api_key)
    target_group = key_data.get("group_name") if key_data else None
    success, msg = await feed_paper_cmd(group=target_group)
    if not success:
        return JSONResponse(status_code=500, content={"success": False, "message": msg})
    return {"success": True, "message": msg}


@public_api_router.post("/print/stop")
async def stop_active_print(_: str = Depends(verify_api_key)):
    """Stop the currently transmitting print job on the thermal printer."""
    active_id = printer_ble.get_active_job_id()
    stopped, msg = printer_ble.stop_printing()
    if active_id:
        db.update_job_status(active_id, "cancelled", error="Stopped via API /api/print/stop")
    if not stopped:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return {"success": True, "message": msg, "job_id": active_id}


@public_api_router.delete("/print/cancel/{job_id}")
@public_api_router.post("/print/cancel/{job_id}")
async def cancel_print_job(
    job_id: str,
    _: str = Depends(verify_api_key),
):
    """Cancel a pending job or stop an actively transmitting print job."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found.")

    if job["status"] == "printing":
        active_id = printer_ble.get_active_job_id()
        if active_id == job_id or not active_id:
            printer_ble.stop_printing()
        db.update_job_status(job_id, "cancelled", error="Cancelled via API while printing")
        return {"job_id": job_id, "status": "cancelled", "message": "Active print job stopped."}

    if job["status"] == "completed":
        return JSONResponse(
            status_code=400,
            content={"job_id": job_id, "status": "completed", "message": "Job already completed."},
        )

    db.update_job_status(job_id, "cancelled", error="Cancelled before print")
    if not job.get("keep_job"):
        db.delete_job(job_id)
    return {"job_id": job_id, "status": "cancelled", "message": "Job cancelled."}


@public_api_router.get("/print/preview/{job_id}")
async def get_job_preview(
    job_id: str,
    _: str = Depends(verify_media_access),
):
    """
    Return PNG preview of queued job from SQLite.
    Protected endpoint: Requires API Key via 'X-API-Key' header, '?api_key=' parameter, or admin session.
    """
    preview_bytes = db.get_job_preview_bytes(job_id)
    if not preview_bytes:
        raise HTTPException(status_code=404, detail="Preview not available.")

    return Response(content=preview_bytes, media_type="image/png")


@public_api_router.get("/queue")
async def get_queue_status(
    page: int = 1,
    per_page: int = 50,
    _: str = Depends(verify_api_key),
):
    """List paginated queue status."""
    return db.get_jobs_paginated(page=page, per_page=per_page)
