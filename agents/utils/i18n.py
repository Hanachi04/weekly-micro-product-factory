"""Lightweight i18n: JSON locales + FACTORY_LANG env (default: ar)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_LOCALES_DIR = _ROOT / "locales"
_SUPPORTED = ("ar", "en")


def resolve_lang(lang: str | None = None) -> str:
    raw = (lang or os.environ.get("FACTORY_LANG") or "ar").strip().lower()
    if raw not in _SUPPORTED:
        return "ar"
    return raw


@lru_cache(maxsize=8)
def _load(lang: str) -> dict[str, str]:
    path = _LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        path = _LOCALES_DIR / "ar.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def get_text(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Return localized string for key; falls back to Arabic then the key itself."""
    code = resolve_lang(lang)
    table = _load(code)
    text = table.get(key)
    if text is None:
        text = _load("ar").get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def clear_cache() -> None:
    _load.cache_clear()
