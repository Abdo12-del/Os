# عقود نقاط القراءة — API Contracts

> **المبدأ:** كل نقطة تُرجع **أقل بيانات تحتاجها المهمة** (data minimization). عندك أطفال، فالحقل الذي لا يحتاجه الوكيل لا يُرسل له أصلًا — لا يُرسل ويُطلب منه تجاهله.
> **الوكيل لا يكتب إلا في `pending_actions`.** لا يوجد endpoint تنفيذ في هذه القائمة كلها.

---

## المصادقة والأمان (موحّد لكل النقاط)

| البند | القيمة |
|---|---|
| الترويسة | `Authorization: Bearer <token>` |
| التخزين | `agent_tokens.token_hash` — لا تُخزَّن التوكنات صريحة |
| النطاق (scope) | لكل وكيل نطاقه: `marketing:read` / `finance:read` / `actions:propose` |
| الانتهاء | 30 يومًا كحد أقصى، ثم تجديد يدوي |
| السحب | `revoked_at` — زر واحد في لوحتك يوقف وكيلًا دون الباقين |
| الحدّ | 60 طلبًا/دقيقة لكل توكن. التجاوز → `429` |
| السجل | كل طلب يكتب سطرًا في `agent_audit_log` في نفس المعاملة |
| بيئة الاختبار | staging بأسماء مستعارة حتى يجتاز الوكيل اختبارات القبول |

### شكل الخطأ الموحّد
```json
{ "error": { "code": "forbidden_scope",
             "message": "التوكن agent_marketing_read لا يملك نطاق finance:read",
             "rule": "05-rules.md — نطاق كل توكن = مهمة الوكيل فقط" } }
```
> **مقصود:** رسالة الخطأ تذكّر بالقاعدة. الوكيل الذي يقرأها يعرف أن يتوقف ويسأل، لا أن يعيد المحاولة.

---

## 1) التسويق

### `GET /api/v1/marketing/funnel?from=YYYY-MM-DD&to=YYYY-MM-DD`
**النطاق:** `marketing:read`

```json
{
  "period": { "from": "2026-10-01", "to": "2026-11-01" },
  "source": "نظام المحاسبة + نظام الأولياء — استعلام 2026-11-09",
  "funnel": {
    "leads": 27,
    "replied_within_1h": 9,
    "replied_within_24h": 6,
    "never_replied": 12,
    "asked_price": 18,
    "trial_booked": 11,
    "trial_attended": 8,
    "enrolled": 6,
    "paid": 5
  },
  "by_source": { "facebook": 14, "instagram": 5, "telegram": 4, "referral": 4 },
  "conversion": { "lead_to_enrolled": 0.222, "trial_to_enrolled": 0.545 },
  "missing": ["asked_price غير متوفر: لا يوجد حقل يميّزه في جدول leads"]
}
```

> **`never_replied` و`replied_within_1h` هما أهم حقلين في العقد كله.** هما اللذان يحسمان هل مشكلتك محتوى أم سرعة رد. وإن كانا غير متاحين في مخططك اليوم، **أضفهما** — `first_reply_at` عمود واحد في `leads`.
> **`missing` إلزامي:** إن نقص حقل، يُعلن صراحة. الوكيل ممنوع أن يملأه بتخمين (القاعدة 4).

### `GET /api/v1/marketing/leads?status=new&limit=100`
**النطاق:** `marketing:read`

```json
{ "leads": [ { "id": "L-204", "first_name": "أحمد", "child_age": 8,
               "source": "facebook", "first_contact_at": "2026-11-03T14:20:00+01:00",
               "first_reply_at": null, "asked_about": "الأسعار", "status": "new" } ],
  "next_cursor": "…" }
```
**ممنوع في الاستجابة:** `phone` • `address` • `email` • أي مبلغ • اسم الطفل الكامل • أي حالة مالية.
> **لماذا:** وكيل التسويق لا يحتاجها لأي مهمة من مهامه. وإن احتاج مراسلة أحد، فالمراسلة من حسابك أنت.

### `POST /api/v1/actions/propose` — النقطة الوحيدة للكتابة
**النطاق:** `actions:propose`
```json
{ "agent": "marketing", "action_type": "publish_post",
  "payload": { "platform": "facebook", "text": "…", "pillar": "نافذة على الحصة" },
  "reason": "ألم فرط الحركة — الزاوية المعتمدة في positioning.md 3.1",
  "risk": "green", "idempotency_key": "post-2026-11-09-fb-01" }
```
**الاستجابة:** `201` مع `{ "id": 88, "status": "pending" }` — **ولا شيء يُنفَّذ**.
⚠️ `publish_post` و`send_parent_msg` **لا يُنفَّذان آليًا أبدًا**، حتى بعد الموافقة. انظر `tech/01-schema.sql` القسم 6.

