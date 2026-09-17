#!/usr/bin/env python3
"""
Design Agent — يعدّل قالباً حتمياً وفق بطاقة التنوع والمحتوى (Template Injection).

Usage:
  python agents/design_agent.py \
    --diversity diversity_card.json \
    --content content.json \
    --templates-dir templates \
    --output index.html
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.llm_client import generate_text, AllProvidersFailedError, available_providers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("design_agent")

MAX_BYTES = 80 * 1024  # 80 KB hard limit

SYSTEM_PROMPT = (
    "أنت مطور واجهات أمامية متخصص في HTML/CSS مضمن فقط. "
    "عدّل القالب المعطى دون إضافة مكتبات خارجية أو CDN. "
    "حافظ على dir=rtl و lang=ar. أخرج ملف HTML كاملاً فقط بدون شرح."
)


def _load_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _list_templates(templates_dir: str) -> list[str]:
    root = Path(templates_dir)
    if not root.exists():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and (d / "index.html").exists()
    )


def _pick_base_template(templates_dir: str, card: dict[str, Any]) -> Path:
    """Choose closest deterministic template as injection base."""
    available = _list_templates(templates_dir)
    if not available:
        raise FileNotFoundError(f"No templates in {templates_dir}")

    layout = (card.get("required_layout") or "").lower()
    interaction = (card.get("interaction_type") or "").lower()
    forbidden = " ".join(card.get("forbidden_patterns") or []).lower()

    # Heuristic scoring
    scores = {name: 0 for name in available}
    for name in available:
        n = name.lower()
        if "tracker" in n or "habit" in n:
            if any(k in layout or k in interaction for k in ("دائر", "radial", "تتبع", "جلسة", "نقر")):
                scores[name] += 3
            if "متتبع" in forbidden or "عادة" in forbidden:
                scores[name] -= 2
        if "calc" in n:
            if any(k in layout for k in ("جدول", "شبكة", "grid")):
                scores[name] += 2
            if "حاسبة" in forbidden:
                scores[name] -= 3
        if "landing" in n:
            if any(k in layout for k in ("هبوط", "عمود", "مركزي", "بطاقة")):
                scores[name] += 2
            if "هبوط" in forbidden or "hero" in forbidden:
                scores[name] -= 2

    best = max(available, key=lambda n: scores.get(n, 0))
    path = Path(templates_dir) / best / "index.html"
    logger.info("Base template selected: %s (score=%s)", best, scores.get(best, 0))
    return path


def _inject_fallback(base_html: str, content: dict[str, Any], card: dict[str, Any]) -> str:
    """Deterministic CSS variable + text injection when LLM unavailable."""
    palette = card.get("suggested_palette") or ["#1a365d", "#ed8936", "#f7fafc"]
    primary = palette[0] if len(palette) > 0 else "#1a365d"
    secondary = palette[1] if len(palette) > 1 else "#ed8936"
    bg = palette[2] if len(palette) > 2 else "#f7fafc"

    title = content.get("title") or "منتج مصغّر"
    desc = content.get("description") or ""
    cta = content.get("cta_primary") or "ابدأ"
    footer = content.get("footer") or ""

    # Inject CSS variables after <style> or in head
    css_vars = f"""
:root {{
  --ai-primary: {primary};
  --ai-secondary: {secondary};
  --ai-bg: {bg};
}}
body {{ background: var(--ai-bg) !important; }}
h1, h2 {{ color: var(--ai-primary) !important; }}
button, .cta, a.cta {{ background: var(--ai-primary) !important; border-color: var(--ai-primary) !important; }}
"""
    if "<style>" in base_html:
        html = base_html.replace("<style>", f"<style>\n{css_vars}\n", 1)
    else:
        html = base_html.replace("</head>", f"<style>{css_vars}</style></head>", 1)

    # Replace first <h1>...</h1>
    html = re.sub(r"<h1[^>]*>.*?</h1>", f"<h1>{title}</h1>", html, count=1, flags=re.DOTALL | re.IGNORECASE)
    # Replace first descriptive <p class="sub|desc|...">
    html = re.sub(
        r'<p class="(?:sub|desc|description)"[^>]*>.*?</p>',
        f'<p class="desc">{desc}</p>',
        html,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # CTA text in anchors/buttons with class cta
    html = re.sub(
        r'(<(?:a|button)[^>]*class="[^"]*cta[^"]*"[^>]*>)(.*?)(</(?:a|button)>)',
        rf"\1{cta}\3",
        html,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if footer and "<footer>" in html:
        html = re.sub(r"<footer>.*?</footer>", f"<footer>{footer}</footer>", html, count=1, flags=re.DOTALL)

    # Mark as AI-assisted fallback
    meta = f'<!-- design_agent: fallback | palette={primary},{secondary},{bg} -->\n'
    if "<!DOCTYPE" in html:
        html = html.replace("<!DOCTYPE", meta + "<!DOCTYPE", 1)
    else:
        html = meta + html
    return html


def _llm_redesign(base_html: str, content: dict[str, Any], card: dict[str, Any]) -> str:
    palette = card.get("suggested_palette") or []
    layout = card.get("required_layout") or "عمود واحد مركزي"
    forbidden = card.get("forbidden_patterns") or []
    tone = card.get("tone_of_voice") or ""
    interaction = card.get("interaction_type") or ""

    # Truncate base to keep prompt small
    base_snip = base_html if len(base_html) < 6000 else base_html[:6000] + "\n<!-- truncated -->"

    prompt = f"""عدّل قالب HTML التالي ليصبح منتجاً جديداً وفق القيود.

