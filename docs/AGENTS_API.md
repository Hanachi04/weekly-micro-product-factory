# Agents API — دليل إضافة وكيل متخصص

> Version: see `/VERSION` · Language: AR + EN

---

## English

### Architecture overview

```
Issue / dispatch
    → triage_agent          (gate)
    → diversity_agent       (constraints card)
    → content_agent         (copy)
    → design_agent          (HTML from templates)
    → adversarial_critic    (review ≤ 2 retries)
    → diversity_analyzer    (objective score)
    → publish + notify
```

All agents are **plain Python** under `agents/`. Shared utilities live in `agents/utils/`.

### Contract for a new agent

1. **File:** `agents/<name>_agent.py` with a `main()` CLI and a pure function entrypoint.
2. **I/O:** prefer JSON files on disk (`--output path.json`) so GitHub Actions can pass artifacts between jobs.
3. **No network in heuristics** unless using `utils.llm_client.generate_text` (which already has multi-provider fallback).
4. **i18n:** user-facing strings via `utils.i18n.get_text(key, lang)`.
5. **Size/safety:** products remain static HTML, offline, &lt; 80KB, no CDN.

### Minimal agent skeleton

```python
#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.i18n import resolve_lang

def run(payload: dict, lang: str) -> dict:
    # your logic
    return {"status": "ok", "lang": lang}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", "-o", default="agent_out.json")
    p.add_argument("--lang", default="")
    args = p.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out = run(data, resolve_lang(args.lang or None))
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### Wiring into `weekly-build.yml`

1. Call the agent in the `smart-agents` job after the step it depends on.
2. Add its JSON output to the `upload-artifact` path list.
3. In `publish`, copy any report you want stored under `products/weekly/<week_id>/`.
4. Keep the job **non-blocking** (`continue-on-error: true`) if the agent is advisory only.

### Domain agent via Issue labels (pattern)

Future specialization can branch on labels, e.g. `education`:

```bash
if echo "$LABELS" | grep -q education; then
  python agents/education_agent.py --html generated_index.html -o education_report.json
fi
```

### Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

Add `tests/test_<name>.py` for every new agent that has deterministic logic.

### LLM helper

```python
from utils.llm_client import generate_text, available_providers, AllProvidersFailedError

if available_providers():
    text = generate_text(prompt, system_prompt="...")
```

Never hard-fail the factory if LLM is down — fall back to templates/heuristics.

---

## العربية

### نظرة عامة

الوكلاء سكربتات Python تحت `agents/`. المساعدات المشتركة في `agents/utils/` (ترجمة، عميل LLM، محلل تنوع، تطبيع عربي).

### عقد الوكيل الجديد

1. ملف `agents/<name>_agent.py` بدالة نقية + CLI.
2. مخرجات JSON للـ Artifacts بين الـ Jobs.
3. النصوص الظاهرة للمستخدم عبر `get_text`.
4. احترام قيود المنتج: HTML ثابت، بدون إنترنت، &lt; 80KB.

### الدمج

- استدعاء في `smart-agents` داخل `.github/workflows/weekly-build.yml`
- رفع المخرجات كـ artifact
- نسخ التقارير المهمة إلى مجلد المنتج عند النشر
- الاختبارات في `tests/` مع `pytest`

### مبدأ الأمان

المسار الحتمي (القوالب) يجب أن يعمل **دائماً** حتى لو فشلت كل مفاتيح الـ LLM أو الوكيل الجديد.

أسئلة؟ افتح Issue بوسم `docs` في المستودع الأم.
