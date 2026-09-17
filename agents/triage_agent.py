#!/usr/bin/env python3
"""
Triage Agent — بوابة فرز الأفكار الواردة من GitHub Issues.

Usage:
  python agents/triage_agent.py --title "..." --description "..." [--category "..."] [--output result.json]
  echo '{"title":"...","description":"..."}' | python agents/triage_agent.py --stdin
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.arabic_normalize import normalize_arabic

_URL_RE = re.compile(r"(https?://|www\.|ftp://)[^\s<>\"']+", re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<\s*script|</\s*script|javascript\s*:|on\w+\s*=", re.IGNORECASE)
_CODE_EXEC_RE = re.compile(
    r"\b(eval\s*\(|exec\s*\(|__import__\s*\(|subprocess\.|os\.system\s*\()",
    re.IGNORECASE,
)
_SENSITIVE_RE = re.compile(
    r"(api[_-]?key|secret[_-]?key|password\s*[:=]|token\s*[:=]|Bearer\s+[A-Za-z0-9._\-]+)",
    re.IGNORECASE,
)


def _check_security(text: str) -> list[str]:
    reasons: list[str] = []
    if _URL_RE.search(text):
        reasons.append("يحتوي على روابط خارجية")
    if _SCRIPT_RE.search(text):
        reasons.append("يحتوي على أكواد script أو أحداث HTML خطرة")
    if _CODE_EXEC_RE.search(text):
        reasons.append("يحتوي على أكواد تنفيذية مشتبه بها")
    if _SENSITIVE_RE.search(text):
        reasons.append("يحتوي على بيانات حساسة محتملة (مفاتيح/كلمات مرور)")
    return reasons


def _one_line_summary(title: str, description: str) -> str:
    title = title.strip()
    desc = description.strip()
    if not desc:
        return title[:80]
    cut = re.split(r"[.。\n]", desc, maxsplit=1)[0].strip()
    if len(cut) > 60:
        cut = cut[:57] + "..."
    if title and cut and cut != title:
        return f"{title}: {cut}"
    return title or cut


def triage(
    title: str,
    description: str,
    category: str = "",
    constraints: str = "",
) -> dict[str, Any]:
    raw_title = (title or "").strip()
    raw_desc = (description or "").strip()
    raw_category = (category or "").strip()
    raw_constraints = (constraints or "").strip()
    combined = f"{raw_title}\n{raw_desc}\n{raw_constraints}"

    if not raw_title:
        return {
            "status": "rejected",
            "reason": "العنوان مفقود",
            "normalized_title": "",
            "normalized_description": "",
            "category": raw_category,
            "summary": "",
            "security_flags": [],
        }
    if not raw_desc:
        return {
            "status": "rejected",
            "reason": "الوصف مفقود",
            "normalized_title": normalize_arabic(raw_title),
            "normalized_description": "",
            "category": raw_category,
            "summary": "",
            "security_flags": [],
        }

    security_flags = _check_security(combined)
    if security_flags:
        return {
            "status": "rejected",
            "reason": "؛ ".join(security_flags),
            "normalized_title": normalize_arabic(raw_title),
            "normalized_description": normalize_arabic(raw_desc),
            "category": raw_category,
            "summary": "",
            "security_flags": security_flags,
        }

    norm_title = normalize_arabic(raw_title)
    norm_desc = normalize_arabic(raw_desc)
    summary = _one_line_summary(norm_title, norm_desc)

    return {
        "status": "approved",
        "reason": None,
        "normalized_title": norm_title,
        "normalized_description": norm_desc,
        "category": raw_category,
        "constraints": normalize_arabic(raw_constraints) if raw_constraints else "",
        "summary": summary,
        "security_flags": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage Agent — فرز الأفكار")
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--output", "-o", default="")
    args = parser.parse_args()

    if args.stdin:
        payload = json.load(sys.stdin)
        result = triage(
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            category=payload.get("category", ""),
            constraints=payload.get("constraints", ""),
        )
    else:
        result = triage(
            title=args.title,
            description=args.description,
            category=args.category,
            constraints=args.constraints,
        )

    out = json.dumps(result, ensure_ascii=False, indent=2)
    print(out)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"OK wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
