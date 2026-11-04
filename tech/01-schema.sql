-- ============================================================
--  البنية التحتية للقوى العاملة بالذكاء الاصطناعي
--  أكاديمية تنمية الطفل — PostgreSQL
-- ============================================================
--  المبدأ: القواعد العشر في 05-rules.md تُفرض هنا، لا في تعليمات الوكيل.
--  الوكيل لا يحذف لأن هذا الملف لا يعطيه DELETE.
--  الوكيل لا يثبّت قيدًا لأن هذا الملف لا يعطيه INSERT على الجداول المالية.
--
--  نفّذ الأقسام بالترتيب. القسم 7 اختبارات إلزامية — لا تتجاوزها.
--  ⚠️ استبدل أسماء الجداول بأسمائك الحقيقية (من knowledge/06-accounting-setup.md القسم 2)
-- ============================================================


-- ------------------------------------------------------------
-- 1) الحذف ممنوع في قاعدة البيانات نفسها (القاعدة 2 في 05-rules.md)
-- ------------------------------------------------------------
-- خطّان للدفاع: (أ) لا أحد يملك DELETE، (ب) حتى من يملكه يمنعه trigger.

-- (أ) أعمدة الحذف الناعم على جداولك الأساسية
-- ALTER TABLE students   ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by TEXT, ADD COLUMN delete_reason TEXT;
-- ALTER TABLE payments   ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by TEXT, ADD COLUMN delete_reason TEXT;
-- ALTER TABLE expenses   ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by TEXT, ADD COLUMN delete_reason TEXT;

-- (ب) trigger يمنع الحذف الفعلي عن أي مستخدم غير مالك القاعدة
CREATE OR REPLACE FUNCTION fn_block_hard_delete() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'الحذف ممنوع في هذه القاعدة (القاعدة 2). استعمل الحذف الناعم: deleted_at + deleted_by + delete_reason.'
    USING HINT = 'UPDATE ... SET deleted_at = now(), deleted_by = $current_user, delete_reason = ''...''';
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- ضعها على كل جدول يهمّك. أمثلة:
-- CREATE TRIGGER trg_no_delete_students BEFORE DELETE ON students FOR EACH ROW EXECUTE FUNCTION fn_block_hard_delete();
-- CREATE TRIGGER trg_no_delete_payments BEFORE DELETE ON payments FOR EACH ROW EXECUTE FUNCTION fn_block_hard_delete();


-- ------------------------------------------------------------
-- 2) طابور الموافقات — الطريق الوحيد للكتابة (القاعدة 1)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pending_actions (
  id              BIGSERIAL PRIMARY KEY,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  agent           TEXT NOT NULL,               -- 'marketing' | 'accountant' | 'head_of_ops' | ...
  action_type     TEXT NOT NULL,               -- 'publish_post' | 'send_parent_msg' | 'correct_payment' | 'teacher_payout' | 'close_month'
  payload         JSONB NOT NULL,              -- ما سيُنفَّذ حرفيًا
  reason          TEXT,                        -- لماذا اقترحه الوكيل
  source_ref      TEXT,                        -- المرجع من بياناتك (مرجع دفعة، معرّف طالب)
  risk            TEXT NOT NULL DEFAULT 'green' CHECK (risk IN ('green','yellow','red')),
  status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired')),
  decided_by      TEXT,
  decided_at      TIMESTAMPTZ,
  executed_at     TIMESTAMPTZ,                 -- يبقى NULL حتى ينفّذه تطبيقك أنت
  idempotency_key TEXT UNIQUE NOT NULL         -- يمنع تكرار نفس الاقتراح
                                             -- (قاعدة المحاسب 14 في 07-prompts/04-accountant.md،
                                             --  لا القاعدة 14 في 05-rules.md — فعددها 11)
);
CREATE INDEX IF NOT EXISTS idx_pending_open   ON pending_actions (status, created_at);
CREATE INDEX IF NOT EXISTS idx_pending_agent  ON pending_actions (agent, status);

