"""Security tests: XSS escaping, CSP meta, AI-HTML gate/validation, LLM max_tokens."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

import design_agent  # noqa: E402
import html_safety  # noqa: E402
from html_safety import CSP_META, add_csp, find_unsafe_html, validate_generated_html  # noqa: E402
from utils import llm_client  # noqa: E402

XSS = "<img src=x onerror=alert(1)>"
XSS_ESC = "&lt;img src=x onerror=alert(1)&gt;"

TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>T</title>
<style>
body{margin:0}
</style>
</head>
<body>
<h1>Old title</h1>
<p class="sub">Old desc</p>
<a class="cta" href="#">Old CTA</a>
<footer>Old footer</footer>
</body>
</html>
"""

GOOD_AI_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><title>AI</title><style>:root{--a:#123}</style></head>
<body><h1>AI PRODUCT</h1><button onclick="go()">x</button>
<script>function go(){localStorage.setItem('k','v')}</script>
</body>
</html>"""


def _load_stats_module():
    spec = importlib.util.spec_from_file_location("generate_stats", ROOT / "scripts" / "generate_stats.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path, content=None, card=None):
    tdir = tmp_path / "templates" / "landing-page"
    tdir.mkdir(parents=True)
    (tdir / "index.html").write_text(TEMPLATE, encoding="utf-8")
    cpath = tmp_path / "content.json"
    dpath = tmp_path / "card.json"
    cpath.write_text(json.dumps(content or {"title": "Hello"}, ensure_ascii=False), encoding="utf-8")
    dpath.write_text(json.dumps(card or {}, ensure_ascii=False), encoding="utf-8")
    return str(dpath), str(cpath), str(tmp_path / "templates"), str(tmp_path / "out.html")


def _run_with_llm(tmp_path, monkeypatch, text, finish_reason="stop"):
    d, c, t, o = _setup(tmp_path)
    monkeypatch.setattr(design_agent, "available_providers", lambda: ["Groq"])
    calls = {}

    def fake(prompt, system_prompt="", max_tokens=None):
        calls["max_tokens"] = max_tokens
        return llm_client.LLMResult(text, "Groq", "llama-3.3-70b-versatile", finish_reason)

    monkeypatch.setattr(design_agent, "generate_text_with_meta", fake)
    meta = design_agent.design_product(d, c, t, o, use_llm=True)
    return meta, Path(o).read_text(encoding="utf-8"), calls


# --- 1. escaping -----------------------------------------------------------

def test_fallback_escapes_xss_in_all_fields():
    content = {"title": XSS, "description": XSS, "cta_primary": XSS, "footer": XSS}
    out = design_agent._inject_fallback(TEMPLATE, content, {})
    assert "<img" not in out
    assert out.count(XSS_ESC) == 4
    assert f"<h1>{XSS_ESC}</h1>" in out
    assert f"<footer>{XSS_ESC}</footer>" in out


def test_fallback_backslash_title_does_not_crash():
    content = {"title": r"C:\new\1 \g<0> \\", "cta_primary": r"go\2", "footer": r"\x"}
    out = design_agent._inject_fallback(TEMPLATE, content, {})
    assert r"<h1>C:\new\1 \g&lt;0&gt; \\</h1>" in out
    assert r"go\2</a>" in out


def test_fallback_rejects_malicious_palette():
    card = {"suggested_palette": ["red}</style><script>alert(1)</script>", "#abc", "x -->"]}
    out = design_agent._inject_fallback(TEMPLATE, {}, card)
    assert "<script>alert" not in out
    assert "--ai-primary: #1a365d" in out
    assert "--ai-secondary: #abc" in out


def test_stats_escapes_catalog_and_contributors(tmp_path, monkeypatch):
    stats = _load_stats_module()
    contrib = tmp_path / "contributors.json"
    contrib.write_text(json.dumps({"contributors": [{"username": XSS, "ideas_produced": 1}]}), encoding="utf-8")
    monkeypatch.setattr(stats, "CONTRIB", contrib)
    catalog = {
        "products": [{
            "title": XSS, "week": XSS, "path": 'p"><script>x</script>',
            "diversity_tags": [XSS], "diversity_score": 55, "critic_score": 7,
            "source_issue_number": XSS,
        }],
        "last_updated": XSS,
    }
    out = stats.build_html(catalog, "en")
    assert "<img" not in out
    assert "<script>x" not in out
    assert XSS_ESC in out
    assert f"@{XSS_ESC}" in out
    assert 'href="../p%22%3E%3Cscript%3Ex%3C/script%3E/"' in out


# --- 2. CSP ----------------------------------------------------------------

def test_csp_meta_first_in_head_stats():
    stats = _load_stats_module()
    out = stats.build_html({"products": []}, "ar")
    head_body = out.split("<head>", 1)[1].lstrip()
    assert head_body.startswith(CSP_META)
    assert "default-src 'none'" in CSP_META and "connect-src 'none'" in CSP_META


def test_csp_meta_in_generated_product(tmp_path):
    d, c, t, o = _setup(tmp_path, content={"title": XSS})
    meta = design_agent.design_product(d, c, t, o, use_llm=False)
    out = Path(o).read_text(encoding="utf-8")
    assert meta["source"] == "fallback"
    assert out.split("<head>", 1)[1].lstrip().startswith(CSP_META)
    assert out.count(CSP_META) == 1


def test_add_csp_idempotent_and_head_with_attrs():
    h = '<html><head lang="x"><title>a</title></head><body></body></html>'
    once = add_csp(h)
    assert once.startswith('<html><head lang="x">\n' + CSP_META)
    assert add_csp(once) == once


# --- 3/5. gate + validation -> fallback ------------------------------------

def test_valid_safe_ai_html_is_used(tmp_path, monkeypatch):
    meta, out, _ = _run_with_llm(tmp_path, monkeypatch, GOOD_AI_HTML)
    assert meta["source"] == "llm"
    assert "AI PRODUCT" in out
    assert CSP_META in out


def test_truncated_html_falls_back(tmp_path, monkeypatch):
    truncated = GOOD_AI_HTML.rsplit("</body>", 1)[0]
    meta, out, _ = _run_with_llm(tmp_path, monkeypatch, truncated)
    assert meta["source"] == "fallback_invalid"
    assert "AI PRODUCT" not in out
    assert "<h1>Hello</h1>" in out


def test_finish_reason_length_falls_back(tmp_path, monkeypatch):
    meta, out, _ = _run_with_llm(tmp_path, monkeypatch, GOOD_AI_HTML, finish_reason="length")
    assert meta["source"] == "fallback_invalid"
    assert "AI PRODUCT" not in out


def test_external_script_falls_back(tmp_path, monkeypatch):
    bad = GOOD_AI_HTML.replace("</head>", '<script src="https://evil.example/x.js"></script></head>')
    meta, out, _ = _run_with_llm(tmp_path, monkeypatch, bad)
    assert meta["source"] == "fallback_unsafe"
    assert "evil.example" not in out


@pytest.mark.parametrize("snippet", [
    "<iframe src=a></iframe>", "<object></object>", "<embed>", '<base href="/">',
    '<meta http-equiv="refresh" content="0;url=/x">', "<script>fetch('/x')</script>",
    "<script>new XMLHttpRequest()</script>", "<script>navigator.sendBeacon('/x')</script>",
    "<script>new WebSocket('wss://x')</script>", '<img src="https://x/y.png">',
    "<a href='//evil.example/'>x</a>", '<div onclick="location=\'https://evil\'">x</div>',
    "<style>body{background:url(https://x/y.png)}</style>",
])
def test_unsafe_gate_patterns(snippet):
    assert find_unsafe_html(GOOD_AI_HTML.replace("<body>", "<body>" + snippet))


def test_unsafe_gate_allows_clean_template_html():
    assert find_unsafe_html(GOOD_AI_HTML) == []
    for tpl in (ROOT / "templates").glob("*/index.html"):
        assert find_unsafe_html(tpl.read_text(encoding="utf-8")) == [], tpl


@pytest.mark.parametrize("html,ok", [
    (GOOD_AI_HTML, True),
    (GOOD_AI_HTML + "\n  ", True),
    (GOOD_AI_HTML.replace("</body>", ""), False),
    (GOOD_AI_HTML.replace("<head>", "").replace("</head>", ""), False),
    ("<html><head></head><body></body>", False),
])
def test_validate_generated_html(html, ok):
    assert validate_generated_html(html)[0] is ok


# --- 4. max_tokens ---------------------------------------------------------

def test_design_passes_8192_max_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
    _, _, calls = _run_with_llm(tmp_path, monkeypatch, GOOD_AI_HTML)
    assert calls["max_tokens"] == 8192


def test_max_tokens_env_override_and_model_cap(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS", "20000")
    assert llm_client.html_max_tokens() == 20000
    assert llm_client.cap_for_model("gemini-2.0-flash", 20000) == 8192
    assert llm_client.cap_for_model("llama-3.3-70b-versatile", 20000) == 20000
    monkeypatch.setenv("LLM_MAX_TOKENS", "junk")
    assert llm_client.html_max_tokens() == 8192


def test_groq_and_mistral_receive_max_tokens(monkeypatch):
    seen = []

    def make_resp(finish):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="<html>ok</html>"), finish_reason=finish)])

    class FakeGroq:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kw):
            seen.append(("groq", kw["model"], kw["max_tokens"]))
            return make_resp("length")

    class FakeMistral:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(complete=self.complete)

        def complete(self, **kw):
            seen.append(("mistral", kw["model"], kw["max_tokens"]))
            return make_resp("stop")

    monkeypatch.setitem(sys.modules, "groq", SimpleNamespace(Groq=FakeGroq))
    monkeypatch.setitem(sys.modules, "mistralai", SimpleNamespace(Mistral=FakeMistral))
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("MISTRAL_API_KEY", "k")

    r = llm_client._try_groq("p", "s", 8192)
    assert r.finish_reason == "length"
    m = llm_client._try_mistral("p", "s", 8192)
    assert m.finish_reason == "stop"
    assert ("groq", "llama-3.3-70b-versatile", 8192) in seen
    assert ("mistral", "mistral-small-latest", 8192) in seen
    # legacy callers (no max_tokens) keep 1024
    seen.clear()
    llm_client._try_groq("p", "s")
    assert seen[0][2] == 1024


def test_gemini_receives_max_output_tokens(monkeypatch):
    seen = {}

    class FakeModel:
        def __init__(self, model_name, system_instruction=None):
            self.name = model_name

        def generate_content(self, prompt, **kw):
            seen["cfg"] = kw.get("generation_config")
            return SimpleNamespace(
                text="<html></html>",
                candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))],
            )

    genai = SimpleNamespace(configure=lambda api_key: None, GenerativeModel=FakeModel)
    google_mod = SimpleNamespace(generativeai=genai)
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = llm_client._try_gemini("p", "s", 8192)
    assert seen["cfg"] == {"max_output_tokens": 8192}
    assert r.finish_reason == "length"
