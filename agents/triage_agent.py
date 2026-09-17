#!/usr/bin/env python3
"""Triage Agent — idea gate with bilingual messages."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.arabic_normalize import normalize_arabic
from utils.i18n import get_text, resolve_lang

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
        reasons.append("external_links")
    if _SCRIPT_RE.search(text) or _CODE_EXEC_RE.search(text):
        reasons.append("dangerous_code")
    if _SENSITIVE_RE.search(text):
        reasons.append("sensitive_data")
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


def parse_issue_body(body: str) -> dict[str, str]:
    body = body or ""
    fields = {"title": "", "description": "", "category": "", "constraints": ""}
    sections = re.split(r"\n###\s+", body)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        label = lines[0].strip().lower()
        value = lines[1].strip() if len(lines) > 1 else ""
        value = re.sub(r"^\s*-\s*\[[ xX]\]\s*.*$", "", value, flags=re.M).strip()
        if "عنوان" in label or "title" in label or "product name" in label:
            fields["title"] = value.split("\n")[0].strip()
        elif "وصف" in label or "description" in label:
            fields["description"] = value.strip()
        elif "فئة" in label or "category" in label:
            fields["category"] = value.split("\n")[0].strip()
        elif "قيود" in label or "ملاحظات" in label or "constraint" in label or "notes" in label:
            fields["constraints"] = value.strip()
    if not fields["title"]:
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                fields["title"] = line[:120]
                break
    return fields


def triage(
    title: str,
    description: str,
    category: str = "",
    constraints: str = "",
    source: str = "manual",
    issue_number: int | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    lang = resolve_lang(lang)
    raw_title = (title or "").strip()
    raw_desc = (description or "").strip()
    raw_category = (category or "").strip()
    raw_constraints = (constraints or "").strip()
    combined = f"{raw_title}\n{raw_desc}\n{raw_constraints}"

    def _rejected(code: str, flags: list[str] | None = None) -> dict:
        reason_key = f"triage.reason.{code}"
        msg_key = {
            "missing_title": "triage.missing_title",
            "missing_description": "triage.missing_description",
            "external_links": "triage.external_links",
            "dangerous_code": "triage.dangerous_code",
            "sensitive_data": "triage.sensitive_data",
        }.get(code, "triage.generic_reject")
        return {
            "status": "rejected",
            "reason": get_text(reason_key, lang),
            "reason_code": code,
            "user_message": get_text(msg_key, lang),
            "normalized_title": normalize_arabic(raw_title) if raw_title else "",
            "normalized_description": normalize_arabic(raw_desc) if raw_desc else "",
            "category": raw_category,
            "summary": "",
            "security_flags": flags or [],
            "source": source,
            "issue_number": issue_number,
            "lang": lang,
        }

    if not raw_title:
        return _rejected("missing_title")
    if not raw_desc:
        return _rejected("missing_description")

    security_flags = _check_security(combined)
    if security_flags:
        return _rejected(security_flags[0], flags=security_flags)

    norm_title = normalize_arabic(raw_title)
    norm_desc = normalize_arabic(raw_desc)
    return {
        "status": "approved",
        "reason": None,
        "reason_code": None,
        "user_message": get_text("triage.approved", lang, title=norm_title),
        "normalized_title": norm_title,
        "normalized_description": norm_desc,
        "category": raw_category,
        "constraints": normalize_arabic(raw_constraints) if raw_constraints else "",
        "summary": _one_line_summary(norm_title, norm_desc),
        "security_flags": [],
        "source": source,
        "issue_number": issue_number,
        "lang": lang,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage Agent")
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--issue-body", default="")
    parser.add_argument("--issue-title", default="")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--issue-number", type=int, default=0)
    parser.add_argument("--lang", default="")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--output", "-o", default="")
    args = parser.parse_args()

    lang = args.lang or None

    if args.stdin:
        payload = json.load(sys.stdin)
        result = triage(
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            category=payload.get("category", ""),
            constraints=payload.get("constraints", ""),
            source=payload.get("source", "manual"),
            issue_number=payload.get("issue_number"),
            lang=payload.get("lang") or lang,
        )
    elif args.issue_body:
        fields = parse_issue_body(args.issue_body)
        title = fields["title"] or args.issue_title
        title = re.sub(r"^\[(?:فكرة|Idea)\]\s*", "", title, flags=re.I).strip()
        result = triage(
            title=title,
            description=fields["description"],
            category=fields["category"],
            constraints=fields["constraints"],
            source=args.source or "github_issue",
            issue_number=args.issue_number or None,
            lang=lang,
        )
    else:
        result = triage(
            title=args.title,
            description=args.description,
            category=args.category,
            constraints=args.constraints,
            source=args.source,
            issue_number=args.issue_number or None,
            lang=lang,
        )

    out = json.dumps(result, ensure_ascii=False, indent=2)
    print(out)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
