"""
High-quality photo and artwork dithering processor for 57mm (384-dot) thermal printers.
Supports multiple professional dithering algorithms (Floyd-Steinberg, Atkinson, Bayer 8x8 matrix),
unsharp mask edge enhancement, dynamic range tuning, and specialized quality presets (Portrait, Sharp Detail, Balanced, High Contrast, Halftone).
"""

from typing import Optional
from PIL import Image, ImageEnhance, ImageFilter, ImageChops

from .constants import PRINT_WIDTH
from .crop import autocrop_whitespace

# 8x8 Bayer threshold matrix normalized to 0-63
BAYER_8X8 = [
    [ 0, 32,  8, 40,  2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44,  4, 36, 14, 46,  6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [ 3, 35, 11, 43,  1, 33,  9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47,  7, 39, 13, 45,  5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21]
]


def bayer_dither(img_gray: Image.Image) -> Image.Image:
    """
    Ordered 8x8 Bayer dithering. Produces a retro newspaper/comic halftone pattern.
    """
    w, h = img_gray.size
    tile_bytes = bytes([int(BAYER_8X8[y % 8][x % 8] * 255 / 64) for y in range(8) for x in range(8)])
    tile = Image.frombytes("L", (8, 8), tile_bytes)

    matrix_img = Image.new("L", (w, h))
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            matrix_img.paste(tile, (x, y))

    diff = ImageChops.subtract(img_gray, matrix_img)
    return diff.point(lambda p: 255 if p > 0 else 0, mode="1")


def atkinson_dither(img_gray: Image.Image) -> Image.Image:
    """
    Bill Atkinson's 1-bit dithering algorithm developed at Apple for the original Macintosh.
    Diffuses only 3/4 of the error (dropping 1/4), preserving crisp highlights and preventing
    excessive dark pooling on thermal paper.
    """
    w, h = img_gray.size
    arr = [int(p) for p in img_gray.getdata()]
    out = bytearray(w * h)

    for y in range(h):
        y_idx = y * w
        for x in range(w):
            idx = y_idx + x
            old = max(0, min(255, arr[idx]))
            new = 255 if old > 127 else 0
            out[idx] = new
            err = (old - new) >> 3  # 1/8 error per distribution cell
            if err != 0:
                if x + 1 < w:
                    arr[idx + 1] += err
                if x + 2 < w:
                    arr[idx + 2] += err
                if y + 1 < h:
                    if x > 0:
                        arr[idx + w - 1] += err
                    arr[idx + w] += err
                    if x + 1 < w:
                        arr[idx + w + 1] += err
                if y + 2 < h:
                    arr[idx + (2 * w)] += err

    return Image.frombytes("L", (w, h), bytes(out)).convert("1")


PHOTO_PRESETS = {
    "portrait": {
        "dither": "floyd",
        "sharpness": 1.2,
        "contrast": 1.12,
        "brightness": 1.08,
        "description": "Optimized for faces & portraits: lifted shadows to avoid blotchy skin",
    },
    "sharp": {
        "dither": "atkinson",
        "sharpness": 2.0,
        "contrast": 1.22,
        "brightness": 1.05,
        "description": "High-definition edge enhancement: makes eyes, hair strands, and jewelry pop",
    },
    "balanced": {
        "dither": "floyd",
        "sharpness": 1.0,
        "contrast": 1.15,
        "brightness": 1.03,
        "description": "Standard natural dynamic range for general landscapes and everyday photos",
    },
    "high_contrast": {
        "dither": "atkinson",
        "sharpness": 1.5,
        "contrast": 1.38,
        "brightness": 1.00,
        "description": "Deep punchy blacks and bright whites for logos, artwork, and sketches",
    },
    "halftone": {
        "dither": "bayer",
        "sharpness": 1.0,
        "contrast": 1.20,
        "brightness": 1.02,
        "description": "Retro comic book & newspaper dot matrix halftone pattern",
    },
}


def render_photo_to_bitmap(
    img: Image.Image,
    scale: float = 1.0,
    autocrop: bool = True,
    strength: int = 7,
    preset: str = "portrait",
    dither_algo: Optional[str] = None,
    sharpness: Optional[float] = None,
    contrast: Optional[float] = None,
    brightness: Optional[float] = None,
) -> Image.Image:
    """
    Converts any color or grayscale photo/image into a 384-pixel wide, 1-bit monochrome
    dithered bitmap (mode="1") optimized for 200dpi thermal receipt paper.

    Supports:
    1. Presets: 'portrait', 'sharp', 'balanced', 'high_contrast', 'halftone'
    2. Dithering algorithms: 'floyd' (Floyd-Steinberg), 'atkinson', 'bayer'
    3. Unsharp Mask spatial sharpening (0.0 to 3.0)
    4. Contrast & brightness dynamic range compensation
    """
    # 1. Resolve preset defaults and explicit overrides
    preset_key = str(preset).lower()
    preset_config = PHOTO_PRESETS.get(preset_key, PHOTO_PRESETS["portrait"])

    active_algo = (dither_algo or preset_config["dither"]).lower().strip()
    active_sharpness = float(sharpness if sharpness is not None else preset_config["sharpness"])
    active_contrast = float(contrast if contrast is not None else preset_config["contrast"])
    active_brightness = float(brightness if brightness is not None else preset_config["brightness"])

    # 2. Flatten alpha/transparency against pure white background
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # 3. Auto-crop empty whitespace borders if requested
    if autocrop:
        img = autocrop_whitespace(img)

    orig_w, orig_h = img.size
    if orig_w == 0 or orig_h == 0:
        return Image.new("1", (PRINT_WIDTH, 100), 1)

    # 4. Scale / resize to 384px width (with Lanczos filtering)
    scale = max(0.4, min(3.0, float(scale)))

    if abs(scale - 1.0) < 0.02:
        new_h = max(1, int(orig_h * (PRINT_WIDTH / float(orig_w))))
        resized = img.resize((PRINT_WIDTH, new_h), Image.Resampling.LANCZOS)
    elif scale < 1.0:
        target_w = max(10, int(PRINT_WIDTH * scale))
        target_h = max(1, int(orig_h * (target_w / float(orig_w))))
        resized_inner = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        canvas = Image.new("RGB", (PRINT_WIDTH, target_h), (255, 255, 255))
        offset_x = (PRINT_WIDTH - target_w) // 2
        canvas.paste(resized_inner, (offset_x, 0))
        resized = canvas
    else:
        target_w = int(PRINT_WIDTH * scale)
        target_h = max(1, int(orig_h * (target_w / float(orig_w))))
        resized_large = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        crop_left = (target_w - PRINT_WIDTH) // 2
        crop_right = crop_left + PRINT_WIDTH
        resized = resized_large.crop((crop_left, 0, crop_right, target_h))

    # 5. Grayscale conversion
    gray = resized.convert("L")

    # 6. Unsharp Mask spatial sharpening (enhances eyes, hair, teeth, fine textures)
    if active_sharpness > 0.05:
        percent = int(active_sharpness * 100)
        radius = 1.5 if active_sharpness <= 1.5 else 2.0
        gray = gray.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=2))

    # 7. Contrast & Brightness calibration
    if active_contrast != 1.0:
        gray = ImageEnhance.Contrast(gray).enhance(active_contrast)
    if active_brightness != 1.0:
        gray = ImageEnhance.Brightness(gray).enhance(active_brightness)

    # 8. Strength tuning: slightly brighten for weaker burning to prevent dot pooling
    if strength < 5:
        boost = 1.0 + (5 - strength) * 0.03
        gray = ImageEnhance.Brightness(gray).enhance(boost)

    # 9. Halftoning / Dithering
    if active_algo == "atkinson":
        return atkinson_dither(gray)
    elif active_algo in ("bayer", "halftone", "ordered"):
        return bayer_dither(gray)
    else:  # Default: Floyd-Steinberg error diffusion
        return gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
