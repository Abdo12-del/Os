#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
طبقة الدردشة — الواجهة التي طلبها المؤسس: messenger، لا لوحات.

الفكرة: كل وكيل **جهة اتصال**. تفتح محادثته فتجد رسائله: ملخصه، حالاته،
مسوّداته — وكل اقتراح يصل كفقاعة فيها زرّا [موافقة] [رفض]. تكتب أنت
بالعربية كما تكتب لأي موظف، ويفهمك **مطابقة قواعد** لا نموذج لغة:

    «شغّل الوكلاء»   → يعمل الأربعة ويرسل كل واحد ما وجد في محادثته
    «الملخص»         → رئيس العمليات يرسل ملخص الصباح
    «المطابقة»       → المحاسب يرسل الحالات الست
    «موافقة 12»      → تُنفَّذ إن كان لها تنفيذ، وإلا تعليمة يدوية
    «رفض 12»         → أسألك السبب أولًا — الرفض بلا سبب لا يُسجَّل
    «أوقف المحاسب»   → /revoke داخل المحادثة نفسها

لماذا مطابقة لا توليد؟ لأن وكيلًا يفهم بالأوامر الصريحة لا يخترع فهمًا.
وما لا يفهمه يقول: «لا أفهم» ويعدّد ما يفهمه — القاعدة الرابعة.
"""
import json
import os
import re
import unicodedata

import agents
import engine
import memory
import nlg
import sem

# ── جهات الاتصال ─────────────────────────────────────────────
THREADS = [
    {'id': 'head_of_ops', 'name': 'رئيس العمليات', 'emoji': '🧭',
     'role': 'يلخّص صباحًا، يوجّه، ويصعّد ما لا يفهمه', 'grad': 'g1'},
    {'id': 'accountant', 'name': 'المحاسب', 'emoji': '🧮',
     'role': 'مطابقة المال، مستندات الأساتذة، إقفال الشهر', 'grad': 'g2'},
    {'id': 'marketing', 'name': 'خبير التسويق', 'emoji': '📣',
     'role': 'قمع المهتمين ومسوّدات النشر — لا ينشر بنفسه', 'grad': 'g3'},
    {'id': 'lead_nurturer', 'name': 'متابع المهتمين', 'emoji': '💬',
     'role': 'مسوّدات الرد الأول — لا يرسل لأحد بدونك', 'grad': 'g4'},
]
BY_ID = {t['id']: t for t in THREADS}

# أسماء يفهمهاParser الإيقاف/الاستئناف
ALIAS = {
    'رئيس العمليات': 'head_of_ops', 'الرئيس': 'head_of_ops',
    'المحاسب': 'accountant', 'محاسب': 'accountant',
    'خبير التسويق': 'marketing', 'التسويق': 'marketing', 'تسويق': 'marketing',
    'متابع المهتمين': 'lead_nurturer', 'المهتمين': 'lead_nurturer',
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread      TEXT NOT NULL,
    sender      TEXT NOT NULL,              -- user | agent | system
    kind        TEXT NOT NULL,              -- text|brief|cases|proposal|result|...
    payload     TEXT NOT NULL,              -- json
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_state (
    thread      TEXT PRIMARY KEY,
    awaiting_reason_for INTEGER             -- رفض ينتظر سببه
);
CREATE INDEX IF NOT EXISTS ix_chat_thread ON chat_messages(thread, id);
"""


def norm(s):
    """تطبيع عربي: بلا تشكيل، همزات موحّدة، لاتيني صغير."""
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    for a, b in (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ى', 'ي'),
                 ('ة', 'ه'), ('ؤ', 'و'), ('ئ', 'ي')):
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip().lower()


# ── التخزين ───────────────────────────────────────────────────
def init(con):
    con.executescript(SCHEMA)
    con.commit()


def post(con, thread, sender, kind, payload):
    cur = con.execute(
        'INSERT INTO chat_messages (thread, sender, kind, payload, created_at)'
        ' VALUES (?,?,?,?,?)',
        (thread, sender, kind, json.dumps(payload, ensure_ascii=False, default=str),
         engine._ts()))
    con.commit()
    return cur.lastrowid


