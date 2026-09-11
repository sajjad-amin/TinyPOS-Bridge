import asyncio
import logging
from typing import Optional, Tuple
from PIL import Image

import printer_ble
import server.db as db
from server.services.relay_manager import relay_manager

logger = logging.getLogger("tinypos.service")


async def schedule_job_cleanup(job_id: str, delay_seconds: int = 300):
    """
    Purges a temporary print job and its stored raster from SQLite
    after delay_seconds (default 300s / 5 minutes).
    """
    try:
        await asyncio.sleep(delay_seconds)
        job = db.get_job(job_id)
        if job and not job.get("keep_job") and job.get("status") != "printing":
            db.delete_job(job_id)
            logger.info(f"Temporary job {job_id} successfully purged from database after {delay_seconds}s.")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error purging temporary job {job_id}: {e}")


async def dispatch_bitmap_print(
    img: Image.Image,
    strength: int = 7,
    job_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Unified print dispatcher. Routes print stream either to local BLE hardware
    or to the remote store client over Cloud Relay WebSocket depending on system mode.
    """
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        logger.info(f"Dispatching print job {job_id} via Cloud Relay WebSocket...")
        return await relay_manager.dispatch_job_to_client(job_id=job_id or "adhoc_job", img=img, strength=strength)
    else:
        logger.info(f"Dispatching print job {job_id} via local Bluetooth LE...")
        return await printer_ble.send_bitmap_to_printer(img, strength=strength, job_id=job_id)


async def stop_print_job(job_id: Optional[str] = None) -> Tuple[bool, str]:
    """Stop active print transmission across either Bluetooth or Cloud Relay mode."""
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        return await relay_manager.stop_active_job()
    else:
        return printer_ble.stop_printing()


async def feed_paper_cmd() -> Tuple[bool, str]:
    """Trigger paper feed across either Bluetooth or Cloud Relay mode."""
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        return await relay_manager.feed_paper()
    else:
        try:
            device = await printer_ble.scan_for_printer(timeout=4.0)
            if not device:
                return False, "Printer not found"
            from bleak import BleakClient
            async with BleakClient(device) as client:
                tx_char = "0000ae01-0000-1000-8000-00805f9b34fb"
                await client.write_gatt_char(tx_char, printer_ble.CMD_FEED_PAPER, response=False)
            return True, "Paper fed successfully"
        except Exception as e:
            return False, str(e)


async def get_system_printer_status() -> dict:
    """
    Returns system printer health and connectivity.
    If Cloud Relay mode is active:
      - Automatically detects which terminal has the portable printer in Bluetooth range.
      - If printer is off, accurately reports terminals connected but printer off.
    If Bluetooth mode is active:
      - Performs local BLE discovery on host machine.
    """
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        client_count = relay_manager.get_client_count()
        if client_count == 0:
            return {
                "status": "offline",
                "mode": "relay",
                "is_printing": False,
                "printer_name": "Cloud Relay (No Terminals Connected)",
                "address": "Disconnected",
                "active_job_id": None,
                "client_count": 0,
                "message": "Cloud Relay mode is active, but no store terminals are currently connected.",
            }

        active = relay_manager.get_active_printing_client()
        if active:
            client_name = active.get("client_name", "Terminal")
            client_ip = active.get("ip", "unknown")
            printer_name = active.get("printer_name") or f"X6 Thermal ({client_name})"
            return {
                "status": "online",
                "mode": "relay",
                "is_printing": relay_manager.is_printing(),
                "printer_name": printer_name,
                "address": f"Relayed via {client_name} ({client_ip})",
                "active_job_id": relay_manager.get_active_job_id(),
                "client_count": client_count,
                "active_client": active,
                "message": f"Portable printer is online at '{client_name}' (RSSI: {active.get('rssi')} dBm)",
            }
        else:
            return {
                "status": "offline",
                "mode": "relay",
                "is_printing": False,
                "printer_name": f"{client_count} Terminal(s) Connected (Printer Off)",
                "address": "Printer out of Bluetooth range",
                "active_job_id": None,
                "client_count": client_count,
                "message": f"{client_count} terminal(s) connected to relay, but printer is turned off or out of Bluetooth range.",
            }
    else:
        ble_status = await printer_ble.get_printer_status()
        ble_status["mode"] = "bluetooth"
        return ble_status


async def execute_print_job(job_id: str):
    """
    Background worker task to stream a queued job's raster.
    Automatically respects active mode (Bluetooth vs Cloud Relay).
    """
    job = db.get_job(job_id)
    if not job or job["status"] != "printing":
        return

    img = db.get_job_image(job_id)
    if not img:
        db.update_job_status(job_id, "failed", error="No bitmap image found in job.")
        fresh_job = db.get_job(job_id)
        if fresh_job and not fresh_job.get("keep_job"):
            asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))
        return

    try:
        strength = job.get("strength", 7)
        success, message = await dispatch_bitmap_print(img, strength=strength, job_id=job_id)
        if success:
            db.update_job_status(job_id, "completed")
            logger.info(f"Job {job_id} printed successfully.")
        else:
            final_status = "cancelled" if ("stop" in message.lower() or "cancel" in message.lower()) else "failed"
            db.update_job_status(job_id, final_status, error=message)
            logger.warning(f"Job {job_id} {final_status}: {message}")
    except Exception as e:
        db.update_job_status(job_id, "failed", error=str(e))
        logger.error(f"Exception printing job {job_id}: {e}")
    finally:
        # If this is a temporary job (keep_job is False), purge it after 5 minutes
        fresh_job = db.get_job(job_id)
        if fresh_job and not fresh_job.get("keep_job"):
            asyncio.create_task(schedule_job_cleanup(job_id, delay_seconds=300))
