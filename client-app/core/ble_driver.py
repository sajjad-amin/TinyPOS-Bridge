"""
TinyPOS Client Bluetooth LE Driver
Handles scanning, presence detection (RSSI), connection, and direct ESC/POS packet streaming
for Bainiu / Tiny Print / X6 thermal printers using Bleak.
"""

import asyncio
import logging
import time
from typing import List, Optional, Tuple
from PIL import Image
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

logger = logging.getLogger("tinypos.client.ble")

PRINT_WIDTH: int = 384

KNOWN_SERVICE_UUIDS: List[str] = [
    "0000ae30-0000-1000-8000-00805f9b34fb",
    "0000af30-0000-1000-8000-00805f9b34fb",
    "0000ff00-0000-1000-8000-00805f9b34fb",
    "49535343-fe7d-4ae5-8fa9-9fafd205e455",
]

KNOWN_TX_CHAR_UUIDS: List[str] = [
    "0000ae01-0000-1000-8000-00805f9b34fb",
    "0000ff02-0000-1000-8000-00805f9b34fb",
    "49535343-8841-43f4-a8d4-ecbe34729bb3",
]

KNOWN_NAMES: List[str] = [
    "x6", "tiny print", "tinyprint", "iprint", "pocket printer",
    "gb01", "x5", "x7", "x2", "x1", "x8", "sc03", "rt034", "mx0", "c9", "c15",
]

HEADER: bytes = b"\x51\x78"
FOOTER: bytes = b"\xff"

CRC8_TABLE: List[int] = [
    0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15, 0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
    0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65, 0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
    0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5, 0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
    0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85, 0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
    0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2, 0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
    0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2, 0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
    0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32, 0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
    0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42, 0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
    0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C, 0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
    0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC, 0xC1, 0xC6, 0xCF, 0xC8, 0xDD, 0xDA, 0xD3, 0xD4,
    0x69, 0x6E, 0x67, 0x60, 0x75, 0x72, 0x7B, 0x7C, 0x51, 0x56, 0x5F, 0x58, 0x4D, 0x4A, 0x43, 0x44,
    0x19, 0x1E, 0x17, 0x10, 0x05, 0x02, 0x0B, 0x0C, 0x21, 0x26, 0x2F, 0x28, 0x3D, 0x3A, 0x33, 0x34,
    0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B, 0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
    0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B, 0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
    0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB, 0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
    0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB, 0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3,
]

CMD_SET_QUALITY_200_DPI: bytes = bytes.fromhex("5178A4000100329EFF")
CMD_APPLY_ENERGY: bytes = bytes.fromhex("5178BE0001000107FF")
CMD_LATTICE_START: bytes = bytes.fromhex("5178A6000B00AA551738445F5F5F44382CA1FF")
CMD_LATTICE_END: bytes = bytes.fromhex("5178A6000B00AA5517000000000000001711FF")
CMD_FEED_PAPER: bytes = bytes.fromhex("5178A10002006000F5FF")


def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc = CRC8_TABLE[crc ^ byte]
    return crc


