"""
Bainiu BLE thermal printer protocol packet builder, CRC8 checksum, and raster encoding.
"""

from typing import List, Tuple
from PIL import Image

from .constants import (
    PRINT_WIDTH,
    HEADER,
    FOOTER,
    CRC8_TABLE,
)


def crc8(data: bytes) -> int:
    """Calculate CRC8 checksum for Bainiu thermal printer packets."""
    crc = 0
    for byte in data:
        crc = CRC8_TABLE[crc ^ byte]
    return crc


def make_packet(cmd: int, payload: bytes = b"") -> bytes:
    """
    Format a command packet according to Bainiu 0x51 0x78 protocol:
    [0x51, 0x78, CMD, 0x00, LEN_L, LEN_H, DATA..., CRC8, 0xFF]
    """
    length = len(payload)
    pkt = HEADER + bytes([cmd, 0x00, length & 0xFF, (length >> 8) & 0xFF]) + payload
    chk = crc8(payload)
    return pkt + bytes([chk, 0xFF])


# Speed packet using make_packet
CMD_SET_SPEED: bytes = make_packet(0xBD, b"\x01")  # Speed 1 for saturated thermal transfer


def get_strength_params(strength: int = 7) -> Tuple[int, float, int]:
    """
    Maps 1-7 print strength to (energy_val, row_delay_s, black_threshold).
    Firmware expects 16-bit Little Endian integer for energy (range 2000 - 30000).
    Level 7 maximizes thermal pulse length and burn pacing for weak/aged thermal paper.
    """
    strength = max(1, min(7, strength))
    params = {
        1: (8000, 0.010, 128),
        2: (11000, 0.012, 135),
        3: (14500, 0.014, 142),
        4: (18500, 0.016, 150),
        5: (22500, 0.019, 162),
        6: (26500, 0.022, 174),
        7: (30000, 0.026, 185),  # Maximum thermal pulse & high-contrast threshold
    }
    return params[strength]


def encode_image_to_lsb_rows(img: Image.Image, threshold: int = 150) -> List[bytes]:
    """
    Encodes image pixels into Bainiu row packets with LSB-first bit order:
    1 = black (burned pin), 0 = white (blank).
    Supports both 1-bit dithered bitmaps (mode="1") and continuous grayscale (mode="L").
    """
    if img.mode == "1":
        bitmap = img
    else:
        bitmap = img.convert("L")

    if bitmap.size[0] != PRINT_WIDTH:
        from .renderer import convert_image_to_bitmap
        bitmap = convert_image_to_bitmap(bitmap)

    w, h = bitmap.size
    pixels = bitmap.load()
    rows = []
    is_1bit = (bitmap.mode == "1")

    for y in range(h):
        row_bytes = bytearray(w // 8)
        for x in range(w):
            val = pixels[x, y]
            is_black = (val == 0) if is_1bit else (val < threshold)
            if is_black:  # Black pixel -> burn pin
                byte_idx = x // 8
                bit_idx = x % 8
                row_bytes[byte_idx] |= (1 << bit_idx)  # LSB first
        rows.append(bytes(row_bytes))

    return rows
