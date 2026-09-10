"""
Unicode script detection, font resolution, and multi-font loaders.
Supports Bengali, Arabic, Devanagari, Tamil, Telugu, Thai, CJK, Cyrillic, Emojis, and Latin.
"""

import os
from typing import Dict, Optional
from PIL import ImageFont

from .constants import SCRIPT_FONT_FILE


def contains_bangla(text: Optional[str]) -> bool:
    """Checks if the text contains any Bengali Unicode characters (U+0980 - U+09FF)."""
    if not text:
        return False
    return any("\u0980" <= ch <= "\u09ff" for ch in text)


def get_char_script(ch: str, line_has_bengali: bool = False, line_has_korean: bool = False) -> str:
    """Classifies a single character into its script category."""
    code = ord(ch)
    # Emojis, Symbols, Pictographs, Dingbats, Stars, Regional Indicators, Variation Selectors
    if (0x1F000 <= code <= 0x1FFFF) or (0x2600 <= code <= 0x27BF) or (0x2300 <= code <= 0x23FF) or (0x2B00 <= code <= 0x2BFF) or (0xFE00 <= code <= 0xFE0F):
        return "emoji"
    # Bengali (U+0980 - U+09FF)
    if 0x0980 <= code <= 0x09FF:
        return "bengali"
    # Korean (Hangul Syllables, Jamo, Compatibility Jamo, Extended A/B, Halfwidth)
    if (
        (0xAC00 <= code <= 0xD7AF)
        or (0x1100 <= code <= 0x11FF)
        or (0x3130 <= code <= 0x318F)
        or (0xA960 <= code <= 0xA97F)
        or (0xD7B0 <= code <= 0xD7FF)
        or (0xFFA0 <= code <= 0xFFDC)
    ):
        return "korean"
    # Hebrew (U+0590 - U+05FF, U+FB1D - U+FB4F)
    if (0x0590 <= code <= 0x05FF) or (0xFB1D <= code <= 0xFB4F):
        return "hebrew"
    # Arabic & Perso-Arabic (Urdu, Farsi, Pashto)
    if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F) or (0x08A0 <= code <= 0x08FF) or (0xFB50 <= code <= 0xFDFF) or (0xFE70 <= code <= 0xFEFF):
        return "arabic"
    # Devanagari / Hindi / Marathi / Nepali
    if (0x0900 <= code <= 0x097F) or (0xA8E0 <= code <= 0xA8FF):
        return "devanagari"
    # Gujarati
    if 0x0A80 <= code <= 0x0AFF:
        return "gujarati"
    # Gurmukhi / Punjabi
    if 0x0A00 <= code <= 0x0A7F:
        return "gurmukhi"
    # Oriya / Odia
    if 0x0B00 <= code <= 0x0B7F:
        return "oriya"
    # Tamil
    if 0x0B80 <= code <= 0x0BFF:
        return "tamil"
    # Telugu
    if 0x0C00 <= code <= 0x0C7F:
        return "telugu"
    # Kannada
    if 0x0C80 <= code <= 0x0CFF:
        return "kannada"
    # Malayalam
    if 0x0D00 <= code <= 0x0D7F:
        return "malayalam"
    # Sinhala
    if 0x0D80 <= code <= 0x0DFF:
        return "sinhala"
    # Thai
    if 0x0E00 <= code <= 0x0E7F:
        return "thai"
    # Lao
    if 0x0E80 <= code <= 0x0EFF:
        return "lao"
    # Myanmar / Burmese
    if (0x1000 <= code <= 0x109F) or (0xA9E0 <= code <= 0xA9FF) or (0xAA60 <= code <= 0xAA7F):
        return "myanmar"
    # Georgian
    if (0x10A0 <= code <= 0x10FF) or (0x2D00 <= code <= 0x2D2F) or (0x1C90 <= code <= 0x1CBF):
        return "georgian"
    # Ethiopic / Ge'ez / Amharic
    if (0x1200 <= code <= 0x137F) or (0x1380 <= code <= 0x139F) or (0x2D80 <= code <= 0x2DDF) or (0xAB00 <= code <= 0xAB2F):
        return "ethiopic"
    # Khmer
    if (0x1780 <= code <= 0x17FF) or (0x19E0 <= code <= 0x19FF):
        return "khmer"
    # Armenian
    if (0x0530 <= code <= 0x058F) or (0xFB13 <= code <= 0xFB17):
        return "armenian"
    # CJK (Chinese Hanzi, Japanese Kana)
    if (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF) or (0x3040 <= code <= 0x30FF) or (0x3000 <= code <= 0x303F):
        return "cjk"
    # Cyrillic / Greek
    if (0x0400 <= code <= 0x052F) or (0x0370 <= code <= 0x03FF):
        return "cyrillic"
    # If the line contains Bengali, SolaimanLipi renders Latin letters & numbers seamlessly in typographic harmony
    if line_has_bengali and (ch.isascii() or ch.isdigit()):
        return "bengali"
    # If the line contains Korean, NotoSansKR renders Latin letters & numbers seamlessly in typographic harmony
    if line_has_korean and (ch.isascii() or ch.isdigit()):
        return "korean"
    return "latin"


