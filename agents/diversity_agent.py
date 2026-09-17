#!/usr/bin/env python3
"""
Diversity Agent — يولّد بطاقة تنوع تمنع تشابه المنتج الجديد مع المنتجات السابقة.

Usage:
  python agents/diversity_agent.py \
    --idea-title "..." --idea-description "..." \
    --catalog catalog/index.json \
    --output diversity_card.json
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
logger = logging.getLogger("diversity_agent")

SYSTEM_PROMPT = (
    "أنت وكيل تنوع في مصنع منتجات رقمية عربية ثابتة (HTML/CSS خفيفة). "
    "مهمتك: فرض قيود صارمة تمنع تكرار ألوان وهياكل وأسلوب المنتجات السابقة. "
    "أجب بـ JSON فقط بدون شرح إضافي وبدون markdown."
)

FALLBACK_CARD = {
    "forbidden_colors": ["#2b6cb0", "#38b2ac", "#2c7a7b"],
    "required_layout": "عمود واحد مركزي مع بطاقة كبيرة بدلاً من شبكة أو جدول",
    "tone_of_voice": "مباشر وعملي، جمل قصيرة",
    "interaction_type": "أزرار بسيطة فقط بدون سحب أو نماذج معقدة",
    "forbidden_patterns": ["حاسبة", "صفحة هبوط تسويقية", "متتبع عادات أسبوعي"],
    "suggested_palette": ["#1a365d", "#ed8936", "#f7fafc"],
    "notes": "بطاقة احتياطية حتمية — لم يُستخدم LLM",
}


def _load_catalog(path: str, limit: int = 12) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        logger.warning("Catalog not found: %s", path)
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    products = data.get("products") or []
    return products[:limit]


def _summarize_history(products: list[dict[str, Any]]) -> str:
    if not products:
        return "لا توجد منتجات سابقة."
    lines = []
    for i, p in enumerate(products, 1):
        lines.append(
            f"{i}. week={p.get('week')} | title={p.get('title')} | "
            f"template={p.get('template')} | desc={str(p.get('description', ''))[:80]}"
        )
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start : end + 1])


def build_diversity_card(
    idea_title: str,
    idea_description: str,
    catalog_path: str = "catalog/index.json",
    use_llm: bool = True,
) -> dict[str, Any]:
    products = _load_catalog(catalog_path)
    history = _summarize_history(products)

    if not use_llm or not available_providers():
        logger.info("No LLM providers configured — using deterministic fallback card")
        card = dict(FALLBACK_CARD)
        card["based_on_products"] = [p.get("week") for p in products[:8]]
        card["idea_title"] = idea_title
        card["source"] = "fallback"
        return card

    prompt = f"""بناءً على قائمة المنتجات السابقة التالية، استخرج الأنماط المتكررة
(ألوان شائعة، أنواع الهياكل، أساليب الكتابة، أنواع التفاعل)،
ثم أنشئ بطاقة تنوع صارمة للمنتج الجديد.

المنتجات السابقة:
{history}

الفكرة الجديدة:
- العنوان: {idea_title}
- الوصف: {idea_description}

أعد كائن JSON بالمفاتيح التالية فقط:
{{
  "forbidden_colors": ["قائمة ألوان hex يُمنع تكرارها"],
  "required_layout": "وصف هيكل مختلف إلزامي",
  "tone_of_voice": "أسلوب كتابة مختلف",
  "interaction_type": "نوع تفاعل مختلف",
  "forbidden_patterns": ["أنماط منتجات سابقة يجب تجنبها"],
  "suggested_palette": ["3 ألوان مقترحة للمنتج الجديد"],
  "notes": "ملاحظة قصيرة بالعربية"
}}
"""

    try:
        raw = generate_text(prompt, system_prompt=SYSTEM_PROMPT)
        card = _extract_json(raw)
        for key, default in FALLBACK_CARD.items():
            if key not in card:
                card[key] = default
        card["based_on_products"] = [p.get("week") for p in products[:8]]
        card["idea_title"] = idea_title
        card["source"] = "llm"
        return card
    except (AllProvidersFailedError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("LLM diversity card failed (%s) — using fallback", exc)
        card = dict(FALLBACK_CARD)
        card["based_on_products"] = [p.get("week") for p in products[:8]]
        card["idea_title"] = idea_title
        card["source"] = "fallback"
        card["error"] = str(exc)
        return card


def main() -> int:
    parser = argparse.ArgumentParser(description="Diversity Agent")
    parser.add_argument("--idea-title", required=True)
    parser.add_argument("--idea-description", default="")
    parser.add_argument("--catalog", default="catalog/index.json")
    parser.add_argument("--output", "-o", default="diversity_card.json")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    print("Diversity Agent starting...")
    print(f"Providers available: {available_providers() or ['none']}")

    card = build_diversity_card(
        idea_title=args.idea_title,
        idea_description=args.idea_description,
        catalog_path=args.catalog,
        use_llm=not args.no_llm,
    )

    out = json.dumps(card, ensure_ascii=False, indent=2)
    Path(args.output).write_text(out, encoding="utf-8")
    print(out)
    print(f"OK Diversity card written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