---

## 2) المالية

### `GET /api/v1/finance/summary?month=YYYY-MM`
**النطاق:** `finance:read`

```json
{
  "month": "2026-10", "currency": "DZD",
  "source": "نظام المحاسبة — استعلام 2026-11-09",
  "flows": {
    "income":   { "due": 180000, "collected": 152000, "arrears": 28000 },
    "teachers": { "basis": "collected", "share_pct": 30, "due": 45600, "settled": 0 },
    "campaigns":{ "spend": 6000, "enrollments_attributed": 4 }
  },
  "expenses_by_account": { "5001": 45600, "5002": 6000, "5003": 2500, "uncategorized": 900 },
  "net": 97000,
  "previous_month": { "net": 88000, "delta": 9000 },
  "trial_sessions": { "count": 8, "teacher_cost": 4200, "income": 0 },
  "alerts": [ "900 دج مصروف بلا تصنيف", "شهر 2026-09 لم يُغلق" ],
  "missing": [ "أساس نسبة الأستاذ غير محسوم في knowledge/06 القسم 3 — القيمة أعلاه افتراضية ولا يجوز اعتمادها" ]
}
```
> ⚠️ **`teachers.basis` لا يُملأ من الكود.** إن لم يكن الأساس (محصَّل/مستحق) مكتوبًا في ملف المعرفة، تُرجع النقطة `basis: null` + سطرًا في `missing` — **ولا تختار افتراضيًا**. المحاسب ممنوع من الحساب على أساس غير محسوم (القاعدة 10 في نظام تشغيله، والاختبار ح5).

### `GET /api/v1/finance/reconcile?month=YYYY-MM`
**النطاق:** `finance:read`
```json
{
  "month": "2026-11",
  "accounting_system": { "count": 22, "total": 96000 },
  "parents_system":    { "count": 24, "total": 101000 },
  "join_key": "student_id",
  "diffs": [
    { "kind": "in_parents_only", "student_id": "S-104", "amount": 3000,
      "reference": "BP-88213", "parents_date": "2026-11-03",
      "known_normal_reason": null },
    { "kind": "amount_mismatch", "student_id": "S-118", "accounting": 5000,
      "parents": 4500, "known_normal_reason": "خصم إخوة معتمد 2026-10-01" }
  ],
  "normal_diffs_excluded": 3,
  "missing": []
}
```
> **`known_normal_reason`** يأتي من `knowledge/06-accounting-setup.md` القسم 5 (أسباب الفرق الطبيعية). **بدونه سيطلق المحاسب إنذارًا كاذبًا كل أسبوع** حتى تفقد الثقة فيه. املأه مرة واحدة.
> **الفرق الذي لا سبب له يُترك `null`** — والمحاسب يكتب «السبب غير معروف من البيانات المتاحة» ولا يخترع.

### `GET /api/v1/finance/teacher-statement?month=YYYY-MM&teacher_id=T-3`
**النطاق:** `finance:read`
```json
{
  "teacher_id": "T-3", "month": "2026-10",
  "sessions_delivered": 12, "students": 9,
  "collected_from_students": 48000, "due_from_students": 54000, "arrears": 6000,
  "basis": null,
  "share_pct": null,
  "amount_due": null,
  "exceptions": [
    { "type": "free_trial", "count": 2, "income": 0, "note": "بلا إيراد مقابل" },
    { "type": "cancelled_session", "count": 1, "reason": null },
    { "type": "sibling_discount", "student_id": "S-077", "amount_delta": -500 }
  ],
  "missing": ["basis غير محسوم", "share_pct غير مسجّل", "سبب الحصة الملغاة غير مسجّل"]
}
```
> **هذا هو العقد الذي يفضح القرار المعلّق رقم 1 في `OPEN-QUESTIONS.md`.** ثلاثة حقول `null` — والمحاسب سيتوقف عندها ويسألك بدل أن يحسب. **هذا السلوك مقصود ومصمَّم، لا عطل.**

---

## 3) رئاسة العمليات

### `GET /api/v1/ops/daily-brief?date=YYYY-MM-DD`
**النطاق:** `ops:read` (يجمع من نطاقَي `marketing:read` و`finance:read` — **بلا كتابة**)

هذه هي النقطة التي تغذّي الملخص اليومي في `03-head-of-operations.md`. **تعيد وقائع، لا أحكامًا**: رئيس العمليات هو من يرتّب ويقرّر ما يحتاج قرارًا، لا الخادم.

