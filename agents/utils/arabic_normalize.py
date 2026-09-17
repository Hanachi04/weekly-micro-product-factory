"""
Lightweight Arabic text normalization utilities (no heavy deps).
"""

from __future__ import annotations

import re
import unicodedata


# Tashkeel (diacritics) range
_TASHKEEL_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")

# Tatweel
_TATWEEL_RE = re.compile(r"\u0640")

# Multiple whitespace
_MULTI_SPACE_RE = re.compile(r"\s+")

# Alef variants → bare alef
_ALEF_MAP = str.maketrans({
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
})

# Yeh / Alef maqsura
_YEH_MAP = str.maketrans({
    "ى": "ي",
    "ئ": "ي",
})

# Teh marbuta → heh (optional normalization for matching)
_TEH_MAP = str.maketrans({
    "ة": "ه",
})


def strip_tashkeel(text: str) -> str:
    return _TASHKEEL_RE.sub("", text)


def normalize_arabic(text: str, *, unify_teh: bool = False) -> str:
    """
    Normalize Arabic text for comparison and clean storage:
    - Unicode NFKC
    - Remove tashkeel and tatweel
    - Unify alef / yeh variants
    - Collapse whitespace
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = strip_tashkeel(text)
    text = _TATWEEL_RE.sub("", text)
    text = text.translate(_ALEF_MAP)
    text = text.translate(_YEH_MAP)
    if unify_teh:
        text = text.translate(_TEH_MAP)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()
