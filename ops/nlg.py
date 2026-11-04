#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
لسان الوكلاء — تركيب الجمل، لا لصق القوائم.

المشروع المدمج: **PyArabic** (github.com/linuxscout/pyarabic — طه زروقي،
منشور في JOSS 2023): معالجة النص العربي — حذف التشكيل، تطبيع الهمزات
والألف والتاء، التقطيع. يُستورد اختياريًا: إن غاب عند المؤسس عمل اللسان
بطبقته الاحتياطية، فلا تتوقف اللغة على pip.

لماذا لا نكتفي بمodule الأعداد فيه؟ لأن مخرجه «أربع و ثلاثون ألف و خمسمئة»:
فواصل غير قياسية، بلا إعراب (ألف لا ألفًا)، وسن الجنس فيه لا ينضبط.
فوقه بُني محرّك المطابقة هنا — وهو جوهر «تركيب الجملة» في العربية.

الخط أنابيب NLG كلاسيكية (Reiter & Dale):
  اختيار المحتوى ← microplanning (مطابقة عدد/جنس + علاقات خطاب) ← realization
والوكيل لا يؤلّف معنى جديدًا: المعنى من استعلاماته، واللسان يلبسه جملةً سليمة.
"""
import re

try:
    import pyarabic.araby as _araby
    HAS_PYARABIC = True
except ImportError:                                  # pragma: no cover
    _araby = None
    HAS_PYARABIC = False


# ── معالجة النص: من PyArabic إن وجد ──
def norm(s):
    s = s or ''
    if HAS_PYARABIC:
        s = _araby.strip_harakat(s)
        s = _araby.normalize_hamza(s)
        s = _araby.normalize_alef(s)
        s = _araby.normalize_teh(s)
    else:
        import unicodedata
        s = unicodedata.normalize('NFKD', s)
        s = ''.join(c for c in s if not unicodedata.combining(c))
        for a, b in (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ى', 'ي'),
                     ('ة', 'ه'), ('ؤ', 'و'), ('ئ', 'ي')):
            s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip().lower()


def tokenize(s):
    if HAS_PYARABIC:
        return [t for t in _araby.tokenize(s) if t.strip()]
    return (s or '').split()


# ── محرّك المطابقة: العدد والمعدود ──
# صيغة التاء (ثلاثة) للمعدود المذكر، وبلا تاء (ثلاث) للمؤنث
ONES_T = {1: 'واحد', 2: 'اثنان', 3: 'ثلاثة', 4: 'أربعة', 5: 'خمسة',
          6: 'ستة', 7: 'سبعة', 8: 'ثمانية', 9: 'تسعة'}
ONES_NT = {1: 'واحدة', 2: 'اثنتان', 3: 'ثلاث', 4: 'أربع', 5: 'خمس',
           6: 'ست', 7: 'سبع', 8: 'ثماني', 9: 'تسع'}
TENS = {2: 'عشرون', 3: 'ثلاثون', 4: 'أربعون', 5: 'خمسون',
        6: 'ستون', 7: 'سبعون', 8: 'ثمانون', 9: 'تسعون'}
HUNDREDS = {1: 'مئة', 2: 'مئتان', 3: 'ثلاثمئة', 4: 'أربعمئة', 5: 'خمسمئة',
            6: 'ستمئة', 7: 'سبعمئة', 8: 'ثمانمئة', 9: 'تسععمئة'}


def _ones(n, g):
    return (ONES_T if g == 'm' else ONES_NT)[n]


def _w99(n, g='m'):
    """1..99 بصيغة العدد نفسه (للمال ولل وصل العقود)."""
    if n < 10:
        return _ones(n, g)
    if n == 10:
        return 'عشرة' if g == 'm' else 'عشر'
    if n == 11:
        return 'أحد عشر' if g == 'm' else 'إحدى عشرة'
    if n == 12:
        return 'اثنا عشر' if g == 'm' else 'اثنتا عشرة'
    if n < 20:
        return f'{_ones(n % 10, g)} {"عشر" if g == "m" else "عشرة"}'
    t, u = divmod(n, 10)
    return f'{_ones(u, g)} و{TENS[t]}' if u else TENS[t]


def _w999(n, g='m'):
    h, r = divmod(n, 100)
    if h and r:
        return f'{HUNDREDS[h]} و{_w99(r, g)}'
    return HUNDREDS[h] if h else _w99(r, g)


def _scale(k, one, two, few, many):
    """k ألف/مليون: واحد/اثنان/جمع/منصوب."""
    if k == 1:
        return one
    if k == 2:
        return two
    if k <= 10:
        return f'{ONES_T[k]} {few}'
    if k <= 99:
        return f'{_w99(k)} {many}'
    return f'{_w999(k)} {one}'


def money(n, currency='دينار'):
    """34500 ← «أربعة وثلاثون ألفًا وخمسمئة دينار»."""
    n = int(round(n))
    if n == 0:
        return f'لا {currency}'
    parts = []
    m, rest = divmod(n, 1_000_000)
    k, r = divmod(rest, 1_000)
    if m:
        parts.append(_scale(m, 'مليون', 'مليونان', 'ملايين', 'مليونًا'))
    if k:
        parts.append(_scale(k, 'ألف', 'ألفان', 'آلاف', 'ألفًا'))
    if r:
        parts.append(_w999(r))
    return ' و'.join(parts) + f' {currency}'


def counted(n, sing, plur, dual=None, g='m'):
    """
    مطابقة العدد والمعدود — الموضع الذي تكسر فيه الآلات العربية.
    counted(3,'يوم','أيام','يومان','m')  ← 'ثلاثة أيام'
    counted(5,'دفعة','دفعات','دفعتان','f') ← 'خمس دفعات'
    """
    n = int(n)
    dual = dual or sing + 'ان'
    if n == 0:
        return f'لا {plur}'
    if n == 1:
        # تنوين النصب على المعدود والصفة: «اقتراحًا واحدًا» / «دفعةً واحدة»
        return (f'{sing}ًا واحدًا' if g == 'm' else f'{sing}ً واحدة')
    if n == 2:
        return dual
    if n <= 10:
        return f'{_ones(n, g)} {plur}'
    if n <= 99:
        # تنوين النصب: على التاء المربوطة «دفعةً»، وعلى غيرها «يومًا»
        tan = 'ً' if sing.endswith('ة') else 'ًا'
        return f'{_w99(n, g)} {sing}{tan}'
    if n <= 999:
        return f'{_w999(n, g)} {sing}'
    return f'{n} {sing}'


def days(n):
    return counted(n, 'يوم', 'أيام', 'يومان', 'm')


# ── العلاقات الخطابية: الوصل لا السرد ──
CONN = {'add': '، ', 'cause': '؛ لذلك ', 'contrast': '، لكن ',
        'seq': '، ثم ', 'conc': '، ورغم ذلك '}


def compose(parts):
    """[(علاقة, جملة)] ← فقرة متماسكة. أول جملة تُفتَح بلا وصل."""
    out = ''
    for i, (rel, clause) in enumerate(parts):
        clause = clause.strip()
        if not clause:
            continue
        out += clause if i == 0 else CONN.get(rel, '، ') + clause
    return out.rstrip('،; ') + '.' if out else ''


# ── realization: كلام الوكلاء ──
def prose_reconcile(r):
    a, p = r['totals']['accounting'], r['totals']['parents']
    parts = [
        ('add', f'طابقتُ المرجعين: {counted(a["count"], "دفعة", "دفعات", "دفعتان", "f")}'
                f' في نظام المحاسبة مجموعها {money(a["sum"])}، مقابل '
                f'{counted(p["count"], "دفعة", "دفعات", "دفعتان", "f")}'
                f' في نظام الأولياء مجموعها {money(p["sum"])}'),
        ('contrast', f'الفرق الصافي {money(abs(r["net_difference"]))} فقط'),
        ('cause', f'تحته {counted(r["case_count"], "حالة", "حالات", "حالتان", "f")}'
                  ' باتجاهين متعاكسين، فلا أحكم على المجموع وحده'),
    ]
    if r.get('arrears'):
        names = ' و'.join(x['alias_name'] for x in r['arrears'])
        parts.append(('add', f'المتأخرات عند {names}'))
    return compose(parts)


def prose_run(rep, names=None):
    names = names or {}
    nm = lambda a: names.get(a, a).replace('_', ' ')
    ran = rep.get('ran', [])
    parts = [('add', f'شغّلتُ {counted(len(ran) + len(rep.get("skipped", [])), "وكيل", "وكلاء", "وكيلان", "m")}')]
    for x in ran:
        parts.append(('add', f'{nm(x["agent"])} اقترح '
                             f'{counted(x["proposed"], "اقتراح", "اقتراحات", "اقتراحان", "m")}'
                             if x['proposed'] else f'{nm(x["agent"])} لم يجد جديدًا'))
    for sk in rep.get('skipped', []):
        parts.append(('conc', f'{nm(sk["agent"])} موقوف بقرارك'))
    parts.append(('cause', f'المجموع {counted(rep.get("proposed", 0), "اقتراح", "اقتراحات", "اقتراحان", "m")}'
                           ' وصل كلٌّ منها فقاعة في محادثة وكيله'))
    return compose(parts)


def prose_teacher(st):
    if st.get('basis') is None:
        return compose([
            ('add', f'لا أحسب مستند {st.get("alias", "")} بلا أساس محسوم'),
            ('cause', f'الفارق بين الأسس {money(st.get("spread_dzd", 0))}،'
                      ' وهو قرارك أنت لا تخميني'),
        ])
    src = st.get('basis_memory')
    tail = [('add', f'مستند {st.get("alias", "")} على أساس المحصَّل الفعلي: '
                    f'{money(st.get("amount_due", 0))}')]
    if src:
        tail.append(('add', f'والمصدر قرارُك المحفوظ في الذاكرة (#{src["id"]})'))
    return compose(tail)


def prose_leads(q):
    # الأعداد هنا أخبارٌ مرفوعة فقط — حروف الجر تكسر العقد الظاهر
    return compose([
        ('add', f'الطابور فيه {counted(q["total_leads"], "مهتم", "مهتمين", "مهتمان", "m")}'),
        ('contrast', f'منهم {counted(q["never_replied"], "مهتم", "مهتمين", "مهتمان", "m")}'
                     ' لم يُردَّ عليهم أبدًا'),
        ('cause', 'هذا أكبر تسرّب عندنا، قبل أي إعلان جديد'),
        ('add', 'كل مسوّدة من دليل الرد الأول، والإرسال يبقى يدك'),
    ])


def prose_approve_exec(aid, ref):
    return compose([
        ('add', f'✅ نُفّذ الاقتراح #{aid} في تطبيقك والمرجع {ref}'),
        ('seq', 'سُجّل في التدقيق باسمك'),
    ])


def prose_approve_manual(aid, at):
    return compose([
        ('add', f'سجّلتُ موافقتك على #{aid} ({at})'),
        ('contrast', 'لا يوجد تنفيذ آلي لإجراء موجّه لولي أمر، ولن يوجد'),
        ('cause', 'انسخ النص وانشره من حسابك'),
    ])


def prose_reject(aid, reason):
    return compose([
        ('add', f'رفضتُ الاقتراح #{aid}'),
        ('seq', f'سجّلت سببك: «{reason}»'),
        ('cause', 'السبب هو الطريقة الوحيدة التي أتعلّم بها'),
    ])