```json
{
  "date": "2026-11-09",
  "generated_at": "2026-11-09T07:00:03+01:00",
  "yesterday": {
    "sessions": { "delivered": 6, "cancelled": 1, "cancelled_reason_missing": 1 },
    "attendance": { "present": 41, "absent": 5, "repeat_absentees": 2 },
    "messages": { "first_contact": 7, "replied_within_1h": 3, "never_replied": 3 },
    "payments": { "recorded": 3, "unresolved_diffs": 1 }
  },
  "open_decisions": [
    { "id": 88, "agent": "accountant", "action_type": "correct_payment",
      "risk": "yellow", "opened_at": "2026-11-05", "days_open": 4, "source_ref": "pay-104-2026-11" }
  ],
  "escalations": [
    { "kind": "red", "what": "مهتم ذكر تشخيصًا طبيًا قائمًا", "since": "2026-11-08", "answered": false }
  ],
  "broken": [
    "تصدير نظام المحاسبة لم يصل منذ 2026-11-06 — لا يمكن المطابقة",
    "شهر 2026-09 غير مغلق",
    "أساس نسبة الأستاذ غير محسوم — مستند الأساتذة يُعيد null"
  ],
  "prepared": [
    "7 مسوَّدات رد على الأولياء", "جدول الغد وفيه تعارض واحد", "منشور الأسبوع"
  ],
  "missing": [
    "asked_price غير متوفر: لا حقل يميّزه في leads",
    "sessions_cancelled_reason ناقص في حالة واحدة"
  ]
}
```

**قواعد هذه النقطة تحديدًا:**
1. **`days_open` إلزامي** لكل بند في `open_decisions` — منه يبني رئيس العمليات علامة `⚠ متأخر` (3 أيام فأكثر).
2. **`never_replied` أهم حقل في الملخص كله.** إن لم يكن متاحًا في مخططك، فأضف `first_reply_at` إلى `leads` — عمود واحد يجيب عن سؤالك الاستراتيجي.
3. **`broken` لا يُكتم أبدًا.** إن فشل بناء قسم، يُرسل الملخص ناقصًا **مع ذكر ما تعطّل**. الكتم يعني أنك لن تعرف أن النظام تعطل.
4. **`missing` إلزامي دائمًا.** حقل ناقص يُعلن صراحة، ولا يُملأ بصفر ولا بـ `null` صامت.
5. **لا أحكام ولا توصيات في الاستجابة.** الخادم يعيد وقائع؛ الترتيب والأولوية والاقتراح عمل رئيس العمليات.

### `POST /api/v1/actions/propose`
نفس النقطة في القسم 1 — يستعملها كل الوكلاء، وكلٌّ بتوكنه ونطاقه.

---

## 4) قواعد عامة لكل النقاط

1. **كل استجابة تحمل `source` و`missing`.** رقم بلا مصدر = رقم مخترع (القاعدة 4).
2. **لا تقريب في الخادم.** الأرقام كما في القاعدة. التقريب قرار الوكيل ويجب أن يصرّح به.
3. **لا تحويل عملة في الخادم.** `currency` يُعلن، والتحويل ممنوع إلا بسعر معتمد تعطيه أنت وتاريخه.
4. **الترقيم (pagination) إلزامي** — `limit` افتراضي 100 وأقصى 500. لا تُرجع جدولًا كاملًا أبدًا.
5. **`403` لا `404` عند تجاوز النطاق** — الوكيل يحتاج أن يعرف أن الطلب ممنوع، لا أن المورد غير موجود.
6. **لا endpoint للنشر أو الإرسال.** ليس «مؤقتًا»، وليس «للتجربة». انظر `05-rules.md` والقسم 6 من `01-schema.sql`.
7. **`GET` فقط للقراءة.** أي `POST` في هذه القائمة هو `actions/propose` وحده.

---

## 5) ما الذي تبنيه أولًا (ترتيب التنفيذ)

| # | النقطة | لماذا أولًا | الجهد |
|---|---|---|---|
| 1 | `finance/reconcile` | تكشف فروقًا حقيقية من اليوم الأول، وتثبت أن البنية تعمل | ساعة |
| 2 | `marketing/funnel` | **أضف عمود `first_reply_at` في `leads`** — هذا العمود وحده يجيب عن سؤالك الاستراتيجي | ساعة |
| 3 | `finance/summary` | تحتاج `basis` محسومًا أولًا، وإلا تُرجع `null` (وهذا صحيح) | ساعة |
| 4 | `finance/teacher-statement` | تحتاج النسبة والأساس مكتوبين | ساعة |
| 5 | `marketing/leads` | بعد أن تثبت أن الـ views تخفي الحقول الحساسة فعلًا | نصف ساعة |
| 6 | `actions/propose` | بعد `pending_actions` واختبارات القسم 7 من `01-schema.sql` | نصف ساعة |
| 7 | `ops/daily-brief` | آخرًا — يجمع ما قبله. لا فائدة منه قبل أن توجد البيانات | ساعة |
