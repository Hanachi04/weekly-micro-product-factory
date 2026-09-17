#!/usr/bin/env python3
"""Select the highest-voted approved open idea via GitHub Reactions (👍)."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
REPO = os.environ.get("GITHUB_REPOSITORY", "")
VOTE_MARKER = "<!-- factory-vote-ballot -->"


def api(path: str) -> Any:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "weekly-micro-product-factory",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def list_approved_open() -> list[dict]:
    # Search open issues with approved label
    q = f"repo:{REPO} is:issue is:open label:approved"
    data = api(f"/search/issues?q={urllib.request.quote(q)}&sort=created&order=asc&per_page=50")
    return data.get("items") or []


def ballot_plus_ones(issue_number: int) -> int:
    comments = api(f"/repos/{REPO}/issues/{issue_number}/comments?per_page=100")
    ballot_id = None
    for c in comments:
        if VOTE_MARKER in (c.get("body") or ""):
            ballot_id = c["id"]
            break
    if not ballot_id:
        return 0
    # reactions on the ballot comment
    try:
        reactions = api(f"/repos/{REPO}/issues/comments/{ballot_id}/reactions?per_page=100")
    except urllib.error.HTTPError:
        return 0
    return sum(1 for r in reactions if r.get("content") == "+1")


def parse_fields(body: str, title: str) -> tuple[str, str]:
    body = body or ""
    fields = {"title": "", "description": ""}
    sections = re.split(r"\n###\s+", body)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        label = lines[0].strip().lower()
        value = lines[1].strip() if len(lines) > 1 else ""
        value = re.sub(r"^\s*-\s*\[[ xX]\]\s*.*$", "", value, flags=re.M).strip()
        if "عنوان" in label:
            fields["title"] = value.split("\n")[0].strip()
        elif "وصف" in label:
            fields["description"] = value.strip()
    title_clean = re.sub(r"^\[فكرة\]\s*", "", title or "").strip()
    idea_title = fields["title"] or title_clean
    idea_desc = fields["description"] or title_clean
    return idea_title, idea_desc


def main() -> int:
    if not TOKEN or not REPO:
        print("ERROR: GITHUB_TOKEN and GITHUB_REPOSITORY required", file=sys.stderr)
        return 1

    issues = list_approved_open()
    ranked = []
    for issue in issues:
        num = issue["number"]
        votes = ballot_plus_ones(num)
        ranked.append({
            "number": num,
            "votes": votes,
            "created_at": issue.get("created_at") or "",
            "title": issue.get("title") or "",
            "body": issue.get("body") or "",
            "html_url": issue.get("html_url") or "",
        })

    # highest votes, then oldest
    ranked.sort(key=lambda x: (-x["votes"], x["created_at"]))

    out_path = sys.argv[1] if len(sys.argv) > 1 else "selected_idea.json"
    if not ranked:
        result = {"selected": False, "reason": "no_approved_open_issues"}
        open(out_path, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    top = ranked[0]
    idea_title, idea_desc = parse_fields(top["body"], top["title"])
    result = {
        "selected": True,
        "issue_number": top["number"],
        "votes": top["votes"],
        "idea_title": idea_title,
        "idea_description": idea_desc,
        "issue_url": top["html_url"],
        "candidates": [
            {"number": r["number"], "votes": r["votes"], "title": r["title"]}
            for r in ranked[:10]
        ],
    }
    open(out_path, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
