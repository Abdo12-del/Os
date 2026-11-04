#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
طبقة البيانات — SQLite، بلا تبعيات.

هنا تُفرَض القواعد فعليًا، لا تُطلب:

  1. الوكيل يفتح اتصالًا بـ `PRAGMA query_only=1`  → أي INSERT/UPDATE/DELETE يفشل
     في المحرّك نفسه. ليست اتفاقية في نص النظام، بل رفض من قاعدة البيانات.
  2. `no_hard_delete` على كل جدول بيانات               → الحذف يفشل ولو للمالك.
  3. `audit_immutable`                                → سجل التدقيق لا يُعدَّل ولا يُمحى.
  4. الاقتراحات تُكتب عبر `propose()` وحدها، وحالتها لا يغيّرها إلا المؤسس.

⚠️ هذه بيانات fixture مختلَقة (tests/fixtures). لا أسماء أطفال حقيقية ولا مبالغ حقيقية.
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('OPS_DB', os.path.join(HERE, 'ops.db'))

DATA_TABLES = (
    'students', 'payments_accounting', 'payments_parents',
    'teachers', 'expenses', 'period_status', 'leads',
)

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- بياناتك (من staging fixture)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
  student_id  TEXT PRIMARY KEY,
  alias_name  TEXT NOT NULL,          -- اسم مستعار، لا اسم حقيقي
  group_name  TEXT NOT NULL,
  teacher_id  TEXT NOT NULL,
  monthly_due REAL NOT NULL,
  note        TEXT,
  deleted_at  TEXT                     -- حذف ناعم فقط
);

