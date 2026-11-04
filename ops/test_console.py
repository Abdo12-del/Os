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
RESULTS = []


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
