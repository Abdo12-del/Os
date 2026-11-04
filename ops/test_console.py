#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اختبار مركز العمليات عبر HTTP — الحلقة الكاملة.

    python3 ops/test_console.py        # يفترض خادمًا يعمل على :8080

12 اختبارًا. **9/12 ليست نجاحًا** — قاعدة الاختبار في README.md.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get('OPS_URL', 'http://127.0.0.1:8080')
DB = os.environ.get('OPS_DB', os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'ops.db'))
RESULTS = []


def reset_db():
    """
    تصفير القاعدة قبل كل تشغيل.

    بدون هذا، المجموعة **لا تُعاد**: التشغيل الأول يوافق على تصحيحات
    correct_payment فتُنفَّذ وتختفي من الطابور، فيرسب التشغيل الثاني.
    الخادم يفتح اتصالًا لكل طلب ولا يحتفظ بشيء، فحذف الملف كافٍ —
    أول طلب بعده يعيد البناء والزرع.
    """
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(DB + suffix)
        except FileNotFoundError:
            pass


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # 404 نتيجة صالحة نريد فحصها، لا استثناءً يكسر الاختبار
        return e.code, json.loads(e.read().decode('utf-8'))


def post(path, body=None):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body or {}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def check(name, ok, detail=''):
    RESULTS.append((name, ok, detail))
    print(f'  {"✅" if ok else "❌"} {name}' + (f' — {detail}' if detail else ''))


def first(pending, action_type):
    return next(x['id'] for x in pending if x['action_type'] == action_type)


