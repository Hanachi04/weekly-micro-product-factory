"""Objective diversity score (0-100) vs recent catalog products."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


def _hex_to_rgb(h: str) -> tuple[float, float, float] | None:
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        return None
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _color_distance(a: str, b: str) -> float:
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    if not ra or not rb:
        return 100.0
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(ra, rb)))


def _extract_colors_from_html(html: str) -> list[str]:
    found = re.findall(r"#([0-9a-fA-F]{3,8})\b", html or "")
    colors = []
    for h in found:
        if len(h) in (3, 6):
            colors.append("#" + h.lower())
    # dedupe preserve order
    seen = set()
    out = []
    for c in colors:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:12]


def _dom_fingerprint(html: str) -> dict[str, int]:
    tags = re.findall(r"<([a-zA-Z0-9]+)", html or "")
    counts: dict[str, int] = {}
    for t in tags:
        t = t.lower()
        if t in ("html", "head", "body", "meta", "link", "script", "style"):
            continue
        counts[t] = counts.get(t, 0) + 1
    return counts


def _fingerprint_distance(a: dict[str, int], b: dict[str, int]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    num = sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys)
    den = sum(a.values()) + sum(b.values()) + 1
    return num / den  # 0 identical .. higher more different


def _token_set(text: str) -> set[str]:
    text = (text or "").lower()
    tokens = re.findall(r"[\w\u0600-\u06ff]{3,}", text)
    stop = {
        "the", "and", "for", "with", "this", "that", "from", "are", "you",
        "من", "على", "في", "هذا", "هذه", "التي", "الذي", "مع", "بدون", "إلى",
    }
    return {t for t in tokens if t not in stop}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def calculate_diversity_score(
    new_html: str,
    new_meta: dict[str, Any] | None,
    catalog_products: list[dict[str, Any]],
    history_limit: int = 8,
) -> dict[str, Any]:
    """
    Returns score 0-100 (higher = more diverse vs recent history) and breakdown.
    """
    history = (catalog_products or [])[:history_limit]
    if not history:
        return {
            "diversity_score": 100.0,
            "breakdown": {"note": "no_history"},
            "components": {"color": 100.0, "structure": 100.0, "text": 100.0, "type": 100.0},
        }

    new_colors = _extract_colors_from_html(new_html)
    new_fp = _dom_fingerprint(new_html)
    new_text = " ".join(
        str((new_meta or {}).get(k) or "") for k in ("title", "description")
    )
    new_tokens = _token_set(new_text)
    new_template = (new_meta or {}).get("path") or (new_meta or {}).get("template") or ""

    color_sims = []
    struct_dists = []
    text_sims = []
    type_hits = 0

    for p in history:
        # colors from diversity_tags (hex entries) or skip
        hist_colors = [
            t for t in (p.get("diversity_tags") or [])
            if isinstance(t, str) and t.startswith("#")
        ]
        if new_colors and hist_colors:
            # min distance between any pair, average
            dists = [
                min(_color_distance(nc, hc) for hc in hist_colors)
                for nc in new_colors[:5]
            ]
            # map distance 0-441 to similarity 1..0
            avg = sum(dists) / len(dists)
            color_sims.append(max(0.0, 1.0 - avg / 200.0))
        elif new_colors:
            color_sims.append(0.3)  # unknown history colors → mild penalty

        # structure: we don't store full HTML; approximate via template + tag hints in tags
        # Use template equality as weak structure signal
        if new_template and p.get("template") == new_template:
            struct_dists.append(0.2)  # similar structure assumed
        else:
            struct_dists.append(0.8)

        hist_tokens = _token_set(
            f"{p.get('title', '')} {p.get('description', '')}"
        )
        text_sims.append(_jaccard(new_tokens, hist_tokens))

        if new_template and p.get("template") == new_template:
            type_hits += 1

    # Convert similarity to diversity contribution
    def avg(xs: list[float], default: float = 0.5) -> float:
        return sum(xs) / len(xs) if xs else default

    color_div = (1.0 - avg(color_sims, 0.4)) * 100
    struct_div = avg(struct_dists, 0.7) * 100
    text_div = (1.0 - avg(text_sims, 0.3)) * 100
    type_div = max(0.0, 100.0 - (type_hits / max(len(history), 1)) * 100)

    # Weighted score
    score = 0.30 * color_div + 0.25 * struct_div + 0.25 * text_div + 0.20 * type_div
    score = round(max(0.0, min(100.0, score)), 1)

    return {
        "diversity_score": score,
        "components": {
            "color": round(color_div, 1),
            "structure": round(struct_div, 1),
            "text": round(text_div, 1),
            "type": round(type_div, 1),
        },
        "history_compared": len(history),
        "new_colors_sample": new_colors[:5],
        "type_repeats_in_window": type_hits,
    }


def analyze_product_dir(product_dir: str | Path, catalog_path: str | Path) -> dict[str, Any]:
    product_dir = Path(product_dir)
    catalog_path = Path(catalog_path)
    html = (product_dir / "index.html").read_text(encoding="utf-8") if (product_dir / "index.html").exists() else ""
    meta = {}
    if (product_dir / "meta.json").exists():
        meta = json.loads((product_dir / "meta.json").read_text(encoding="utf-8"))
    products = []
    if catalog_path.exists():
        products = json.loads(catalog_path.read_text(encoding="utf-8")).get("products") or []
    return calculate_diversity_score(html, meta, products)


if __name__ == "__main__":
    import sys
    pd = sys.argv[1] if len(sys.argv) > 1 else "products/weekly"
    cp = sys.argv[2] if len(sys.argv) > 2 else "catalog/index.json"
    print(json.dumps(analyze_product_dir(pd, cp), ensure_ascii=False, indent=2))
