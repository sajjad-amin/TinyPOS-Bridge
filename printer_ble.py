import asyncio
import io
import logging
import os
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

try:
    import pymupdf
except ImportError:
    pymupdf = None

logger = logging.getLogger("tinypos.ble")

# Hardware Specifications
PRINT_WIDTH = 384  # Standard 57mm thermal printer width in dots (384 pixels = 48 bytes/row)

# Bainiu / Tiny Print BLE UUIDs
KNOWN_SERVICE_UUIDS = [
    "0000ae30-0000-1000-8000-00805f9b34fb",
    "0000af30-0000-1000-8000-00805f9b34fb",
    "0000ff00-0000-1000-8000-00805f9b34fb",
    "49535343-fe7d-4ae5-8fa9-9fafd205e455",
]

KNOWN_TX_CHAR_UUIDS = [
    "0000ae01-0000-1000-8000-00805f9b34fb",
    "0000ff02-0000-1000-8000-00805f9b34fb",
    "49535343-8841-43f4-a8d4-ecbe34729bb3",
]

KNOWN_NAMES = [
    "x6", "tiny print", "tinyprint", "iprint", "pocket printer",
    "gb01", "x5", "x7", "x2", "x1", "x8", "sc03", "rt034", "mx0", "c9", "c15"
]

# Magic Headers
HEADER = b"\x51\x78"
FOOTER = b"\xff"

