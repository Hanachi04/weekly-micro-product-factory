#!/usr/bin/env python3
"""Generate static RTL/LTR stats dashboard from catalog (bilingual)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
from utils.i18n import get_text, resolve_lang  # noqa: E402

CATALOG = ROOT / "catalog" / "index.json"
CONTRIB = ROOT / "catalog" / "contributors.json"
OUT = ROOT / "stats" / "index.html"


def load_catalog() -> dict:
    if not CATALOG.exists():
        return {"products": [], "total_count": 0, "last_updated": None}
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def build_html(catalog: dict, lang: str) -> str:
    t = lambda k, **kw: get_text(k, lang, **kw)
    products = catalog.get("products") or []
    total = len(products)
    ai = sum(1 for p in products if p.get("build_method") == "ai_generated")
    det = total - ai
    issues = [p.get("source_issue_number") for p in products if p.get("source_issue_number")]
    unique_issues = len(set(str(i) for i in issues if i))
    critic_scores = [float(p["critic_score"]) for p in products if p.get("critic_score") is not None]
    div_scores = [float(p["diversity_score"]) for p in products if p.get("diversity_score") is not None]
    avg_critic = round(sum(critic_scores) / len(critic_scores), 1) if critic_scores else None
    avg_div = round(sum(div_scores) / len(div_scores), 1) if div_scores else None
    revisions = sum(1 for p in products if p.get("critic_verdict") == "needs_revision" or p.get("quality_warning"))


    tags: dict[str, int] = {}
    for p in products:
        for tag in p.get("diversity_tags") or []:
            tags[str(tag)] = tags.get(str(tag), 0) + 1
    top_tags = sorted(tags.items(), key=lambda x: -x[1])[:8]

    cards = ""
    for p in products[:5]:
        week = p.get("week", "")
        title = p.get("title", "—")
        method = t("stats.method_ai") if p.get("build_method") == "ai_generated" else t("stats.method_det")
        path = p.get("path") or f"products/weekly/{week}"
        src = p.get("source_issue_number")
        src_html = f'<span class="badge">Issue #{src}</span>' if src else ""
        cards += f'''
      <a class="card" href="../{path}/">
        <div class="week">{week}</div>
        <h3>{title}</h3>
        <div class="meta"><span class="badge">{method}</span> {src_html}</div>
      </a>'''

    tags_html = "".join(f'<span class="tag">{x} ({c})</span>' for x, c in top_tags) or f'<span class="muted">{t("stats.no_tags")}</span>'

    if total:
        story = t("stats.story_products", total=total)
        if unique_issues:
            story += t("stats.story_issues", issues=unique_issues)
        if ai:
            story += t("stats.story_ai", ai=ai)
    else:
        story = t("stats.story_empty")


    bars = ""
    for p in products[:8]:
        ds = p.get("diversity_score")
        cs = p.get("critic_score")
        if ds is None and cs is None:
            continue
        week = p.get("week", "")
        try:
            w = max(4, min(100, float(ds))) if ds is not None else 4
        except (TypeError, ValueError):
            w = 4
        try:
            cw = max(4, min(100, float(cs) * 10)) if cs is not None else 0
        except (TypeError, ValueError):
            cw = 0
        ds_s = ds if ds is not None else "—"
        cs_s = cs if cs is not None else "—"
        bars += (
            f'<div class="bar-row"><span class="bar-label">{week}</span>'
            f'<span class="bar" style="width:{w}%" title="diversity"></span>'
            f'<span class="bar bar-critic" style="width:{cw}%" title="critic"></span>'
            f'<span class="bar-val">D {ds_s} · C {cs_s}</span></div>\n'
        )
    if not bars:
        bars = f'<p class="muted">{"لا بيانات تنوع بعد" if lang == "ar" else "No diversity data yet"}</p>'

    # contributors top 5
    contrib_rows = []
    if CONTRIB.exists():
        try:
            contrib_rows = (json.loads(CONTRIB.read_text(encoding="utf-8")).get("contributors") or [])[:5]
        except Exception:
            contrib_rows = []
    contrib_html = ""
    for c in contrib_rows:
        u = c.get("username") or "?"
        produced = c.get("ideas_produced") or 0
        submitted = c.get("ideas_submitted") or 0
        avg = c.get("avg_diversity_score")
        avg_s = f"{avg}" if avg is not None else "—"
        contrib_html += (
            f'<div class="contrib"><strong>@{u}</strong> · '
            f'{produced} {t("stats.produced")} · {submitted} {t("stats.ideas")} · '
            f'D {avg_s}</div>\n'
        )
    if not contrib_html:
        contrib_html = f'<p class="muted">{t("stats.no_contributors")}</p>'

    telegram_on = (os.environ.get("TELEGRAM_CONFIGURED") or "").lower() in ("1", "true", "yes")
    telegram_label = t("stats.telegram_on") if telegram_on else t("stats.telegram_off")
    telegram_badge = "✅" if telegram_on else "❌"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    last = catalog.get("last_updated") or now
    repo = os.environ.get("GITHUB_REPOSITORY", "Hanachi04/weekly-micro-product-factory")
    direction = "rtl" if lang == "ar" else "ltr"

    return f'''<!DOCTYPE html>
<html lang="{lang}" dir="{direction}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t("stats.title")}</title>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--accent:#38bdf8}}
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
.card{{display:block;background:var(--card);border-radius:12px;padding:1rem;text-decoration:none;color:inherit;border:1px solid transparent}}
.card:hover{{border-color:var(--accent)}}
.card .week{{font-size:.75rem;color:var(--muted)}}
.card h3{{font-size:1rem;margin:.35rem 0}}
.badge{{display:inline-block;background:#334155;font-size:.7rem;padding:.15rem .45rem;border-radius:999px;margin-inline-start:.25rem}}
.tag{{display:inline-block;background:#1e3a5f;color:var(--accent);font-size:.75rem;padding:.2rem .55rem;border-radius:999px;margin:.2rem}}
.muted{{color:var(--muted);font-size:.9rem}}
footer{{margin-top:2rem;padding-top:1rem;border-top:1px solid #334155;color:var(--muted);font-size:.8rem}}
a.home{{color:var(--accent);text-decoration:none}}
</style>
</head>
<body>
<div class="wrap">
  <h1>{t("stats.heading")}</h1>
  <p class="story">{story}</p>
  <div class="grid">
    <div class="stat"><div class="n">{total}</div><div class="l">{t("stats.total")}</div></div>
    <div class="stat"><div class="n">{ai}</div><div class="l">{t("stats.ai")}</div></div>
    <div class="stat"><div class="n">{det}</div><div class="l">{t("stats.deterministic")}</div></div>
    <div class="stat"><div class="n">{unique_issues}</div><div class="l">{t("stats.community")}</div></div>
  </div>
  <h2>{t("stats.last_products")}</h2>
  <div class="cards">{cards if cards else f'<p class="muted">{t("stats.no_products")}</p>'}</div>
  <h2>{t("stats.diversity")}</h2>
  <div>{tags_html}</div>

  <h2>{"جودة الإنتاج" if lang == "ar" else "Production quality"}</h2>
  <div class="grid">
    <div class="stat"><div class="n">{avg_critic if avg_critic is not None else "—"}</div><div class="l">{"متوسط النقد /10" if lang == "ar" else "Avg critic /10"}</div></div>
    <div class="stat"><div class="n">{avg_div if avg_div is not None else "—"}</div><div class="l">{"متوسط التنوع /100" if lang == "ar" else "Avg diversity /100"}</div></div>
    <div class="stat"><div class="n">{revisions}</div><div class="l">{"تحذيرات مراجعة" if lang == "ar" else "Revision warnings"}</div></div>
  </div>
  <div class="bars">
    {bars}
  </div>

  <h2>{t("stats.contributors")}</h2>
  <div class="contrib-list">{contrib_html}</div>

  <h2>{t("stats.notifications")}</h2>
  <p class="muted">{telegram_badge} {telegram_label}</p>

  <footer>
    {t("stats.updated")}: {last}<br>
    {t("stats.generated")}: {now}<br>
    <a class="home" href="../">{t("stats.home")}</a> ·
    <a class="home" href="https://github.com/{repo}/issues/new/choose">{t("stats.submit")}</a>
  </footer>
</div>
</body>
</html>
'''


def main() -> int:
    lang = resolve_lang(os.environ.get("FACTORY_LANG"))
    catalog = load_catalog()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = build_html(catalog, lang)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} lang={lang} ({len(html.encode())} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
