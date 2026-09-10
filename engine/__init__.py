"""
TinyPOS Engine Package
Modular architecture for thermal printer protocol, typography, text layout, and raster rendering.
"""

from .constants import (
    PRINT_WIDTH,
    KNOWN_SERVICE_UUIDS,
    KNOWN_TX_CHAR_UUIDS,
    KNOWN_NAMES,
    HEADER,
    FOOTER,
    CRC8_TABLE,
    CMD_GET_DEV_STATE,
    CMD_SET_QUALITY_200_DPI,
    CMD_APPLY_ENERGY,
    CMD_LATTICE_START,
    CMD_LATTICE_END,
    CMD_FEED_PAPER,
    SCRIPT_FONT_FILE,
)

from .protocol import (
    crc8,
    make_packet,
    CMD_SET_SPEED,
    get_strength_params,
    encode_image_to_lsb_rows,
)

from .fonts import (
    contains_bangla,
    get_char_script,
    detect_script,
    get_bundled_fonts_dir,
    load_multi_fonts,
    load_cross_platform_font,
)

from .layout import (
    segment_line,
    tokenize_segments,
    wrap_segments,
)

from .renderer import (
    autocrop_whitespace,
    convert_image_to_bitmap,
    render_pdf_to_bitmap,
    render_text_to_bitmap,
)

__all__ = [
    # Constants
    "PRINT_WIDTH",
    "KNOWN_SERVICE_UUIDS",
    "KNOWN_TX_CHAR_UUIDS",
    "KNOWN_NAMES",
    "HEADER",
    "FOOTER",
    "CRC8_TABLE",
    "CMD_GET_DEV_STATE",
    "CMD_SET_QUALITY_200_DPI",
    "CMD_APPLY_ENERGY",
    "CMD_LATTICE_START",
    "CMD_LATTICE_END",
    "CMD_FEED_PAPER",
    "SCRIPT_FONT_FILE",
    # Protocol
    "crc8",
    "make_packet",
    "CMD_SET_SPEED",
    "get_strength_params",
    "encode_image_to_lsb_rows",
    # Fonts
    "contains_bangla",
    "get_char_script",
    "detect_script",
    "get_bundled_fonts_dir",
    "load_multi_fonts",
    "load_cross_platform_font",
    # Layout
    "segment_line",
    "tokenize_segments",
    "wrap_segments",
    # Renderer
    "autocrop_whitespace",
    "convert_image_to_bitmap",
    "render_pdf_to_bitmap",
    "render_text_to_bitmap",
]