-- لا يجوز للوكيل أن يغيّر حالة اقتراحه بنفسه
CREATE OR REPLACE FUNCTION fn_lock_pending_status() RETURNS trigger AS $$
BEGIN
  IF OLD.status <> 'pending' AND current_user LIKE 'agent_%' THEN
    RAISE EXCEPTION 'الوكيل لا يغيّر حالة إجراء مقترح. القرار للمؤسس فقط.';
  END IF;
  IF NEW.status <> 'pending' AND NEW.decided_by IS NULL THEN
    RAISE EXCEPTION 'لا تغيير حالة بدون decided_by.';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lock_pending BEFORE UPDATE ON pending_actions
  FOR EACH ROW EXECUTE FUNCTION fn_lock_pending_status();


-- ------------------------------------------------------------
-- 3) سجل التدقيق — لا يُمحى، ولا يُعدَّل (القاعدة 3)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_audit_log (
  id          BIGSERIAL PRIMARY KEY,
  ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
  agent       TEXT NOT NULL,
  action      TEXT NOT NULL,   -- 'read_payments' | 'propose_correction' | 'refused_delete' | 'escalated' | 'unknown_asked'
  target      TEXT,            -- أي صفوف/كيانات لُمست
  row_count   INT,
  outcome     TEXT NOT NULL CHECK (outcome IN ('ok','refused','needs_approval','unknown_asked','error')),
  note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON agent_audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON agent_audit_log (agent, ts DESC);

-- سجل التدقيق للقراءة والإضافة فقط: لا تعديل ولا حذف، لأحد، ولا لك
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON agent_audit_log
  FOR EACH ROW EXECUTE FUNCTION fn_block_hard_delete();

CREATE OR REPLACE FUNCTION fn_audit_no_update() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'سجل التدقيق لا يُعدَّل. إن امتلأ، أرشفه في جدول آخر — لا تمسحه ولا تغيّره.';
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON agent_audit_log
  FOR EACH ROW EXECUTE FUNCTION fn_audit_no_update();

-- ⚠️ سجّل الرفضات و«لا أعرف» كذلك. عددها مقياس صحة الوكيل لا عيبه.


-- ------------------------------------------------------------
-- 4) التوكنات — واحد لكل وكيل، يُسحب وحده (القاعدة: وكيل واحد لا يفسد الباقي)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_tokens (
  id           SERIAL PRIMARY KEY,
  agent        TEXT NOT NULL UNIQUE,
  token_hash   TEXT NOT NULL,          -- لا تخزّن التوكن صريحًا، خزّن hash
  scopes       TEXT[] NOT NULL,        -- {'marketing:read','finance:read','actions:propose'}
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,   -- 30 يومًا كحد أقصى، ثم تجديد
  revoked_at   TIMESTAMPTZ,            -- زر «الإنسان يتجاوز النظام» = املأ هذا الحقل
  last_used_at TIMESTAMPTZ
);


-- ------------------------------------------------------------
-- 5) مستخدمو القراءة فقط — وكيل واحد = مستخدم واحد
-- ------------------------------------------------------------
-- ⚠️ لا يشترك وكيلان في مستخدم واحد أبدًا. وإن احتجت سحب صلاحية وكيل، تسحبه وحده.

-- 5.1) وكيل التسويق
-- CREATE USER agent_marketing_read WITH PASSWORD '<قوي، من مولّد>';
-- GRANT CONNECT ON DATABASE academy TO agent_marketing_read;
-- GRANT USAGE ON SCHEMA public TO agent_marketing_read;
-- GRANT SELECT ON leads, enrollments, sessions, attendance TO agent_marketing_read;
-- GRANT INSERT ON pending_actions TO agent_marketing_read;
-- GRANT INSERT ON agent_audit_log TO agent_marketing_read;
-- GRANT USAGE, SELECT ON SEQUENCE pending_actions_id_seq TO agent_marketing_read;
-- GRANT USAGE, SELECT ON SEQUENCE agent_audit_log_id_seq TO agent_marketing_read;
--
-- ⚠️ خفّض البيانات: وكيل التسويق لا يحتاج هاتفًا ولا عنوانًا ولا مبلغ دفعة.
--    أعطه views لا الجداول:
-- CREATE VIEW v_marketing_leads AS
--   SELECT id, first_name, child_age, source, first_contact_at, asked_about, status
--   FROM leads;                       -- بلا phone، بلا address، بلا amount
-- GRANT SELECT ON v_marketing_leads TO agent_marketing_read;

