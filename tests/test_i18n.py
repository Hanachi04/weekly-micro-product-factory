"""Unit tests for agents.utils.i18n"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from utils.i18n import clear_cache, get_text, resolve_lang  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_lang_env(monkeypatch):
    monkeypatch.delenv("FACTORY_LANG", raising=False)
    clear_cache()
    yield
    clear_cache()


def test_resolve_lang_default_ar():
    assert resolve_lang() == "ar"
    assert resolve_lang(None) == "ar"
    assert resolve_lang("") == "ar"


def test_resolve_lang_explicit():
    assert resolve_lang("en") == "en"
    assert resolve_lang("AR") == "ar"
    assert resolve_lang("fr") == "ar"  # unsupported → ar


def test_resolve_lang_from_env(monkeypatch):
    monkeypatch.setenv("FACTORY_LANG", "en")
    assert resolve_lang() == "en"


def test_get_text_ar_key():
    text = get_text("stats.title", "ar")
    assert "إحصائيات" in text or "المصنع" in text


def test_get_text_en_key():
    text = get_text("stats.title", "en")
    assert "Stats" in text or "Factory" in text


def test_get_text_format_kwargs():
    text = get_text("triage.approved", "ar", title="اختبار")
    assert "اختبار" in text
    assert "✅" in text


def test_get_text_unknown_key_returns_key():
    assert get_text("does.not.exist.ever", "en") == "does.not.exist.ever"


def test_ar_en_key_parity():
    import json

    ar = json.loads((ROOT / "locales" / "ar.json").read_text(encoding="utf-8"))
    en = json.loads((ROOT / "locales" / "en.json").read_text(encoding="utf-8"))
    assert set(ar.keys()) == set(en.keys())
    assert len(ar) >= 40
