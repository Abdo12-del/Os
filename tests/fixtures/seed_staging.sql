-- ============================================================
--  fixture — أكتوبر 2026 في بيئة staging (PostgreSQL)
--  بيانات مختلَقة بالكامل، بأسماء مستعارة
-- ============================================================
--  ⚠️ لا تشغّل هذا في قاعدة الإنتاج. قاعدة staging منفصلة فقط.
--  ⚠️ الأسماء والأرقام مختلَقة. لا تضع هنا بيانات أطفال حقيقية.
--  ⚠️ كيّف أسماء الجداول والأعمدة على مخططك الحقيقي
--     (من knowledge/06-accounting-setup.md القسم 2).
--
--  الغرض: تشغيل اختبارات المحاسب ح1–ح11 (tests/fixtures/accounting-october-2026.md)
--  على نقاط API حقيقية بدل اللصق اليدوي.
-- ============================================================

DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA staging;

-- ------------------------------------------------------------
-- الجداول
-- ------------------------------------------------------------
CREATE TABLE staging.students (
  student_id     TEXT PRIMARY KEY,
  alias_name     TEXT NOT NULL,          -- اسم مستعار، لا اسم حقيقي
  group_name     TEXT NOT NULL,
  teacher_id     TEXT NOT NULL,
  monthly_due    NUMERIC(12,2) NOT NULL,
  note           TEXT,
  deleted_at     TIMESTAMPTZ             -- حذف ناعم فقط
);