-- 5.2) وكيل المحاسب
-- CREATE USER agent_accountant_read WITH PASSWORD '<قوي، من مولّد>';
-- GRANT CONNECT ON DATABASE academy TO agent_accountant_read;
-- GRANT USAGE ON SCHEMA public TO agent_accountant_read;
-- GRANT SELECT ON payments, expenses, teacher_payouts, sessions TO agent_accountant_read;
-- GRANT INSERT ON pending_actions TO agent_accountant_read;
-- GRANT INSERT ON agent_audit_log TO agent_accountant_read;
-- GRANT USAGE, SELECT ON SEQUENCE pending_actions_id_seq TO agent_accountant_read;
-- GRANT USAGE, SELECT ON SEQUENCE agent_audit_log_id_seq TO agent_accountant_read;
--
-- ⚠️ المحاسب يستعمل معرّف الطالب لا اسمه (قاعدة المحاسب 13 في 07-prompts/04-accountant.md،
--    وأصلها القاعدة 6 في 05-rules.md: خصوصية الطفل). أعطه view:
-- CREATE VIEW v_finance_payments AS
--   SELECT p.id, p.student_id, p.amount, p.currency, p.method, p.paid_at, p.reference
--   FROM payments p;                  -- بلا اسم الطفل، بلا هاتف ولي الأمر


-- ------------------------------------------------------------
-- 6) التنفيذ — دالة واحدة في تطبيقك، أنت من يناديها
-- ------------------------------------------------------------
-- الوكيل لا يناديها. لا يوجد endpoint يعرّضها. تُستدعى من زر الموافقة في لوحتك.
--
-- CREATE OR REPLACE FUNCTION approve_and_execute(p_action_id BIGINT, p_founder TEXT)
-- RETURNS void AS $$
-- DECLARE v_action pending_actions%ROWTYPE;
-- BEGIN
--   SELECT * INTO v_action FROM pending_actions WHERE id = p_action_id FOR UPDATE;
--   IF v_action.status <> 'pending' THEN
--     RAISE EXCEPTION 'الإجراء % ليس معلّقًا (حالته: %)', p_action_id, v_action.status;
--   END IF;
--
--   UPDATE pending_actions
--      SET status='approved', decided_by=p_founder, decided_at=now()
--    WHERE id = p_action_id;
--
--   -- هنا التنفيذ الحقيقي حسب action_type، داخل تطبيقك أنت:
--   --   'correct_payment'  → UPDATE payments SET ... (بـ deleted_by/audit)
--   --   'teacher_payout'   → INSERT INTO teacher_payouts ...
--   --   'publish_post'     → ⚠️ لا تنفّذها هنا. النشر يبقى يدويًا من حسابك.
--   --   'send_parent_msg'  → ⚠️ لا تنفّذها هنا. الإرسال يبقى من حسابك.
--
--   UPDATE pending_actions SET executed_at = now() WHERE id = p_action_id;
--   INSERT INTO agent_audit_log (agent, action, target, outcome, note)
--   VALUES (v_action.agent, 'executed:'||v_action.action_type, v_action.source_ref, 'ok', 'approved by '||p_founder);
-- END;
-- $$ LANGUAGE plpgsql;
--
-- ⚠️ انتبه للسطرين المعلّمين بـ ⚠️: publish_post و send_parent_msg لا يُنفَّذان آليًا أبدًا.
--    القرار المؤسسي: النشر والإرسال يبقى يدويًا من حسابك. لا تبني لهما تنفيذًا آليًا ولو لاحقًا.