CREATE TABLE IF NOT EXISTS payments_accounting (   -- نظام المحاسبة = مرجع المال
  ref           TEXT PRIMARY KEY,
  student_id    TEXT NOT NULL,
  amount        REAL NOT NULL,
  method        TEXT,
  paid_at       TEXT NOT NULL,
  operation_no  TEXT,                  -- NULL = دفعة بلا مرجع (خطأ مزروع)
  suspected_dup INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments_parents (      -- نظام الأولياء = مرجع التقييمات
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id    TEXT NOT NULL,
  amount        REAL NOT NULL,
  paid_at       TEXT NOT NULL,
  operation_no  TEXT
);

CREATE TABLE IF NOT EXISTS teachers (
  teacher_id        TEXT PRIMARY KEY,
  alias_name        TEXT NOT NULL,
  group_name        TEXT NOT NULL,
  sessions_delivered INTEGER NOT NULL,
  free_trials       INTEGER NOT NULL DEFAULT 0,
  sessions_cancelled INTEGER NOT NULL DEFAULT 0,
  cancelled_reason  TEXT,              -- NULL = سبب غير مسجّل (خطأ مزروع)
  share_pct         REAL,
  share_basis       TEXT               -- NULL = الأساس غير محسوم (القرار 1)
);

CREATE TABLE IF NOT EXISTS expenses (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  account_code TEXT,                   -- NULL = مصروف بلا تصنيف
  label        TEXT NOT NULL,
  amount       REAL NOT NULL,
  spent_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS period_status (
  month     TEXT PRIMARY KEY,
  closed_at TEXT                       -- NULL = شهر غير مغلق
);

CREATE TABLE IF NOT EXISTS leads (
  lead_id        TEXT PRIMARY KEY,
  source         TEXT NOT NULL,        -- facebook | instagram | telegram | referral
  first_msg_at   TEXT NOT NULL,
  first_reply_at TEXT,                 -- NULL = لم يُرد عليه إطلاقًا
  asked_price    INTEGER NOT NULL DEFAULT 0,
  booked_trial   INTEGER NOT NULL DEFAULT 0,
  attended_trial INTEGER NOT NULL DEFAULT 0,
  enrolled       INTEGER NOT NULL DEFAULT 0,
  paid           INTEGER NOT NULL DEFAULT 0,
  topic          TEXT                  -- ما سأل عنه (للمطابقة مع دليل الرد الأول)
);

-- ─────────────────────────────────────────────
-- بنية الوكلاء
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pending_actions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at      TEXT NOT NULL,
  agent           TEXT NOT NULL,
  action_type     TEXT NOT NULL,
  payload         TEXT NOT NULL,       -- JSON: ما سيُنفَّذ حرفيًا
  reason          TEXT,
  source_ref      TEXT,
  risk            TEXT NOT NULL DEFAULT 'green'
                  CHECK (risk IN ('green','yellow','red')),
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','approved','rejected','expired')),
  decided_by      TEXT,
  decided_at      TEXT,
  executed_at     TEXT,                -- يبقى NULL لـ publish_post و send_parent_msg أبدًا
  rejection_reason TEXT,               -- السبب يعود للوكيل كتعليمة
  idempotency_key TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_audit_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,
  agent     TEXT NOT NULL,
  action    TEXT NOT NULL,
  target    TEXT,
  row_count INTEGER,
  outcome   TEXT NOT NULL
            CHECK (outcome IN ('ok','refused','needs_approval','unknown_asked','error')),
  note      TEXT
);

CREATE TABLE IF NOT EXISTS agent_state (
  agent       TEXT PRIMARY KEY,
  revoked_at  TEXT,                    -- زر الطوارئ /revoke
  last_run_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_actions(status, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_ts       ON agent_audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_leads_reply    ON leads(first_reply_at);

-- ── طبقة الدردشة: الواجهة messenger، لا لوحات ──
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread      TEXT NOT NULL,               -- وكيل = جهة اتصال
    sender      TEXT NOT NULL,               -- user | agent | system
    kind        TEXT NOT NULL,               -- text|brief|cases|proposal|result|...
    payload     TEXT NOT NULL,               -- json
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_state (
    thread      TEXT PRIMARY KEY,
    awaiting_reason_for INTEGER              -- رفض ينتظر سببه من المؤسس
);
CREATE INDEX IF NOT EXISTS idx_chat_thread ON chat_messages(thread, id);
"""


def _triggers():
    """القواعد المفروضة في المحرّك نفسه."""
    sql = []
    # 2) لا حذف فعلي — ولو للمالك (القاعدة 2 في 05-rules.md)
    for t in DATA_TABLES:
        sql.append(f"""
        CREATE TRIGGER IF NOT EXISTS no_hard_delete_{t}
        BEFORE DELETE ON {t}
        BEGIN
          SELECT RAISE(ABORT,
            'القاعدة 2: لا حذف في أي أداة لأي سبب. استعمل deleted_at (حذف ناعم).');
        END;""")
    # الحذف الناعم المسموح على students فقط
    sql.append("""
        CREATE TRIGGER IF NOT EXISTS no_hard_delete_pending
        BEFORE DELETE ON pending_actions
        BEGIN
          SELECT RAISE(ABORT, 'الاقتراحات لا تُمحى — سجّل تاريخها. القاعدة 3.');
        END;""")
    # 3) سجل التدقيق لا يُمسّ
    for op in ('UPDATE', 'DELETE'):
        sql.append(f"""
        CREATE TRIGGER IF NOT EXISTS audit_immutable_{op.lower()}
        BEFORE {op} ON agent_audit_log
        BEGIN
          SELECT RAISE(ABORT, 'سجل التدقيق لا يُعدَّل ولا يُمحى — القاعدة 3.');
        END;""")
    return sql


# ─────────────────────────────────────────────
# الاتصالات: دورٌ لكل مستخدم
# ─────────────────────────────────────────────
def connect(role='founder'):
    """
    role='agent'   → قراءة فقط، مفروضة بـ PRAGMA query_only. أي كتابة تفشل.
    role='founder' → قراءة وكتابة، لكن الحذف ما زال محظورًا بالـ trigger.

    ⚠️ الإقلاع لا يمرّ هنا أبدًا: اتصال الوكيل قراءة فقط، فلو حاول بناء المخطط
       لفشل. البناء يتم في init() باتصال قابل للكتابة، قبل فتح أي دور.
    """
    if not os.path.exists(DB_PATH):
        init()          # يبني ويزرع باتصال مستقل، ثم نعود لفتح الدور المطلوب
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    if role == 'agent':
        # هذا هو الفرق بين «طلب» و«فرض»: الوكيل لا يستطيع الكتابة ولو أراد.
        con.execute('PRAGMA query_only = ON')
    return con


def bootstrap(con):
    con.executescript(SCHEMA)
    for stmt in _triggers():
        con.execute(stmt)
    con.commit()
    seed(con)


GUARD = """
-- صفوف حارسة (id=0): تمنع حذف الجدول وهو فارغ.
-- الـ trigger في SQLite يُطلق لكل صف — فبلا صف لا يوجد منع.
-- كل استعلام حقيقي في engine.py يضيف `WHERE id > 0`.
INSERT OR IGNORE INTO pending_actions
  (id, created_at, agent, action_type, payload, risk, status, idempotency_key)
VALUES
  (0, '1970-01-01T00:00:00', '__guard__', '__guard__', '{}', 'green', 'expired', '__guard__');

INSERT OR IGNORE INTO agent_audit_log
  (id, ts, agent, action, outcome, note)
VALUES
  (0, '1970-01-01T00:00:00', '__guard__', '__guard__', 'ok',
   'سطر حارس — وجوده يجعل حذف الجدول مستحيلًا ولو كان فارغًا');
"""


def init():
    """يبني القاعدة ويزرعها إن لم تكن موجودة."""
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    for stmt in _triggers():
        con.execute(stmt)
    con.commit()
    if con.execute('SELECT COUNT(*) FROM students').fetchone()[0] == 0:
        seed(con)
    # الصفوف الحارسة تُزرع بعد إنشاء الـ triggers وإلا منعته
    con.executescript(GUARD)
    for a in AGENTS:
        con.execute(
            'INSERT OR IGNORE INTO agent_state (agent) VALUES (?)', (a,))
    con.commit()
    con.close()
    return DB_PATH


AGENTS = ('head_of_ops', 'accountant', 'marketing', 'lead_nurturer')


# ─────────────────────────────────────────────
# زرع البيانات — من tests/fixtures، مختلَقة بالكامل
# ─────────────────────────────────────────────
def seed(con):
    con.executemany('INSERT INTO students VALUES (?,?,?,?,?,?,?)', [
        ('S-101', 'ط-أحمد', 'أ', 'T-1', 3000, None, None),
        ('S-102', 'ط-بلال', 'أ', 'T-1', 3000, None, None),
        ('S-103', 'ط-ياسمين', 'أ', 'T-1', 2500, 'خصم إخوة معتمد 2026-09-01', None),
        ('S-104', 'ط-ريان', 'أ', 'T-1', 3000, None, None),
        ('S-105', 'ط-لينة', 'أ', 'T-1', 3000, None, None),
        ('S-106', 'ط-سارة وط-آدم', 'أ', 'T-1', 4500, 'طفلان، خصم إخوة معتمد 2026-09-15', None),
        ('S-107', 'ط-أنس', 'ب', 'T-2', 3000, None, None),
        ('S-108', 'ط-مريم', 'ب', 'T-2', 3000, None, None),
        ('S-109', 'ط-يوسف', 'ب', 'T-2', 3000, None, None),
        ('S-110', 'ط-هدى', 'ب', 'T-2', 3000, None, None),
        ('S-111', 'ط-إلياس', 'ب', 'T-2', 3000, None, None),
        ('S-112', 'ط-نور', 'ب', 'T-2', 3000, 'مسجّل، لم يدفع أكتوبر', None),
    ])
    # إجمالي المستحق = 37 000 دج

    con.executemany('INSERT INTO payments_accounting VALUES (?,?,?,?,?,?,?)', [
        ('P-9001', 'S-101', 3000, 'بريدي موبيلي', '2026-10-03', 'BP-88213', 0),
        ('P-9002', 'S-102', 3000, 'CCP', '2026-10-05', 'CCP-4471', 0),
        ('P-9003', 'S-103', 2500, 'نقدًا', '2026-10-07', 'RCPT-12', 0),
        ('P-9004', 'S-104', 3000, 'بريدي موبيلي', '2026-10-09', 'BP-88390', 0),
        ('P-9005', 'S-105', 3000, 'CCP', '2026-10-12', 'CCP-4488', 0),
        ('P-9006', 'S-106', 5000, 'نقدًا', '2026-10-15', 'RCPT-19', 0),   # خصم لم يُعدَّل
        ('P-9007', 'S-107', 3000, 'بريدي موبيلي', '2026-10-18', 'BP-88501', 0),
        ('P-9008', 'S-108', 3000, 'CCP', '2026-10-22', 'CCP-4502', 0),
        ('P-9009', 'S-101', 3000, 'بريدي موبيلي', '2026-10-25', 'BP-88610', 1),  # تكرار محتمل
        ('P-9010', 'S-109', 3000, 'نقدًا', '2026-10-28', 'RCPT-25', 0),
        ('P-9011', 'S-107', 3000, 'نقدًا', '2026-10-31', None, 1),        # بلا مرجع + تكرار
    ])

    con.executemany(
        'INSERT INTO payments_parents (student_id, amount, paid_at, operation_no)'
        ' VALUES (?,?,?,?)', [
        ('S-101', 3000, '2026-10-03', 'BP-88213'),
        ('S-102', 3000, '2026-10-05', 'CCP-4471'),
        ('S-103', 2500, '2026-10-07', 'RCPT-12'),
        ('S-104', 3000, '2026-10-09', 'BP-88390'),
        ('S-105', 3000, '2026-10-12', 'CCP-4488'),
        ('S-106', 4500, '2026-10-15', 'RCPT-19'),
        ('S-107', 3000, '2026-10-18', 'BP-88501'),
        ('S-108', 3000, '2026-10-22', 'CCP-4502'),
        ('S-110', 3000, '2026-10-24', 'BP-88555'),   # وصل ولم يُسجَّل في المحاسبة
        ('S-109', 3000, '2026-10-28', 'RCPT-25'),
        ('S-111', 3000, '2026-10-30', 'BP-88700'),   # فرق توقيت طبيعي
    ])

    # share_basis = NULL عن قصد — القرار 1 لم يُحسم
    con.executemany('INSERT INTO teachers VALUES (?,?,?,?,?,?,?,?,?)', [
        ('T-1', 'أ. سمير', 'أ', 8, 2, 0, None, 30, None),
        ('T-2', 'أ. نادية', 'ب', 7, 1, 1, None, 30, None),
    ])

    con.executemany(
        'INSERT INTO expenses (account_code, label, amount, spent_at) VALUES (?,?,?,?)', [
        ('5002', 'حملات إعلانية (فيسبوك)', 6000, '2026-10-20'),
        ('5003', 'استضافة ونطاق', 2500, '2026-10-05'),
        ('5004', 'اشتراك أدوات', 3000, '2026-10-08'),
        (None, 'مصروف غير مصنَّف', 900, '2026-10-27'),
    ])

    con.executemany('INSERT INTO period_status VALUES (?,?)',
                    [('2026-09', None), ('2026-10', None)])

    seed_leads(con)
    con.commit()


def seed_leads(con):
    """
    27 مهتمًا يطابقون أرقام fixture التسويق بالضبط:
      12 بلا رد إطلاقًا • 9 خلال ساعة • 6 خلال 24 ساعة
      18 سألوا السعر • 11 حجزوا • 8 حضروا • 6 سجّلوا • 5 دفعوا
      المصادر: فيسبوك 14 • إنستغرام 5 • تيليجرام 4 • توصية 4
    """
    sources = (['facebook'] * 14 + ['instagram'] * 5
               + ['telegram'] * 4 + ['referral'] * 4)
    topics = ['price', 'adhd', 'shy', 'price', 'what_do_you_teach',
              'price', 'trial', 'price', 'is_this_tutoring', 'price',
              'adhd', 'price', 'vague', 'price', 'shy',
              'price', 'trial', 'adhd', 'price', 'what_do_you_teach',
              'price', 'trial', 'vague', 'price', 'is_this_tutoring',
              'price', 'shy']

    rows = []
    for i in range(27):
        lid = f'L-{2001 + i}'
        src = sources[i]
        day = 1 + (i % 28)
        first = f'2026-10-{day:02d}T09:{(i * 7) % 60:02d}:00'

        if i < 12:                       # 12 بلا رد إطلاقًا — أكبر تسرّب
            reply = None
        elif i < 21:                     # 9 خلال ساعة
            h, m = 9 + ((i * 7) % 60) // 60, ((i * 7) % 60) + 10
            reply = f'2026-10-{day:02d}T{h + (m // 60):02d}:{m % 60:02d}:00'
        else:                            # 6 خلال 24 ساعة (لا خلال ساعة)
            nd = day + 1 if day < 28 else 28
            reply = f'2026-10-{nd:02d}T14:00:00'

        # القمع متداخل: من دفع ⊂ من سجّل ⊂ من حضر ⊂ من حجز
        booked = 1 if i in (12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22) else 0
        attended = 1 if booked and i in (12, 13, 14, 15, 16, 17, 18, 19) else 0
        enrolled = 1 if attended and i in (12, 13, 14, 15, 16, 17) else 0
        paid = 1 if enrolled and i in (12, 13, 14, 15, 16) else 0
        asked = 1 if topics[i] in ('price', 'trial', 'what_do_you_teach') else 0

        rows.append((lid, src, first, reply, asked, booked,
                     attended, enrolled, paid, topics[i]))

    con.executemany(
        'INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    # 18 سألوا السعر — نضبطها على الرقم المعلن في الـ fixture
    deficit = 18 - sum(r[4] for r in rows)
    if deficit > 0:
        for r in rows:
            if deficit <= 0:
                break
            if not r[4]:
                con.execute('UPDATE leads SET asked_price=1 WHERE lead_id=?',
                            (r[0],))
                deficit -= 1
    con.commit()
