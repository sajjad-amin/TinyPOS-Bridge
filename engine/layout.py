"""
Text layout engine: multi-font line segmentation, tokenization, and word wrapping.
"""

from typing import Dict, List, Tuple
from PIL import ImageFont

from .fonts import get_char_script


def segment_line(line: str) -> List[Tuple[str, str]]:
    """
    Splits a single text line into consecutive segments of (text, script).
    Spaces attach to the preceding script to preserve word spacing.
    """
    has_bengali = any(0x0980 <= ord(c) <= 0x09FF for c in line)
    has_korean = any(
        (0xAC00 <= ord(c) <= 0xD7AF)
        or (0x1100 <= ord(c) <= 0x11FF)
        or (0x3130 <= ord(c) <= 0x318F)
        for c in line
    )
    chunks: List[Tuple[str, str]] = []
    curr_script: str = ""
    curr_text: str = ""

    for ch in line:
        s = get_char_script(ch, line_has_bengali=has_bengali, line_has_korean=has_korean)
        if ch.isspace() and curr_script:
            curr_text += ch
            continue
        if s == curr_script or not curr_script:
            curr_script = s
            curr_text += ch
        else:
            if curr_text:
                chunks.append((curr_text, curr_script))
            curr_text = ch
            curr_script = s

    if curr_text:
        chunks.append((curr_text, curr_script))

    return chunks


def tokenize_segments(segs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Tokenizes segments into word and space tokens for wrapping."""
    tokens: List[Tuple[str, str]] = []
    for txt, scr in segs:
        parts = txt.split(" ")
        for i, p in enumerate(parts):
            if p:
                tokens.append((p, scr))
            if i < len(parts) - 1:
                tokens.append((" ", scr))
    return tokens


def wrap_segments(
    segs: List[Tuple[str, str]],
    fonts: Dict[str, ImageFont.ImageFont],
    max_width: int,
) -> List[List[Tuple[str, str]]]:
    """Wraps mixed-script segments into lines fitting within max_width."""
    tokens = tokenize_segments(segs)
    lines: List[List[Tuple[str, str]]] = []
    curr_line: List[Tuple[str, str]] = []
    curr_w: float = 0.0

    for tok_txt, scr in tokens:
        f = fonts.get(scr, fonts["latin"])
        tok_w = f.getlength(tok_txt)

        if not curr_line and tok_txt.isspace():
            continue

        if curr_w + tok_w <= max_width:
            curr_line.append((tok_txt, scr))
            curr_w += tok_w
        else:
            if curr_line:
                lines.append(curr_line)
                curr_line = []
                curr_w = 0.0
            if not tok_txt.isspace():
                if tok_w > max_width:
                    sub = ""
                    for ch in tok_txt:
                        ch_w = f.getlength(sub + ch)
                        if ch_w <= max_width:
                            sub += ch
                        else:
                            if sub:
                                lines.append([(sub, scr)])
                            sub = ch
                    if sub:
                        curr_line = [(sub, scr)]
                        curr_w = f.getlength(sub)
                else:
                    curr_line = [(tok_txt, scr)]
                    curr_w = tok_w

    if curr_line:
        lines.append(curr_line)

    return lines
