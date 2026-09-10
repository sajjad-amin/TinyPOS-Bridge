"""
TinyPOS BLE Driver & Hardware Transport
Provides BLE discovery, connection management, cancellation state, and packet streaming.
All rendering, font resolution, text layout, and protocol serialization are provided
by the modular 'engine' package.
"""

import asyncio
import logging
from typing import Optional, Tuple
from PIL import Image
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# Import and re-export all engine modules for 100% backward-compatibility
from engine import (
    PRINT_WIDTH,
    KNOWN_SERVICE_UUIDS,
    KNOWN_TX_CHAR_UUIDS,
    KNOWN_NAMES,
    HEADER,
    FOOTER,
    CRC8_TABLE,
    CMD_GET_DEV_STATE,
    CMD_SET_QUALITY_200_DPI,
    CMD_SET_SPEED,
    CMD_APPLY_ENERGY,
    CMD_LATTICE_START,
    CMD_LATTICE_END,
    CMD_FEED_PAPER,
    SCRIPT_FONT_FILE,
    crc8,
    make_packet,
    get_strength_params,
    encode_image_to_lsb_rows,
    contains_bangla,
    get_char_script,
    detect_script,
    get_bundled_fonts_dir,
    load_multi_fonts,
    load_cross_platform_font,
    segment_line,
    tokenize_segments,
    wrap_segments,
    autocrop_whitespace,
    convert_image_to_bitmap,
    render_pdf_to_bitmap,
    render_text_to_bitmap,
    render_qr_to_bitmap,
    render_photo_to_bitmap,
)

logger = logging.getLogger("tinypos.ble")


async def scan_for_printer(timeout: float = 5.0) -> Optional[BLEDevice]:
    """
    Scans for the Tiny Print / Bainiu / X6 BLE thermal printer.
    """
    logger.info("Scanning for BLE printer...")
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)

    for device, adv in discovered.values():
        name = (device.name or adv.local_name or "").lower()
        services = [str(u).lower() for u in (adv.service_uuids or [])]

        if any(any(s in u for s in ["ae30", "af30", "ff00"]) for u in services):
            logger.info(f"Found printer by Service UUID: {device.name} ({device.address})")
            return device

        if any(known in name for known in KNOWN_NAMES):
            logger.info(f"Found printer by Name: {device.name} ({device.address})")
            return device

    return None


_is_printing: bool = False
_cancel_requested: bool = False
_active_job_id: Optional[str] = None
_active_device_address: Optional[str] = None


def is_printing() -> bool:
    """Return True if a BLE print transmission is currently in progress."""
    return _is_printing


def get_active_job_id() -> Optional[str]:
    """Return the ID of the job currently being transmitted, if any."""
    return _active_job_id


def stop_printing() -> Tuple[bool, str]:
    """
    Signal the active print job to stop transmitting immediately.
    Returns (True, message) if a stop was requested, or (False, message) if no job was running.
    """
    global _cancel_requested
    if not _is_printing:
        return False, "No active print job is running."
    _cancel_requested = True
    logger.warning("Stop print command issued. Aborting active print stream.")
    return True, "Stop signal transmitted to active print job."


async def get_printer_status() -> dict:
    """
    Checks if the printer is online and discoverable over BLE.
    Returns online immediately if a job is currently transmitting.
    """
    if _is_printing:
        return {
            "status": "online",
            "is_printing": True,
            "printer_name": "X6 Thermal Printer (Printing)",
            "address": _active_device_address or "Connected",
            "active_job_id": _active_job_id,
        }

    try:
        device = await scan_for_printer(timeout=4.0)
        if device:
            return {
                "status": "online",
                "is_printing": False,
                "printer_name": device.name or "Tiny Print Thermal Printer",
                "address": device.address,
                "active_job_id": None,
            }
        return {"status": "offline", "is_printing": False, "printer_name": None, "address": None, "active_job_id": None}
    except Exception as e:
        logger.error(f"Error checking printer status: {e}")
        return {"status": "offline", "is_printing": False, "error": str(e), "printer_name": None, "address": None, "active_job_id": None}


