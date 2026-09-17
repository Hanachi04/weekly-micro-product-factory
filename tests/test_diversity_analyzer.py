"""Unit tests for diversity_analyzer."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from utils.diversity_analyzer import (  # noqa: E402
    _extract_colors_from_html,
    _hex_to_rgb,
    calculate_diversity_score,
)


def test_hex_to_rgb():
    assert _hex_to_rgb("#ff0000") == (255, 0, 0)
    assert _hex_to_rgb("00ff00") == (0, 255, 0)
    assert _hex_to_rgb("#fff") == (255, 255, 255)
    assert _hex_to_rgb("zz") is None
    assert _hex_to_rgb("#12") is None


def test_extract_colors():
    html = '<div style="color:#1a2b3c;background:#fff">x</div>'
    colors = _extract_colors_from_html(html)
    assert "#1a2b3c" in colors
    assert any(c.startswith("#") for c in colors)


def test_score_no_history_is_max():
    r = calculate_diversity_score("<html><body>hi</body></html>", {"title": "a"}, [])
    assert r["diversity_score"] == 100.0


def test_score_with_history_bounded():
    history = [
        {
            "title": "حاسبة",
            "description": "عمليات حسابية",
            "template": "calculator",
            "diversity_tags": ["#ff6600", "#003366"],
        },
        {
            "title": "صفحة هبوط",
            "description": "عرض منتج",
            "template": "landing-page",
            "diversity_tags": ["#112233"],
        },
    ]
    html = """<!DOCTYPE html><html><body style="color:#00aa88">
    <h1>مؤقت</h1><button>ابدأ</button></body></html>"""
    r = calculate_diversity_score(
        html, {"title": "مؤقت شاي", "description": "ثلاث دقائق", "path": "weekly-tracker"}, history
    )
    assert 0 <= r["diversity_score"] <= 100
    assert "components" in r
    for key in ("color", "structure", "text", "type"):
        assert key in r["components"]


def test_same_template_lowers_type_component():
    history = [{"title": "a", "description": "b", "template": "calculator", "diversity_tags": []}] * 5
    r = calculate_diversity_score(
        "<html><body>x</body></html>",
        {"title": "c", "description": "d", "path": "calculator"},
        history,
    )
    assert r["components"]["type"] < 50
