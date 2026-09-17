#!/usr/bin/env python3
"""Optional Telegram notify after successful publish."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
from utils.i18n import get_text, resolve_lang  # noqa: E402


def send(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
            return bool(data.get("ok"))
    except urllib.error.HTTPError as e:
        print(f"Telegram HTTP {e.code}: {e.read()[:300]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Telegram error: {e}", file=sys.stderr)
        return False


def main() -> int:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("Telegram secrets not set — skip notify")
        return 0

    lang = resolve_lang(os.environ.get("FACTORY_LANG"))
    meta_path = Path(os.environ.get("META_PATH") or "meta.json")
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    week = meta.get("week") or os.environ.get("WEEK_ID") or ""
    title = meta.get("title") or week or "product"
    repo = os.environ.get("GITHUB_REPOSITORY") or "Hanachi04/weekly-micro-product-factory"
    pages = (os.environ.get("PAGES_BASE_URL") or "").rstrip("/")
    if pages:
        url = f"{pages}/products/weekly/{week}/"
    else:
        url = f"https://github.com/{repo}/tree/main/products/weekly/{week}"

    div = meta.get("diversity_score")
    diversity = f"{div}" if div is not None else "—"
    cscore = meta.get("critic_score")
    critic_score = f"{cscore}" if cscore is not None else "—"
    verdict = meta.get("critic_verdict") or "—"
    critic_icon = (
        "✅" if verdict == "approved" else ("⚠️" if verdict == "needs_revision" else "•")
    )
    contributor = os.environ.get("CONTRIBUTOR") or get_text("telegram.no_contributor", lang)

    text = get_text(
        "telegram.success",
        lang,
        title=title,
        week=week,
        url=url,
        diversity=diversity,
        critic_icon=critic_icon,
        critic_score=critic_score,
        verdict=verdict,
        contributor=contributor,
    )
    ok = send(token, chat_id, text)
    print("Telegram sent" if ok else "Telegram failed (non-blocking)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