def messages(con, thread, since=0, limit=300):
    rows = con.execute(
        'SELECT * FROM chat_messages WHERE thread=? AND id>? ORDER BY id LIMIT ?',
        (thread, since, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d['payload'] = json.loads(r['payload'])
        out.append(d)
    return out


def _preview(m):
    k, p = m['kind'], m['payload']
    if k == 'text':
        return p.get('text', '')
    if k == 'proposal':
        return f"اقتراح #{p.get('id')}: {p.get('action_type')}"
    if k == 'brief':
        return 'الملخص اليومي'
    if k == 'cases':
        return f"المطابقة — فرق {p.get('net_difference')} دج"
    if k == 'teacher':
        return f"مستند {p.get('alias', '')}"
    if k == 'funnel':
        return 'قمع التسويق'
    if k == 'leads':
        return f"{p.get('never_replied')} بانتظار رد أول"
    if k == 'audit':
        return 'آخر سجلّ التدقيق'
    if k == 'result':
        return p.get('text', '')
    return k


def threads_meta(con):
    """لقائمة الجهات: آخر رسالة، وعدّاد المعلّق، وحالة الإيقاف."""
    out = []
    for t in THREADS:
        last = con.execute(
            'SELECT * FROM chat_messages WHERE thread=? ORDER BY id DESC LIMIT 1',
            (t['id'],)).fetchone()
        pend = con.execute(
            "SELECT COUNT(*) c FROM pending_actions WHERE id>0 AND status='pending'"
            " AND agent=?", (t['id'],)).fetchone()['c']
        st = con.execute('SELECT * FROM agent_state WHERE agent=?',
                         (t['id'],)).fetchone()
        out.append({
            **t,
            'last_preview': _preview(dict(last, payload=json.loads(last['payload'])))
            if last else 'لا رسائل بعد — اكتب «شغّل»',
            'last_at': last['created_at'] if last else None,
            'last_id': last['id'] if last else 0,
            'pending_count': pend,
            'revoked_at': st['revoked_at'] if st else None,
        })
    return out


def seed(con):
    """تحية أولى إن كانت المحادثات فارغة — لا شاشة بيضاء."""
    n = con.execute('SELECT COUNT(*) c FROM chat_messages').fetchone()['c']
    if n:
        return
    post(con, 'head_of_ops', 'agent', 'text', {'text': (
        'صباح الخير. أنا رئيس العمليات.\n'
        'كل صباح أضع عندك ثلاثة أقسام: ما حدث، ما يحتاج قرارك، وما تعطّل.\n'
        'لا أنشر شيئًا ولا أراسل أحدًا بدونك — ولا يوجد في هذا النظام كود ينفّذ '
        'النشر أصلًا، فالموافقة تسجَّل والتنفيذ يبقى يدك.')})
    post(con, 'head_of_ops', 'agent', 'text', {'text': (
        'تقدر تكتب لي كما تكتب لموظف: «الملخص»، «شغّل الوكلاء»، '
        '«ما المعلّق؟»، «موافقة 12»، «رفض 12 السبب: …»، «أوقف المحاسب».\n'
        'وما لا أفهمه أقول لا أفهمه — لا أخمّن.')})
    post(con, 'accountant', 'agent', 'text', {'text': (
        'المحاسب هنا. مرجعي للمال نظام المحاسبة، وللتقييمات نظام الأولياء.\n'
        'اكتب «المطابقة» لأريك الحالات، أو «مستند الأستاذ» لمستند الحصة — '
        'وإن لم يكن الأساس محسومًا عندك سأقول لك لا أعرف وأريك الفارق بين الأسس.')})
    post(con, 'marketing', 'agent', 'text', {'text': (
        'خبير التسويق هنا. اكتب «القمع» لأريك أين تسرّب المهتمون.\n'
        'مسوّدات النشر أضعها عندك فقاعة بزر موافقة — والنشر يدك، لا يدي.')})
    post(con, 'lead_nurturer', 'agent', 'text', {'text': (
        'متابع المهتمين هنا. اكتب «الردود» لأريك من ينتظر ردًّا أول.\n'
        'كل مسوّدة من دليل الرد الأول — ثمانية ردود محفوظة، لا أؤلّف تاسعًا. '
        'والإرسال لولي أمر بدون إذنك: لا يوجد له تنفيذ في هذا النظام.')})


# ── الأفهام ───────────────────────────────────────────────────
def _say(con, thread, text, **extra):
    pid = post(con, thread, 'agent', 'text', {'text': text, **extra})
    return pid


def _post_pending(con, thread, row):
    d = dict(row)
    d['payload'] = json.loads(row['payload']) if isinstance(row['payload'], str) \
        else row['payload']
    d['manual_only'] = row['action_type'] in engine.MANUAL_ONLY
    d['executed'] = bool(row['executed_at'])
    les = memory.recall(con, f"{row['action_type']} {row.get('reason') or ''}",
                        owner=row['agent'], kinds=('lesson',), k=1)
    if les:
        d['memory_note'] = f"{les[0]['subject']} — {les[0]['text']}"
    return post(con, thread, 'agent', 'proposal', d)


def _do_run(con, thread):
    rep = engine.run_all(con)
    lines = []
    for r in rep['ran']:
        t = BY_ID.get(r['agent'])
        lines.append(f"• {t['name'] if t else r['agent']}: {r['proposed']} اقتراحًا")
    for s in rep['skipped']:
        t = BY_ID.get(s['agent'])
        lines.append(f"• {t['name'] if t else s['agent']}: ⛔ {s['reason']}")
    _say(con, 'head_of_ops', nlg.prose_run(
            rep, {t['id']: t['name'] for t in THREADS})
         + (f'\n⚠️ تعطّل: {rep["broken"]}' if rep['broken'] else ''))
    # كل اقتراح معلّق لم يُرسل بعد → فقاعة في محادثة وكيله
    sent = 0
    for row in engine.pending(con, 'pending'):
        already = con.execute(
            "SELECT 1 FROM chat_messages WHERE kind='proposal' AND payload LIKE ?",
            (f'%"id": {row["id"]},%',)).fetchone()
        if already:
            continue
        _post_pending(con, row['agent'], row)
        sent += 1
    if sent:
        _say(con, thread, f'وصلت {nlg.counted(sent, "فقاعة", "فقاعات", "فقاعتان", "f")}'
                          ' اقتراح — زرّا موافقة/رفض تحت كل واحدة.')
    return rep


def _do_brief(con, thread):
    b = agents.daily_brief(con)
    b['memory'] = memory.brief_memory(con)
    post(con, thread, 'agent', 'brief', b)


def _do_reconcile(con, thread):
    r = agents.reconcile(con)
    post(con, thread, 'agent', 'cases', r)
    _say(con, thread, nlg.prose_reconcile(r))


def _do_teacher(con, thread, tid=None):
    if not tid:
        rows = con.execute('SELECT teacher_id, alias_name FROM teachers'
                           ' ORDER BY teacher_id').fetchall()
        _say(con, thread, 'عندك أستاذان: ' +
             '، '.join(f"{r['teacher_id']} ({r['alias_name']})" for r in rows) +
             '.\nاكتب «مستند T-1» أو «مستند T-2».')
        return
    st = memory.apply_decision_to_statement(con, agents.teacher_statement(con, tid))
    post(con, thread, 'agent', 'teacher', st)
    if st.get('basis') is None:
        _say(con, thread, nlg.prose_teacher(st)
             + '\n(هذا ليس تقصيرًا — هذا هو الأمان: لا رقم على أساس غير محسوم.)')
    else:
        _say(con, thread, nlg.prose_teacher(st))


def _do_funnel(con, thread):
    f = agents.funnel(con)
    post(con, thread, 'agent', 'funnel', f)


def _do_leads(con, thread):
    q = agents.lead_nurturer_queue(con)
    post(con, thread, 'agent', 'leads', q)
    _say(con, thread, nlg.prose_leads(q))


def _do_pending(con, thread):
    rows = engine.pending(con, 'pending')
    if not rows:
        _say(con, thread, 'لا شيء معلّق الآن. الصفر هنا خبر جيد، لا خلل.')
        return
    mine = [r for r in rows if r['agent'] == thread] or rows
    _say(con, thread, f'عندك {len(rows)} اقتراحًا معلّقًا'
         + ('' if mine is rows else f'، منها {len(mine)} في هذه المحادثة') + ':')
    for r in mine:
        _post_pending(con, thread, r)


def _do_audit(con, thread):
    rows = engine.audit_log(con, 15)
    post(con, thread, 'agent', 'audit', {'rows': rows})


def _do_revoke(con, thread, agent):
    r = engine.revoke(con, agent)
    post(con, thread, 'system', 'result',
         {'text': f"⛔ أوقفتُ {BY_ID[agent]['name']} — لن يقترح شيئًا حتى تعيده.",
          'ok': True, 'detail': r})


def _do_restore(con, thread, agent):
    r = engine.restore(con, agent)
    post(con, thread, 'system', 'result',
         {'text': f"▶️ أعدتُ {BY_ID[agent]['name']} إلى العمل.",
          'ok': True, 'detail': r})


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASIS_LABEL = {
    'collected_net': 'المحصَّل المسجَّل في مرجع المال',
    'collected_actual': 'المحصَّل فعلًا (المسجَّل + ما وصل ولم يُسجَّل)',
    'collected_gross': 'إجمالي مرجع المال (بما فيه المشتبه بتكراره)',
    'due': 'المستحق (سواء دُفع أم لا)',
}


def _raw_after(text, needle):
    i = norm(text).find(norm(needle))
    return text[i + len(needle):].strip() if i >= 0 else ''


def _do_recall(con, thread, q, kinds=None, title=None):
    if q:
        items = memory.recall(con, q, kinds=kinds, k=5)
    else:
        act = [m for m in memory.all_memories(con, include_invalid=False)
               if not kinds or m['kind'] in kinds]
        items = act[-5:][::-1]
    if not items:
        _say(con, thread, 'لا تذكر ذاكرتي شيئًا عن هذا — ولا أخترع ذكرى.')
        return
    post(con, thread, 'agent', 'memory',
         {'title': title or f'عن «{q}»', 'items': items})


def _do_remember(con, thread, raw):
    raw = raw.strip()
    if not raw:
        _say(con, thread, 'أتذكر ماذا؟ اكتب الجملة كاملة.')
        return
    kind = 'promise' if re.search(r'(وعد|ساتصل|سارسل|سعيد|سادفع|ساحضر)',
                                  norm(raw)) else 'fact'
    mid = memory.remember(con, kind, 'founder', raw[:48], raw,
                          tags='#ذاكرة', source='chat')
    _say(con, thread, f'حفظتُها في العقل الثاني (#{mid}) كـ'
         f'{"وعد" if kind == "promise" else "حقيقة"}.\n'
         'ستظهر في الملخص الصباحي حتى تُنفَّذ، ولن تُمحى — إن تغيّرت فسأبطلها '
         'وأكتب الجديدة جنبها.')


def _do_decide(con, thread, raw):
    tt = norm(raw)
    if ('اساس' in tt and ('استاذ' in tt or 'حصه' in tt or 'نسبه' in tt)) \
            or 'share_basis' in tt:
        key = None
        if 'مستحق' in tt:
            key = 'due'
        elif 'فعلي' in tt or 'واصل' in tt or 'وصل' in tt:
            key = 'collected_actual'
        elif 'اجمالي' in tt or 'كلي' in tt:
            key = 'collected_gross'
        elif 'صافي' in tt or 'مسجل' in tt:
            key = 'collected_net'
        if key:
            old, new = memory.decide(con, '#share_basis', 'أساس حصة الأستاذ',
                                     raw.strip(), source='chat',
                                     extra_tags=f'#basis:{key}')
            msg = (f'قرار محفوظ (#{new}): أساس حصة الأستاذ = {BASIS_LABEL[key]}.\n'
                   'من الآن يخرج مستند الأستاذ بمبلغ محسوب، ومصدره هذه الذكرى.')
            if old:
                msg += (f'\nالقرار السابق (#{old["id"]}) أُبطل وبقي في التاريخ — '
                        'لا شيء يُمحى.')
            _say(con, thread, msg)
            return
        _say(con, thread, 'أي أساس؟ اكتب واحدة: صافي المسجَّل / الفعلي الواصل / '
                          'الإجمالي / المستحق.')
        return
    mid = memory.remember(con, 'decision', 'founder', raw.strip()[:48],
                          raw.strip(), tags='#قرار', source='chat')
    _say(con, thread, f'سجّلتُ قرارك (#{mid}) في العقل الثاني. سأبني عليه '
                      'ولا أنساه.')


def _do_export(con, thread):
    path = os.path.join(REPO_ROOT, 'memory', 'exports',
                        f'export-{engine.NOW.date().isoformat()}.md')
    n = memory.export_md(con, path)
    _say(con, thread, f'صدّرتُ {n} ذكرى إلى {os.path.relpath(path, REPO_ROOT)}.\n'
         'اعمل لها commit فيصير درسُ اليوم تدريبًا دائمًا للوكلاء.')


HELP = ('أفهم هذه — ولا أدّعي غيرها:\n'
        '• تذكّر أن … — احفظها في العقل الثاني\n'
        '• قررت … — قرار يُبطِل ما قبله ويبقيه في التاريخ\n'
        '• ماذا تذكر عن …؟ / ماذا قررت؟ / لماذا رفضت؟\n'
        '• صدّر الذاكرة — اكتبها ملفًّا لتcommitها\n'
        '• درّب الفهم — أعد بناء متجهات الكلمات من نصوصك\n'
        '• شغّل الوكلاء — يعمل الأربعة\n'
        '• الملخص — ملخص الصباح بأقسامه الثلاثة\n'
        '• المطابقة — حالات المال الست\n'
        '• مستند T-1 / مستند T-2 — حصة الأستاذ\n'
        '• القمع — أين تسرّب المهتمون\n'
        '• الردود — طابور الرد الأول\n'
        '• ما المعلّق؟ — فقاعات الاقتراحات\n'
        '• موافقة 12 / رفض 12 السبب: …\n'
        '• أوقف المحاسب / أعد المحاسب\n'
        '• السجل — آخر ما سُجّل عني')


def _find_agent(text):
    for ar, aid in ALIAS.items():
        if norm(ar) in text:
            return aid
    for aid in BY_ID:
        if aid in text:
            return aid
    return None


def handle(con, thread, text):
    """
    يفهم رسالة المؤسس ويردّ. يعيد معرفات الرسائل الجديدة.

    الترتيب مهم: الأرقام (موافقة/رفض) قبل المواضيع، والإيقاف قبل «شغّل»
    لأن «أوقف المحاسب» تحتوي فعلًا.
    """
    before = con.execute('SELECT COALESCE(MAX(id),0) m FROM chat_messages').fetchone()['m']
    t = norm(text)

    # ٠) كنا سألنا عن سبب رفض — هذه الرسالة هي السبب
    st = con.execute('SELECT awaiting_reason_for a FROM chat_state WHERE thread=?',
                     (thread,)).fetchone()
    if st and st['a']:
        aid = st['a']
        con.execute('UPDATE chat_state SET awaiting_reason_for=NULL WHERE thread=?',
                    (thread,))
        con.commit()
        r = engine.reject(con, aid, text)
        if r.get('outcome') == 'refused':
            _say(con, thread, r['error'])
        else:
            _say(con, thread, nlg.prose_reject(aid, text))
        return _since(con, before)

    # ١) رفض — بالسبب أو أسأل عنه
    m = re.search(r'(رفض|ارفض|reject)\s*#?\s*(\d+)(.*)$', t)
    if m:
        aid = int(m.group(2))
        # السبب يُؤخذ من نص المؤسس **الأصلي** لا من المطبَّع — التطبيع للمطابقة فقط
        m2 = re.search(r'(?:رفض|ارفض|reject)\s*#?\s*' + str(aid) + r'(.*)$',
                       text, re.I | re.S)
        rest = (m2.group(1) if m2 else '').strip()
        rest = re.sub(r'^(?:بسبب|السبب|لأن|:|\s)+', '', rest).strip()
        if not rest:
            con.execute('INSERT INTO chat_state (thread, awaiting_reason_for)'
                        ' VALUES (?,?) ON CONFLICT(thread) DO UPDATE SET'
                        ' awaiting_reason_for=excluded.awaiting_reason_for',
                        (thread, aid))
            con.commit()
            _say(con, thread, f'ما السبب في رفض #{aid}؟\n'
                              'الرفض بلا سبب لا يُسجَّل عندي — السبب هو درس الشهر القادم.')
            return _since(con, before)
        r = engine.reject(con, aid, rest)
        if r.get('outcome') == 'refused':
            _say(con, thread, r['error'])
        else:
            _say(con, thread, nlg.prose_reject(aid, rest))
        return _since(con, before)

    # ٢) موافقة
    m = re.search(r'(موافق|وافق|اعتمد|approve)\w*\s*#?\s*(\d+)', t)
    if m:
        _approve_msg(con, thread, int(m.group(2)))
        return _since(con, before)

    # ٣) إيقاف / استئناف
    m = re.search(r'(اوقف|وقف|ايقاف|revoke|suspend)', t)
    if m:
        a = _find_agent(t)
        if a:
            _do_revoke(con, thread, a)
        else:
            _say(con, thread, 'أوقف من؟ سمِّ الوكيل: المحاسب، التسويق، المهتمين، الرئيس.')
        return _since(con, before)
    m = re.search(r'(اعد|استئناف|restore|فك)', t)
    if m:
        a = _find_agent(t)
        if a:
            _do_restore(con, thread, a)
        else:
            _say(con, thread, 'أعيد من؟ سمِّ الوكيل.')
        return _since(con, before)

    # ٣.٥) الذاكرة — العقل الثاني
    if re.search(r'(درب الفهم|اعد تدريب الفهم|تدريب الفهم)', t):
        n = sem.build_vectors(REPO_ROOT)
        m = sem.load_synonyms(REPO_ROOT)
        _say(con, thread, f'درّبتُ الفهم على نصوص مستودعك: {n} متجه كلمة، '
                          f'و{m} عنقود مترادفات من memory/synonyms.md.\n'
                          'من الآن «ما يركز» تفهمها «فرط الحركة»، و«خبر التسويق» '
                          'تفهمها «خبير التسويق».')
        return _since(con, before)
    if re.search(r'(صدر الذاكره|تصدير الذاكره)', t):
        _do_export(con, thread)
        return _since(con, before)
    m = re.search(r'(ماذا تذكر|ما الذي تذكره|ذاكرتك عن|ابحث في الذاكره|تذكر ماذا)'
                  r'\s*(.*)$', t)
    if m:
        _do_recall(con, thread, _raw_after(text, m.group(1)))
        return _since(con, before)
    m = re.search(r'(ماذا قررت|ما قرارك عن|قراراتي)\s*(.*)$', t)
    if m:
        _do_recall(con, thread, _raw_after(text, m.group(1)),
                   kinds=('decision',), title='قراراتك المحفوظة')
        return _since(con, before)
    if re.search(r'(لماذا رفضت|دروس الرفض|اسباب الرفض)', t):
        # الدروس تُستعرض الأحدث أولًا — سؤالها لا يحمل رموز بحث
        _do_recall(con, thread, '', kinds=('lesson',),
                   title='دروس محفوظة من رفضك')
        return _since(con, before)
    m = re.search(r'^(?:تذكر|اذكر)\s*(?:ان|:)?\s*(.+)$', t)
    if m:
        _do_remember(con, thread, text[m.end(0) - len(m.group(1)):])
        return _since(con, before)
    m = re.search(r'^(?:قررت|قراري)\s*:?\s*(.+)$', t)
    if m:
        _do_decide(con, thread, m.group(1))
        return _since(con, before)

    # ٤) تشغيل
    if re.search(r'(شغل|تشغيل|run|ابدا العمل|يبدا العمل)', t):
        _do_run(con, thread)
        return _since(con, before)

    # ٥) المواضيع
    if re.search(r'(ملخص|بريف|الصباح|ماذا حدث)', t):
        _do_brief(con, thread)
        return _since(con, before)
    if re.search(r'(مطابق|مال|دفعات|فرق|حساب)', t):
        _do_reconcile(con, thread)
        return _since(con, before)
    m = re.search(r'(مستند|استاذ|حصه)\s*(t-\d+)?', t)
    if m:
        _do_teacher(con, thread, (m.group(2) or '').upper() or None)
        return _since(con, before)
    if re.search(r'(قمع|تسويق|اعلان|funnel)', t):
        _do_funnel(con, thread)
        return _since(con, before)
    if re.search(r'(مهتم|ردود|lead)', t) or re.search(r'(^|\s)رد($|\s)', t):
        _do_leads(con, thread)
        return _since(con, before)
    if re.search(r'(معلق|pending|قرارات|ينتظر)', t):
        _do_pending(con, thread)
        return _since(con, before)
    if re.search(r'(سجل|تدقيق|audit)', t):
        _do_audit(con, thread)
        return _since(con, before)
    if re.search(r'(مساعده|help|اوامر|ماذا تعرف)', t):
        _say(con, thread, HELP)
        return _since(con, before)
    if re.search(r'(سلام|مرحبا|هلا|صباح الخير|هاي)', t):
        _say(con, thread, 'وعليكم السلام. أنا هنا — اكتب «مساعدة» إن شئت، '
                          'أو «شغّل الوكلاء» مباشرة.')
        return _since(con, before)

    # ٦) لا أفهم — القاعدة الرابعة، لا تخمين
    _say(con, thread, f'لا أفهم «{text}».\nلست نموذج لغة — أنا قواعد مطابقة، '
                      'وما لا أطابقه أقوله صريحًا.\n' + HELP)
    return _since(con, before)


def _approve_msg(con, thread, aid):
    row = con.execute('SELECT * FROM pending_actions WHERE id=? AND id>0',
                      (aid,)).fetchone()
    if not row:
        _say(con, thread, f'لا اقتراح بالمعرّف #{aid} — لا أنفّذ ما لا أراه.')
        return
    r = engine.approve(con, aid)
    if r.get('outcome') == 'error':
        _say(con, thread, r['error'])
        return
    if r.get('executed'):
        res = r.get('result', {})
        ref = res.get('inserted') or res.get('updated') or res.get('closed') \
            or res.get('expense_id') or res.get('lead_id') or '—'
        _say(con, thread, nlg.prose_approve_exec(aid, ref))
    elif r.get('manual_instruction'):
        _say(con, thread,
             nlg.prose_approve_manual(aid, row['action_type'])
             + '\n' + r['manual_instruction'], manual=True,
             draft=(json.loads(row['payload']) or {}).get('text'))
    else:
        _say(con, thread, f"سجّلت موافقتك على #{aid}، لكن: {r.get('error')}")


def apply_action(con, thread, op, **kw):
    """أزرار الفقاعات: موافقة/رفض من داخل المحادثة نفسها."""
    before = con.execute('SELECT COALESCE(MAX(id),0) m FROM chat_messages').fetchone()['m']
    if op == 'approve':
        _approve_msg(con, thread, int(kw['id']))
    elif op == 'reject':
        reason = (kw.get('reason') or '').strip()
        if not reason:
            _say(con, thread, 'الرفض بلا سبب لا يُسجَّل — اكتب السبب في الصندوق.')
        else:
            r = engine.reject(con, int(kw['id']), reason)
            if r.get('outcome') == 'refused':
                _say(con, thread, r['error'])
            else:
                _say(con, thread, nlg.prose_reject(int(kw['id']), reason))
    elif op == 'revoke':
        _do_revoke(con, thread, kw['agent'])
    elif op == 'restore':
        _do_restore(con, thread, kw['agent'])
    else:
        _say(con, thread, f'لا أعرف زرًّا اسمه {op}.')
    return _since(con, before)


def _since(con, before):
    """كل الرسائل التي وُلدت أثناء فهم الرسالة — ليرسمها الطرف فورًا."""
    return _collect(con, before)


def _collect(con, before):
    rows = con.execute('SELECT * FROM chat_messages WHERE id>? ORDER BY id',
                       (before,)).fetchall()
    return [dict(r, payload=json.loads(r['payload'])) for r in rows]
