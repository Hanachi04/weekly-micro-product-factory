#!/usr/bin/env python3
"""Generate static RTL stats dashboard from catalog/index.json."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "index.json"
OUT = ROOT / "stats" / "index.html"


def load_catalog() -> dict:
    if not CATALOG.exists():
        return {"products": [], "total_count": 0, "last_updated": None}
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def build_html(catalog: dict) -> str:
    products = catalog.get("products") or []
    total = len(products)
    ai = sum(1 for p in products if p.get("build_method") == "ai_generated")
    det = total - ai
    issues = [p.get("source_issue_number") for p in products if p.get("source_issue_number")]
    unique_issues = len(set(str(i) for i in issues if i))

    # diversity tags aggregate
    tags: dict[str, int] = {}
    for p in products:
        for t in p.get("diversity_tags") or []:
            tags[str(t)] = tags.get(str(t), 0) + 1
    top_tags = sorted(tags.items(), key=lambda x: -x[1])[:8]

    last5 = products[:5]
    cards = ""
    for p in last5:
        week = p.get("week", "")
        title = p.get("title", "منتج")
        method = "ذكي" if p.get("build_method") == "ai_generated" else "حتمي"
        path = p.get("path") or f"products/weekly/{week}"
        src = p.get("source_issue_number")
        src_html = f'<span class="badge">Issue #{src}</span>' if src else ""
        cards += f'''
      <a class="card" href="../{path}/">
        <div class="week">{week}</div>
        <h3>{title}</h3>
        <div class="meta"><span class="badge">{method}</span> {src_html}</div>
      </a>'''

    tags_html = "".join(f'<span class="tag">{t} ({c})</span>' for t, c in top_tags) or '<span class="muted">لا توجد وسوم تنوع بعد</span>'

    story = (
        f"أنتج المجتمع <strong>{total}</strong> أداة رقمية"
        if total
        else "لم تُنشر منتجات بعد — كن أول من يقدّم فكرة!"
    )
    if unique_issues:
        story += f" انطلاقاً من <strong>{unique_issues}</strong> فكرة مجتمعية."
    if ai and total:
        story += f" منها <strong>{ai}</strong> مولَّدة بالذكاء الاصطناعي."

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    last = catalog.get("last_updated") or now

    return f'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>لوحة إحصائيات المصنع</title>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--accent:#38bdf8;--ok:#34d399;--warm:#f59e0b}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,"Segoe UI",Tahoma,Arial,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;padding:1.25rem}}
.wrap{{max-width:920px;margin:0 auto}}
h1{{font-size:1.5rem;margin-bottom:.35rem}}
.story{{color:var(--muted);margin-bottom:1.5rem;font-size:1.05rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.75rem;margin-bottom:1.5rem}}
.stat{{background:var(--card);border-radius:12px;padding:1rem;text-align:center}}
.stat .n{{font-size:1.75rem;font-weight:700;color:var(--accent)}}
.stat .l{{font-size:.8rem;color:var(--muted);margin-top:.25rem}}
h2{{font-size:1.1rem;margin:1.25rem 0 .75rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.75rem}}
.card{{display:block;background:var(--card);border-radius:12px;padding:1rem;text-decoration:none;color:inherit;border:1px solid transparent;transition:border-color .15s}}
.card:hover{{border-color:var(--accent)}}
.card .week{{font-size:.75rem;color:var(--muted)}}
.card h3{{font-size:1rem;margin:.35rem 0}}
.badge{{display:inline-block;background:#334155;color:var(--text);font-size:.7rem;padding:.15rem .45rem;border-radius:999px;margin-left:.25rem}}
.tag{{display:inline-block;background:#1e3a5f;color:var(--accent);font-size:.75rem;padding:.2rem .55rem;border-radius:999px;margin:.2rem}}
.muted{{color:var(--muted);font-size:.9rem}}
footer{{margin-top:2rem;padding-top:1rem;border-top:1px solid #334155;color:var(--muted);font-size:.8rem}}
a.home{{color:var(--accent);text-decoration:none}}
</style>
</head>
<body>
<div class="wrap">
  <h1>🏭 لوحة المصنع</h1>
  <p class="story">{story}</p>

  <div class="grid">
    <div class="stat"><div class="n">{total}</div><div class="l">منتجات منشورة</div></div>
    <div class="stat"><div class="n">{ai}</div><div class="l">جيل ذكي</div></div>
    <div class="stat"><div class="n">{det}</div><div class="l">قوالب حتمية</div></div>
    <div class="stat"><div class="n">{unique_issues}</div><div class="l">أفكار من المجتمع</div></div>
  </div>

  <h2>آخر المنتجات</h2>
  <div class="cards">
    {cards if cards else '<p class="muted">لا توجد منتجات بعد</p>'}
  </div>

  <h2>أنماط التنوع</h2>
  <div>{tags_html}</div>

  <footer>
    آخر تحديث للكتالوج: {last}<br>
    وُلدت هذه الصفحة: {now}<br>
    <a class="home" href="../">العودة للمستودع</a> ·
    <a class="home" href="https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'Hanachi04/weekly-micro-product-factory')}/issues/new/choose">قدّم فكرة</a>
  </footer>
</div>
</body>
</html>
'''


def main() -> int:
    catalog = load_catalog()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = build_html(catalog)
    OUT.write_text(html, encoding="utf-8")
    size = len(html.encode("utf-8"))
    print(f"Wrote {OUT} ({size} bytes)")
    if size > 30 * 1024:
        print("WARNING: stats page exceeds 30KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
