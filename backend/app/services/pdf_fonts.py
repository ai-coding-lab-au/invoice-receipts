"""Bundled Unicode fonts and small ReportLab fallback helpers.

The built-in PDF Type 1 fonts silently replace characters outside their
limited encodings. These helpers keep document rendering offline and portable
while covering CJK, Cyrillic, Greek and Arabic customer data.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import unicodedata

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


FONT_BASE = "AgreementNotoSansSC"
FONT_BOLD = "AgreementNotoSansSC-Bold"
FONT_OBLIQUE = "AgreementNotoSansSC-Oblique"
FONT_FALLBACK = "AgreementNotoSans"
FONT_FALLBACK_BOLD = "AgreementNotoSans-Bold"
FONT_ARABIC = "AgreementNotoSansArabic"
FONT_ARABIC_BOLD = "AgreementNotoSansArabic-Bold"

_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
_FONT_FILES = {
    FONT_BASE: "NotoSansSC-VF.ttf",
    # Use a real static bold face for Latin/Greek/Cyrillic. CJK glyphs fall
    # back to the comprehensive SC face below because ReportLab does not
    # currently select the weight axis from the bundled variable CJK font.
    FONT_BOLD: "NotoSans-Bold.ttf",
    FONT_OBLIQUE: "NotoSans-Regular.ttf",
    FONT_FALLBACK: "NotoSans-Regular.ttf",
    FONT_FALLBACK_BOLD: "NotoSans-Bold.ttf",
    FONT_ARABIC: "NotoSansArabic-Regular.ttf",
    FONT_ARABIC_BOLD: "NotoSansArabic-Bold.ttf",
}
_FONT_GLYPHS: dict[str, set[int]] = {}


def register_pdf_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename in _FONT_FILES.items():
        if name in registered:
            font = pdfmetrics.getFont(name)
        else:
            font = TTFont(name, str(_FONT_DIR / filename), shapable=True)
            pdfmetrics.registerFont(font)
        glyphs = getattr(getattr(font, "face", None), "charToGlyph", {})
        _FONT_GLYPHS[name] = set(glyphs)
    pdfmetrics.registerFontFamily(
        FONT_BASE,
        normal=FONT_BASE,
        bold=FONT_BOLD,
        italic=FONT_OBLIQUE,
        boldItalic=FONT_BOLD,
    )


register_pdf_fonts()


def _is_bold(font: str) -> bool:
    return font in {FONT_BOLD, FONT_FALLBACK_BOLD, FONT_ARABIC_BOLD}


# The CJK-first base face gives common Latin punctuation (curly quotes,
# dashes, ellipsis) fullwidth advances, which reads as a stray space after
# every apostrophe ("Clients'  Account"). Prefer the Latin companion face for
# these characters when they appear in Latin-preferred text.
_LATIN_PUNCTUATION = {ord(ch) for ch in "‘’“”–—…"}


@lru_cache(maxsize=8192)
def font_for_character(character: str, preferred: str = FONT_BASE) -> str:
    """Return a bundled font containing ``character`` or fail explicitly."""
    codepoint = ord(character)
    if codepoint in _LATIN_PUNCTUATION and preferred == FONT_BASE:
        if codepoint in _FONT_GLYPHS.get(FONT_FALLBACK, set()):
            return FONT_FALLBACK
    if codepoint in _FONT_GLYPHS.get(preferred, set()):
        return preferred
    if unicodedata.category(character) in {"Cc", "Cf"}:
        return preferred
    candidates = (
        (FONT_FALLBACK_BOLD, FONT_ARABIC_BOLD, FONT_BASE)
        if _is_bold(preferred)
        else (FONT_FALLBACK, FONT_ARABIC, FONT_BASE)
    )
    for name in candidates:
        if codepoint in _FONT_GLYPHS.get(name, set()):
            return name
    raise ValueError(
        f"PDF font coverage is missing character U+{codepoint:04X}; "
        "document generation was stopped to prevent silent corruption"
    )


def font_runs(text: object, preferred: str = FONT_BASE) -> list[tuple[str, str]]:
    value = "" if text is None else str(text)
    if not value:
        return []
    runs: list[tuple[str, str]] = []
    active_font = font_for_character(value[0], preferred)
    active_text = value[0]
    for character in value[1:]:
        character_font = font_for_character(character, preferred)
        if character_font == active_font:
            active_text += character
        else:
            runs.append((active_font, active_text))
            active_font = character_font
            active_text = character
    runs.append((active_font, active_text))
    return runs


def unicode_markup(escaped_text: str, preferred: str = FONT_BASE) -> str:
    """Add ReportLab ``font`` spans around fallback-only character runs.

    ``escaped_text`` must already be escaped for ReportLab's XML-like parser.
    """
    parts: list[str] = []
    for font, text in font_runs(escaped_text, preferred):
        parts.append(text if font == preferred else f'<font name="{font}">{text}</font>')
    return "".join(parts)


def string_width(text: object, font: str, size: float) -> float:
    return sum(pdfmetrics.stringWidth(run, run_font, size) for run_font, run in font_runs(text, font))


def draw_unicode_string(
    canvas,
    x: float,
    y: float,
    text: object,
    *,
    font: str = FONT_BASE,
    size: float = 10,
    align: str = "left",
) -> None:
    """Draw mixed-script text with fallback fonts and optional alignment."""
    runs = font_runs(text, font)
    total_width = sum(pdfmetrics.stringWidth(run, run_font, size) for run_font, run in runs)
    cursor = x
    if align == "right":
        cursor -= total_width
    elif align == "center":
        cursor -= total_width / 2
    for run_font, run in runs:
        canvas.setFont(run_font, size)
        is_rtl = any(unicodedata.bidirectional(ch) in {"AL", "AN", "R"} for ch in run)
        canvas.drawString(
            cursor,
            y,
            run,
            direction="rtl" if is_rtl else "ltr",
            shaping=True,
        )
        cursor += pdfmetrics.stringWidth(run, run_font, size)
