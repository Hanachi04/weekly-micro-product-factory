#!/usr/bin/env python3
"""Adversarial critic — strict but fair pre-publish review."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.llm_client import generate_text, AllProvidersFailedError, available_providers
from utils.i18n import resolve_lang

MAX_BYTES = 80 * 1024


def _load(path: str) -> Any:
    p = Path(path)
    if not p.exists():
        return {}
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    return p.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no json")
    return json.loads(text[start : end + 1])


def _heuristic_review(html: str, card: dict, content: dict, lang: str) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    suggestions: list[str] = []
    score = 8.5

    size = len((html or "").encode("utf-8"))
    if size > MAX_BYTES:
        issues.append({"severity": "high", "msg": f"Size {size} exceeds 80KB"})
        suggestions.append("Reduce inline CSS/JS; simplify markup")
        score -= 3
    if not re.search(r"<html", html or "", re.I):
        issues.append({"severity": "high", "msg": "Missing <html> root"})
        score -= 2
    if not re.search(r"<body", html or "", re.I):
        issues.append({"severity": "high", "msg": "Missing <body>"})
        score -= 2

    if lang == "ar":
        if 'dir="rtl"' not in (html or "") and "dir='rtl'" not in (html or ""):
            issues.append({"severity": "high", "msg": "Arabic product missing dir=rtl"})
            suggestions.append('Add dir="rtl" lang="ar" on <html>')
            score -= 1.5

    palette = card.get("suggested_palette") or []
    found = [c for c in palette if c and c.lower() in (html or "").lower()]
    if palette and not found:
        issues.append({
            "severity": "medium",
            "msg": "None of suggested_palette colors found in HTML",
        })
        suggestions.append(f"Apply palette colors: {', '.join(palette[:3])}")
        score -= 1.5
    elif palette and len(found) < min(2, len(palette)):
        issues.append({
            "severity": "low",
            "msg": f"Only {len(found)}/{len(palette)} palette colors applied",
        })
        score -= 0.5

    forbidden = card.get("forbidden_patterns") or []
    hits = [p for p in forbidden if p and str(p).lower() in (html or "").lower()]
    if hits:
        issues.append({
            "severity": "medium",
            "msg": f"Possible forbidden pattern text: {hits[:3]}",
        })
        suggestions.append("Remove or rephrase forbidden pattern echoes")
        score -= 1.0

    title = (content.get("title") or "").strip()
    if not title:
        issues.append({"severity": "medium", "msg": "Content title empty"})
        score -= 1.0
    desc = (content.get("description") or "").strip()
    if desc and len(desc) < 20:
        issues.append({"severity": "low", "msg": "Description very short"})
        score -= 0.3

    # empty interactive traps
    if re.search(r"<button[^>]*>\s*</button>", html or "", re.I):
        issues.append({"severity": "low", "msg": "Empty button label"})
        score -= 0.4

    score = max(0.0, min(10.0, round(score, 1)))
    high = any(i["severity"] == "high" for i in issues)
    verdict = "needs_revision" if high or score < 6.0 else "approved"
    return {
        "score": score,
        "issues": issues,
        "suggestions": suggestions,
        "verdict": verdict,
        "source": "heuristic",
    }


def _llm_review(html: str, card: dict, content: dict, lang: str) -> dict[str, Any]:
    html_snip = html if len(html) < 5000 else html[:5000] + "\n<!-- truncated -->"
    prompt = f"""You are a strict but fair product critic for offline static HTML micro-products.
Language of review notes: {"Arabic" if lang == "ar" else "English"}.

Diversity card constraints:
{json.dumps(card, ensure_ascii=False)[:1500]}

Content package:
{json.dumps(content, ensure_ascii=False)[:800]}

HTML (may be truncated):
{html_snip}

Return JSON only:
{{
  "score": 0-10 number,
  "issues": [{{"severity": "high|medium|low", "msg": "..."}}],
  "suggestions": ["..."],
  "verdict": "approved" or "needs_revision"
}}
Rules: prefer approved unless real problems (missing RTL for Arabic, ignored palette, broken structure, empty UX).
"""
    raw = generate_text(
        prompt,
        system_prompt="You review static HTML products. Reply with JSON only.",
    )
    data = _extract_json(raw)
    data["source"] = "llm"
    if "verdict" not in data:
        data["verdict"] = "approved" if float(data.get("score") or 0) >= 6 else "needs_revision"
    return data


def review(
    html_path: str,
    diversity_path: str = "diversity_card.json",
    content_path: str = "content.json",
    lang: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    lang = resolve_lang(lang)
    html = _load(html_path) if not str(html_path).endswith(".json") else ""
    if isinstance(html, dict):
        html = ""
    html = html if isinstance(html, str) else Path(html_path).read_text(encoding="utf-8")
    card = _load(diversity_path) if Path(diversity_path).exists() else {}
    content = _load(content_path) if Path(content_path).exists() else {}
    if not isinstance(card, dict):
        card = {}
    if not isinstance(content, dict):
        content = {}

    base = _heuristic_review(html, card, content, lang)
    if use_llm and available_providers():
        try:
            llm = _llm_review(html, card, content, lang)
            # merge: take lower score, union issues
            score = round(min(float(base["score"]), float(llm.get("score") or base["score"])), 1)
            issues = list(base.get("issues") or []) + list(llm.get("issues") or [])
            # dedupe by msg
            seen = set()
            uniq = []
            for i in issues:
                m = i.get("msg")
                if m in seen:
                    continue
                seen.add(m)
                uniq.append(i)
            suggestions = list(dict.fromkeys(
                list(base.get("suggestions") or []) + list(llm.get("suggestions") or [])
            ))
            high = any(i.get("severity") == "high" for i in uniq)
            verdict = "needs_revision" if high or score < 6.0 else "approved"
            # fair default: if heuristic approved and llm harsh without high issues, soften
            if base["verdict"] == "approved" and not high and score >= 5.5:
                verdict = "approved"
            return {
                "score": score,
                "issues": uniq[:12],
                "suggestions": suggestions[:8],
                "verdict": verdict,
                "source": "heuristic+llm",
            }
        except (AllProvidersFailedError, ValueError, json.JSONDecodeError, Exception) as exc:
            base["llm_error"] = str(exc)
            return base
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Adversarial critic agent")
    parser.add_argument("--html", required=True)
    parser.add_argument("--diversity", default="diversity_card.json")
    parser.add_argument("--content", default="content.json")
    parser.add_argument("--lang", default="")
    parser.add_argument("--output", "-o", default="critic_report.json")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    report = review(
        html_path=args.html,
        diversity_path=args.diversity,
        content_path=args.content,
        lang=args.lang or None,
        use_llm=not args.no_llm,
    )
    out = json.dumps(report, ensure_ascii=False, indent=2)
    Path(args.output).write_text(out, encoding="utf-8")
    print(out)
    print(f"verdict={report.get('verdict')} score={report.get('score')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
