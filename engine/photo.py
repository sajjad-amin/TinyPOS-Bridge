"""
High-quality photo and artwork dithering processor for 57mm (384-dot) thermal printers.
Uses Floyd-Steinberg error-diffusion dithering with thermal dot-gain compensation
to produce smooth skin tones, soft gradients, and realistic photographic prints.
"""

from typing import Optional
from PIL import Image, ImageEnhance

from .constants import PRINT_WIDTH
from .crop import autocrop_whitespace


def render_photo_to_bitmap(
    img: Image.Image,
    scale: float = 1.0,
    autocrop: bool = True,
    strength: int = 7,
    contrast: float = 1.15,
    brightness: float = 1.05,
) -> Image.Image:
    """
    Converts any color or grayscale photo/image into a 384-pixel wide, 1-bit monochrome
    dithered bitmap (mode="1") optimized for 200dpi thermal receipt paper.

    Applies:
    1. Alpha flattening over solid white.
    2. Auto-cropping of empty whitespace borders (optional).
    3. High-precision LANCZOS resizing to 384px width (with scale multiplier).
    4. Thermal dot-gain compensation (brightness/contrast curve tuning).
    5. Floyd-Steinberg error-diffusion halftoning.
    """
    # 1. Flatten alpha/transparency against white background
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
        return Image.new("1", (PRINT_WIDTH, 100), 1)

    # 3. Apply scale factor (zoom / size adjustment)
    scale = max(0.4, min(3.0, float(scale)))

    if abs(scale - 1.0) < 0.02:
        # Standard fit: scale directly to PRINT_WIDTH (384px) maintaining aspect ratio
        new_h = max(1, int(orig_h * (PRINT_WIDTH / float(orig_w))))
        resized = img.resize((PRINT_WIDTH, new_h), Image.Resampling.LANCZOS)
    elif scale < 1.0:
        # Shrink and center horizontally on 384px canvas
        target_w = max(10, int(PRINT_WIDTH * scale))
        target_h = max(1, int(orig_h * (target_w / float(orig_w))))
        resized_inner = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        canvas = Image.new("RGB", (PRINT_WIDTH, target_h), (255, 255, 255))
        offset_x = (PRINT_WIDTH - target_w) // 2
        canvas.paste(resized_inner, (offset_x, 0))
        resized = canvas
    else:
        # scale > 1.0: Zoom and center-crop to 384px
        target_w = int(PRINT_WIDTH * scale)
        target_h = max(1, int(orig_h * (target_w / float(orig_w))))
        resized_large = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        crop_left = (target_w - PRINT_WIDTH) // 2
        crop_right = crop_left + PRINT_WIDTH
        resized = resized_large.crop((crop_left, 0, crop_right, target_h))

    # 4. Convert to grayscale
    gray = resized.convert("L")

    # 5. Dynamic range and thermal dot-gain compensation
    # Thermal print heads cause slight heat bleed ("dot gain").
    # Slightly lifting brightness and gently boosting contrast keeps shadows
    # from pooling into solid black and prevents blown-out skin highlights.
    if contrast != 1.0:
        gray = ImageEnhance.Contrast(gray).enhance(contrast)
    if brightness != 1.0:
        gray = ImageEnhance.Brightness(gray).enhance(brightness)

    # Strength adjustments: lighter strengths reduce black dot density
    if strength < 5:
        # For lower burn strengths, slightly brighten to prevent dot accumulation
        boost = 1.0 + (5 - strength) * 0.03
        gray = ImageEnhance.Brightness(gray).enhance(boost)

    # 6. Floyd-Steinberg error diffusion dithering (produces 1-bit mode "1" image)
    dithered = gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

    return dithered
