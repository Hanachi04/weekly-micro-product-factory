#!/usr/bin/env python3
"""
Content Agent — يولّد نصوص المنتج بالعربية وفق نبرة بطاقة التنوع.

Usage:
  python agents/content_agent.py \
    --idea-title "..." --idea-description "..." \
    --diversity diversity_card.json \
    --output content.json
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
from utils.i18n import get_text, resolve_lang

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("content_agent")

SYSTEM_PROMPT = (
    "أنت كاتب منتجات رقمية عربية. اكتب نصوص واجهة قصيرة وواضحة. "
    "التزم بالنبرة المطلوبة حرفياً. أجب بـ JSON فقط بدون markdown."
)

FALLBACK_CONTENT = {
    "title": "منتج مصغّر",
    "description": "أداة بسيطة وخفيفة تعمل مباشرة من المتصفح بدون إنترنت.",
    "cta_primary": "ابدأ",
    "cta_secondary": "إعادة",
    "labels": {"input": "أدخل قيمة", "result": "النتيجة", "status": "الحالة"},
    "messages": {
        "success": "تم بنجاح",
        "error": "حدث خطأ، حاول مرة أخرى",
        "empty": "لا توجد بيانات بعد",
    },
    "footer": "منتج من مصنع المنتجات المصغرة الأسبوعي",
    "source": "fallback",
}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object in model output")
    return json.loads(text[start : end + 1])


def _load_diversity(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def generate_content(
    idea_title: str,
    idea_description: str,
    diversity_path: str = "diversity_card.json",
    use_llm: bool = True,
) -> dict[str, Any]:
    card = _load_diversity(diversity_path)
    tone = card.get("tone_of_voice") or "واضح وعملي"
    layout = card.get("required_layout") or ""
    interaction = card.get("interaction_type") or ""

    lang = resolve_lang()
    if not use_llm or not available_providers():
        logger.info("No LLM — using fallback content")
        out = dict(FALLBACK_CONTENT)
        out["title"] = idea_title or get_text("content.fallback_title", lang)
        out["description"] = (idea_description or get_text("content.fallback_description", lang))[:200]
        out["cta_primary"] = get_text("content.cta_primary", lang)
        out["cta_secondary"] = get_text("content.cta_secondary", lang)
        out["footer"] = get_text("content.footer", lang)
        out["tone_applied"] = tone
        out["lang"] = lang
        return out

    prompt = f"""أنشئ نصوص واجهة عربية لمنتج رقمي ثابت (صفحة HTML واحدة).

الفكرة:
- العنوان المقترح: {idea_title}
- الوصف: {idea_description}

قيود بطاقة التنوع (إلزامية):
- النبرة (tone_of_voice): {tone}
- الهيكل المطلوب: {layout}
- نوع التفاعل: {interaction}

التزم بالنبرة بدقة. لا تستخدم أسلوباً مختلفاً عنها.

أعد JSON بالمفاتيح التالية فقط:
{{
  "title": "عنوان جذاب قصير",
  "description": "وصف 50-80 كلمة يشرح القيمة",
  "cta_primary": "نص الزر الرئيسي",
  "cta_secondary": "نص زر ثانوي إن لزم",
  "labels": {{"input": "...", "result": "...", "status": "..."}},
  "messages": {{"success": "...", "error": "...", "empty": "..."}},
  "footer": "سطر تذييل قصير"
}}
"""

    try:
        raw = generate_text(prompt, system_prompt=SYSTEM_PROMPT)
        data = _extract_json(raw)
        for key, default in FALLBACK_CONTENT.items():
            if key not in data and key != "source":
                data[key] = default
        data["tone_applied"] = tone
        data["source"] = "llm"
        return data
    except (AllProvidersFailedError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Content LLM failed (%s) — fallback", exc)
        out = dict(FALLBACK_CONTENT)
        out["title"] = idea_title or out["title"]
        out["description"] = (idea_description or out["description"])[:200]
        out["tone_applied"] = tone
        out["source"] = "fallback"
        out["error"] = str(exc)
        return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Content Agent")
    parser.add_argument("--idea-title", required=True)
    parser.add_argument("--idea-description", default="")
    parser.add_argument("--diversity", default="diversity_card.json")
    parser.add_argument("--output", "-o", default="content.json")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    print("✍️ Content Agent starting...")
    print(f"   Providers: {available_providers() or ['none']}")

    content = generate_content(
        idea_title=args.idea_title,
        idea_description=args.idea_description,
        diversity_path=args.diversity,
        use_llm=not args.no_llm,
    )

    out = json.dumps(content, ensure_ascii=False, indent=2)
    Path(args.output).write_text(out, encoding="utf-8")
    print(out)
    print(f"✅ content written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