def main():
    print('=' * 68)
    print(' اختبار مركز العمليات — 12 اختبارًا')
    print('=' * 68)
    reset_db()
    print('\n  (صُفّرت القاعدة — المجموعة قابلة للإعادة)')

    # ── 1) الواجهة تُقدَّم ──
    print('\n[١] الواجهة')
    for path, ctype in (('/', 'html'), ('/style.css', 'css'), ('/app.js', 'javascript')):
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            body = r.read().decode('utf-8')
            check(f'{path} → 200 وفيه {ctype}',
                  r.status == 200 and ctype in r.headers.get('Content-Type', ''),
                  f'{len(body)} بايت')

    # ── 2) الملخص اليومي: العقد ──
    print('\n[٢] الملخص اليومي — العقد في tech/02-api-contracts.md §3')
    _, b = get('/api/brief')
    s = b.get('sections', {})
    check('missing حاضر دائمًا', 'missing' in b, f'{len(b.get("missing", []))} بند')
    check('broken موجود ولو فارغًا', 'broken' in s)
    check('الأقسام الأربعة', all(k in s for k in
          ('happened', 'needs_decision', 'broken', 'prepared')))
    nd = s.get('needs_decision', [])
    check('days_open إلزامي في كل بند قرار',
          all('days_open' in x for x in nd) if nd else False,
          f'{len(nd)} بند')

    # ── 2.5) الأرقام تطابق fixture — **قبل أي تعديل على البيانات** ──
    # ترتيب هذا الفحص مقصود: الموافقة على تصحيح تُنفَّذ فعلًا فتغيّر الأرقام.
    # فحصها بعد التنفيذ كان يُظهر «فشلًا» بينما النظام كان يعمل صحيحًا.
    print('\n[٢.٥] الأرقام تطابق مفتاح الإجابة في tests/fixtures — على قاعدة بكر')
    print('\n[١١] الأرقام تطابق مفتاح الإجابة في tests/fixtures')
    _, f = get('/api/funnel')
    st = {x['stage']: x['count'] for x in f['stages']}
    check('27 مهتمًا / 12 بلا رد', st.get('تواصلوا') == 27
          and st.get('لم يُرد عليهم إطلاقًا') == 12)
    _, rec = get('/api/reconcile')
    check('الفرق الصافي 500 دج وتحته حالات',
          rec['net_difference'] == 500 and rec['case_count'] >= 4,
          f'{rec["case_count"]} حالة')
    _, t = get('/api/teacher/T-2')
    amts = [c['amount'] for c in t['candidates']
            if c['basis'] in ('collected_net', 'collected_actual', 'due')]
    check('أسس الأستاذ 2700 / 4500 / 5400', amts == [2700.0, 4500.0, 5400.0], str(amts))
    check('basis = null و amount_due = null',
          t['basis'] is None and t['amount_due'] is None)
    _, lq = get('/api/leads')
    check('كل مسوَّدة إرسال محجوبة',
          all(x['send_blocked'] for x in lq['queue']) and lq['never_replied'] == 12)

    # ── 3) تشغيل الوكلاء ──
    print('\n[٣] تشغيل الوكلاء')
    _, r = post('/api/run')
    check('الأربعة عملوا', len(r.get('ran', [])) == 4,
          ', '.join(f'{x["agent"]}={x["proposed"]}' for x in r.get('ran', [])))
    check('لا شيء تعطّل', not r.get('broken'),
          str(r.get('broken')) if r.get('broken') else '')

    _, q = get('/api/pending')
    pend = q['pending']
    check('العداد يطابق الطابور فعلًا',
          r['proposed'] == len(pend),
          f'أُبلغ {r["proposed"]} وفي الطابور {len(pend)}')

    # ── 4) الأهم: النشر والإرسال لا يُنفَّذان ──
    print('\n[٤] القاعدة الأهم — لا نشر ولا إرسال آليًا')
    for at in ('publish_post', 'send_parent_msg'):
        if not any(x['action_type'] == at for x in pend):
            check(f'{at} موجود في الطابور', False)
            continue
        aid = first(pend, at)
        _, res = post('/api/approve', {'id': aid})
        check(f'{at}: وافقتَ ولم يُنفَّذ',
              res.get('status') == 'approved' and res.get('executed') is False
              and res.get('executed_at') is None,
              f'#{aid} executed={res.get("executed")}')
        check(f'{at}: أعاد تعليمة التنفيذ اليدوي',
              bool(res.get('manual_instruction')))

    # ── 5) إجراء قابل للتنفيذ يُنفَّذ فعلًا ──
    print('\n[٥] إجراء مالي — يُنفَّذ فعلًا بعد الموافقة')
    _, q = get('/api/pending')
    pend = q['pending']
    if any(x['action_type'] == 'correct_payment' for x in pend):
        aid = first(pend, 'correct_payment')
        _, before = get('/api/reconcile')
        n_before = before['totals']['accounting']['count']
        _, res = post('/api/approve', {'id': aid})
        _, after = get('/api/reconcile')
        n_after = after['totals']['accounting']['count']
        check('correct_payment نُفّذ في القاعدة',
              res.get('executed') is True and n_after == n_before + 1,
              f'الدفعات {n_before} ← {n_after}')
        # الدليل أنه تنفيذ حقيقي لا عرض: الأرقام تغيّرت بعدها
        _, rec2 = get('/api/reconcile')
        check('التنفيذ غيّر المطابقة فعلًا (ليس عرضًا)',
              rec2['net_difference'] != before['net_difference'],
              f'{before["net_difference"]} ← {rec2["net_difference"]} دج')
        check('وحالة «إيراد غير مسجَّل» اختفت بعد التصحيح',
              sum(1 for c in rec2['cases'] if c['kind'] == 'unrecorded_income')
              < sum(1 for c in before['cases'] if c['kind'] == 'unrecorded_income'))
    else:
        check('correct_payment موجود في الطابور', False)

    # ── 6) الرفض بلا سبب مرفوض ──
    print('\n[٦] الرفض يتطلب سببًا')
    _, q = get('/api/pending')
    pend = q['pending']
    if pend:
        aid = pend[0]['id']
        code, res = post('/api/reject', {'id': aid, 'reason': ''})
        check('رفض بلا سبب → مرفوض', code == 400 and 'إلزامي' in res.get('error', ''),
              res.get('error', '')[:40])
        code, res = post('/api/reject', {'id': aid, 'reason': 'السعر لم يُحسم بعد'})
        check('رفض بسبب → مقبول والسبب مسجَّل',
              code == 200 and res.get('status') == 'rejected'
              and res.get('reason') == 'السعر لم يُحسم بعد')

    # ── 7) idempotency ──
    print('\n[٧] idempotency_key — الضغط مرتين لا ينفّذ مرتين')
    _, before = get('/api/pending')
    post('/api/run')
    _, after = get('/api/pending')
    check('تشغيل ثانٍ لا يكرّر الاقتراحات',
          len(after['pending']) == len(before['pending']),
          f'{len(before["pending"])} ← {len(after["pending"])}')

    # ── 8) /revoke زر الطوارئ ──
    print('\n[٨] زر الطوارئ /revoke')
    post('/api/revoke', {'agent': 'lead_nurturer'})
    _, a = get('/api/agents')
    st = next(x for x in a['agents'] if x['agent'] == 'lead_nurturer')
    check('الوكيل صار موقوفًا', bool(st['revoked_at']), st['revoked_at'])
    _, r2 = post('/api/run')
    check('لم يعمل في التشغيل التالي',
          any(x['agent'] == 'lead_nurturer' for x in r2.get('skipped', [])))
    post('/api/restore', {'agent': 'lead_nurturer'})
    _, a = get('/api/agents')
    st = next(x for x in a['agents'] if x['agent'] == 'lead_nurturer')
    check('أُعيد تشغيله', st['revoked_at'] is None)

    # ── 9) الوكيل لا يكتب ──
    print('\n[٩] الصلاحيات — القراءة عبر اتصال وكيل فقط')
    _, ag = get('/api/agents')
    check('publish_post و send_parent_msg في قائمة «يدوي دائمًا»',
          set(ag['manual_only']) == {'publish_post', 'send_parent_msg'},
          str(ag['manual_only']))
    check('قائمة ما يُنفَّذ لا تتضمنهما',
          not (set(ag['executable']) & {'publish_post', 'send_parent_msg'}),
          str(ag['executable']))

    # ── 10) السجلّ ──
    print('\n[٩+١٠] السجلّ يسجّل كل شيء بما فيه الرفض')
    _, al = get('/api/audit')
    outcomes = {x['outcome'] for x in al['log']}
    actions = {x['action'] for x in al['log']}
    check('الرفض مسجَّل', 'refused' in outcomes, str(sorted(outcomes)))
    check('«بحاجة موافقة» مسجَّل', 'needs_approval' in outcomes)
    check('التنفيذ مسجَّل', any(a.startswith('executed:') for a in actions),
          str(sorted(a for a in actions if a.startswith('executed'))))
    check('امتناع المحاسب عن مستند بلا أساس مسجَّل',
          'refuse_payout' in actions)

    # ── 12) مسار غير معرَّف ──
    print('\n[١٢] لا يُخترع مسار غير معرَّف')
    from urllib.parse import quote
    code, res = get(quote('/api/غير-موجود'))
    check('404 مع «لا أخترع مسارًا»', code == 404 and 'لا نقطة' in res.get('error', ''),
          res.get('error', '')[:40])

    # ── ١٣) الدردشة: الواجهة messenger ──
    print('\n[١٣] الدردشة — وكيل لكل محادثة، والقرار داخل الفقاعة')
    code, res = get('/api/threads')
    th = res.get('threads', [])
    check('أربع جهات اتصال بأسماء الوكلاء', code == 200 and len(th) == 4
          and {t['id'] for t in th} == {'head_of_ops', 'accountant',
                                        'marketing', 'lead_nurturer'},
          ', '.join(t['name'] for t in th))
    check('كل جهة فيها تحية أولى — لا شاشة بيضاء',
          all(t['last_preview'] and 'لا رسائل' not in t['last_preview'] for t in th))

    with urllib.request.urlopen(BASE + '/') as r:
        root = r.read().decode()
    with urllib.request.urlopen(BASE + '/console') as r:
        cons = r.read().decode()
    check('الجذر / هو الدردشة، واللوحات في /console',
          'pane-threads' in root and 'pane-threads' not in cons)

    code, res = post('/api/chat', {'thread': 'head_of_ops', 'text': 'شغّل الوكلاء'})
    txt = ' '.join(m['payload'].get('text', '') for m in res.get('messages', []))
    check('«شغّل الوكلاء» يشغّل ويرسل ملخصًا مركَّبًا لرئيس العمليات',
          code == 200 and 'شغّلتُ' in txt and 'وكلاء' in txt, txt[:50])
    code, res = get('/api/messages?thread=accountant')
    nprop = sum(1 for m in res['messages'] if m['kind'] == 'proposal')
    check('كل اقتراح وصل فقاعة في محادثة وكيله', nprop >= 1, f'{nprop} فقاعة')

    # موافقة من داخل الفقاعة على إجراء له تنفيذ
    code, res = get('/api/messages?thread=accountant')
    ex = next((m['payload'] for m in res['messages']
               if m['kind'] == 'proposal' and m['payload']['status'] == 'pending'
               and m['payload']['action_type'] in
               ('classify_expense', 'close_month', 'correct_payment')), None)
    if ex:
        code, res = post('/api/chat/action',
                         {'thread': 'accountant', 'op': 'approve', 'id': ex['id']})
        last = res['messages'][-1]['payload']['text']
        check('موافقة داخل الفقاعة تُنفَّذ وتقول المرجع',
              code == 200 and 'نُفّذ' in last and 'المرجع' in last, last[:55])
    else:
        check('موافقة داخل الفقاعة تُنفَّذ وتقول المرجع', False, 'لا اقتراح قابلًا')

    # موافقة على إجراء يدوي: تُسجَّل ولا تُنفَّذ
    code, res = get('/api/messages?thread=lead_nurturer')
    man = next((m['payload'] for m in res['messages']
                if m['kind'] == 'proposal' and m['payload']['status'] == 'pending'
                and m['payload']['manual_only']), None)
    if man:
        code, res = post('/api/chat/action',
                         {'thread': 'lead_nurturer', 'op': 'approve', 'id': man['id']})
        last = res['messages'][-1]['payload']
        check('موافقة على إرسال لولي أمر: تُسجَّل ولا تُنفَّذ + مسوّدة تُنسخ',
              'لا يوجد تنفيذ آلي' in last['text'] and bool(last.get('draft')),
              last['text'][:50])
        code, res2 = post('/api/chat/action',
                          {'thread': 'lead_nurturer', 'op': 'reject',
                           'id': man['id'], 'reason': ''})
        check('زر الرفض بلا سبب يُوقف ويُطلب السبب',
              'الرفض بلا سبب' in res2['messages'][-1]['payload']['text'])
        code, res3 = post('/api/chat', {'thread': 'lead_nurturer',
                                        'text': f'رفض {man["id"]} السبب: تجربة'})
        t3 = res3['messages'][-1]['payload']['text']
        check('الرفض بالسبب يُسجَّل نظيفًا بلا نقطتين سابقتين',
              '«تجربة»' in t3, t3[:55])
    else:
        check('موافقة على إرسال لولي أمر: تُسجَّل ولا تُنفَّذ + مسوّدة تُنسخ',
              False, 'لا اقتراح يدويًا')
        check('زر الرفض بلا سبب يُوقف ويُطلب السبب', False, '')
        check('الرفض بالسبب يُسجَّل نظيفًا بلا نقطتين سابقتين', False, '')

    code, res = post('/api/chat', {'thread': 'accountant', 'text': 'المطابقة'})
    check('«المطابقة» ترسل بطاقة الحالات',
          any(m['kind'] == 'cases' for m in res['messages']))
    code, res = post('/api/chat', {'thread': 'accountant', 'text': 'مستند T-1'})
    tm = [m for m in res['messages'] if m['kind'] == 'teacher']
    check('«مستند T-1» بلا أساس محسوم: لا أعرف + الفارق',
          tm and tm[0]['payload']['basis'] is None
          and 'الفارق' in res['messages'][-1]['payload']['text'])
    code, res = post('/api/chat', {'thread': 'head_of_ops', 'text': 'اطلب بيتزا'})
    check('ما لا يفهمه يقول لا أفهم',
          'لا أفهم' in res['messages'][-1]['payload']['text'])
    code, res = post('/api/chat', {'thread': 'accountant', 'text': 'أوقف المحاسب'})
    check('«أوقف المحاسب» من داخل المحادثة',
          'أوقفتُ' in res['messages'][-1]['payload']['text'])
    code, res = post('/api/chat', {'thread': 'accountant', 'text': 'أعد المحاسب'})
    check('«أعد المحاسب» يعيده',
          'أعدتُ' in res['messages'][-1]['payload']['text'])
    code, res = get('/api/messages?thread=head_of_ops&since=1')
    check('since= يعيد الجديد فقط', all(m['id'] > 1 for m in res['messages']))

    # ── ١٤) الذاكرة: العقل الثاني ──
    print('\n[١٤] الذاكرة — تتدرّب من GitHub، تتعلّم من رفضك، ولا تنسى')
    code, res = get('/api/memory?all=1')
    mem = res.get('memories', [])
    nrepo = sum(1 for m in mem if m['source'].startswith('repo:memory/'))
    check('التدريب من memory/*.md أُلتهم عند الإقلاع',
          code == 200 and nrepo >= 30, f'{nrepo} من {len(mem)} ذكرى')
    check('المجموعات السابقة التقطت ذاكرة تلقائيًا (رفض/تنفيذ)',
          any(m['source'].startswith('engine:') for m in mem),
          str(sum(1 for m in mem if m['source'].startswith('engine:'))))
    check('الأنواع الأربعة + درس موجودة',
          {'fact', 'decision', 'lesson'} <= {m['kind'] for m in mem})

    code, res = post('/api/chat', {'thread': 'head_of_ops',
                                   'text': 'تذكّر أني وعدت وليّ بالاتصال قبل الخميس'})
    check('«تذكّر أن …» تحفظ وعدًا لا حقيقة',
          'وعد' in res['messages'][-1]['payload']['text']
          and any(m['kind'] == 'promise'
                  for m in get('/api/memory?all=1')[1]['memories']))

    code, res = post('/api/chat', {'thread': 'marketing',
                                   'text': 'ماذا تذكر عن فرط الحركة؟'})
    card = [m for m in res['messages'] if m['kind'] == 'memory']
    top = card[0]['payload']['items'][0]['subject'] if card else ''
    check('الاسترجاع مرجّح: فرط الحركة تجيب درس «لا وعد بعلاج» أو وجعها',
          bool(card) and top in ('لا وعد بعلاج', 'الوجع الأول', 'الزاوية المعتمدة'),
          top)

    post('/api/chat', {'thread': 'head_of_ops', 'text': 'شغّل الوكلاء'})
    live = {x['id'] for x in get('/api/pending')[1]['pending']}   # الحيّ لا لقطة الفقاعة
    pr, prth = [], None
    for th in ('accountant', 'marketing', 'lead_nurturer'):
        _, rr = get('/api/messages?thread=' + th)
        pr = [m['payload'] for m in rr['messages']
              if m['kind'] == 'proposal' and m['payload']['id'] in live]
        if pr:
            prth = th
            break
    if pr:
        post('/api/chat/action', {'thread': prth, 'op': 'reject',
                                  'id': pr[0]['id'], 'reason': 'يوحي بعلاج فرط الحركة'})
        les = [m for m in get('/api/memory?all=1')[1]['memories']
               if m['kind'] == 'lesson' and m['source'].startswith('engine:reject')]
        check('كل رفض يلتقط درسًا تلقائيًا بمصدره',
              bool(les) and 'يوحي بعلاج' in les[-1]['text'],
              les[-1]['source'] if les else 'لا درس')
        code, res = post('/api/chat', {'thread': prth,
                                       'text': 'لماذا رفضت؟'})
        c2 = [m for m in res['messages'] if m['kind'] == 'memory']
        check('«لماذا رفضت؟» تسترجع الدروس', bool(c2)
              and c2[0]['payload']['items'][0]['kind'] == 'lesson')
    else:
        check('كل رفض يلتقط درسًا تلقائيًا بمصدره', False, 'لا اقتراح')
        check('«لماذا رفضت؟» تسترجع الدروس', False, '')

    code, res = post('/api/chat', {'thread': 'accountant',
                                   'text': 'قررت أساس حصة الأستاذ على المحصل الفعلي الواصل'})
    _, st = get('/api/teacher/T-2')
    cand = next((c for c in st['candidates'] if c['basis'] == 'collected_actual'), {})
    check('القرار المحفوظ يصير رقمًا محسوبًا في المستند',
          st['basis'] == 'collected_actual' and st['amount_due'] == cand.get('amount')
          and st.get('basis_memory'), f"basis={st['basis']} due={st['amount_due']}")
    mem = get('/api/memory?all=1')[1]['memories']
    dead = [m for m in mem if m['kind'] == 'decision' and m['superseded_by']]
    act = [m for m in mem if m['kind'] == 'decision'
           and not m['superseded_by'] and '#share_basis' in m['tags']]
    check('القرار القديم يُبطل ويبقى في التاريخ — لا حذف',
          bool(dead) and len(act) == 1,
          f'مُبطل {len(dead)} / نشط {len(act)}')
    check('الملخص أزاح القرار عن كتفه: 5 مفتوحة من 6',
          len(get('/api/brief')[1]['memory']['open_decisions']) == 5)

    code, res = post('/api/memory/export', {})
    import os as _os
    check('«صدّر الذاكرة» تكتب لقطة في memory/exports بلا أن تصير تدريبًا',
          code == 200 and _os.path.exists(res['path'])
          and not any(m['source'].endswith(_os.path.basename(res['path']))
                      for m in get('/api/memory?all=1')[1]['memories']),
          res.get('path', ''))

    # ── ١٥) اللسان: تركيب الجمل ومطابقة العدد ──
    print('\n[١٥] اللسان — PyArabic مدمج + محرّك مطابقة، لا قوائم مكسورة')
    import nlg as _nlg
    check('PyArabic مدمج ويعمل (linuxscout/pyarabic)', _nlg.HAS_PYARABIC)
    cases = [
        (_nlg.counted(3, 'يوم', 'أيام', 'يومان', 'm'), 'ثلاثة أيام'),
        (_nlg.counted(2, 'يوم', 'أيام', 'يومان', 'm'), 'يومان'),
        (_nlg.counted(11, 'يوم', 'أيام', 'يومان', 'm'), 'أحد عشر يومًا'),
        (_nlg.counted(5, 'دفعة', 'دفعات', 'دفعتان', 'f'), 'خمس دفعات'),
        (_nlg.counted(12, 'دفعة', 'دفعات', 'دفعتان', 'f'), 'اثنتا عشرة دفعةً'),
        (_nlg.money(34500), 'أربعة وثلاثون ألفًا وخمسمئة دينار'),
        (_nlg.money(3000), 'ثلاثة آلاف دينار'),
        (_nlg.counted(1, 'اقتراح', 'اقتراحات', 'اقتراحان', 'm'), 'اقتراحًا واحدًا'),
        (_nlg.counted(16, 'اقتراح', 'اقتراحات', 'اقتراحان', 'm'), 'ستة عشر اقتراحًا'),
    ]
    bad = [f'{g} ≠ {w}' for g, w in cases if g != w]
    check('مطابقة العدد والمعدود والإعراب', not bad, '؛ '.join(bad))
    check('الوصل الخطابي: لكن/لذلك', '، لكن ' in _nlg.CONN.values().__str__()
          and _nlg.compose([('add', 'أ'), ('cause', 'ب')]).endswith('؛ لذلك ب.'))

    code, res = post('/api/chat', {'thread': 'accountant', 'text': 'المطابقة'})
    txt = ' '.join(m['payload'].get('text', '') for m in res['messages']
                   if m['kind'] == 'text')
    check('كلام المحاسب جملة متماسكة بأعداد مكتوبة',
          'طابقتُ المرجعين' in txt and 'حالات' in txt and 'دينار' in txt,
          txt[:70])
    check('لا رقم خامًا حيث يجب الكلام', '34500' not in txt and '500 دج' not in txt)
    code, res = post('/api/chat', {'thread': 'head_of_ops', 'text': 'شغّل الوكلاء'})
    txt = ' '.join(m['payload'].get('text', '') for m in res['messages'])
    check('ملخص التشغيل فقرة لا قائمة', 'شغّلتُ' in txt and 'اقتراحًا' in txt,
          txt[:60])

    # ── ١٦) الفهم الدلالي: تميّز الكلمة مهما اختلفت مفرداتها ──
    print('\n[١٦] الفهم — مورفولوجيا + مترادفات مدرَّبة + متجهات نصوصه + ليفنشتاين')
    import sem as _sem
    _sem.load_synonyms('.')          # نفس الملفات في عملية الاختبار
    check('Tashaphyne مدمج (linuxscout/tashaphyne)', _sem.HAS_TASHAPHYNE)
    check('الجذر يوحّي الأشكال: يتحركون/الحركة',
          bool(_sem.stem_candidates('يتحركون') & _sem.stem_candidates('الحركة')))
    check('عنقود المترادفات محمّل من memory/synonyms.md',
          len(_sem._CLUSTERS) >= 8, f'{len(_sem._CLUSTERS)} عنقودًا')
    ex = _sem.expand(['يركز'], use_vectors=False)
    check('«يركز» تفهمها «فرط الحركة» بلا نموذج عصبي',
          {'فرط', 'الحركه'} <= ex, sorted(ex)[:6])

    code, res = post('/api/chat', {'thread': 'head_of_ops', 'text': 'درّب الفهم'})
    check('«درّب الفهم» تبني متجهات من نصوصه',
          'متجه' in res['messages'][-1]['payload']['text'],
          res['messages'][-1]['payload']['text'][:50])

    code, res = post('/api/chat', {'thread': 'marketing',
                                   'text': 'ماذا تذكر عن ابن ما يركز؟'})
    card = [m for m in res['messages'] if m['kind'] == 'memory']
    top = card[0]['payload']['items'][0]['subject'] if card else ''
    check('«ابن ما يركّز» تسترجع درس فرط الحركة',
          bool(card) and top in ('لا وعد بعلاج', 'الوجع الأول', 'الزاوية المعتمدة'),
          top)
    code, res = post('/api/chat', {'thread': 'marketing',
                                   'text': 'ماذا تذكر عن المحضورات؟'})
    card = [m for m in res['messages'] if m['kind'] == 'memory']
    subs = [it['subject'] for m in card for it in m['payload']['items']]
    check('«المحضورات» (خطأ إملائي) تفهمها «محظورات» بليفنشتاين ١',
          any('محظورات' in x for x in subs), str(subs)[:40])
    code, res = post('/api/chat', {'thread': 'marketing',
                                   'text': 'ماذا تذكر عن الحصة التجريبية؟'})
    card = [m for m in res['messages'] if m['kind'] == 'memory']
    subs = [it['subject'] for m in card for it in m['payload']['items']]
    check('«التجريبية» تسترجع حقيقة «الحصة التعريفية»',
          any('التعريفية' in x for x in subs), str(subs)[:40])
    code, res = post('/api/chat', {'thread': 'marketing',
                                   'text': 'ماذا تذكر عن فرط الحركة؟'})
    card = [m for m in res['messages'] if m['kind'] == 'memory']
    items = card[0]['payload']['items'] if card else []
    check('التوسيع يعيد الترتيب لكن أول نتيجة تحوي لفظك حرفيًا',
          bool(items) and 'فرط' in (items[0].get('matched') or []),
          str(items[0].get('matched') if items else None)[:40])

    # ── ١٧) الإنترنت — بحث مجاني بالكامل: ddgs بلا مفتاح، ويكيبيديا، كاش، صدق ──
    print('\n[١٧] الإنترنت — بحث مجاني بالكامل، قراءة فقط، وصدق عند الانقطاع')
    import os as _os
    import db as _db
    import web as _web
    check('ddgs مثبّت — مجاني بالكامل بلا مفتاح ولا تسجيل', _web.HAS_DDGS)
    _fc = _db.connect('founder')
    _web.ensure(_fc)
    _fake = lambda q, n: [{'title': f'نتيجة {i} عن {q}',
                           'url': f'https://example.test/{i}',
                           'snippet': 'مقتطف للاختبار'} for i in range(1, 4)]
    _orig = (_web._ddg, _web._wiki, _web._tavily)
    try:
        _web._ddg, _web._wiki = _fake, _fake
        r = _web.search(_fc, 'اختبار الكاش عبر HTTP ٧٧٧')
        check('سلسلة المزوّدين تعيد نتائج مهيكلة', r['provider'] == 'ddgs'
              and len(r['results']) == 3, r['provider'])
        r2 = _web.search(_fc, 'اختبار الكاش عبر HTTP ٧٧٧')
        check('الكاش يرد بلا إعادة طلب — توفيرًا للمعدل', r2.get('cached')
              and 'كاش' in r2['provider'], r2['provider'])
        _os.environ['TAVILY_API_KEY'] = 'fake-key-for-test'
        _web._tavily = _fake
        r3 = _web.search(_fc, 'اختبار تافيلي الاختياري')
        check('مفتاح Tavily المجاني يتقدم السلسلة إن وُجد',
              r3['provider'] == 'tavily', r3['provider'])
        del _os.environ['TAVILY_API_KEY']

        def _boom(q, n):
            raise OSError('no network')
        _web._ddg, _web._wiki = _boom, _boom
        r4 = _web.search(_fc, 'استعلام مقطوع تماما')
        check('بلا إنترنت: خطأ صادق ولا نتائج مختلَقة',
              not r4['results'] and 'ما وصلت للإنترنت' in r4['error'],
              r4.get('error', '')[:50])
    finally:
        _web._ddg, _web._wiki, _web._tavily = _orig
        _fc.close()

    # الكاش المبذور أعلاه يردّ عبر HTTP الحقيقي — بلا شبكة في الاختبار
    code, res = post('/api/chat', {'thread': 'marketing',
                                   'text': 'ابحث عن اختبار الكاش عبر HTTP ٧٧٧'})
    ws = [m for m in res['messages'] if m['kind'] == 'websearch']
    ok_card = bool(ws) and len(ws[0]['payload']['items']) == 3
    check('«ابحث عن …» تعيد بطاقة بحث من الكاش عبر HTTP', ok_card,
          str([m['kind'] for m in res['messages']])[:50])
    check('البطاقة تذكر القاعدة: قراءة فقط ولا قرار بدونك',
          ok_card and 'بدونك' in ws[0]['payload'].get('note', ''))

    code, res = post('/api/chat', {'thread': 'head_of_ops',
                                   'text': 'ابحث عن استعلام حي لم يخزن من قبل ٩٩٩'})
    ws = [m for m in res['messages'] if m['kind'] == 'websearch']
    txt = res['messages'][-1]['payload'].get('text', '') if res['messages'] else ''
    check('الاستعلام الحي: نتائج حقيقية أو اعتراف صادق بالانقطاع',
          bool(ws) or 'ما وصلت للإنترنت' in txt,
          (ws[0]['payload']['title'][:40] if ws else txt[:40]))

    code, res = post('/api/chat', {'thread': 'marketing',
                                   'text': 'ماذا تذكر عن اختبار الكاش؟'})
    card = [m for m in res['messages'] if m['kind'] == 'memory']
    subs = [it['subject'] for m in card for it in m['payload']['items']]
    check('كل بحث يُحفظ حلقةً في الذاكرة — يُسترجع لاحقًا',
          any(x.startswith('بحث:') for x in subs), str(subs)[:50])

    # ── الحصيلة ──
    ok = sum(1 for _, o, _ in RESULTS if o)
    print('\n' + '=' * 68)
    print(f' {ok}/{len(RESULTS)} — {"✅ ناجح" if ok == len(RESULTS) else "❌ غير ناجح"}')
    print('=' * 68)
    if ok != len(RESULTS):
        print('\nالراسب:')
        for name, o, d in RESULTS:
            if not o:
                print(f'  ❌ {name}' + (f' — {d}' if d else ''))
        print('\nقاعدة الاختبار في README.md: 10/10 و11/11 — **9/10 ليست نجاحًا**.')
    return 0 if ok == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
