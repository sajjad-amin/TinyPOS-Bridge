"""
Auto-cropping utilities to trim whitespace margins from receipts and images.
"""

from PIL import Image


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
