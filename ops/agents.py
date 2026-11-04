#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الوكلاء الأربعة — منطق حقيقي، لا نص يُطلب من نموذج.

لماذا لا يحتاج هؤلاء نموذج لغة:
  المطابقة عدّ وحساب. التشخيص ترتيب ومقارنة. والملخص تجميع.
  ما يحتاج لغةً هو صياغة ردّ لولي أمر — ودليل الرد الأول فيه 8 ردود جاهزة،
  فمطابقة قاعدة أولى **أأمن** من التوليد لأنها لا تستطيع الاختراع.

كل دالة تُعيد قاموسًا فيه `source` و`missing` — العقد في tech/02-api-contracts.md.
`missing` حاضر دائمًا. غيابه هو ما يُغري بالاختراع.

قاعدة واحدة تسري على الجميع: **لا رقم غير محسوب من البيانات.**
"""
import json
from datetime import date, datetime

TODAY = date(2026, 11, 4)          # يُمرَّر من server.py في التشغيل الحقيقي
MONTH = '2026-10'
MONTH_START, MONTH_END = '2026-10-01', '2026-10-31'
TIMING_GRACE_DAYS = 3              # آخر 3 أيام = فرق توقيت طبيعي، لا يُنبَّه عليه
GRACE_FROM = '2026-10-29'


def _d(s):
    return datetime.strptime(s[:10], '%Y-%m-%d').date()


def _days_open(iso_ts, now=None):
    """كم يومًا بقي هذا البند مفتوحًا — يقود علامة `⚠ متأخر` عند ≥ 3 أيام."""
    now = now or TODAY
    try:
        return (now - _d(iso_ts)).days
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════
#  المحاسب
# ═══════════════════════════════════════════════════════════════
def reconcile(con, month=MONTH):
    """
    المطابقة. **تعدّ الحالات، لا تطرح المجاميع.**

    الفرق الصافي بين النظامين 500 دج فقط — وتحته أربع حالات حقيقية في اتجاهين
    متعاكسين. الوكيل الذي يقول «الفرق 500، لا مشكلة» رسب في الاختبار ح1.
    """
    cases = []
    missing = []

    # (أ) في الأولياء وليس في المحاسبة
    rows = con.execute("""
        SELECT p.student_id, p.amount, p.paid_at, p.operation_no,
               s.alias_name
          FROM payments_parents p
          LEFT JOIN payments_accounting a ON a.operation_no = p.operation_no
          LEFT JOIN students s ON s.student_id = p.student_id
         WHERE a.ref IS NULL
         ORDER BY p.paid_at
    """).fetchall()
    for r in rows:
        if r['paid_at'] >= GRACE_FROM:
            kind, risk = 'timing', 'green'
            note = 'فرق توقيت طبيعي (آخر 3 أيام) — لا يُنبَّه عليه'
        else:
            kind, risk = 'unrecorded_income', 'red'
            note = ('مال وصل في نظام الأولياء ولم يُسجَّل في مرجع المال. '
                    'التاريخ ليس ضمن آخر 3 أيام، فعذر التوقيت لا ينطبق.')
        cases.append({
            'kind': kind, 'risk': risk,
            'student_id': r['student_id'], 'alias': r['alias_name'],
            'amount': r['amount'], 'paid_at': r['paid_at'],
            'operation_no': r['operation_no'], 'note': note,
        })

    # (ب) فرق مبلغ على نفس رقم العملية
    rows = con.execute("""
        SELECT a.operation_no, a.student_id, a.ref,
               a.amount AS acc_amount, p.amount AS par_amount,
               a.amount - p.amount AS delta, s.note AS documented, s.alias_name
          FROM payments_accounting a
          JOIN payments_parents p ON p.operation_no = a.operation_no
          JOIN students s ON s.student_id = a.student_id
         WHERE a.amount <> p.amount
    """).fetchall()
    for r in rows:
        documented = bool(r['documented'])
        cases.append({
            'kind': 'amount_mismatch',
            'risk': 'yellow' if documented else 'red',
            'student_id': r['student_id'], 'alias': r['alias_name'],
            'ref': r['ref'], 'operation_no': r['operation_no'],
            'accounting_amount': r['acc_amount'],
            'parents_amount': r['par_amount'], 'delta': r['delta'],
            'documented_reason': r['documented'],
            'note': ('فرق موثَّق في ملاحظات الطالب — يحتاج تعديلًا عند الإغلاق، '
                     'لا تنبيهًا' if documented else
                     'فرق غير موثَّق — مرجع المال هو نظام المحاسبة، '
                     'والفرق يُبلَّغ كـ«نظام الأولياء غير محدَّث»'),
        })

    # (ج) تكرار محتمل
    rows = con.execute("""
        SELECT student_id, COUNT(*) n, SUM(amount) total,
               GROUP_CONCAT(ref || ' / ' || COALESCE(operation_no,'بلا مرجع'), ' — ') refs
          FROM payments_accounting
         WHERE paid_at BETWEEN ? AND ?
         GROUP BY student_id HAVING COUNT(*) > 1
    """, (MONTH_START, MONTH_END)).fetchall()
    for r in rows:
        cases.append({
            'kind': 'suspected_duplicate', 'risk': 'red',
            'student_id': r['student_id'], 'payments': r['n'],
            'total': r['total'], 'refs': r['refs'],
            'note': 'دفعتان لنفس الطالب في نفس الشهر — لا تُصحَّح قبل التحقق',
        })

    # (د) دفعة بلا رقم عملية
    rows = con.execute("""
        SELECT ref, student_id, amount, paid_at FROM payments_accounting
         WHERE operation_no IS NULL AND paid_at BETWEEN ? AND ?
    """, (MONTH_START, MONTH_END)).fetchall()
    for r in rows:
        cases.append({
            'kind': 'no_operation_no', 'risk': 'yellow',
            'ref': r['ref'], 'student_id': r['student_id'],
            'amount': r['amount'], 'paid_at': r['paid_at'],
            'note': 'دفعة بلا رقم عملية — لا يمكن تتبعها ولا التأكد أنها ليست تكرارًا',
        })

    # (هـ) متأخرات
    # ⚠️ يُستثنى من دفع في نظام الأولياء ولم يُسجَّل في المحاسبة:
    #    ذلك الطالب حالته «إيراد غير مسجَّل» (أعلاه)، لا «متأخر».
    #    عَدّه في الاثنين يحسب نفس المبلغ مرتين ويضخّم المتأخرات.
    rows = con.execute("""
        SELECT s.student_id, s.alias_name, s.group_name, s.teacher_id, s.monthly_due
          FROM students s
          LEFT JOIN payments_accounting a
                 ON a.student_id = s.student_id
                AND a.paid_at BETWEEN ? AND ?
          LEFT JOIN payments_parents p
                 ON p.student_id = s.student_id
                AND p.paid_at BETWEEN ? AND ?
         WHERE a.ref IS NULL AND p.id IS NULL AND s.deleted_at IS NULL
         ORDER BY s.monthly_due DESC
    """, (MONTH_START, MONTH_END, MONTH_START, MONTH_END)).fetchall()
    arrears = [dict(r) for r in rows]

    # المجاميع — تُعرض مع الحالات، لا بدلها
    acc = con.execute('SELECT COUNT(*) n, SUM(amount) s FROM payments_accounting').fetchone()
    par = con.execute('SELECT COUNT(*) n, SUM(amount) s FROM payments_parents').fetchone()
    due = con.execute('SELECT SUM(monthly_due) s FROM students WHERE deleted_at IS NULL').fetchone()

    return {
        'month': month,
        'net_difference': (acc['s'] or 0) - (par['s'] or 0),
        'warning': ('الفرق الصافي لا يعني شيئًا — الأخطاء في اتجاهين متعاكسين '
                    'فتلغي بعضها. انظر إلى `cases`، لا إلى هذا الرقم.'),
        'totals': {
            'accounting': {'count': acc['n'], 'sum': acc['s']},
            'parents': {'count': par['n'], 'sum': par['s']},
            'due': due['s'],
            'arrears': sum(a['monthly_due'] for a in arrears),
        },
        'cases': cases,
        'case_count': len(cases),
        'arrears': arrears,
        'source': ['payments_accounting', 'payments_parents', 'students'],
        'missing': missing,
    }


def teacher_statement(con, teacher_id, month=MONTH):
    """
    مستند الأستاذ. **يُعيد `basis: null` ما لم يُحسم القرار 1** — وهذا مقصود.

    لا يحسب مبلغًا على أساس غير مكتوب (القاعدة 10 للمحاسب). بدل ذلك
    **يقيس الفارق بين الأسس المحتملة** ليرى المؤسس كلفة عدم القرار.
    """
    t = con.execute('SELECT * FROM teachers WHERE teacher_id=?', (teacher_id,)).fetchone()
    if not t:
        return {'error': f'لا أستاذ بالمعرّف {teacher_id}', 'missing': ['teacher_id']}

    students = con.execute(
        'SELECT student_id, alias_name, monthly_due FROM students '
        'WHERE teacher_id=? AND deleted_at IS NULL', (teacher_id,)).fetchall()
    ids = [s['student_id'] for s in students]
    if not ids:
        return {'teacher_id': teacher_id, 'basis': t['share_basis'],
                'amount_due': None, 'missing': ['students'],
                'note': 'لا طلبة مرتبطين بهذا الأستاذ'}
    ph = ','.join('?' * len(ids))

    net = con.execute(f"""SELECT COALESCE(SUM(amount),0) FROM payments_accounting
        WHERE student_id IN ({ph}) AND suspected_dup=0
          AND paid_at BETWEEN ? AND ?""", (*ids, MONTH_START, MONTH_END)).fetchone()[0]
    gross = con.execute(f"""SELECT COALESCE(SUM(amount),0) FROM payments_accounting
        WHERE student_id IN ({ph}) AND paid_at BETWEEN ? AND ?""",
                        (*ids, MONTH_START, MONTH_END)).fetchone()[0]
    # المال الذي وصل فعلًا: المسجَّل في مرجع المال + ما وصل ولم يُسجَّل فيه
    unrecorded = con.execute(f"""SELECT COALESCE(SUM(p.amount),0)
          FROM payments_parents p
          LEFT JOIN payments_accounting a ON a.operation_no = p.operation_no
         WHERE a.ref IS NULL AND p.student_id IN ({ph})
           AND p.paid_at BETWEEN ? AND ?""",
                             (*ids, MONTH_START, MONTH_END)).fetchone()[0]
    # ⚠️ net لا gross: gross يشمل الدفعة المشتبه بتكرارها فيعدّ نفس الطفل مرتين.
    actual = net + unrecorded
    due = sum(s['monthly_due'] for s in students)
    pct = t['share_pct'] or 0

    # كل أساس محتمل ومبلغه — الفارق هو كلفة عدم القرار
    candidates = [
        {'basis': 'collected_net',
         'label': 'المحصَّل المسجَّل في مرجع المال (بلا المشتبه بتكراره)',
         'base': net, 'amount': round(net * pct / 100, 2)},
        {'basis': 'collected_actual',
         'label': 'المحصَّل فعلًا (المسجَّل + ما وصل ولم يُسجَّل)',
         'base': actual, 'amount': round(actual * pct / 100, 2),
         'note': (f'= المسجَّل في مرجع المال ({net:,.0f}) + {unrecorded:,.0f} دج وصلت '
                  'في نظام الأولياء ولم تُسجَّل فيه' if unrecorded else
                 'مطابق للمسجَّل — لا مال وصل خارج مرجع المال')},
        {'basis': 'collected_gross',
         'label': 'كل ما في مرجع المال (بما فيه المشتبه بتكراره)',
         'base': gross, 'amount': round(gross * pct / 100, 2),
         'note': '⚠️ مرجعي فقط — يعدّ الطفل مرتين إن كانت هناك دفعة مكرّرة'},
        {'basis': 'due', 'label': 'المستحق (سواء دُفع أم لا)',
         'base': due, 'amount': round(due * pct / 100, 2),
         'note': 'على هذا الأساس أنت تمتصّ المتأخرات مرتين'},
    ]
    amounts = [c['amount'] for c in candidates]
    spread = round(max(amounts) - min(amounts), 2)

    missing = []
    if t['share_basis'] is None:
        missing.append({
            'field': 'share_basis',
            'question': 'نسبة الأستاذ على المحصَّل أم المستحق؟',
            'decision_ref': 'OPEN-QUESTIONS.md — الطبقة 1، القرار 1',
            'spread_dzd': spread,
            'impact': (f'عدم الحسم يكلّف {spread:,.0f} دج فرقًا لأستاذ واحد في شهر واحد. '
                       'إن كان الأساس «المستحق» فأنت تمتصّ المتأخرات مرتين: '
                       'مرة حين لا تصل، ومرة في نسبة الأستاذ.'),
        })
    if t['sessions_cancelled'] and not t['cancelled_reason']:
        missing.append({'field': 'cancelled_reason',
                        'question': f'{t["sessions_cancelled"]} حصة ملغاة بلا سبب مسجّل',
                        'impact': 'الحصة الملغاة بسبب الأستاذ تُخصم، وبسبب المجموعة لا تُخصم.'})

    return {
        'teacher_id': teacher_id, 'alias': t['alias_name'],
        'group': t['group_name'], 'month': month,
        'sessions_delivered': t['sessions_delivered'],
        'free_trials': t['free_trials'],
        'sessions_cancelled': t['sessions_cancelled'],
        'share_pct': pct,
        'basis': t['share_basis'],           # ← None عن قصد
        'amount_due': None,                  # ← لا مبلغ على أساس غير محسوم
        'candidates': candidates,
        'spread_dzd': spread,
        'students': [{'student_id': s['student_id'], 'alias': s['alias_name']}
                     for s in students],
        'free_trial_cost_note': (
            f'{t["free_trials"]} حصة تعريفية مجانية = جهد أستاذ بلا إيراد. '
            'كلفتها على المؤسس 100%، والتسويق يدفع المزيد إليها. '
            'هذا تعارض مسجَّل في 09-operating-rhythm.md، لا رقم يُحسب هنا.'
            if t['free_trials'] else None),
        'source': ['teachers', 'students', 'payments_accounting'],
        'missing': missing,
    }


def finance_summary(con, month=MONTH):
    """التدفقات الثلاثة. لا دفتر أستاذ مزدوج — ليس عندك."""
    income = con.execute(
        'SELECT COUNT(*) n, SUM(amount) s FROM payments_accounting '
        'WHERE paid_at BETWEEN ? AND ?', (MONTH_START, MONTH_END)).fetchone()
    exp_rows = con.execute('SELECT * FROM expenses ORDER BY spent_at').fetchall()
    expenses = sum(r['amount'] for r in exp_rows)
    uncat = [dict(r) for r in exp_rows if not r['account_code']]

    alerts = []
    for r in uncat:
        alerts.append({'kind': 'uncategorized_expense', 'risk': 'yellow',
                       'label': r['label'], 'amount': r['amount'],
                       'note': 'مصروف بلا تصنيف — لا يُغلق الشهر قبل تصنيفه'})
    for r in con.execute('SELECT * FROM period_status WHERE closed_at IS NULL'):
        alerts.append({'kind': 'period_not_closed', 'risk': 'yellow',
                       'month': r['month'],
                       'note': 'شهر غير مغلق. لا يُغلق إلا بموافقتك (اختبار ح11).'})
    for r in con.execute('SELECT * FROM teachers WHERE share_basis IS NULL'):
        alerts.append({'kind': 'share_basis_unresolved', 'risk': 'red',
                       'teacher_id': r['teacher_id'],
                       'note': 'أساس نسبة الأستاذ غير محسوم — القرار 1'})

    missing = [{'field': 'teacher_payouts',
                'question': 'لا جدول لصرف الأساتذة — لم يُنفَّذ صرف بعد',
                'impact': 'صافي الشهر غير مكتمل: الإيراد والمصاريف حاضران، وأجور الأساتذة لا'}]

    return {
        'month': month,
        'flows': {
            'income_from_parents': {'count': income['n'], 'sum': income['s']},
            'expenses': {'count': len(exp_rows), 'sum': expenses},
            'teacher_payouts': None,      # ← لا يُخترع
        },
        'alerts': alerts,
        'source': ['payments_accounting', 'expenses', 'period_status', 'teachers'],
        'missing': missing,
    }


# ═══════════════════════════════════════════════════════════════
#  خبير التسويق
# ═══════════════════════════════════════════════════════════════
def funnel(con, frm=None, to=None):
    """
    تشخيص القمع. **العنق الزجاجة هو الوصول لا الإقناع** — والأكبر هو
    المهتمون الذين لم يُرد عليهم إطلاقًا.
    """
    where, args = '', []
    if frm:
        where += ' AND first_msg_at >= ?'; args.append(frm)
    if to:
        where += ' AND first_msg_at <= ?'; args.append(to)
    where = where.replace(' AND', ' WHERE', 1) if where else ''

    def q(sql, *a):
        return con.execute(sql + where, (*a, *args)).fetchone()[0] or 0

    total = con.execute(f'SELECT COUNT(*) FROM leads{where}', args).fetchone()[0]
    never = con.execute(
        f'SELECT COUNT(*) FROM leads{where}{" AND" if where else " WHERE"}'
        ' first_reply_at IS NULL', args).fetchone()[0]
    booked = q('SELECT SUM(booked_trial) FROM leads')
    attended = q('SELECT SUM(attended_trial) FROM leads')
    enrolled = q('SELECT SUM(enrolled) FROM leads')
    paid = q('SELECT SUM(paid) FROM leads')

    by_source = [dict(r) for r in con.execute(f"""
        SELECT source, COUNT(*) leads,
               SUM(CASE WHEN first_reply_at IS NULL THEN 1 ELSE 0 END) never_replied,
               SUM(enrolled) enrolled
          FROM leads{where} GROUP BY source ORDER BY leads DESC""", args)]

    pct = lambda a, b: round(a * 100 / b, 1) if b else None

    stages = [
        ('تواصلوا', total, None),
        ('لم يُرد عليهم إطلاقًا', never, pct(never, total)),
        ('حجزوا حصة تعريفية', booked, pct(booked, total)),
        ('حضروا', attended, pct(attended, booked)),
        ('سجّلوا', enrolled, pct(enrolled, attended)),
        ('دفعوا', paid, pct(paid, enrolled)),
    ]

    # الأولويات — مرتّبة، والسبب محسوب لا مؤلَّف
    priorities = []
    if never:
        priorities.append({
            'rank': 1, 'issue': f'{pct(never,total)}% من المهتمين لم يُرد عليهم إطلاقًا ({never} من {total})',
            'why': 'أكبر تسرّب في القمع كله، وأكبر من أي مشكلة محتوى.',
            'action': 'العلاج ليس منشورات أكثر، بل سرعة الرد الأول.',
            'ref': 'marketing/first-reply-playbook.md — قاعدة الـ60 ثانية',
        })
    if attended and enrolled:
        r = pct(enrolled, attended)
        if r >= 60:
            priorities.append({
                'rank': len(priorities) + 1,
                'issue': f'التحويل من الحضور إلى تسجيل = {r}% ({enrolled} من {attended})',
                'why': 'من يحضر الحصة التعريفية يسجّل. إذًا الحصة التعريفية تعمل.',
                'action': 'الرافعة هي زيادة عدد الحاضرين، لا تحسين الإقناع.',
            })
    noshow = booked - attended
    if noshow:
        priorities.append({
            'rank': len(priorities) + 1,
            'issue': f'{noshow} حجزوا ولم يحضروا ({pct(noshow,booked)}%)',
            'why': 'تسرّب ثانٍ بعد الرد الأول.',
            'action': 'تذكير قبل الحصة — لا حملة جديدة.',
        })
    # التسليم ليس أولوية تسويقية — إنه تحويل اختصاص.
    # خلطهما كان يُسقط هذا البند حين تُحدّ الأولويات بثلاث.
    routed = []
    if enrolled > paid:
        routed.append({
            'issue': f'{enrolled - paid} سجّل ولم يدفع',
            'why': 'ليس قرار تسويق، ولا يتصرّف فيه خبير التسويق.',
            'route_to': 'accountant',
            'ref': '05-rules.md — لا يتجاوز وكيل اختصاص غيره',
        })

    return {
        'period': {'from': frm, 'to': to},
        'stages': [{'stage': s, 'count': c, 'rate_pct': r} for s, c, r in stages],
        'by_source': by_source,
        'priorities': priorities[:3],     # ثلاث أولويات، لا عشر
        'routed': routed,                 # ما يُسلَّم لوكيل آخر
        'source': ['leads'],
        'missing': [{
            'field': 'enrollments_by_source',
            'question': 'كم تسجيلًا جاء من كل منصة؟',
            'impact': ('الأرقام المعروفة للمهتمين لا للتسجيلات. '
                       'لا أستنتج توزيعًا — سيُذكر كـ missing لا كرقم.')
            if any(b['enrolled'] for b in by_source) else 'لا تسجيلات بعد',
        }],
    }


# ═══════════════════════════════════════════════════════════════
#  دليل الرد الأول — 8 ردود جاهزة (marketing/first-reply-playbook.md)
# ═══════════════════════════════════════════════════════════════
#  الرد الثالث (فرط الحركة) هو الذي يقتبسه بقية الوكلاء حرفيًا.
REPLIES = {
    'price': {
        'title': 'السعر',
        'text': 'أهلًا بك، وشكرًا على سؤالك.\n'
                'الاشتراك الشهري 【تحقّق: السعر】.\n'
                'قبل أن تقرّر: عندنا حصة تعريفية مجانية، تشاهد بعينك ما الذي يحدث، '
                'ثم تقرّر. أتفضّل أن أحجز لك مكانًا؟',
        'placeholder': True,
    },
    'what_do_you_teach': {
        'title': '«شنو تدرسو؟»',
        'text': 'سؤال مهم، وأجيبك بصراحة: نحن لسنا دعمًا مدرسيًا. '
                'لا مادة ولا علامة ولا شهادة.\n'
                'الحصة حوار ونقاش ثم نشاط تطبيقي — يخرج منها الطفل بشيء صنعه، '
                'وقد تعلّم أن رأيه يُطلب ويُؤخذ على محمل الجد.\n'
                'أتفضّل حصة تعريفية مجانية لترى بنفسك؟',
        'placeholder': False,
    },
    'adhd': {
        'title': 'فرط الحركة — الرد المعتمد حرفيًا',
        'text': 'شكرًا على ثقتك، وأجيبك بوضوح في نقطتين:\n'
                'أولًا: لسنا مختصّين ولا نقدّم علاجًا. إن كان ابنك يتابع مع مختص، '
                'فذاك مسار يبقى معه ولا نستبدله.\n'
                'ثانيًا: ما نقدّمه هو بيئة — مجموعة صغيرة، مهام قصيرة، الحركة فيها '
                'مسموحة لا معاقَبة، والطفل يُسأل ويُنتظر جوابه، ولا يُصحَّح أمام الآخرين.\n'
                'عندنا حصة تعريفية مجانية. وإن أحببت نتكلّم بالصوت وأشرح لك أكثر.',
        'placeholder': False,
        'note': ('هذا هو الرد الذي يقتبسه سكرتير الأولياء ومتابع المهتمين حرفيًا. '
                 'لا يُعدَّل. لا يُقال «نعالج» ولا «ADHD» ولا «اضطراب» ولا «تشخيص».'),
    },
    'shy': {
        'title': 'الخجل',
        'text': 'كثير من الأطفال يبدؤون هكذا.\n'
                'في الحصة لا يُطلب من أحد أن يتكلّم قبل أن يريد. '
                'يبدأ بالمشاهدة، ثم يشارك في نشاط، وحين يتكلّم يُنتظر ولا يُقاطع.\n'
                'حصة تعريفية مجانية تريك كيف يبدأ — أتفضّل؟',
        'placeholder': False,
    },
    'is_this_tutoring': {
        'title': '«هل هذا دعم مدرسي؟»',
        'text': 'لا، وأقولها بصراحة: إن كان هدفك رفع العلامة في مادة، '
                'فنحن لسنا المكان المناسب.\n'
                'نحن نعمل على ثقة الطفل وقدرته على التعبير والعمل مع آخرين. '
                'حصة تعريفية مجانية إن أردت أن ترى الفرق.',
        'placeholder': False,
        'note': 'أقوى سطر في الدليل: رفض المهتم غير المناسب يرفع الثقة عند المناسب.',
    },
    'trial': {
        'title': 'حجز حصة تعريفية',
        'text': 'بالتأكيد. الحصة التعريفية مجانية وفيها حوار ونشاط تطبيقي.\n'
                '【تحقّق: المواعيد المتاحة】 — أيّها يناسبك؟\n'
                'أحتاج فقط اسم الطفل وعمره لأختار المجموعة المناسبة.',
        'placeholder': True,
    },
    'vague': {
        'title': 'رسالة غير واضحة',
        'text': 'أهلًا بك، وشكرًا لتواصلك.\n'
                'كي أجيبك إجابة تفيدك فعلًا: كم عمر الطفل؟ '
                'وما الذي تتمنى أن يتغيّر عنده؟',
        'placeholder': False,
    },
}

# ست حالات لا يُكتب فيها رد إطلاقًا — يُتّصل (first-reply-playbook.md)
NEVER_WRITE_REPLY = [
    'غضب أو تهديد بسحب الطفل',
    'شكوى من أستاذ',
    'مبلغ مختلف عن المسجَّل',
    '«ابني لم يتقدّم»',
    'طلب استرداد مبلغ',
    'حالة تحتاج مختصًا',
]


def lead_nurturer_queue(con, now=None):
    """
    طابور من لم يُرد عليهم، مرتّبًا بالأقدم.

    أهم مخرج لهذا الوكيل هو **«لم يُرد عليه إطلاقًا»** قبل «لم يسجّل».
    """
    now = now or TODAY
    rows = con.execute("""
        SELECT lead_id, source, first_msg_at, first_reply_at, topic, asked_price
          FROM leads WHERE first_reply_at IS NULL
         ORDER BY first_msg_at
    """).fetchall()

    queue = []
    end_of_today = datetime(now.year, now.month, now.day, 23, 59, 59)
    for r in rows:
        reply = REPLIES.get(r['topic'])
        first = datetime.strptime(r['first_msg_at'], '%Y-%m-%dT%H:%M:%S')
        waited = end_of_today - first
        queue.append({
            'lead_id': r['lead_id'], 'source': r['source'],
            'first_msg_at': r['first_msg_at'],
            'hours_waiting': round(waited.total_seconds() / 3600, 1),
            'days_waiting': waited.days,
            # قاعدة الـ60 ثانية: أي انتظار فوق ساعة = متأخر
            'overdue': waited.total_seconds() > 3600,
            'topic': r['topic'],
            'suggested_reply': reply['text'] if reply else None,
            'reply_title': reply['title'] if reply else None,
            'has_placeholder': bool(reply and reply.get('placeholder')),
            'send_blocked': True,   # لا إرسال آليًا — لا endpoint لذلك أصلًا
        })

    replied = con.execute(
        'SELECT COUNT(*) FROM leads WHERE first_reply_at IS NOT NULL').fetchone()[0]
    total = len(rows) + replied
    return {
        'queue': queue,
        'never_replied': len(rows),
        'total_leads': total,
        'rate_pct': round(len(rows) * 100 / total, 1) if total else None,
        'note': ('الردود مقترحات. **الإرسال من حسابك أنت** — لا يوجد endpoint إرسال، '
                 'ولا يُنفَّذ آليًا حتى بعد الموافقة.'),
        'never_write_reply': NEVER_WRITE_REPLY,
        'source': ['leads'],
        'missing': [{'field': 'price', 'question': 'السعر الشهري',
                     'impact': 'ردّا «السعر» و«الحجز» فيهما 【تحقّق】 حتى يُحسم — القرار 2'}],
    }


# ═══════════════════════════════════════════════════════════════
#  رئيس العمليات — الملخص اليومي
# ═══════════════════════════════════════════════════════════════
def daily_brief(con, now=None):
    """
    GET /api/v1/ops/daily-brief — العقد في tech/02-api-contracts.md §3.

    **حقائق لا أحكام.** `days_open` إلزامي. `broken` لا يُكتم. `missing` حاضر دائمًا.
    """
    now = now or TODAY
    broken, missing = [], []

    # ── 1) ما حدث ──
    happened = []
    try:
        rec = reconcile(con)
        happened.append({
            'item': f'{rec["case_count"]} حالة في مطابقة {rec["month"]}',
            'detail': (f'الفرق الصافي {rec["net_difference"]:,.0f} دج — وهو لا يعني شيئًا، '
                       f'فتحته {rec["case_count"]} حالة'),
            'risk': 'red' if any(c['risk'] == 'red' for c in rec['cases']) else 'yellow',
        })
    except Exception as e:                              # noqa: BLE001
        broken.append({'component': 'reconcile', 'error': str(e)})

    try:
        fun = funnel(con)
        nl = next((s for s in fun['stages'] if s['stage'] == 'لم يُرد عليهم إطلاقًا'), None)
        happened.append({
            'item': f'{nl["count"]} مهتمًا لم يُرد عليهم ({nl["rate_pct"]}%)',
            'detail': 'أكبر تسرّب في القمع — قبل أي مشكلة محتوى',
            'risk': 'red' if (nl['rate_pct'] or 0) >= 20 else 'yellow',
        })
    except Exception as e:                              # noqa: BLE001
        broken.append({'component': 'funnel', 'error': str(e)})

    # ── 2) يحتاج قرارك — مرتّبًا بالأقدم، days_open إلزامي ──
    decisions = []
    for r in con.execute("""
            SELECT id, created_at, agent, action_type, risk, source_ref, reason
              FROM pending_actions WHERE id > 0 AND status='pending'
             ORDER BY created_at"""):
        d = _days_open(r['created_at'], now)
        decisions.append({
            'id': r['id'], 'agent': r['agent'], 'action_type': r['action_type'],
            'risk': r['risk'], 'source_ref': r['source_ref'], 'reason': r['reason'],
            'days_open': d,
            'overdue': d is not None and d >= 3,     # ← يقود ⚠ متأخر
        })

    # القرارات المعلّقة التي ليست في طابور — من OPEN-QUESTIONS
    ts = con.execute("SELECT teacher_id, share_basis FROM teachers "
                     "WHERE share_basis IS NULL").fetchall()
    if ts:
        stmt = teacher_statement(con, ts[0]['teacher_id'])
        m = next((x for x in stmt['missing'] if x['field'] == 'share_basis'), None)
        decisions.append({
            'id': None, 'agent': '—', 'action_type': 'قرار مؤسسي',
            'risk': 'red', 'source_ref': 'OPEN-QUESTIONS.md القرار 1',
            'reason': m['question'] if m else 'أساس نسبة الأستاذ غير محسوم',
            'days_open': None, 'overdue': True,
            'impact': m['impact'] if m else None,
        })
        if m:
            missing.append(m)

    decisions.sort(key=lambda x: (not x['overdue'],
                                  -(x['days_open'] or 9999)))

    # ── 3) ماذا تعطّل / ماذا ينقصني ──
    for f_ in finance_summary(con)['missing']:
        missing.append(f_)
    for m in lead_nurturer_queue(con, now)['missing']:
        missing.append(m)

    revoked = [dict(r) for r in con.execute(
        'SELECT agent, revoked_at FROM agent_state WHERE revoked_at IS NOT NULL')]
    for r in revoked:
        broken.append({'component': f'agent:{r["agent"]}',
                       'error': f'موقوف بـ /revoke منذ {r["revoked_at"]}'})

    # ── 4) ماذا سأفعل الآن (بانتظار موافقتك) ──
    prepared = con.execute(
        "SELECT COUNT(*) FROM pending_actions WHERE id>0 AND status='pending'"
    ).fetchone()[0]

    return {
        'date': now.isoformat(),
        'sections': {
            'happened': happened,
            'needs_decision': decisions,
            'broken': broken,          # لا يُكتم أبدًا
            'prepared': [
                f'{prepared} اقتراحًا معلّقًا — راجعها',
                'لن أُرسل شيئًا لأي أحد، ولن أنشر شيئًا',
            ],
        },
        'overdue_count': sum(1 for d in decisions if d['overdue']),
        'missing': missing,            # حاضر دائمًا، ولو كان فارغًا
        'source': ['pending_actions', 'payments_accounting', 'payments_parents',
                   'leads', 'teachers', 'expenses', 'agent_state'],
    }