def make_packet(cmd: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    pkt = HEADER + bytes([cmd, 0x00, length & 0xFF, (length >> 8) & 0xFF]) + payload
    chk = crc8(payload)
    return pkt + bytes([chk, 0xFF])


CMD_SET_SPEED: bytes = make_packet(0xBD, b"\x01")


def get_strength_params(strength: int = 7) -> Tuple[int, float, int]:
    strength = max(1, min(7, strength))
    params = {
        1: (8000, 0.010, 128),
        2: (11000, 0.012, 135),
        3: (14500, 0.014, 142),
        4: (18500, 0.016, 150),
        5: (22500, 0.019, 162),
        6: (26500, 0.022, 174),
        7: (30000, 0.026, 185),
    }
    return params[strength]


def encode_image_to_lsb_rows(img: Image.Image, threshold: int = 150) -> List[bytes]:
    if img.mode == "1":
        bitmap = img
    else:
        bitmap = img.convert("L")

    # Ensure 384px width
    if bitmap.width != PRINT_WIDTH:
        aspect = bitmap.height / bitmap.width
        new_h = max(1, int(PRINT_WIDTH * aspect))
        bitmap = bitmap.resize((PRINT_WIDTH, new_h), Image.Resampling.LANCZOS)
        if img.mode != "1":
            bitmap = bitmap.convert("L")

    w, h = bitmap.size
    pixels = bitmap.load()
    rows = []
    is_1bit = (bitmap.mode == "1")

    for y in range(h):
        row_bytes = bytearray(w // 8)
        for x in range(w):
            val = pixels[x, y]
            is_black = (val == 0) if is_1bit else (val < threshold)
            if is_black:
                byte_idx = x // 8
                bit_idx = x % 8
                row_bytes[byte_idx] |= (1 << bit_idx)
        rows.append(bytes(row_bytes))

    return rows


class BLEDriver:
    def __init__(self):
        self.device: Optional[BLEDevice] = None
        self.device_name: Optional[str] = None
        self.device_address: Optional[str] = None
        self.rssi: Optional[int] = None
        self.is_online: bool = False
        self._lock: Optional[asyncio.Lock] = None
        self._is_busy: bool = False
        self._missed_scans: int = 0
        self._last_success_time: float = 0.0

    def _get_lock(self) -> asyncio.Lock:
        """Lazily create or return the asyncio.Lock bound to the current running event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def scan_printer(self, timeout: float = 3.5) -> Optional[BLEDevice]:
        """Scan for nearby portable thermal printer with debouncing and post-activity grace period."""
        # 1. If currently busy printing or feeding, printer is definitely online
        if self._is_busy:
            self.is_online = True
            return self.device

        # 2. If recent successful communication occurred, keep online during cooldown
        now = time.time()
        if (now - self._last_success_time) < 25.0 and self.device:
            self.is_online = True
            return self.device

        try:
            discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
            found_device = None
            found_adv = None

            for device, adv in discovered.values():
                name = (device.name or adv.local_name or "").lower()
                services = [str(u).lower() for u in (adv.service_uuids or [])]

                # Match by known thermal printer service UUIDs
                if any(any(s in u for s in ["ae30", "af30", "ff00", "49535343"]) for u in services):
                    found_device, found_adv = device, adv
                    break

                # Match by known thermal printer advertisement names
                if any(k in name for k in KNOWN_NAMES):
                    found_device, found_adv = device, adv
                    break

                # Match by previously saved device address/UUID
                if self.device_address and device.address == self.device_address:
                    found_device, found_adv = device, adv
                    break

            if found_device:
                self.device = found_device
                self.device_name = found_device.name or (found_adv.local_name if found_adv else None) or "X6 Thermal"
                self.device_address = found_device.address
                self.rssi = found_adv.rssi if found_adv else self.rssi
                self.is_online = True
                self._missed_scans = 0
                return found_device

            # If device not found in this single scan:
            self._missed_scans += 1
            # Only declare offline after at least 4 consecutive missed scans (~18-20 seconds)
            if self._missed_scans >= 4:
                self.is_online = False
                self.rssi = None
                return None
            else:
                # Retain current online state during debouncing period
                return self.device if self.is_online else None

        except Exception as e:
            logger.debug(f"BLE scan exception: {e}")
            self._missed_scans += 1
            if self._missed_scans >= 4:
                self.is_online = False
                self.rssi = None
            return None

    def get_status(self) -> dict:
        return {
            "online": self.is_online,
            "printer_name": self.device_name or "X6 Thermal",
            "address": self.device_address,
            "rssi": self.rssi,
        }

    async def feed_paper(self) -> Tuple[bool, str]:
        """Send feed paper command to the printer."""
        if not self.device:
            await self.scan_printer(timeout=3.0)
        device = self.device
        if not device:
            return False, "Printer not found or out of Bluetooth range"

        async with self._get_lock():
            self._is_busy = True
            try:
                async with BleakClient(device, timeout=10.0) as client:
                    tx_char = None
                    for service in client.services:
                        for char in service.characteristics:
                            if "write" in char.properties or "write-without-response" in char.properties:
                                if any(k in char.uuid.lower() for k in ["ae01", "ff02", "8841"]):
                                    tx_char = char.uuid
                                    break
                        if tx_char:
                            break

                    if not tx_char:
                        tx_char = KNOWN_TX_CHAR_UUIDS[0]

                    await client.write_gatt_char(tx_char, CMD_FEED_PAPER, response=False)
                    await asyncio.sleep(0.4)
                    self._last_success_time = time.time()
                    self.is_online = True
                    self._missed_scans = 0
                    logger.info("Paper fed successfully via BLE.")
                    return True, "Paper fed successfully"
            except Exception as e:
                logger.error(f"Error feeding paper: {e}")
                return False, f"Feed error: {e}"
            finally:
                self._is_busy = False

    async def print_bitmap(self, img: Image.Image, strength: int = 7) -> Tuple[bool, str]:
        """Connect to printer and stream raster bitmap image packets."""
        device = self.device or await self.scan_printer(timeout=4.0)
        if not device:
            return False, "Printer not found or out of Bluetooth range."

        async with self._get_lock():
            self._is_busy = True
            try:
                energy_val, row_delay, threshold = get_strength_params(strength)
                rows = encode_image_to_lsb_rows(img, threshold=threshold)

                async with BleakClient(device, timeout=12.0) as client:
                    tx_char = None
                    for service in client.services:
                        for char in service.characteristics:
                            if "write" in char.properties or "write-without-response" in char.properties:
                                if any(k in char.uuid.lower() for k in ["ae01", "ff02", "8841"]):
                                    tx_char = char.uuid
                                    break
                        if tx_char:
                            break

                    if not tx_char:
                        tx_char = KNOWN_TX_CHAR_UUIDS[0]

                    # Initialize printer
                    await client.write_gatt_char(tx_char, CMD_SET_QUALITY_200_DPI, response=False)
                    await asyncio.sleep(0.04)

                    cmd_energy = make_packet(0xAF, energy_val.to_bytes(2, byteorder="little"))
                    await client.write_gatt_char(tx_char, cmd_energy, response=False)
                    await asyncio.sleep(0.04)

                    await client.write_gatt_char(tx_char, CMD_APPLY_ENERGY, response=False)
                    await asyncio.sleep(0.04)

                    await client.write_gatt_char(tx_char, CMD_SET_SPEED, response=False)
                    await asyncio.sleep(0.04)

                    await client.write_gatt_char(tx_char, CMD_LATTICE_START, response=False)
                    await asyncio.sleep(0.06)

                    # Stream rows
                    for row_data in rows:
                        row_pkt = make_packet(0xA2, row_data)
                        await client.write_gatt_char(tx_char, row_pkt, response=False)
                        await asyncio.sleep(row_delay)

                    # Finalize print
                    await client.write_gatt_char(tx_char, CMD_LATTICE_END, response=False)
                    await asyncio.sleep(0.08)

                    await client.write_gatt_char(tx_char, CMD_FEED_PAPER, response=False)
                    await asyncio.sleep(0.4)

                    self._last_success_time = time.time()
                    self.is_online = True
                    self._missed_scans = 0
                    return True, "Printed successfully."
            except Exception as e:
                logger.error(f"Error printing bitmap: {e}")
                return False, f"BLE Print Error: {e}"
            finally:
                self._is_busy = False


ble_driver = BLEDriver()