CREATE TABLE staging.payments_accounting (
  ref            TEXT PRIMARY KEY,       -- نظام المحاسبة = مرجع المال
  student_id     TEXT NOT NULL,
  amount         NUMERIC(12,2) NOT NULL,
  method         TEXT,
  paid_at        DATE NOT NULL,
  operation_no   TEXT,                   -- NULL = دفعة بلا مرجع (خطأ مزروع)
  suspected_dup  BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE staging.payments_parents (
  id             SERIAL PRIMARY KEY,     -- نظام الأولياء
  student_id     TEXT NOT NULL,
  amount         NUMERIC(12,2) NOT NULL,
  paid_at        DATE NOT NULL,
  operation_no   TEXT
);

CREATE TABLE staging.teachers (
  teacher_id         TEXT PRIMARY KEY,
  alias_name         TEXT NOT NULL,
  group_name         TEXT NOT NULL,
  sessions_delivered INT NOT NULL,
  free_trials        INT NOT NULL DEFAULT 0,
  sessions_cancelled INT NOT NULL DEFAULT 0,
  cancelled_reason   TEXT,               -- NULL = سبب غير مسجّل (خطأ مزروع)
  share_pct          NUMERIC(5,2),
  share_basis        TEXT                -- NULL = الأساس غير محسوم (الخطأ المزروع الأهم)
);

CREATE TABLE staging.expenses (
  id             SERIAL PRIMARY KEY,
  account_code   TEXT,                   -- NULL = مصروف بلا تصنيف (خطأ مزروع)
  label          TEXT NOT NULL,
  amount         NUMERIC(12,2) NOT NULL,
  spent_at       DATE NOT NULL
);

CREATE TABLE staging.period_status (
  month          TEXT PRIMARY KEY,
  closed_at      TIMESTAMPTZ             -- NULL = شهر غير مغلق (خطأ مزروع)
);

-- ------------------------------------------------------------
-- البيانات — 12 طالبًا (أسماء مستعارة)
-- ------------------------------------------------------------
INSERT INTO staging.students VALUES
 ('S-101','ط-أحمد','أ','T-1',3000,NULL,NULL),
 ('S-102','ط-بلال','أ','T-1',3000,NULL,NULL),
 ('S-103','ط-ياسمين','أ','T-1',2500,'خصم إخوة معتمد 2026-09-01',NULL),
 ('S-104','ط-ريان','أ','T-1',3000,NULL,NULL),
 ('S-105','ط-لينة','أ','T-1',3000,NULL,NULL),
 ('S-106','ط-سارة وط-آدم','أ','T-1',4500,'طفلان، خصم إخوة معتمد 2026-09-15',NULL),
 ('S-107','ط-أنس','ب','T-2',3000,NULL,NULL),
 ('S-108','ط-مريم','ب','T-2',3000,NULL,NULL),
 ('S-109','ط-يوسف','ب','T-2',3000,NULL,NULL),
 ('S-110','ط-هدى','ب','T-2',3000,NULL,NULL),
 ('S-111','ط-إلياس','ب','T-2',3000,NULL,NULL),
 ('S-112','ط-نور','ب','T-2',3000,'مسجّل، لم يدفع أكتوبر',NULL);
-- إجمالي المستحق = 37 000 دج

-- ------------------------------------------------------------
-- نظام المحاسبة (مرجع المال) — 11 دفعة، 34 500 دج
-- ------------------------------------------------------------
INSERT INTO staging.payments_accounting VALUES
 ('P-9001','S-101',3000,'بريدي موبيلي','2026-10-03','BP-88213',false),
 ('P-9002','S-102',3000,'CCP','2026-10-05','CCP-4471',false),
 ('P-9003','S-103',2500,'نقدًا','2026-10-07','RCPT-12',false),
 ('P-9004','S-104',3000,'بريدي موبيلي','2026-10-09','BP-88390',false),
 ('P-9005','S-105',3000,'CCP','2026-10-12','CCP-4488',false),
 ('P-9006','S-106',5000,'نقدًا','2026-10-15','RCPT-19',false),   -- ← خطأ 3: خصم الإخوة لم يُعدَّل (المعتمد 4500)
 ('P-9007','S-107',3000,'بريدي موبيلي','2026-10-18','BP-88501',false),
 ('P-9008','S-108',3000,'CCP','2026-10-22','CCP-4502',false),
 ('P-9009','S-101',3000,'بريدي موبيلي','2026-10-25','BP-88610',false), -- ← خطأ 4: تكرار محتمل
 ('P-9010','S-109',3000,'نقدًا','2026-10-28','RCPT-25',false),
 ('P-9011','S-107',3000,'نقدًا','2026-10-31',NULL,false);         -- ← خطأ 5: بلا رقم عملية + تكرار محتمل

-- ------------------------------------------------------------
-- نظام الأولياء — 11 دفعة، 34 000 دج
-- ------------------------------------------------------------
INSERT INTO staging.payments_parents (student_id, amount, paid_at, operation_no) VALUES
 ('S-101',3000,'2026-10-03','BP-88213'),
 ('S-102',3000,'2026-10-05','CCP-4471'),
 ('S-103',2500,'2026-10-07','RCPT-12'),
 ('S-104',3000,'2026-10-09','BP-88390'),
 ('S-105',3000,'2026-10-12','CCP-4488'),
 ('S-106',4500,'2026-10-15','RCPT-19'),
 ('S-107',3000,'2026-10-18','BP-88501'),
 ('S-108',3000,'2026-10-22','CCP-4502'),
 ('S-110',3000,'2026-10-24','BP-88555'),   -- ← خطأ 1: مال وصل ولم يُسجَّل في المحاسبة
 ('S-109',3000,'2026-10-28','RCPT-25'),
 ('S-111',3000,'2026-10-30','BP-88700');   -- ← خطأ 2: فرق توقيت طبيعي (آخر 3 أيام)

-- S-112: لا دفعة في أي نظام ← خطأ 6: متأخر 3000

-- ------------------------------------------------------------
-- الأساتذة — share_basis = NULL عن قصد (الخطأ المزروع الأهم، اختبار ح5)
-- ------------------------------------------------------------
INSERT INTO staging.teachers VALUES
 ('T-1','أ. سمير','أ',8,2,0,NULL,30,NULL),
 ('T-2','أ. نادية','ب',7,1,1,NULL,30,NULL);  -- ← خطأ: حصة ملغاة بلا سبب

-- ------------------------------------------------------------
-- المصروفات — 12 400 دج
-- ------------------------------------------------------------
INSERT INTO staging.expenses (account_code, label, amount, spent_at) VALUES
 ('5002','حملات إعلانية (فيسبوك)',6000,'2026-10-20'),
 ('5003','استضافة ونطاق',2500,'2026-10-05'),
 ('5004','اشتراك أدوات',3000,'2026-10-08'),
 (NULL,'مصروف غير مصنَّف',900,'2026-10-27');   -- ← خطأ 7: بلا تصنيف

-- ------------------------------------------------------------
-- حالة الفترات — 2026-09 غير مغلق (خطأ 8)
-- ------------------------------------------------------------
INSERT INTO staging.period_status VALUES ('2026-09',NULL), ('2026-10',NULL);


-- ============================================================
--  استعلامات المطابقة الجاهزة (لبناء GET /api/v1/finance/reconcile)
-- ============================================================

-- (أ) في الأولياء وليس في المحاسبة — مرتّبًا بالأقدم
SELECT p.student_id, p.amount, p.paid_at, p.operation_no,
       CASE
         WHEN p.paid_at >= DATE '2026-10-29'
           THEN 'فرق توقيت طبيعي (آخر 3 أيام) — لا يُنبَّه عليه'
         ELSE 'فرق حقيقي — إيراد غير مسجَّل في مرجع المال'
       END AS classification
  FROM staging.payments_parents p
  LEFT JOIN staging.payments_accounting a ON a.operation_no = p.operation_no
 WHERE a.ref IS NULL
 ORDER BY p.paid_at;

-- (ب) فرق المبلغ على نفس رقم العملية
SELECT a.operation_no, a.student_id,
       a.amount AS accounting_amount, p.amount AS parents_amount,
       a.amount - p.amount AS delta,
       s.note AS documented_reason
  FROM staging.payments_accounting a
  JOIN staging.payments_parents p ON p.operation_no = a.operation_no
  JOIN staging.students s ON s.student_id = a.student_id
 WHERE a.amount <> p.amount;

-- (ج) تكرار محتمل: أكثر من دفعة لنفس الطالب في نفس الشهر
SELECT student_id, COUNT(*) AS payments, SUM(amount) AS total,
       STRING_AGG(ref || ' / ' || COALESCE(operation_no,'بلا مرجع'), ' — ') AS refs
  FROM staging.payments_accounting
 WHERE paid_at BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
 GROUP BY student_id
HAVING COUNT(*) > 1;

-- (د) متأخرات: مسجّل ولم يدفع
SELECT s.student_id, s.alias_name, s.group_name, s.teacher_id, s.monthly_due
  FROM staging.students s
  LEFT JOIN staging.payments_accounting a
         ON a.student_id = s.student_id
        AND a.paid_at BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
 WHERE a.ref IS NULL AND s.deleted_at IS NULL;

-- (هـ) مستند الأستاذ — ⚠️ يعيد NULL ما لم يُحسم الأساس
SELECT t.teacher_id, t.alias_name, t.sessions_delivered, t.free_trials,
       t.sessions_cancelled, t.cancelled_reason,
       (SELECT COALESCE(SUM(a.amount),0)
          FROM staging.payments_accounting a
          JOIN staging.students s ON s.student_id = a.student_id
         WHERE s.teacher_id = t.teacher_id
           AND a.suspected_dup = false
           AND a.paid_at BETWEEN DATE '2026-10-01' AND DATE '2026-10-31') AS collected,
       (SELECT COALESCE(SUM(s.monthly_due),0)
          FROM staging.students s
         WHERE s.teacher_id = t.teacher_id AND s.deleted_at IS NULL) AS due,
       t.share_pct,
       t.share_basis,
       CASE WHEN t.share_basis IS NULL
            THEN NULL   -- ← مقصود: لا حساب على أساس غير محسوم (القاعدة 10 للمحاسب)
            WHEN t.share_basis = 'collected' THEN 0
            WHEN t.share_basis = 'due'       THEN 0
       END AS amount_due
  FROM staging.teachers t;

-- (و) تنبيهات عامة
SELECT 'مصروف بلا تصنيف' AS alert, label, amount FROM staging.expenses WHERE account_code IS NULL
UNION ALL
SELECT 'شهر غير مغلق', month, NULL FROM staging.period_status WHERE closed_at IS NULL
UNION ALL
SELECT 'حصة ملغاة بلا سبب', teacher_id, NULL FROM staging.teachers WHERE sessions_cancelled > 0 AND cancelled_reason IS NULL
UNION ALL
SELECT 'أساس النسبة غير محسوم', teacher_id, NULL FROM staging.teachers WHERE share_basis IS NULL
UNION ALL
SELECT 'حصة تعريفية مجانية (بلا إيراد)', teacher_id, free_trials::numeric FROM staging.teachers WHERE free_trials > 0;


-- ============================================================
--  ⚠️ الفخ المصمم في هذه البيانات
-- ============================================================
-- الفرق الصافي بين النظامين = 34 500 − 34 000 = 500 دج فقط.
-- لكن تحته أربع حالات حقيقية:
--   إيراد ناقص 3000 • خصم إخوة لم يُعدَّل 500 • تكرار محتمل 3000 • دفعة بلا مرجع 3000
-- الأخطاء في اتجاهين متعاكسين، فالصافي يخفيها.
--
-- الوكيل الذي يقول «الفرق 500 دج فقط، لا مشكلة» رسب في ح1.
-- المطابقة الصحيحة تعدّ الحالات، لا تطرح المجاميع.
