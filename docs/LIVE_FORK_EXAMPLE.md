# Live Fork Example / مثال مصنع فرعي حي

> A copy-paste friendly walkthrough. Target time: **&lt; 30 minutes**.

---

## English

### Why a “live” example?

`FORK_GUIDE.md` explains the theory. This page shows a **concrete specialization**: an education-focused factory that only ships offline learning tools for Arabic/English classrooms.

Live example repo: **[Hanachi04/arabic-education-factory](https://github.com/Hanachi04/arabic-education-factory)**  
(Start from [weekly-micro-product-factory](https://github.com/Hanachi04/weekly-micro-product-factory) and specialize as below.)

### Side-by-side settings

| Setting | Parent factory | Education fork |
|---------|----------------|----------------|
| `FACTORY_LANG` | `ar` (default) | `ar` or `en` |
| Issue form title | New product idea | New classroom tool idea |
| Templates | calculator, landing-page, weekly-tracker | Add `flashcards/`, `quiz-timer/` |
| Diversity agent | General layout rotation | Prefer high-contrast, large type |
| Critic focus | Palette + size + RTL | Also: min 18px body text, no pure decorative clutter |
| Telegram | Optional community channel | Optional teachers channel |

### Minimal specialization steps

1. **Fork** the parent repo → rename to your factory.
2. **Secrets** (optional): `GROQ_API_KEY` / `GEMINI_API_KEY`, and for notify: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. **Variable**: `FACTORY_LANG=ar` (or `en`).
4. **Locales**: edit rejection / vote messages in `locales/*.json` for a classroom tone.
5. **Diversity**: in `agents/diversity_agent.py` system prompt, add domain constraints, e.g.  
   *“Prefer high contrast, avoid decorative-only layouts, favor list/quiz structures.”*
6. **Critic**: in `adversarial_critic_agent.py` heuristics, add a medium issue if body text CSS has `font-size` under 16px.
7. **Templates**: copy `templates/weekly-tracker/` → `templates/flashcards/` and simplify to Q/A cards with `localStorage`.
8. **First issue**: open the idea form → vote 👍 → wait for weekly select or dispatch manually.
9. **Pages**: enable GitHub Pages from root or `/docs` so students open products on phones.

### Launch checklist

- [ ] Actions enabled on the fork  
- [ ] At least one API secret **or** deterministic-only path verified  
- [ ] Test issue triaged (approve + vote ballot)  
- [ ] One manual `workflow_dispatch` with `enable_ai=true` succeeded  
- [ ] `/stats/` shows the product  
- [ ] Optional: Telegram test message after publish  
- [ ] README points teachers to Issues + stats  

### Contributing back

If you invent a great education template, open a PR upstream with only the `templates/` folder and a short note in `docs/`.

---

## العربية

### لماذا مثال حي؟

`FORK_GUIDE.md` يشرح الفكرة. هنا **تخصص عملي**: مصنع أدوات تعليمية تعمل بدون إنترنت للفصول.

مستودع المثال الحي: **[Hanachi04/arabic-education-factory](https://github.com/Hanachi04/arabic-education-factory)**

### مقارنة سريعة

| العنصر | المصنع الأم | مصنع التعليم |
|--------|-------------|--------------|
| اللغة | عربية افتراضياً | عربية أو إنجليزية |
| القوالب | حاسبة / هبوط / متتبع | أضف بطاقات / مؤقت اختبار |
| التنوع | تدوير عام | تباين عالٍ ونص كبير |
| النقد | ألوان وحجم وRTL | + حد أدنى لحجم الخط |
| Telegram | قناة مجتمع اختيارية | قناة معلّمين اختيارية |

### خطوات التخصص

1. Fork للمستودع الأم وتسميته.
2. إضافة Secrets اختيارية للمفاتيح وTelegram.
3. ضبط `FACTORY_LANG`.
4. تعديل نبرة الرسائل في `locales/`.
5. تقييد وكيل التنوع لمجال التعليم.
6. تشديد الناقد على وضوح النص.
7. إضافة قالب `flashcards` من قالب موجود.
8. تجربة Issue + تصويت أو تشغيل يدوي.
9. تفعيل GitHub Pages للوصول من الهاتف.

### قائمة الإطلاق

- [ ] Actions مفعّلة  
- [ ] مسار حتمي أو ذكي نجح مرة  
- [ ] Issue تجريبي مقبول  
- [ ] `/stats/` يعرض المنتج  
- [ ] (اختياري) إشعار Telegram  
- [ ] README للمعلمين واضح  

مرحباً بك في شبكة المصانع. 🏭📚🌍