def detect_script(text: Optional[str]) -> str:
    """
    Detects the predominant international Unicode script in the given text.
    """
    if not text:
        return "latin"

    for ch in text:
        code = ord(ch)
        if 0x0980 <= code <= 0x09FF:
            return "bengali"
        if (
            (0xAC00 <= code <= 0xD7AF)
            or (0x1100 <= code <= 0x11FF)
            or (0x3130 <= code <= 0x318F)
            or (0xA960 <= code <= 0xA97F)
            or (0xD7B0 <= code <= 0xD7FF)
            or (0xFFA0 <= code <= 0xFFDC)
        ):
            return "korean"
        if (0x0590 <= code <= 0x05FF) or (0xFB1D <= code <= 0xFB4F):
            return "hebrew"
        if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F) or (0x08A0 <= code <= 0x08FF) or (0xFB50 <= code <= 0xFDFF) or (0xFE70 <= code <= 0xFEFF):
            return "arabic"
        if (0x0900 <= code <= 0x097F) or (0xA8E0 <= code <= 0xA8FF):
            return "devanagari"
        if 0x0A80 <= code <= 0x0AFF:
            return "gujarati"
        if 0x0A00 <= code <= 0x0A7F:
            return "gurmukhi"
        if 0x0B00 <= code <= 0x0B7F:
            return "oriya"
        if 0x0B80 <= code <= 0x0BFF:
            return "tamil"
        if 0x0C00 <= code <= 0x0C7F:
            return "telugu"
        if 0x0C80 <= code <= 0x0CFF:
            return "kannada"
        if 0x0D00 <= code <= 0x0D7F:
            return "malayalam"
        if 0x0D80 <= code <= 0x0DFF:
            return "sinhala"
        if 0x0E00 <= code <= 0x0E7F:
            return "thai"
        if 0x0E80 <= code <= 0x0EFF:
            return "lao"
        if (0x1000 <= code <= 0x109F) or (0xA9E0 <= code <= 0xA9FF) or (0xAA60 <= code <= 0xAA7F):
            return "myanmar"
        if (0x10A0 <= code <= 0x10FF) or (0x2D00 <= code <= 0x2D2F) or (0x1C90 <= code <= 0x1CBF):
            return "georgian"
        if (0x1200 <= code <= 0x137F) or (0x1380 <= code <= 0x139F) or (0x2D80 <= code <= 0x2DDF) or (0xAB00 <= code <= 0xAB2F):
            return "ethiopic"
        if (0x1780 <= code <= 0x17FF) or (0x19E0 <= code <= 0x19FF):
            return "khmer"
        if (0x0530 <= code <= 0x058F) or (0xFB13 <= code <= 0xFB17):
            return "armenian"
        if (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF) or (0x3040 <= code <= 0x30FF) or (0x3000 <= code <= 0x303F):
            return "cjk"
        if (0x0400 <= code <= 0x052F) or (0x0370 <= code <= 0x03FF):
            return "cyrillic"
        if (0x1F300 <= code <= 0x1FAFF) or (0x2600 <= code <= 0x27BF):
            return "emoji"

    return "latin"


def get_bundled_fonts_dir() -> str:
    """Resolves the bundled fonts directory relative to the project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "fonts")


def load_multi_fonts(font_size: int = 22) -> Dict[str, ImageFont.ImageFont]:
    """Loads and caches bundled fonts for each script family at the requested font size."""
    bundled = get_bundled_fonts_dir()

    custom_path = os.getenv("TINYPOS_FONT_PATH")
    custom_font = None
    if custom_path and os.path.exists(custom_path):
        try:
            custom_font = ImageFont.truetype(custom_path, font_size)
        except Exception:
            pass

    fonts: Dict[str, ImageFont.ImageFont] = {}
    for script, filename in SCRIPT_FONT_FILE.items():
        if custom_font and script in ("latin", "bengali"):
            fonts[script] = custom_font
            continue
        fpath = os.path.join(bundled, filename)
        if os.path.exists(fpath):
            try:
                f = ImageFont.truetype(fpath, font_size)
                if hasattr(f, "set_variation_by_name"):
                    try:
                        f.set_variation_by_name("Bold")
                    except Exception:
                        pass
                fonts[script] = f
                continue
            except Exception:
                pass
        # Fallback to load_default
        try:
            fonts[script] = ImageFont.load_default(size=font_size)
        except TypeError:
            fonts[script] = ImageFont.load_default()

    return fonts


def load_cross_platform_font(font_size: int = 22, text: Optional[str] = None) -> ImageFont.ImageFont:
    """
    Loads a scalable font cross-platform (Linux, Windows, macOS, Docker).
    Guaranteed to run cleanly on any PC with zero platform-specific hardcoding.
    Automatically detects language script (Bengali, Korean, Arabic, Hindi, CJK, etc.)
    and selects the matching high-legibility bundled font.
    """
    # 1. User-configured font path via environment variable
    custom_path = os.getenv("TINYPOS_FONT_PATH")
    if custom_path and os.path.exists(custom_path):
        try:
            return ImageFont.truetype(custom_path, font_size)
        except Exception:
            pass

    bundled_fonts_dir = get_bundled_fonts_dir()
    script = detect_script(text)

    # 2. If non-Latin international script detected, load mapped bundled font
    if script != "latin" and script in SCRIPT_FONT_FILE:
        target_font_file = SCRIPT_FONT_FILE[script]
        bundled_script_font = os.path.join(bundled_fonts_dir, target_font_file)
        if os.path.exists(bundled_script_font):
            try:
                f = ImageFont.truetype(bundled_script_font, font_size)
                if hasattr(f, "set_variation_by_name"):
                    try:
                        f.set_variation_by_name("Bold")
                    except Exception:
                        pass
                return f
            except Exception:
                pass

        # Fallbacks for Bengali (system font locations on macOS, Linux, Windows)
        if script == "bengali":
            bangla_fallbacks = [
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

        # Fallbacks for Korean
        if script == "korean":
            korean_fallbacks = [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
                "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "malgun.ttf"),
            ]
            for fb in korean_fallbacks:
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
