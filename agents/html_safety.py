"""
HTML safety helpers for pages published to GitHub Pages.

GitHub Pages cannot send HTTP security headers, so the Content-Security-Policy
is delivered as a <meta http-equiv> tag placed first in <head>.

Also provides:
  - esc(): html.escape(str(value), quote=True) for every external value
  - safe_css_color(): allow-list for palette values injected into <style>
  - find_unsafe_html(): gate for AI-generated HTML (remote loads, exfiltration)
  - validate_generated_html(): structural / truncation check for AI HTML
"""

from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser
from typing import Any, Optional

# The bundled templates use inline <script>, inline on*= handlers and inline
# <style>, hence 'unsafe-inline'. No template loads any external asset.
CSP_POLICY = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; "
    "connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; "
    "frame-src 'none'"
)
CSP_META = f'<meta http-equiv="Content-Security-Policy" content="{CSP_POLICY}">'

_HEAD_OPEN_RE = re.compile(r"<head(?:\s[^>]*)?>", re.IGNORECASE)
_HTML_OPEN_RE = re.compile(r"<html(?:\s[^>]*)?>", re.IGNORECASE)


def esc(value: Any) -> str:
    """Escape any external value for HTML text or quoted-attribute context."""
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


_COLOR_RE = re.compile(
    r"^(?:#[0-9a-fA-F]{3,8}"
    r"|[a-zA-Z]{3,30}"
    r"|(?:rgb|rgba|hsl|hsla)\(\s*[0-9.,%\s/]+\))$"
)


def safe_css_color(value: Any, default: str) -> str:
    """Return value only if it is a plain CSS color; otherwise default."""
    if isinstance(value, str) and _COLOR_RE.match(value.strip()):
        return value.strip()
    return default


def add_csp(html: str) -> str:
    """Insert CSP_META as the first element of <head> (idempotent)."""
    if CSP_META in html:
        return html
    m = _HEAD_OPEN_RE.search(html)
    if m:
        return html[: m.end()] + "\n" + CSP_META + html[m.end():]
    m = _HTML_OPEN_RE.search(html)
    if m:
        return html[: m.end()] + "\n<head>" + CSP_META + "</head>" + html[m.end():]
    return "<head>" + CSP_META + "</head>\n" + html


# --- Unsafe AI HTML gate ---------------------------------------------------

_EXT_URL = r"""(?:https?:)?//"""
_UNSAFE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("external_script_src", re.compile(r"<script[^>]+src\s*=", re.I)),
    ("iframe", re.compile(r"<iframe", re.I)),
    ("object", re.compile(r"<object", re.I)),
    ("embed", re.compile(r"<embed", re.I)),
    ("base", re.compile(r"<base[\s/>]", re.I)),
    ("meta_refresh", re.compile(r"""http-equiv\s*=\s*["']?\s*refresh""", re.I)),
    ("fetch", re.compile(r"\bfetch\s*\(", re.I)),
    ("xmlhttprequest", re.compile(r"XMLHttpRequest", re.I)),
    ("sendbeacon", re.compile(r"sendBeacon", re.I)),
    ("websocket", re.compile(r"WebSocket", re.I)),
    (
        "external_url_attr",
        re.compile(
            r"""\b(?:src|href|srcset|action|formaction|poster|data|background)\s*=\s*["']?\s*"""
            + _EXT_URL,
            re.I,
        ),
    ),
    ("javascript_url", re.compile(r"""\b(?:src|href|action|formaction)\s*=\s*["']?\s*javascript:""", re.I)),
    ("external_css_url", re.compile(r"""url\(\s*["']?\s*""" + _EXT_URL, re.I)),
    ("css_import", re.compile(r"@import", re.I)),
    (
        "remote_event_handler",
        re.compile(r"""\son[a-z]+\s*=\s*(?:"[^"]*""" + _EXT_URL + r"""|'[^']*""" + _EXT_URL + r")", re.I),
    ),
]


def find_unsafe_html(html: str) -> list[str]:
    """Return the names of unsafe patterns found (empty list == safe)."""
    return [name for name, rx in _UNSAFE_PATTERNS if rx.search(html or "")]


# --- Structural validation ---------------------------------------------------


class _TagBalance(HTMLParser):
    TRACKED = ("html", "head", "body")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.opened = {t: 0 for t in self.TRACKED}
        self.closed = {t: 0 for t in self.TRACKED}

    def handle_starttag(self, tag: str, attrs: list) -> None:  # noqa: D401
        if tag in self.opened:
            self.opened[tag] += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.closed:
            self.closed[tag] += 1


def is_truncated_finish(finish_reason: Optional[str]) -> bool:
    fr = (finish_reason or "").strip().lower()
    return fr in ("length", "max_tokens", "max_output_tokens") or "length" in fr or "max_tokens" in fr


def validate_generated_html(html: str, finish_reason: Optional[str] = None) -> tuple[bool, str]:
    """Return (ok, reason). ok is False for truncated or structurally broken HTML."""
    if is_truncated_finish(finish_reason):
        return False, f"finish_reason={finish_reason} (output truncated)"
    s = (html or "").strip()
    low = s.lower()
    for tag in ("<html", "<head", "<body"):
        if tag not in low:
            return False, f"missing {tag}>"
    if not low.endswith("</html>"):
        return False, "does not end with </html>"
    parser = _TagBalance()
    try:
        parser.feed(s)
        parser.close()
    except Exception as exc:  # pragma: no cover - html.parser is lenient
        return False, f"html.parser error: {exc}"
    for tag in _TagBalance.TRACKED:
        if parser.opened[tag] < 1:
            return False, f"no <{tag}> element"
        if parser.closed[tag] < parser.opened[tag]:
            return False, f"unclosed <{tag}>"
    return True, "ok"
