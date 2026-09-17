"""Unit tests for triage_agent (no LLM required)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from triage_agent import parse_issue_body, triage  # noqa: E402


def test_approve_simple_ar():
    r = triage("حاسبة بسيطة", "أداة للجمع والطرح تعمل بدون إنترنت", lang="ar")
    assert r["status"] == "approved"
    assert r["lang"] == "ar"
    assert "تم قبول" in r["user_message"]
    assert r["normalized_title"]


def test_approve_simple_en():
    r = triage("Tip jar", "Track cash tips offline for a small cafe", lang="en")
    assert r["status"] == "approved"
    assert r["lang"] == "en"
    assert "approved" in r["user_message"].lower() or "Your idea" in r["user_message"]


def test_reject_missing_title():
    r = triage("", "وصف كافٍ للفكرة هنا", lang="ar")
    assert r["status"] == "rejected"
    assert r["reason_code"] == "missing_title"


def test_reject_missing_description():
    r = triage("عنوان فقط", "", lang="en")
    assert r["status"] == "rejected"
    assert r["reason_code"] == "missing_description"


def test_reject_external_links():
    r = triage("أداة", "انظر https://example.com للمزيد", lang="ar")
    assert r["status"] == "rejected"
    assert r["reason_code"] == "external_links"
    assert "روابط" in r["user_message"] or "link" in r["user_message"].lower()


def test_reject_script_pattern():
    r = triage("صفحة", "تحتوي <script>alert(1)</script> كوداً", lang="en")
    assert r["status"] == "rejected"
    assert r["reason_code"] == "dangerous_code"


def test_parse_issue_body_ar_sections():
    body = """### عنوان المنتج المقترح

مؤقت شاي

### وصف الفكرة

مؤقت ثلاث دقائق مع تنبيه بصري

### الفئة المستهدفة

أداة
"""
    fields = parse_issue_body(body)
    assert "مؤقت" in fields["title"]
    assert "دقائق" in fields["description"]


def test_parse_issue_body_en_title_label():
    body = """### Product title

Flashcards

### Description

Offline Q and A cards for students
"""
    fields = parse_issue_body(body)
    assert fields["title"] == "Flashcards"
    assert "Offline" in fields["description"]
