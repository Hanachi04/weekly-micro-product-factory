#!/usr/bin/env python3
"""
Triage Agent — بوابة فرز الأفكار الواردة من GitHub Issues أو workflow_dispatch.

Usage:
  python agents/triage_agent.py --title "..." --description "..." [--category "..."] [--output result.json]
  python agents/triage_agent.py --issue-body "..." --output result.json
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

# Friendly Arabic rejection messages keyed by reason code
_USER_MESSAGES = {
    "missing_title": (
        "شكراً لاهتمامك بالمشروع! 🙏\n\n"
        "لاحظنا أن **عنوان المنتج** غير موجود أو فارغ. "
        "العنوان يساعد المصنع على فهم الفكرة بسرعة.\n\n"
        "عدّل الـ Issue وأضف عنواناً واضحاً، وسنراجعها مجدداً بكل سرور. ✨"
    ),
    "missing_description": (
        "شكراً لفكرتك! 🌱\n\n"
        "الوصف مفقود أو قصير جداً. نحتاج سطراً أو اثنين يشرحان ماذا يفعل المنتج ولمن يفيد.\n\n"
        "أضف وصفاً موجزاً ثم أعد فتح الـ Issue أو أنشئ واحداً جديداً. نحن بانتظارك!"
    ),
    "external_links": (
        "شكراً لفكرتك! 😊\n\n"
        "لاحظنا أنها تحتوي على **روابط خارجية**. "
        "منتجات المصنع تعمل بدون إنترنت ولا تعتمد على مواقع خارجية، "
        "لذلك نتجنب الروابط في مرحلة الفكرة.\n\n"
        "احذف الروابط وأعد تقديم الفكرة — سنكون سعداء بمراجعتها. 🚀"
    ),
    "dangerous_code": (
        "شكراً لمشاركتك.\n\n"
        "تم رفض الفكرة لأنها تحتوي على أكواد أو أنماط تنفيذية غير مسموحة "
        "(مثل script أو أوامر نظام). المصنع ينتج صفحات HTML ثابتة وآمنة فقط.\n\n"
        "صِغ الفكرة كنص وصفي بسيط بدون أكواد، وسنرحب بها."
    ),
    "sensitive_data": (
        "شكراً لتنبيهك.\n\n"
        "يبدو أن النص يحتوي على بيانات حساسة محتملة (مفاتيح أو كلمات مرور). "
        "لا نقبل مثل هذه المحتويات حفاظاً على أمان المجتمع.\n\n"
        "أزل أي أسرار وأعد التقديم إن رغبت."
    ),
    "generic": (
        "شكراً لفكرتك! 🙏\n\n"
        "لم تجتز الفكرة بوابة الفرز الآلي لهذه الدورة. "
        "يمكنك تعديلها وفق ملاحظات المصنع وإعادة التقديم.\n\n"
        "نرحب دائماً بأفكار بسيطة، عربية، وتعمل بدون إنترنت."
    ),
}


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


def _reason_code(security_flags: list[str], missing: str | None) -> str:
    if missing == "title":
        return "missing_title"
    if missing == "description":
        return "missing_description"
    joined = " ".join(security_flags)
    if "روابط" in joined:
        return "external_links"
    if "script" in joined.lower() or "تنفيذ" in joined:
        return "dangerous_code"
    if "حساسة" in joined:
        return "sensitive_data"
    return "generic"


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
    """Extract fields from GitHub Issue Form markdown body."""
    body = body or ""
    fields = {"title": "", "description": "", "category": "", "constraints": ""}

    # Pattern: ### Label\n\nvalue
    sections = re.split(r"\n###\s+", body)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        label = lines[0].strip().lower()
        value = lines[1].strip() if len(lines) > 1 else ""
        # strip checkbox leftovers
        value = re.sub(r"^\s*-\s*\[[ xX]\]\s*.*$", "", value, flags=re.M).strip()
        if "عنوان" in label:
            fields["title"] = value.split("\n")[0].strip()
        elif "وصف" in label:
            fields["description"] = value.strip()
        elif "فئة" in label or "category" in label:
            fields["category"] = value.split("\n")[0].strip()
        elif "قيود" in label or "ملاحظات" in label:
            fields["constraints"] = value.strip()

    # Fallback: if form parse failed, use first non-empty line as title
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
) -> dict[str, Any]:
    raw_title = (title or "").strip()
    raw_desc = (description or "").strip()
    raw_category = (category or "").strip()
    raw_constraints = (constraints or "").strip()
    combined = f"{raw_title}\n{raw_desc}\n{raw_constraints}"

    def _rejected(reason: str, code: str, flags: list[str] | None = None, missing: str | None = None) -> dict:
        return {
            "status": "rejected",
            "reason": reason,
            "reason_code": code,
            "user_message": _USER_MESSAGES.get(code, _USER_MESSAGES["generic"]),
            "normalized_title": normalize_arabic(raw_title) if raw_title else "",
            "normalized_description": normalize_arabic(raw_desc) if raw_desc else "",
            "category": raw_category,
            "summary": "",
            "security_flags": flags or [],
            "source": source,
            "issue_number": issue_number,
        }

    if not raw_title:
        return _rejected("العنوان مفقود", "missing_title", missing="title")
    if not raw_desc:
        return _rejected("الوصف مفقود", "missing_description", missing="description")

    security_flags = _check_security(combined)
    if security_flags:
        code = _reason_code(security_flags, None)
        return _rejected("؛ ".join(security_flags), code, flags=security_flags)

    norm_title = normalize_arabic(raw_title)
    norm_desc = normalize_arabic(raw_desc)
    summary = _one_line_summary(norm_title, norm_desc)

    return {
        "status": "approved",
        "reason": None,
        "reason_code": None,
        "user_message": (
            f"تم قبول فكرتك: **{norm_title}** ✅\n\n"
            "ستدخل دورة الإنتاج الذكية قريباً. "
            "ستجد المنتج في مجلد `products/weekly/` بعد اكتمال البناء.\n\n"
            "شكراً لمساهمتك في مصنع المنتجات المصغرة! 🏭✨"
        ),
        "normalized_title": norm_title,
        "normalized_description": norm_desc,
        "category": raw_category,
        "constraints": normalize_arabic(raw_constraints) if raw_constraints else "",
        "summary": summary,
        "security_flags": [],
        "source": source,
        "issue_number": issue_number,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage Agent — فرز الأفكار")
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--issue-body", default="", help="Raw GitHub issue body (form markdown)")
    parser.add_argument("--issue-title", default="", help="GitHub issue title line")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--issue-number", type=int, default=0)
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
            source=payload.get("source", "manual"),
            issue_number=payload.get("issue_number"),
        )
    elif args.issue_body:
        fields = parse_issue_body(args.issue_body)
        # Prefer explicit product title from form; fall back to issue title
        title = fields["title"] or args.issue_title
        # Strip [فكرة] prefix from issue title if used as fallback
        title = re.sub(r"^\[فكرة\]\s*", "", title).strip()
        result = triage(
            title=title,
            description=fields["description"],
            category=fields["category"],
            constraints=fields["constraints"],
            source=args.source or "github_issue",
            issue_number=args.issue_number or None,
        )
    else:
        result = triage(
            title=args.title,
            description=args.description,
            category=args.category,
            constraints=args.constraints,
            source=args.source,
            issue_number=args.issue_number or None,
        )

    out = json.dumps(result, ensure_ascii=False, indent=2)
    print(out)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"OK wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
