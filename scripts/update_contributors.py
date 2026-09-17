#!/usr/bin/env python3
"""Update catalog/contributors.json reputation after a successful publish."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRIB_PATH = ROOT / "catalog" / "contributors.json"
API = "https://api.github.com"


def load() -> dict[str, Any]:
    if CONTRIB_PATH.exists():
        return json.loads(CONTRIB_PATH.read_text(encoding="utf-8"))
    return {"contributors": [], "last_updated": None}


def save(data: dict[str, Any]) -> None:
    CONTRIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    CONTRIB_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def api_get(path: str, token: str) -> Any:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "weekly-micro-product-factory",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def resolve_username(issue_number: str, repo: str, token: str) -> str | None:
    if not issue_number or not token:
        return None
    try:
        issue = api_get(f"/repos/{repo}/issues/{issue_number}", token)
    except urllib.error.HTTPError:
        return None
    labels = [l.get("name") for l in (issue.get("labels") or [])]
    if "no-tracking" in labels:
        print("Issue has no-tracking — skip reputation")
        return None
    return (issue.get("user") or {}).get("login")


def upsert(
    username: str,
    *,
    produced: bool,
    week: str,
    diversity_score: float | None,
) -> dict[str, Any]:
    data = load()
    rows = data.get("contributors") or []
    row = next((c for c in rows if c.get("username") == username), None)
    if row is None:
        row = {
            "username": username,
            "ideas_submitted": 0,
            "ideas_produced": 0,
            "avg_diversity_score": None,
            "diversity_sum": 0.0,
            "diversity_count": 0,
            "last_contribution": None,
        }
        rows.append(row)

    if produced:
        row["ideas_produced"] = int(row.get("ideas_produced") or 0) + 1
        row["ideas_submitted"] = max(
            int(row.get("ideas_submitted") or 0), int(row["ideas_produced"])
        )
        if diversity_score is not None:
            row["diversity_sum"] = float(row.get("diversity_sum") or 0) + float(
                diversity_score
            )
            row["diversity_count"] = int(row.get("diversity_count") or 0) + 1
            row["avg_diversity_score"] = round(
                row["diversity_sum"] / max(row["diversity_count"], 1), 1
            )
        row["last_contribution"] = week

    rows.sort(
        key=lambda c: (
            -int(c.get("ideas_produced") or 0),
            -(float(c.get("avg_diversity_score") or 0)),
        )
    )
    data["contributors"] = rows
    save(data)
    return row


def main() -> int:
    issue = (os.environ.get("SOURCE_ISSUE") or "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    week = os.environ.get("WEEK_ID") or ""
    div_raw = os.environ.get("DIVERSITY_SCORE") or ""
    diversity = float(div_raw) if div_raw not in ("", "None", "null") else None
    username = (os.environ.get("CONTRIBUTOR") or "").strip()

    if not username and issue:
        username = resolve_username(issue, repo, token) or ""

    if not username:
        print("No contributor to update")
        data = load()
        save(data)
        return 0

    row = upsert(username, produced=True, week=week, diversity_score=diversity)
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
