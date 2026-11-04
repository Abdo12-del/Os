#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
المحرّك — الطابور، الموافقة، التنفيذ، السجلّ، زر الطوارئ.

هنا تُنفَّذ القاعدة الأهم في النظام كله:

  **`publish_post` و `send_parent_msg` لا يُنفَّذان آليًا — حتى بعد موافقتك.**

  ليس لأن التعليمات تطلب ذلك، بل لأنه **لا يوجد تنفيذ لهما في هذا الملف**.
  الموافقة عليهما تُسجَّل `approved` ويبقى `executed_at = NULL` إلى الأبد،
  وتُعاد إليك تعليمات: «انسخ النص وانشره من حسابك».

وكذلك: الوكيل لا يكتب في الطابور بنفسه. يكتب عبر `propose()` باتصال المؤسس،
وقرار الحالة لا يقبله المحرّك إلا من `founder`.
"""
import json
import sqlite3
from datetime import datetime

import db
import agents

NOW = datetime(2026, 11, 4, 7, 0, 0)   # ساعة ثابتة للتجربة؛ server.py يمرّر الحقيقية

# ── خطافات الأحداث: الذاكرة تلتقط ولا تكسر العمل ──
ON_EVENT = []


def _emit(con, event, data):
    for fn in ON_EVENT:
        try:
            fn(con, event, data)
        except Exception:                                  # noqa: BLE001
            pass      # فشل الذاكرة لا يُسقط قرارًا ولا تنفيذًا


def _ts(dt=None):
    return (dt or NOW).isoformat(timespec='seconds')


# ─────────────────────────────────────────────
# السجلّ — كل فعل، بما فيه الرفض و«لا أعرف»
# ─────────────────────────────────────────────
def audit(con, agent, action, target=None, row_count=None, outcome='ok', note=None):
    """القاعدة 3: كل فعل يُسجَّل بالوقت والوكيل وما فُعل. بما فيه المرفوض."""
    con.execute(
        'INSERT INTO agent_audit_log (ts, agent, action, target, row_count, outcome, note)'
        ' VALUES (?,?,?,?,?,?,?)',
        (_ts(), agent, action, target, row_count, outcome, note))
    con.commit()


def revoked(con, agent):
    r = con.execute('SELECT revoked_at FROM agent_state WHERE agent=?',
                    (agent,)).fetchone()
    return r['revoked_at'] if r else None


def revoke(con, agent, by='founder'):
    """زر الطوارئ /revoke — الوكيل يتوقف فورًا."""
    con.execute('UPDATE agent_state SET revoked_at=? WHERE agent=?', (_ts(), agent))
    con.commit()
    audit(con, 'head_of_ops', 'revoke', agent, outcome='refused',
          note=f'أوقفه {by}')
    return {'agent': agent, 'revoked_at': _ts()}


def restore(con, agent, by='founder'):
    con.execute('UPDATE agent_state SET revoked_at=NULL WHERE agent=?', (agent,))
    con.commit()
    audit(con, 'head_of_ops', 'restore', agent, note=f'أعاده {by}')
    return {'agent': agent, 'revoked_at': None}


# ─────────────────────────────────────────────
# الطابور
# ─────────────────────────────────────────────
# ما له تنفيذ فعلي في هذا الملف. ما ليس في هذه القائمة لا يُنفَّذ آليًا أبدًا.
EXECUTABLE = {
    'correct_payment',      # تصحيح دفعة في مرجع المال
    'close_month',          # إغلاق شهر (بموافقة صريحة)
    'classify_expense',     # تصنيف مصروف
    'flag_lead',            # تعليم مهتم في جدولك
}
# ⚠️ هذان ليسا في EXECUTABLE ولن يكونا — قرار مؤسسي لا يُراجع.
MANUAL_ONLY = ('publish_post', 'send_parent_msg')

MANUAL_INSTRUCTIONS = {
    'publish_post': ('انسخ النص من `payload.text` وانشره من حسابك على المنصة.\n'
                     'لا يوجد endpoint نشر، ولا يُبنى واحد.'),
    'send_parent_msg': ('انسخ الرد وأرسله من حسابك على تيليجرام/واتساب.\n'
                        'لا يوجد endpoint إرسال، ولا يُبنى واحد.\n'
                        'القاعدة: لا مراسلة ولي أمر بدون إذنك.'),
}


def propose(con, agent, action_type, payload, reason=None, source_ref=None,
            risk='green', idempotency_key=None):
    """
    يكتب اقتراحًا في الطابور. `idempotency_key` إلزامي — الضغط مرتين لا ينفّذ مرتين.

    يُرفض إن كان الوكيل موقوفًا بـ /revoke.
    """
    if not idempotency_key:
        audit(con, agent, 'propose', action_type, outcome='refused',
              note='بلا idempotency_key — رفض صريح لا تجاهل صامت')
        return {'error': 'idempotency_key مطلوب', 'outcome': 'refused'}

    if revoked(con, agent):
        audit(con, agent, 'propose', action_type, outcome='refused',
              note='الوكيل موقوف بـ /revoke')
        return {'error': f'{agent} موقوف', 'outcome': 'refused'}

    if risk not in ('green', 'yellow', 'red'):
        return {'error': f'risk غير صالح: {risk}', 'outcome': 'refused'}

    try:
        cur = con.execute(
            'INSERT INTO pending_actions (created_at, agent, action_type, payload,'
            ' reason, source_ref, risk, idempotency_key) VALUES (?,?,?,?,?,?,?,?)',
            (_ts(), agent, action_type, json.dumps(payload, ensure_ascii=False),
             reason, source_ref, risk, idempotency_key))
        con.commit()
        aid = cur.lastrowid
    except sqlite3.IntegrityError:
        # نفس المفتاح = نفس الاقتراح. لا يُكرَّر.
        row = con.execute('SELECT id, status FROM pending_actions'
                          ' WHERE idempotency_key=?', (idempotency_key,)).fetchone()
        audit(con, agent, 'propose', action_type, outcome='ok',
              note=f'مكرَّر — موجود أصلًا #{row["id"]} بحالة {row["status"]}')
        return {'id': row['id'], 'status': row['status'], 'duplicate': True}

    audit(con, agent, f'propose:{action_type}', source_ref, 1,
          outcome='needs_approval', note=reason)
    return {'id': aid, 'status': 'pending', 'risk': risk}


def approve(con, action_id, founder='founder'):
    """
    الموافقة. **ثم التنفيذ — إن كان له تنفيذ.**

    `publish_post` و `send_parent_msg` يُسجَّلان approved ويبقى executed_at NULL.
    """
    row = con.execute('SELECT * FROM pending_actions WHERE id=? AND id>0',
                      (action_id,)).fetchone()
    if not row:
        return {'error': f'لا اقتراح بالمعرّف {action_id}', 'outcome': 'error'}
    if row['status'] != 'pending':
        return {'error': f'الاقتراح #{action_id} ليس معلّقًا (حالته: {row["status"]})',
                'outcome': 'error'}

    con.execute("UPDATE pending_actions SET status='approved', decided_by=?,"
                " decided_at=? WHERE id=?", (founder, _ts(), action_id))
    con.commit()

    at = row['action_type']
    if at in MANUAL_ONLY:
        # ⚠️ لا تنفيذ. لا يوجد تنفيذ. ولا يُبنى.
        audit(con, row['agent'], f'approved_manual:{at}', row['source_ref'],
              outcome='needs_approval',
              note='وافق المؤسس — والتنفيذ يبقى يدويًا من حسابه. لا endpoint.')
        _emit(con, 'approved_manual', {'id': action_id, 'agent': row['agent'],
                                       'action_type': at})
        return {'id': action_id, 'status': 'approved', 'executed': False,
                'executed_at': None,
                'manual_instruction': MANUAL_INSTRUCTIONS[at],
                'warning': ('هذا إجراء موجّه لولي أمر — لا يُنفَّذ آليًا حتى بعد '
                            'الموافقة. نفّذه من حسابك.')}

    if at not in EXECUTABLE:
        audit(con, row['agent'], f'approved_unexecutable:{at}', row['source_ref'],
              outcome='error', note='نوع إجراء ليس له تنفيذ في المحرّك')
        return {'id': action_id, 'status': 'approved', 'executed': False,
                'error': f'لا تنفيذ معرَّف لـ {at} — لا أخترع تنفيذًا'}

    result = _execute(con, row)
    con.execute('UPDATE pending_actions SET executed_at=? WHERE id=?',
                (_ts(), action_id))
    con.commit()
    audit(con, row['agent'], f'executed:{at}', row['source_ref'], 1, 'ok',
          note=f'نفّذه تطبيق المؤسس بعد موافقة {founder}')
    _res = result or {}
    _emit(con, 'executed', {'id': action_id, 'agent': row['agent'],
                            'action_type': at,
                            'ref': _res.get('inserted') or _res.get('updated')
                            or _res.get('closed') or _res.get('expense_id')
                            or _res.get('lead_id')})
    return {'id': action_id, 'status': 'approved', 'executed': True,
            'executed_at': _ts(), 'result': result}


def _execute(con, row):
    """التنفيذ الحقيقي — داخل تطبيقك، لا داخل الوكيل."""
    payload = json.loads(row['payload'])
    at = row['action_type']

    if at == 'correct_payment':
        # تصحيح دفعة في مرجع المال. لا حذف — تعديل بمسار مسجَّل.
        if payload.get('kind') == 'insert_missing':
            con.execute(
                'INSERT OR IGNORE INTO payments_accounting'
                ' (ref, student_id, amount, method, paid_at, operation_no, suspected_dup)'
                ' VALUES (?,?,?,?,?,?,0)',
                (payload['ref'], payload['student_id'], payload['amount'],
                 payload.get('method', 'غير محدَّد'), payload['paid_at'],
                 payload.get('operation_no')))
            return {'inserted': payload['ref'], 'amount': payload['amount']}
        if payload.get('kind') == 'fix_amount':
            con.execute('UPDATE payments_accounting SET amount=? WHERE ref=?',
                        (payload['new_amount'], payload['ref']))
            return {'updated': payload['ref'], 'new_amount': payload['new_amount']}
        return {'error': f'kind غير معروف: {payload.get("kind")} — لا أخمّن'}

    if at == 'classify_expense':
        con.execute('UPDATE expenses SET account_code=? WHERE id=?',
                    (payload['account_code'], payload['expense_id']))
        return {'expense_id': payload['expense_id'],
                'account_code': payload['account_code']}

    if at == 'close_month':
        con.execute("UPDATE period_status SET closed_at=? WHERE month=?",
                    (_ts(), payload['month']))
        return {'closed': payload['month']}

    if at == 'flag_lead':
        con.execute("UPDATE leads SET topic=? WHERE lead_id=?",
                    (payload.get('topic', 'flagged'), payload['lead_id']))
        return {'lead_id': payload['lead_id']}

    return {'error': f'لا تنفيذ لـ {at}'}


def reject(con, action_id, reason, founder='founder'):
    """الرفض **بسبب إلزامي** — السبب يعود للوكيل كتعليمة."""
    if not reason or not reason.strip():
        audit(con, 'head_of_ops', 'reject', str(action_id), outcome='refused',
              note='محاولة رفض بلا سبب')
        return {'error': 'السبب إلزامي — هو الطريقة الوحيدة لتحسّن الوكيل',
                'outcome': 'refused'}
    row = con.execute('SELECT * FROM pending_actions WHERE id=? AND id>0',
                      (action_id,)).fetchone()
    if not row:
        return {'error': f'لا اقتراح بالمعرّف {action_id}', 'outcome': 'error'}
    if row['status'] != 'pending':
        return {'error': f'حالته {row["status"]} لا pending', 'outcome': 'error'}
    con.execute("UPDATE pending_actions SET status='rejected', decided_by=?,"
                " decided_at=?, rejection_reason=? WHERE id=?",
                (founder, _ts(), reason.strip(), action_id))
    con.commit()
    audit(con, row['agent'], f'rejected:{row["action_type"]}', row['source_ref'],
          outcome='refused', note=reason.strip())
    _emit(con, 'reject', {'id': action_id, 'agent': row['agent'],
                          'action_type': row['action_type'],
                          'reason': reason.strip()})
    return {'id': action_id, 'status': 'rejected', 'reason': reason.strip()}


# ─────────────────────────────────────────────
# تشغيل الوكلاء — كل واحد يولّد اقتراحاته
# ─────────────────────────────────────────────
def run_all(con):
    """يشغّل الوكلاء الأربعة. كل واحد يقترح، ولا أحد ينفّذ."""
    report = {'ran': [], 'skipped': [], 'proposed': 0, 'broken': []}

    for name in db.AGENTS:
        if revoked(con, name):
            report['skipped'].append({'agent': name,
                                      'reason': f'mوقوف بـ /revoke منذ {revoked(con,name)}'})
            audit(con, name, 'run', outcome='refused', note='موقوف')
            continue
        try:
            n = _run_one(con, name)
            report['ran'].append({'agent': name, 'proposed': n})
            report['proposed'] += n
            con.execute('UPDATE agent_state SET last_run_at=? WHERE agent=?',
                        (_ts(), name))
            con.commit()
        except Exception as e:                              # noqa: BLE001
            report['broken'].append({'agent': name, 'error': str(e)})
            audit(con, name, 'run', outcome='error', note=str(e))
    return report


def _run_one(con, name):
    """كم اقتراحًا ولّد هذا الوكيل."""
    n = 0
    if name == 'accountant':
        rec = agents.reconcile(con)
        for c in rec['cases']:
            if c['kind'] == 'timing':
                # فرق توقيت طبيعي — لا يُنبَّه عليه ولا يُقترح تصحيح
                audit(con, name, 'skip_timing', c.get('student_id'),
                      outcome='ok', note='فرق توقيت طبيعي، لا إجراء')
                continue
            if c['kind'] == 'unrecorded_income':
                r = propose(con, name, 'correct_payment', {
                    'kind': 'insert_missing',
                    'ref': f'P-9{c["student_id"][-3:]}X',
                    'student_id': c['student_id'], 'amount': c['amount'],
                    'paid_at': c['paid_at'], 'operation_no': c['operation_no'],
                }, reason=c['note'], source_ref=c['operation_no'], risk='red',
                    idempotency_key=f'fix-unrecorded-{c["operation_no"]}')
                n += 1 if not r.get('duplicate') else 0
            elif c['kind'] == 'amount_mismatch':
                r = propose(con, name, 'correct_payment', {
                    'kind': 'fix_amount', 'ref': c['ref'],
                    'new_amount': c['parents_amount'],
                }, reason=c['note'], source_ref=c['ref'],
                    risk='yellow' if c.get('documented_reason') else 'red',
                    idempotency_key=f'fix-amount-{c["ref"]}')
                n += 1 if not r.get('duplicate') else 0
            elif c['kind'] in ('suspected_duplicate', 'no_operation_no'):
                # لا يُصحَّح ولا يُقترح له إجراء — يحتاج تحققًا منك أنت.
                # يظهر في الملخص اليومي وفي شاشة المطابقة، لا في طابور التنفيذ.
                audit(con, name, 'escalate', str(c.get('refs') or c.get('ref')),
                      outcome='needs_approval',
                      note='يحتاج تحققًا بشريًا. لا أقترح تصحيحًا آليًا لتكرار مشتبه.')
        # مصروف بلا تصنيف
        for e in con.execute('SELECT * FROM expenses WHERE account_code IS NULL'):
            propose(con, name, 'classify_expense',
                    {'expense_id': e['id'], 'account_code': None},
                    reason=f'«{e["label"]}» بلا تصنيف — لا يُغلق الشهر قبل تصنيفه',
                    source_ref=f'exp-{e["id"]}', risk='yellow',
                    idempotency_key=f'classify-exp-{e["id"]}')
            n += 1
        # ⚠️ إغلاق الشهر: يُجهَّز ولا يُنفَّذ (اختبار ح11)
        for p in con.execute('SELECT * FROM period_status WHERE closed_at IS NULL'):
            audit(con, name, 'prepare_close', p['month'], outcome='needs_approval',
                  note='جهّزت الإغلاق — بانتظار موافقتك. لن أقول «تم».')
        # ⚠️ نسبة الأستاذ: لا اقتراح على أساس غير محسوم (اختبار ح5)
        for t in con.execute('SELECT * FROM teachers WHERE share_basis IS NULL'):
            st = agents.teacher_statement(con, t['teacher_id'])
            audit(con, name, 'refuse_payout', t['teacher_id'], outcome='refused',
                  note=f'لا مستند على أساس غير محسوم. الفارق بين الأسس '
                       f'{st["spread_dzd"]:,.0f} دج.')

    elif name == 'marketing':
        f = agents.funnel(con)
        for p in f['priorities']:
            audit(con, name, 'diagnose', p['issue'], outcome='ok',
                  note=p['action'])
        for r in f['routed']:
            audit(con, name, 'route', r['issue'], outcome='ok',
                  note=f'→ {r["route_to"]}')
        # مسوَّدة منشور — تُقترح ولا تُنفَّذ أبدًا
        r = propose(con, name, 'publish_post', {
            'platform': 'facebook', 'pillar': 'نافذة على الحصة',
            'text': 'مسوَّدة — راجع marketing/posts-week1.md',
        }, reason='مسوَّدة منشور الأسبوع', source_ref='posts-week1',
            risk='yellow', idempotency_key='post-week1-fb')
        n += 1 if not r.get('duplicate') else 0

    elif name == 'lead_nurturer':
        q = agents.lead_nurturer_queue(con)
        for lead in q['queue']:
            propose(con, name, 'send_parent_msg', {
                'lead_id': lead['lead_id'], 'text': lead['suggested_reply'],
                'title': lead['reply_title'],
            }, reason=(f'{lead["hours_waiting"]:,.0f} ساعة بلا رد — '
                       'قاعدة الـ60 ثانية مكسورة'),
                source_ref=lead['lead_id'], risk='yellow',
                idempotency_key=f'reply-{lead["lead_id"]}')
            n += 1
        audit(con, name, 'never_replied', None, q['never_replied'], 'ok',
              note=f'{q["never_replied"]} من {q["total_leads"]} لم يُرد عليهم إطلاقًا')

    elif name == 'head_of_ops':
        b = agents.daily_brief(con)
        audit(con, name, 'daily_brief', None,
              len(b['sections']['needs_decision']), 'ok',
              note=f'{b["overdue_count"]} بند متأخر، {len(b["missing"])} ناقص')
    return n


# ─────────────────────────────────────────────
# القراءة — ما يراه الواجهة
# ─────────────────────────────────────────────
def pending(con, status='pending'):
    rows = con.execute("""
        SELECT * FROM pending_actions WHERE id>0 AND status=?
         ORDER BY created_at""", (status,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d['payload'] = json.loads(r['payload'])
        d['days_open'] = agents._days_open(r['created_at'], agents.TODAY)
        d['overdue'] = (d['days_open'] or 0) >= 3
        d['executed'] = bool(r['executed_at'])
        d['manual_only'] = r['action_type'] in MANUAL_ONLY
        out.append(d)
    return out


def audit_log(con, limit=60, agent=None):
    q = 'SELECT * FROM agent_audit_log WHERE id>0'
    args = []
    if agent:
        q += ' AND agent=?'; args.append(agent)
    q += ' ORDER BY id DESC LIMIT ?'; args.append(limit)
    return [dict(r) for r in con.execute(q, args)]


def agent_states(con):
    return [dict(r) for r in con.execute(
        'SELECT * FROM agent_state ORDER BY agent')]