async def send_bitmap_to_printer(
    img: Image.Image,
    address: Optional[str] = None,
    strength: int = 7,
    job_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Connects to the printer via BLE and transmits the exact Bainiu packet stream
    configured for the requested strength level (1-7). Supports mid-stream cancellation.
    """
    global _is_printing, _cancel_requested, _active_job_id, _active_device_address
    if _is_printing:
        return False, "A print job is already currently in progress."

    _is_printing = True
    _cancel_requested = False
    _active_job_id = job_id
    _active_device_address = address

    try:
        device = None
        if address:
            device = await BleakScanner.find_device_by_address(address, timeout=5.0)
        if not device:
            device = await scan_for_printer(timeout=5.0)

        if not device:
            return False, "Printer not found. Make sure it is powered on, Bluetooth is enabled, and it is in pairing range."

        if _cancel_requested:
            return False, "Print job stopped by user before transmission began."

        _active_device_address = device.address
        energy_val, row_delay, threshold = get_strength_params(strength)
        rows = encode_image_to_lsb_rows(img, threshold=threshold)
        logger.info(f"Connecting to BLE printer: {device.name} ({device.address}) at Strength {strength} (Energy: {energy_val})...")

        async with BleakClient(device) as client:
            if not client.is_connected:
                return False, "Failed to establish BLE connection with printer."

            # Locate write characteristic
            tx_char = None
            for service in client.services:
                for char in service.characteristics:
                    char_uuid = str(char.uuid).lower()
                    if "ae01" in char_uuid or "ff02" in char_uuid:
                        tx_char = char
                        break
                if tx_char:
                    break

            if not tx_char:
                tx_char = "0000ae01-0000-1000-8000-00805f9b34fb"

            logger.info(f"Initiating print session on TX: {tx_char}")

            if _cancel_requested:
                return False, "Print job stopped by user before sending raster."

            # Build dynamic energy command matching Bainiu protocol: 51 78 AF 00 02 00 [LOW] [HIGH] [CRC] FF
            cmd_energy = make_packet(0xAF, bytes([energy_val & 0xFF, (energy_val >> 8) & 0xFF]))

            # 1. Initialization sequence
            await client.write_gatt_char(tx_char, CMD_GET_DEV_STATE, response=False)
            await asyncio.sleep(0.03)
            await client.write_gatt_char(tx_char, CMD_SET_QUALITY_200_DPI, response=False)
            await asyncio.sleep(0.03)
            await client.write_gatt_char(tx_char, cmd_energy, response=False)
            await asyncio.sleep(0.03)
            await client.write_gatt_char(tx_char, CMD_SET_SPEED, response=False)
            await asyncio.sleep(0.03)
            await client.write_gatt_char(tx_char, CMD_APPLY_ENERGY, response=False)
            await asyncio.sleep(0.03)
            await client.write_gatt_char(tx_char, CMD_LATTICE_START, response=False)
            await asyncio.sleep(0.03)

            # 2. Stream raster rows
            logger.info(f"Streaming {len(rows)} raster rows at {row_delay*1000:.1f}ms pacing...")
            stopped_early = False
            for idx, row in enumerate(rows):
                if _cancel_requested:
                    logger.warning(f"Print job {_active_job_id or 'unknown'} aborted by user at row {idx}/{len(rows)}.")
                    stopped_early = True
                    break
                pkt = make_packet(0xA2, row)
                await client.write_gatt_char(tx_char, pkt, response=False)
                await asyncio.sleep(row_delay)

            # 3. Finalize lattice
            await asyncio.sleep(0.05)
            await client.write_gatt_char(tx_char, CMD_LATTICE_END, response=False)
            await asyncio.sleep(0.05)

            if stopped_early:
                try:
                    await client.write_gatt_char(tx_char, CMD_GET_DEV_STATE, response=False)
                except Exception:
                    pass
                return False, "Print job stopped by user."

            await client.write_gatt_char(tx_char, CMD_FEED_PAPER, response=False)
            await asyncio.sleep(0.05)
            await client.write_gatt_char(tx_char, CMD_GET_DEV_STATE, response=False)

            logger.info("Print job successfully completed!")
            return True, "Printed successfully"
    except asyncio.CancelledError:
        logger.warning(f"Print task was cancelled asynchronously.")
        return False, "Print job cancelled."
    except Exception as e:
        logger.error(f"Error during BLE print transmission: {e}")
        return False, str(e)
    finally:
        _is_printing = False
        _cancel_requested = False
        _active_job_id = None
        _active_device_address = None
