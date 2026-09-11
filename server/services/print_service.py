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
    target_group: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Unified print dispatcher. Routes print stream either to local BLE hardware
    or to the remote store client over Cloud Relay WebSocket depending on system mode.
    If target_group is specified, routes strictly to terminals within that group.
    """
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        logger.info(f"Dispatching print job {job_id} via Cloud Relay WebSocket (Group: {target_group})...")
        return await relay_manager.dispatch_job_to_client(
            job_id=job_id or "adhoc_job",
            img=img,
            strength=strength,
            target_group=target_group,
        )
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


async def feed_paper_cmd(group: Optional[str] = None) -> Tuple[bool, str]:
    """Trigger paper feed across either Bluetooth or Cloud Relay mode."""
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        return await relay_manager.feed_paper(group=group)
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


async def get_system_printer_status(group: Optional[str] = None) -> dict:
    """
    Returns system printer health and connectivity.
    If group is specified, scopes status strictly to terminals within that group.
    If Cloud Relay mode is active:
      - Automatically detects which terminal in group has the portable printer in Bluetooth range.
      - If printer is off, accurately reports terminals connected but printer off.
    If Bluetooth mode is active:
      - Performs local BLE discovery on host machine.
    """
    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay":
        client_count = relay_manager.get_client_count(group=group)
        group_label = f" in group '{group}'" if group else ""
        if client_count == 0:
            return {
                "status": "offline",
                "mode": "relay",
                "is_printing": False,
                "printer_name": f"Cloud Relay (No Terminals Connected{group_label})",
                "address": "Disconnected",
                "active_job_id": None,
                "client_count": 0,
                "group": group,
                "message": f"Cloud Relay mode is active, but no store terminals{group_label} are currently connected.",
            }

        active = relay_manager.get_active_printing_client(group=group)
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
                "group": group,
                "active_client": active,
                "message": f"Portable printer is online at '{client_name}' (RSSI: {active.get('rssi')} dBm)",
            }
        else:
            return {
                "status": "offline",
                "mode": "relay",
                "is_printing": False,
                "printer_name": f"{client_count} Terminal(s) Connected (Printer Off{group_label})",
                "address": "Printer out of Bluetooth range",
                "active_job_id": None,
                "client_count": client_count,
                "group": group,
                "message": f"{client_count} terminal(s){group_label} connected to relay, but printer is turned off or out of Bluetooth range.",
            }
    else:
        ble_status = await printer_ble.get_printer_status()
        ble_status["mode"] = "bluetooth"
        return ble_status


async def execute_print_job(job_id: str):
    """
    Background worker task to stream a queued job's raster.
    Automatically respects active mode (Bluetooth vs Cloud Relay) and scopes to API key's group.
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

    # Resolve target group from API key or admin printer setting
    target_group = None
    job_api_key = job.get("api_key")
    if job_api_key and job_api_key not in ("web_ui", "test_page"):
        key_data = db.get_api_key(job_api_key)
        if key_data:
            target_group = key_data.get("group_name")
    elif job_api_key in ("web_ui", "test_page"):
        target_group = db.get_setting("admin_printer_group")

    mode = db.get_setting("bridge_mode", "bluetooth")
    if mode == "relay" and job_api_key in ("web_ui", "test_page") and not target_group:
        db.update_job_status(job_id, "failed", error="Admin Printer group is not configured in Settings.")
        return

    try:
        strength = job.get("strength", 7)
        success, message = await dispatch_bitmap_print(
            img,
            strength=strength,
            job_id=job_id,
            target_group=target_group,
        )
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