=== القالب الأساسي ===
{base_snip}

=== المحتوى (ادمجه حرفياً) ===
{json.dumps(content, ensure_ascii=False, indent=2)}

=== قيود التنوع (إلزامية) ===
- الهيكل المطلوب: {layout}
- لوحة الألوان: {palette}
- الأنماط الممنوعة: {forbidden}
- النبرة: {tone}
- التفاعل: {interaction}

قواعد تقنية صارمة:
1. HTML واحد كامل مع CSS مضمن فقط
2. dir="rtl" و lang="ar"
3. ممنوع CDN أو مكتبات خارجية أو ملفات خارجية
4. الحجم النهائي يجب أن يكون صغيراً (أقل من 60KB نصاً)
5. استخدم ألوان suggested_palette في :root كمتغيرات CSS
6. لا تكرر الأنماط الممنوعة

أعد ملف HTML كاملاً فقط بدءاً من <!DOCTYPE html>
"""

    raw = generate_text(prompt, system_prompt=SYSTEM_PROMPT)
    # Extract HTML
    raw = raw.strip()
    if "```" in raw:
        m = re.search(r"```(?:html)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
    if "<!DOCTYPE" in raw.upper() or "<html" in raw.lower():
        start = raw.upper().find("<!DOCTYPE")
        if start == -1:
            start = raw.lower().find("<html")
        raw = raw[start:]
    if not re.search(r"<html", raw, re.I):
        raise ValueError("LLM output is not valid HTML")
    return raw


def design_product(
    diversity_path: str,
    content_path: str,
    templates_dir: str = "templates",
    output_path: str = "index.html",
    use_llm: bool = True,
) -> dict[str, Any]:
    card = _load_json(diversity_path)
    content = _load_json(content_path)
    base_path = _pick_base_template(templates_dir, card)
    base_html = base_path.read_text(encoding="utf-8")
    base_name = base_path.parent.name

    source = "fallback"
    try:
        if use_llm and available_providers():
            html = _llm_redesign(base_html, content, card)
            source = "llm"
        else:
            html = _inject_fallback(base_html, content, card)
    except (AllProvidersFailedError, ValueError, Exception) as exc:
        logger.warning("Design LLM failed (%s) — fallback injection", exc)
        html = _inject_fallback(base_html, content, card)
        source = "fallback"

    # Size guard: if too large, fall back to injection
    if len(html.encode("utf-8")) > MAX_BYTES:
        logger.warning("Generated HTML exceeds 80KB (%s bytes) — using fallback", len(html.encode("utf-8")))
        html = _inject_fallback(base_html, content, card)
        source = "fallback_size_limit"

    # Ensure RTL
    if 'dir="rtl"' not in html and "dir='rtl'" not in html:
        html = html.replace("<html", '<html lang="ar" dir="rtl"', 1)

    Path(output_path).write_text(html, encoding="utf-8")
    size = len(html.encode("utf-8"))
    meta = {
        "source": source,
        "base_template": base_name,
        "size_bytes": size,
        "output": output_path,
        "palette": card.get("suggested_palette"),
    }
    logger.info("Design done: source=%s size=%s base=%s", source, size, base_name)
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Design Agent")
    parser.add_argument("--diversity", default="diversity_card.json")
    parser.add_argument("--content", default="content.json")
    parser.add_argument("--templates-dir", default="templates")
    parser.add_argument("--output", "-o", default="index.html")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    print("🎨 Design Agent starting...")
    print(f"   Providers: {available_providers() or ['none']}")

    meta = design_product(
        diversity_path=args.diversity,
        content_path=args.content,
        templates_dir=args.templates_dir,
        output_path=args.output,
        use_llm=not args.no_llm,
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"✅ HTML written to {args.output} ({meta['size_bytes']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