-- ------------------------------------------------------------
-- 7) اختبارات إلزامية — لا تتجاوز هذا القسم
-- ------------------------------------------------------------
-- نفّذها بيديك. كل واحدة يجب أن تفشل. إن نجحت، البنية مكسورة — توقّف وأصلحها.

-- 7.1) الوكيل المالي لا يستطيع الكتابة في جدول مالي (يجب أن يفشل: permission denied)
-- SET ROLE agent_accountant_read;
-- INSERT INTO payments (student_id, amount, paid_at) VALUES (1, 3000, now());
-- RESET ROLE;

-- 7.2) الوكيل لا يستطيع الحذف (يجب أن يفشل)
-- SET ROLE agent_accountant_read;
-- DELETE FROM payments WHERE id = 1;
-- RESET ROLE;

-- 7.3) حتى المالك لا يستطيع الحذف الفعلي (يجب أن يفشل برسالة القاعدة 2)
-- DELETE FROM payments WHERE id = 1;

-- 7.4) الوكيل لا يستطيع تغيير حالة اقتراحه (يجب أن يفشل)
-- SET ROLE agent_accountant_read;
-- UPDATE pending_actions SET status='approved' WHERE id = 1;
-- RESET ROLE;

-- 7.5) سجل التدقيق لا يُعدَّل ولا يُمحى (يجب أن يفشل الاثنان)
-- UPDATE agent_audit_log SET note='x' WHERE id = 1;
-- DELETE FROM agent_audit_log WHERE id = 1;

-- 7.6) وكيل التسويق لا يرى الجداول المالية (يجب أن يفشل: permission denied)
-- SET ROLE agent_marketing_read;
-- SELECT * FROM payments LIMIT 1;
-- RESET ROLE;

-- 7.7) وكيل التسويق لا يرى أرقام الهواتف (يجب أن يفشل أو يُرجع أعمدة مخفّضة فقط)
-- SET ROLE agent_marketing_read;
-- SELECT phone FROM leads LIMIT 1;
-- RESET ROLE;

-- 7.8) لا اقتراح مكرر على نفس المرجع (يجب أن يفشل الثاني: duplicate key)
-- INSERT INTO pending_actions (agent, action_type, payload, idempotency_key)
--   VALUES ('accountant','correct_payment','{}','pay-104-2026-11');
-- INSERT INTO pending_actions (agent, action_type, payload, idempotency_key)
--   VALUES ('accountant','correct_payment','{}','pay-104-2026-11');


-- ------------------------------------------------------------
-- 8) استعلامات المراقبة — شغّلها أسبوعيًا
-- ------------------------------------------------------------

-- 8.1) الطابور المتراكم: كم اقتراحًا معلّقًا ينتظرك؟
-- SELECT agent, count(*) AS open_actions, min(created_at) AS oldest
--   FROM pending_actions WHERE status='pending' GROUP BY agent ORDER BY oldest;

-- 8.2) كم مرة رفض الوكيل أو قال «لا أعرف»؟ (مقياس صحة، لا عيب)
-- SELECT agent, outcome, count(*) FROM agent_audit_log
--   WHERE ts > now() - interval '30 days' GROUP BY agent, outcome ORDER BY 3 DESC;

-- 8.3) أي وكيل لمس أكثر البيانات حساسية؟
-- SELECT agent, target, count(*), max(ts) FROM agent_audit_log
--   WHERE action LIKE 'read_%' AND ts > now() - interval '7 days'
--   GROUP BY agent, target ORDER BY 3 DESC;

-- 8.4) توكنات قاربت على الانتهاء أو لم تُستعمل (تنظيف)
-- SELECT agent, expires_at, last_used_at FROM agent_tokens
--   WHERE revoked_at IS NULL AND (expires_at < now() + interval '7 days' OR last_used_at < now() - interval '30 days');
