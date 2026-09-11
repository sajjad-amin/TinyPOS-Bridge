"""
Image, PDF, and text rasterization rendering into 384px thermal bitmaps.
"""

import io
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageEnhance

try:
    import pymupdf
except ImportError:
    pymupdf = None

from .constants import PRINT_WIDTH
from .crop import autocrop_whitespace
from .fonts import load_multi_fonts
from .layout import segment_line, wrap_segments


def convert_image_to_bitmap(
    img: Image.Image,
    scale: float = 1.0,
    autocrop: bool = True,
    strength: int = 7,
    mode: str = "text",
    dither: bool = False,
) -> Image.Image:
    """
    Processes an image into a 384-pixel wide bitmap.
    If mode == "photo" or dither is True, applies Floyd-Steinberg error-diffusion dithering
    for photorealistic shading, soft gradients, and delicate skin tones.
    Otherwise (default "text" mode), applies high-contrast binarization for receipts and invoices.
    """
    if str(mode).lower() == "photo" or dither:
        from .photo import render_photo_to_bitmap
        return render_photo_to_bitmap(img, scale=scale, autocrop=autocrop, strength=strength)

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

    # 4. Enhance contrast so small text remains crisp and legible on thermal paper
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(1.35)

    return gray


def render_pdf_to_bitmap(
    pdf_bytes: bytes,
    scale: float = 1.0,
    autocrop: bool = True,
    strength: int = 7,
    mode: str = "text",
    dither: bool = False,
) -> Image.Image:
    """
    Renders a PDF (all pages combined vertically) to a 384px wide grayscale image.
    Supports autocrop, scale zoom factors, and photo dithering mode.
    """
    if not pymupdf:
        raise RuntimeError("PyMuPDF (pymupdf) is not installed")

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page_images = []

    for page in doc:
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

    return convert_image_to_bitmap(stitched, scale=scale, autocrop=autocrop, strength=strength, mode=mode, dither=dither)


def render_text_to_bitmap(text: str, font_size: int = 22, strength: int = 7) -> Image.Image:
    """
    Renders receipt text cleanly onto a 384px wide canvas with auto-wrapping.
    Enforces bold stroke weight when strength >= 5 to boost legibility on weak paper.
    Supports seamless multi-script mixing: English, Bengali, Arabic, CJK, and Emojis
    can all appear on the exact same line without missing glyph boxes.
    """
    fonts = load_multi_fonts(font_size)

    margin = 16
    max_text_width = PRINT_WIDTH - (margin * 2)

    wrapped_rows: List[List[Tuple[str, str]]] = []
    for raw_line in text.splitlines():
        trimmed = raw_line.strip()
        if not trimmed:
            wrapped_rows.append([("", "latin")])
            continue

        # Preserve horizontal divider lines (e.g. ---, ===) as dedicated line tokens
        if trimmed.startswith("---") or trimmed.startswith("==="):
            wrapped_rows.append([(trimmed[:3], "divider")])
            continue

        segs = segment_line(raw_line)
        total_w = sum(fonts.get(s, fonts["latin"]).getlength(t) for t, s in segs)

        # If the line already fits within receipt printable width, keep segments intact (preserves column spaces)
        if total_w <= max_text_width:
            wrapped_rows.append(segs)
        else:
            wrapped_rows.extend(wrap_segments(segs, fonts, max_text_width))

    line_spacing = int(font_size * 0.35)
    line_height = int(font_size * 1.3)
    total_height = margin * 2 + len(wrapped_rows) * (line_height + line_spacing)

    canvas = Image.new("L", (PRINT_WIDTH, total_height), 255)
    draw = ImageDraw.Draw(canvas)

    # Ensure solid thermal stroke weight for high strength across all font sizes (especially 26-36pt)
    stroke = 1 if strength >= 5 else 0

    y = margin
    for row in wrapped_rows:
        if len(row) == 1 and row[0][1] == "divider":
            draw.line([(margin, y + line_height // 2), (PRINT_WIDTH - margin, y + line_height // 2)], fill=0, width=2)
        else:
            curr_x = float(margin)
            for txt, scr in row:
                f = fonts.get(scr, fonts["latin"])
                draw.text((curr_x, y), txt, font=f, fill=0, stroke_width=stroke)
                curr_x += f.getlength(txt)
        y += line_height + line_spacing

    return canvas


def render_qr_to_bitmap(
    content: str,
    header_text: Optional[str] = None,
    footer_text: Optional[str] = None,
    qr_size: int = 280,
    strength: int = 7,
) -> Image.Image:
    """
    Renders a high-contrast QR code centered on a 384px thermal canvas.
    Optionally prepends header_text and appends footer_text, rendered with multi-script font support.
    """
    import qrcode

    qr_size = max(140, min(PRINT_WIDTH - 16, int(qr_size)))

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("L")
    qr_resized = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)

    elements: List[Image.Image] = []

    if header_text and header_text.strip():
        hdr = render_text_to_bitmap(header_text.strip(), font_size=22, strength=strength)
        hdr_cropped = autocrop_whitespace(hdr, padding=4)
        elements.append(hdr_cropped)

    elements.append(qr_resized)

    if footer_text and footer_text.strip():
        ftr = render_text_to_bitmap(footer_text.strip(), font_size=18, strength=strength)
        ftr_cropped = autocrop_whitespace(ftr, padding=4)
        elements.append(ftr_cropped)

    gap = 12
    margin_top = 16
    margin_bottom = 16
    total_height = margin_top + margin_bottom + sum(e.size[1] for e in elements) + gap * (len(elements) - 1)

    canvas = Image.new("L", (PRINT_WIDTH, total_height), 255)

    y = margin_top
    for elem in elements:
        x = max(0, (PRINT_WIDTH - elem.size[0]) // 2)
        canvas.paste(elem, (x, y))
        y += elem.size[1] + gap

    return canvas

