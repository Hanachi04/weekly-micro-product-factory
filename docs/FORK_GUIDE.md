# Fork Guide / دليل إنشاء مصنع فرعي

> Goal: stand up your own specialized micro-product factory in **under 30 minutes**.

---

## English

### Why fork?

- Different **language** or region
- Different **domain** (kids’ stories, education tools, local utilities)
- Separate community with its own voting queue

### Setup (≈ 30 minutes)

1. **Fork** this repository on GitHub.
2. Rename if you like (e.g. `edu-micro-factory`).
3. Open **Settings → Secrets and variables → Actions** and add at least one:
   - `GROQ_API_KEY` and/or `GEMINI_API_KEY` (optional for AI path; templates still work without keys).
4. Enable **Actions** (allow workflow runs).
5. Optional: enable **GitHub Pages** from `/` or `/docs` / `/stats`.
6. Edit `locales/en.json` and `locales/ar.json` (or set `FACTORY_LANG=en` only).
7. Open a test issue with the **New product idea** template.

### Language

- Default: `FACTORY_LANG=ar`
- For English-first factory, set repository variable `FACTORY_LANG=en`  
  (**Settings → Secrets and variables → Actions → Variables**)
- Or pass `lang=en` on `workflow_dispatch` for `weekly-build`.

### Customize agents

| File | What to change |
|------|----------------|
| `locales/*.json` | Bot comments, stats labels, rejection messages |
| `agents/diversity_agent.py` | Domain-specific diversity constraints |
| `templates/` | Add your own deterministic HTML starters |
| `.github/ISSUE_TEMPLATE/` | Idea form labels for your community |

Keep products: **static HTML**, **offline**, **&lt; 80KB**, **no CDN**.

### Contribute upstream

- Open a PR to the parent repo with new templates or locale keys.
- Share your fork link so others can discover specialized factories.

---

## العربية

### لماذا Fork؟

- لغة أو منطقة مختلفة
- مجال متخصص (قصص أطفال، أدوات تعليمية، خدمات محلية)
- مجتمع منفصل مع قائمة تصويت خاصة

### الإعداد (أقل من 30 دقيقة)

1. اعمل **Fork** لهذا المستودع.
2. غيّر الاسم إن رغبت.
3. من **Settings → Secrets** أضف `GROQ_API_KEY` أو `GEMINI_API_KEY` (اختياري للمسار الذكي).
4. فعّل **Actions**.
5. اختياري: فعّل **GitHub Pages**.
6. عدّل `locales/ar.json` و `locales/en.json`.
7. افتح Issue تجريبي بقالب **فكرة منتج جديد**.

### اللغة

- الافتراضي: `FACTORY_LANG=ar`
- لمصنع إنجليزي: أضف Variable باسم `FACTORY_LANG=en`
- أو مرّر `lang=en` عند تشغيل `weekly-build` يدوياً.

### التخصيص

| الملف | التعديل |
|-------|---------|
| `locales/*.json` | رسائل البوت واللوحة |
| `agents/diversity_agent.py` | قيود تنوع لمجالكم |
| `templates/` | قوالب حتمية جديدة |
| قوالب Issues | نموذج تقديم الأفكار |

التزم بـ: HTML ثابت، بدون إنترنت، أقل من 80KB، بدون مكتبات خارجية.

### المساهمة في المصنع الأم

- افتح PR بالقوالب أو مفاتيح الترجمة الجديدة.
- شارك رابط مصنعك الفرعي مع المجتمع.

---

## Checklist

- [ ] Fork created  
- [ ] Secrets (optional) set  
- [ ] `FACTORY_LANG` chosen  
- [ ] Test issue triaged  
- [ ] `/stats` generated after a build  

Welcome to the factory network. 🏭🌍
