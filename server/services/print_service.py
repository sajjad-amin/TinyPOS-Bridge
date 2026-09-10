import asyncio
import logging
import printer_ble
from server.db import delete_job, get_job, get_job_image, update_job_status

logger = logging.getLogger("tinypos.service")


async def schedule_job_cleanup(job_id: str, delay_seconds: int = 300):
    """
    Purges a temporary print job and its stored raster from SQLite
    after delay_seconds (default 300s / 5 minutes).
    """
    try:
        await asyncio.sleep(delay_seconds)
        job = get_job(job_id)
        if job and not job.get("keep_job") and job.get("status") != "printing":
            delete_job(job_id)
            logger.info(f"Temporary job {job_id} successfully purged from database after {delay_seconds}s.")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error purging temporary job {job_id}: {e}")


async def execute_print_job(job_id: str):
    """
    Background worker task to stream a queued job's raster to the BLE thermal printer.
    """
    job = get_job(job_id)
    if not job or job["status"] != "printing":
        return

    img = get_job_image(job_id)
    if not img:
        update_job_status(job_id, "failed", error="No bitmap image found in job.")
        fresh_job = get_job(job_id)
        if fresh_job and not fresh_job.get("keep_job"):
            asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))
        return

    try:
        strength = job.get("strength", 7)
        success, message = await printer_ble.send_bitmap_to_printer(img, strength=strength, job_id=job_id)
        if success:
            update_job_status(job_id, "completed")
            logger.info(f"Job {job_id} printed successfully.")
        else:
            final_status = "cancelled" if ("stop" in message.lower() or "cancel" in message.lower()) else "failed"
            update_job_status(job_id, final_status, error=message)
            logger.warning(f"Job {job_id} {final_status}: {message}")
    except Exception as e:
        update_job_status(job_id, "failed", error=str(e))
        logger.error(f"Exception printing job {job_id}: {e}")
    finally:
        # If this is a temporary job (keep_job is False), purge it after 5 minutes
        fresh_job = get_job(job_id)
        if fresh_job and not fresh_job.get("keep_job"):
            asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))