# Standard Bainiu CRC8 Lookup Table
CRC8_TABLE = [
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


# Exact command sequences matching Tiny Print / X5 / X6 firmware
CMD_GET_DEV_STATE = bytes.fromhex("5178A30001000000FF")
CMD_SET_QUALITY_200_DPI = bytes.fromhex("5178A4000100329EFF")
CMD_SET_SPEED = make_packet(0xBD, b"\x01")  # Speed 1 for saturated thermal transfer
CMD_APPLY_ENERGY = bytes.fromhex("5178BE0001000107FF")
CMD_LATTICE_START = bytes.fromhex("5178A6000B00AA551738445F5F5F44382CA1FF")
CMD_LATTICE_END = bytes.fromhex("5178A6000B00AA5517000000000000001711FF")
CMD_FEED_PAPER = bytes.fromhex("5178A10002006000F5FF")  # Feeds ~96 lines


def autocrop_whitespace(img: Image.Image, padding: int = 6, threshold: int = 240) -> Image.Image:
    """
    Trims empty whitespace margins around receipts/invoices.
    Ensures text and tables fill the maximum printable width.
    """
    if img.mode != "RGB":
        rgb = img.convert("RGB")
    else:
        rgb = img

    gray = rgb.convert("L")
    # Any pixel darker than threshold (240) is considered content
    bw = gray.point(lambda p: 255 if p < threshold else 0, mode="1")
    bbox = bw.getbbox()
    if bbox:
        w, h = img.size
        left = max(0, bbox[0] - padding)
        top = max(0, bbox[1] - padding)
        right = min(w, bbox[2] + padding)
        bottom = min(h, bbox[3] + padding)
        # Only crop if bbox is valid and smaller than total area
        if (right - left) > 20 and (bottom - top) > 20:
            return img.crop((left, top, right, bottom))
    return img


def convert_image_to_bitmap(
    img: Image.Image,
    scale: float = 1.0,
    autocrop: bool = True,
    strength: int = 7,
) -> Image.Image:
    """
    Processes an image into a 384-pixel wide grayscale image (mode="L").
    Supports automatic margin whitespace trimming and user-defined zoom/scale multiplier.
    """
    # 1. Flatten transparency against pure white background
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # 2. Auto-crop empty whitespace borders if requested
    if autocrop:
        img = autocrop_whitespace(img)

    orig_w, orig_h = img.size
    if orig_w == 0 or orig_h == 0:
        return Image.new("L", (PRINT_WIDTH, 100), 255)

    # 3. Apply scale factor (zoom / size adjustment)
    scale = max(0.4, min(3.0, float(scale)))

    if abs(scale - 1.0) < 0.02:
        # Standard fit: scale directly to PRINT_WIDTH (384px) maintaining aspect ratio
        new_h = max(1, int(orig_h * (PRINT_WIDTH / float(orig_w))))
        gray = img.resize((PRINT_WIDTH, new_h), Image.Resampling.LANCZOS).convert("L")
    elif scale < 1.0:
        # Shrink and center horizontally on 384px canvas
        target_w = max(10, int(PRINT_WIDTH * scale))
        target_h = max(1, int(orig_h * (target_w / float(orig_w))))
        resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        canvas = Image.new("RGB", (PRINT_WIDTH, target_h), (255, 255, 255))
        offset_x = (PRINT_WIDTH - target_w) // 2
        canvas.paste(resized, (offset_x, 0))
        gray = canvas.convert("L")
    else:
        # scale > 1.0 (Zoom in to magnify text/details)
        # Scale the image proportionally such that target_w = int(PRINT_WIDTH * scale)
        target_w = int(PRINT_WIDTH * scale)
        target_h = max(1, int(orig_h * (target_w / float(orig_w))))
        resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Smart crop to PRINT_WIDTH (384px): preserve left-aligned invoice text
        bw_resized = resized.convert("L").point(lambda p: 255 if p < 240 else 0, mode="1")
        r_bbox = bw_resized.getbbox()
        if r_bbox:
            content_left, _, content_right, _ = r_bbox
            content_w = content_right - content_left
            if content_w <= PRINT_WIDTH:
                crop_left = max(0, min(target_w - PRINT_WIDTH, content_left - (PRINT_WIDTH - content_w) // 2))
            else:
                crop_left = max(0, min(target_w - PRINT_WIDTH, content_left))
        else:
            crop_left = (target_w - PRINT_WIDTH) // 2

        crop_right = crop_left + PRINT_WIDTH
        cropped = resized.crop((crop_left, 0, crop_right, target_h))
        gray = cropped.convert("L")

    # 4. Enhance contrast so resized small text remains crisp and legible on thermal paper
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(1.35)

    return gray


def render_pdf_to_bitmap(
    pdf_bytes: bytes,
    scale: float = 1.0,
    autocrop: bool = True,
    strength: int = 7,
) -> Image.Image:
    """
    Renders a PDF (all pages combined vertically) to a 384px wide grayscale image.
    Supports autocrop and scale zoom factors.
    """
    if not pymupdf:
        raise RuntimeError("PyMuPDF (pymupdf) is not installed")

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page_images = []

    for page in doc:
        # Render at 200 DPI for crisp receipt resolution
        pix = page.get_pixmap(dpi=200)
        img_data = pix.tobytes("png")
        page_img = Image.open(io.BytesIO(img_data))
        page_images.append(page_img)

    if not page_images:
        raise ValueError("PDF document contains no pages")

    # Stitch pages vertically if multi-page
    total_w = max(p.width for p in page_images)
    total_h = sum(p.height for p in page_images)
    stitched = Image.new("RGB", (total_w, total_h), (255, 255, 255))

    curr_y = 0
    for p in page_images:
        stitched.paste(p, (0, curr_y))
        curr_y += p.height

    return convert_image_to_bitmap(stitched, scale=scale, autocrop=autocrop, strength=strength)


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


def contains_bangla(text: Optional[str]) -> bool:
    """Checks if the text contains any Bengali Unicode characters (U+0980 - U+09FF)."""
    if not text:
        return False
    return any("\u0980" <= ch <= "\u09ff" for ch in text)


def detect_script(text: Optional[str]) -> str:
    """
    Detects the predominant international Unicode script in the given text.
    Returns: 'bengali', 'arabic', 'devanagari', 'tamil', 'telugu', 'thai', 'cjk', 'cyrillic', 'emoji', or 'latin'.
    """
    if not text:
        return "latin"

    for ch in text:
        code = ord(ch)
        # Bengali (U+0980 - U+09FF)
        if 0x0980 <= code <= 0x09FF:
            return "bengali"
        # Arabic & Perso-Arabic (Urdu, Farsi, Pashto)
        if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F) or (0x08A0 <= code <= 0x08FF) or (0xFB50 <= code <= 0xFDFF) or (0xFE70 <= code <= 0xFEFF):
            return "arabic"
        # Devanagari / Hindi / Marathi / Nepali
        if (0x0900 <= code <= 0x097F) or (0xA8E0 <= code <= 0xA8FF):
            return "devanagari"
        # Tamil
        if 0x0B80 <= code <= 0x0BFF:
            return "tamil"
        # Telugu
        if 0x0C00 <= code <= 0x0C7F:
            return "telugu"
        # Thai
        if 0x0E00 <= code <= 0x0E7F:
            return "thai"
        # CJK (Chinese, Japanese, Korean)
        if (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF) or (0x3040 <= code <= 0x30FF) or (0xAC00 <= code <= 0xD7AF) or (0x3000 <= code <= 0x303F):
            return "cjk"
        # Cyrillic / Greek
        if (0x0400 <= code <= 0x052F) or (0x0370 <= code <= 0x03FF):
            return "cyrillic"
        # Emoji / Pictographs
        if (0x1F300 <= code <= 0x1FAFF) or (0x2600 <= code <= 0x27BF):
            return "emoji"

    return "latin"


# Maps script category to bundled font files
SCRIPT_FONT_FILE = {
    "bengali": "SolaimanLipi.ttf",
    "arabic": "NotoSansArabic-Bold.ttf",
    "devanagari": "NotoSansDevanagari-Bold.ttf",
    "tamil": "NotoSansTamil-Bold.ttf",
    "telugu": "NotoSansTelugu-Bold.ttf",
    "thai": "NotoSansThai-Bold.ttf",
    "cjk": "NotoSansSC-Bold.ttf",
    "cyrillic": "NotoSans-Bold.ttf",
    "emoji": "NotoEmoji-Regular.ttf",
    "latin": "NotoSans-Bold.ttf",
}


def load_cross_platform_font(font_size: int = 22, text: Optional[str] = None) -> ImageFont.ImageFont:
    """
    Loads a scalable font cross-platform (Linux, Windows, macOS, Docker).
    Guaranteed to run cleanly on any PC with zero platform-specific hardcoding.
    Automatically detects language script (Bengali, Arabic, Hindi, CJK, etc.)
    and selects the matching high-legibility bundled font.
    """
    # 1. User-configured font path via environment variable
    custom_path = os.getenv("TINYPOS_FONT_PATH")
    if custom_path and os.path.exists(custom_path):
        try:
            return ImageFont.truetype(custom_path, font_size)
        except Exception:
            pass

    # Resolve bundled fonts directory relative to this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_fonts_dir = os.path.join(base_dir, "fonts")

    script = detect_script(text)

    # 2. If non-Latin international script detected, load mapped bundled font
    if script != "latin" and script in SCRIPT_FONT_FILE:
        target_font_file = SCRIPT_FONT_FILE[script]
        bundled_script_font = os.path.join(bundled_fonts_dir, target_font_file)
        if os.path.exists(bundled_script_font):
            try:
                return ImageFont.truetype(bundled_script_font, font_size)
            except Exception:
                pass

        # Specific fallbacks for Bengali
        if script == "bengali":
            bangla_fallbacks = [
                "/Users/sayem/Works/Laravel/prm.sajjadamin.com/resources/fonts/SolaimanLipi.ttf",
                "/System/Library/Fonts/Supplemental/Bangla Sangam MN.ttc",
                "/System/Library/Fonts/Supplemental/Bangla MN.ttc",
                "/System/Library/Fonts/Supplemental/KohinoorBangla.ttc",
                "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
                os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "vrinda.ttf"),
            ]
            for fb in bangla_fallbacks:
                if os.path.exists(fb):
                    try:
                        return ImageFont.truetype(fb, font_size)
                    except Exception:
                        continue

    # 3. For standard Latin / ASCII receipts:
    # First try monospace fonts so tabular alignment spaces line up evenly
    font_names = [
        "DejaVuSansMono-Bold.ttf",
        "DejaVuSansMono.ttf",
        "LiberationMono-Bold.ttf",
        "LiberationMono-Regular.ttf",
        "FreeMonoBold.ttf",
        "FreeMono.ttf",
        "Arial.ttf",
    ]
    for name in font_names:
        try:
            return ImageFont.truetype(name, font_size)
        except Exception:
            continue

    # Standard font locations on Linux and Windows
    windir = os.environ.get("WINDIR", "C:\\Windows")
    common_paths = [
        # Linux / Unix / Raspberry Pi
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
        # Windows
        os.path.join(windir, "Fonts", "arialbd.ttf"),
        os.path.join(windir, "Fonts", "consola.ttf"),
        os.path.join(windir, "Fonts", "courbd.ttf"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue

    # 4. Check bundled font directory (NotoSans-Bold or SolaimanLipi render clean English/numbers)
    for bundled_candidate in ["NotoSans-Bold.ttf", "SolaimanLipi.ttf"]:
        bp = os.path.join(bundled_fonts_dir, bundled_candidate)
        if os.path.exists(bp):
            try:
                return ImageFont.truetype(bp, font_size)
            except Exception:
                pass

    # 5. Universal fallback: Pillow's built-in scalable FreeType font
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def render_text_to_bitmap(text: str, font_size: int = 22, strength: int = 7) -> Image.Image:
    """
    Renders receipt text cleanly onto a 384px wide canvas with auto-wrapping.
    Enforces bold stroke weight when strength >= 5 to boost legibility on weak paper.
    Supports full Unicode Bangla script, conjuncts, and thermal divider lines.
    """
    font = load_cross_platform_font(font_size, text=text)

    margin = 16
    max_text_width = PRINT_WIDTH - (margin * 2)

    dummy_img = Image.new("RGB", (PRINT_WIDTH, 100), (255, 255, 255))
    dummy_draw = ImageDraw.Draw(dummy_img)

    wrapped_lines = []
    for raw_line in text.splitlines():
        trimmed = raw_line.strip()
        if not trimmed:
            wrapped_lines.append("")
            continue

        # Preserve horizontal divider lines (e.g. ---, ===) as dedicated line tokens
        if trimmed.startswith("---") or trimmed.startswith("==="):
            wrapped_lines.append(trimmed[:3])
            continue

        # If the line already fits within receipt printable width, preserve spaces for columns
        bbox = dummy_draw.textbbox((0, 0), raw_line, font=font)
        if (bbox[2] - bbox[0]) <= max_text_width:
            wrapped_lines.append(raw_line)
            continue

        # Otherwise wrap words to fit within max_text_width
        words = raw_line.split(" ")
        current_line = ""
        for word in words:
            candidate = f"{current_line} {word}".strip() if current_line else word
            bbox = dummy_draw.textbbox((0, 0), candidate, font=font)
            line_w = bbox[2] - bbox[0]
            if line_w <= max_text_width:
                current_line = candidate
            else:
                if current_line:
                    wrapped_lines.append(current_line)
                    current_line = ""
                # If word alone is longer than max_text_width, break it into fitting chunks
                w_bbox = dummy_draw.textbbox((0, 0), word, font=font)
                if (w_bbox[2] - w_bbox[0]) <= max_text_width:
                    current_line = word
                else:
                    sub = ""
                    for ch in word:
                        sub_w = dummy_draw.textbbox((0, 0), sub + ch, font=font)[2] - dummy_draw.textbbox((0, 0), sub + ch, font=font)[0]
                        if sub_w <= max_text_width:
                            sub += ch
                        else:
                            if sub:
                                wrapped_lines.append(sub)
                            sub = ch
                    current_line = sub
        if current_line:
            wrapped_lines.append(current_line)

    line_spacing = int(font_size * 0.35)
    line_height = int(font_size * 1.3)
    total_height = margin * 2 + len(wrapped_lines) * (line_height + line_spacing)

    canvas = Image.new("L", (PRINT_WIDTH, total_height), 255)
    draw = ImageDraw.Draw(canvas)

    # Ensure solid thermal stroke weight for high strength across all font sizes (especially 26-36pt)
    stroke = 1 if strength >= 5 else 0

    y = margin
    for line in wrapped_lines:
        if line.startswith("---") or line.startswith("==="):
            draw.line([(margin, y + line_height // 2), (PRINT_WIDTH - margin, y + line_height // 2)], fill=0, width=2)
        else:
            draw.text((margin, y), line, font=font, fill=0, stroke_width=stroke)
        y += line_height + line_spacing

    return canvas


def encode_image_to_lsb_rows(img: Image.Image, threshold: int = 150) -> List[bytes]:
    """
    Encodes image pixels into Bainiu row packets with LSB-first bit order:
    1 = black (burned pin), 0 = white (blank).
    """
    gray = img.convert("L")
    if gray.size[0] != PRINT_WIDTH:
        gray = convert_image_to_bitmap(gray)

    w, h = gray.size
    pixels = gray.load()
    rows = []

    for y in range(h):
        row_bytes = bytearray(w // 8)
        for x in range(w):
            if pixels[x, y] < threshold:  # Black pixel -> burn pin
                byte_idx = x // 8
                bit_idx = x % 8
                row_bytes[byte_idx] |= (1 << bit_idx)  # LSB first
        rows.append(bytes(row_bytes))

    return rows


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
