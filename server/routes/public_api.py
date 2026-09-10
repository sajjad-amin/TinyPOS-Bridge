import asyncio
import io
import uuid
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from PIL import Image

import printer_ble
from server.auth import verify_api_key
import server.db as db
from server.services.print_service import execute_print_job, schedule_job_cleanup

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


@public_api_router.get("/status")
async def check_status(_: str = Depends(verify_api_key)):
    """Probe thermal printer online/offline status."""
    return await printer_ble.get_printer_status()


@public_api_router.post("/print/raw")
async def print_raw_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    strength: int = Form(7, description="Print strength 1-7"),
    scale: float = Form(1.0, description="Scale zoom multiplier (e.g. 1.25 for 80mm receipts, 1.5 for A4)"),
    autocrop: bool = Form(True, description="Auto-crop whitespace margins before resizing"),
    immediate: bool = Form(True, description="Directly execute and print immediately (default: true)"),
    keep_job: Optional[bool] = Form(None, description="When true, permanently preserves job in database. Default false (temporary, purged after 5 minutes)"),
    keepjob: Optional[bool] = Form(None, description="Alias for keep_job"),
    x_api_key: str = Depends(verify_api_key),
):
    """
    Upload and print an invoice PDF or image.
    If immediate=true (default), queues and immediately transmits the job to the printer.
    If keep_job=false (default), the job is temporary and removed from SQLite after 5 minutes.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".pdf") or file.content_type == "application/pdf":
            bitmap = printer_ble.render_pdf_to_bitmap(content, scale=scale, autocrop=autocrop, strength=strength)
            job_type = "pdf"
        else:
            raw_img = Image.open(io.BytesIO(content))
            bitmap = printer_ble.convert_image_to_bitmap(raw_img, scale=scale, autocrop=autocrop, strength=strength)
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
async def get_job_preview(job_id: str):
    """Return PNG preview of queued job from SQLite."""
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
