#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الذاكرة — العقل الثاني.

لماذا وُجدت: المؤسس شخص واحد، وتعب من أن يكون الذاكرة الوحيدة في شركته.
هنا تُحفظ القرارات والحقائق والوعود والحلقات والدروس — لكلٍّ مصدر وتاريخ،
ولا تُمحى ذكرى أبدًا: تُبطَل (valid_to + superseded_by) وتبقى للتاريخ.

المعمارية مستعارة من البحث ومصرَّحة في memory/00-architecture.md:
  CoALA (arXiv:2309.02427)        → الأنواع: حلقة/حقيقة/قرار/وعد/درس
  Generative Agents (2304.03442)  → الاسترجاع = صلة + أقدمية + أهمية
  Zep/Graphiti (2501.13956)       → الزمان على كل حقيقة، وإبطال لا overwrite

بلا نموذج لغة فلا embeddings: الصلة هنا **تداخل رموز** بعد تطبيع عربي،
موزونًا بـ idf — صريح، قابل للتفتيش، ولا يخترع تشابهًا.
"""
import glob
import math
import os
import re
import unicodedata

import engine

KINDS = ('episode', 'fact', 'decision', 'promise', 'lesson')
# الشيخوخة تختلف بالنوع: الحلقة تتقادم سريعًا، الحقيقة والمرجع ببطء
HALF_LIFE = {'episode': 30, 'lesson': 90, 'fact': 365,
             'decision': 365, 'promise': 30}
IMPORTANCE = {'decision': .9, 'promise': .8, 'lesson': .7,
              'fact': .6, 'episode': .4}
KIND_AR = {'episode': 'حلقة', 'fact': 'حقيقة', 'decision': 'قرار',
           'promise': 'وعد', 'lesson': 'درس'}

STOP = set('''من إلى في على عن أن إن ما لا نعم هو هي هل ثم أو و لل بال كما لكن
كل بعض الذي التي هذا هذه ذلك تلك يوم عند مع قد كان كانت يكون بعد قبل بين حتى
أنا أنت نحن لكم عليك إليه إليها إليها'''.split())


def _norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    for a, b in (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ى', 'ي'),
                 ('ة', 'ه'), ('ؤ', 'و'), ('ئ', 'ي')):
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip().lower()


def tokens(s):
    return [t for t in _norm(s).split() if t not in STOP and len(t) > 1]


# ── الكتابة ───────────────────────────────────────────────────
def remember(con, kind, owner, subject, text, tags='', source='chat',
             importance=None):
    if kind not in KINDS:
        return None
    imp = importance if importance is not None else IMPORTANCE[kind]
    cur = con.execute(
        'INSERT INTO memories (kind, owner, subject, text, tags, source,'
        ' importance, created_at) VALUES (?,?,?,?,?,?,?,?)',
        (kind, owner, subject, text, tags, source, imp, engine._ts()))
    con.commit()
    return cur.lastrowid


def supersede(con, mid, by_id):
    """إبطال ثم إضافة — لا overwrite ولا حذف (قاعدة المؤسس + Zep)."""
    con.execute('UPDATE memories SET valid_to=?, superseded_by=? WHERE id=?',
                (engine._ts(), by_id, mid))
    con.commit()


def decide(con, tag, subject, text, source='chat', extra_tags=''):
    """قرار جديد يُبطل القرار السابق بنفس الوسم. يعيد (القديم, الجديد)."""
    old = con.execute(
        "SELECT * FROM memories WHERE kind='decision' AND superseded_by IS NULL"
        " AND tags LIKE ?", (f'%{tag}%',)).fetchone()
    new = remember(con, 'decision', 'founder', subject, text,
                   tags=f'{tag} #قرار {extra_tags}'.strip(), source=source,
                   importance=.9)
    if old:
        supersede(con, old['id'], new)
    return (dict(old) if old else None, new)


def decision_for(con, tag):
    row = con.execute(
        "SELECT * FROM memories WHERE kind='decision' AND superseded_by IS NULL"
        " AND tags LIKE ? ORDER BY id DESC LIMIT 1", (f'%{tag}%',)).fetchone()
    return dict(row) if row else None


# ── القراءة: صلة + أقدمية + أهمية (Park et al. 2023) ──────────
def recall(con, query, owner=None, kinds=None, k=5, include_invalid=False):
    q = tokens(query)
    if not q:
        return []
    sql = 'SELECT * FROM memories'
    wh, args = [], []
    if not include_invalid:
        wh.append('superseded_by IS NULL')
    if owner:
        wh.append('owner=?'); args.append(owner)
    if kinds:
        wh.append('kind IN (%s)' % ','.join('?' * len(kinds)))
        args += list(kinds)
    if wh:
        sql += ' WHERE ' + ' AND '.join(wh)
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    if not rows:
        return []
    docs = {r['id']: set(tokens(r['subject'] + ' ' + r['text'] + ' ' + r['tags']))
            for r in rows}
    df = {}
    for t in set(q):
        df[t] = sum(1 for d in docs.values() if t in d) or 10**9
    now = engine.NOW
    out = []
    for r in rows:
        d = docs[r['id']]
        matched = [t for t in q if t in d]
        if not matched:
            continue
        rel = sum(1.0 / math.log(1 + df[t]) for t in matched) / len(q)
        try:
            age = (now - engine.datetime.fromisoformat(r['created_at'])).days
        except ValueError:
            age = 0
        rec = .5 ** (max(age, 0) / HALF_LIFE.get(r['kind'], 90))
        score = rel + .3 * rec + .4 * r['importance']
        out.append({**r, 'score': round(score, 3), 'matched': matched,
                    'age_days': age, 'kind_ar': KIND_AR[r['kind']]})
    out.sort(key=lambda x: -x['score'])
    return out[:k]


def all_memories(con, include_invalid=True):
    rows = con.execute('SELECT * FROM memories ORDER BY id').fetchall()
    return [{**dict(r), 'kind_ar': KIND_AR[r['kind']]} for r in rows
            if include_invalid or r['superseded_by'] is None]


def brief_memory(con):
    """ما تضعه الذاكرة في الملخص الصباحي — لتزيح عن كتفه."""
    open_dec = [dict(r) for r in con.execute(
        "SELECT * FROM memories WHERE kind='decision' AND superseded_by IS NULL"
        " AND tags LIKE '%#مفتوح%' ORDER BY id")]
    promises = [dict(r) for r in con.execute(
        "SELECT * FROM memories WHERE kind='promise' AND superseded_by IS NULL"
        " ORDER BY id")]
    lessons = [dict(r) for r in con.execute(
        "SELECT * FROM memories WHERE kind='lesson' AND superseded_by IS NULL"
        " ORDER BY id DESC LIMIT 3")]
    return {'open_decisions': open_dec, 'promises': promises,
            'recent_lessons': lessons}


def apply_decision_to_statement(con, st):
    """قرار محفوظ في الذاكرة يصير رقمًا محسوبًا.

    إن حسم المؤسس أساس حصة الأستاذ في الدردشة («قررت …») فالمستند يخرج
    بمبلغ حقيقي مصدره ذكرى موقّعة — لا برأي الوكيل.
    """
    dec = decision_for(con, '#share_basis')
    if not dec or st.get('basis'):
        return st
    m = re.search(r'#basis:(\w+)', dec['tags'])
    if not m:
        return st
    key = m.group(1)
    cand = next((c for c in st.get('candidates', []) if c['basis'] == key), None)
    if not cand:
        return st
    st['basis'] = key
    st['amount_due'] = cand['amount']
    st['basis_memory'] = {'id': dec['id'], 'text': dec['text'],
                          'source': dec['source'], 'created_at': dec['created_at']}
    st['missing'] = [x for x in st.get('missing', [])
                     if x.get('field') != 'share_basis']
    return st


# ── الالتقاط التلقائي: الحلقة تُقطَّر إلى درس ──────────────────
def capture(con, event, data):
    """يُسجَّل في engine.ON_EVENT — الذاكرة لا تكسر العمل إن أخفقت."""
    if event == 'reject':
        remember(con, 'lesson', data['agent'],
                 f"رفض #{data['id']} ({data['action_type']})",
                 data['reason'],
                 tags=f"{data['action_type']} #{data['agent']} #درس",
                 source=f"engine:reject#{data['id']}", importance=.7)
    elif event == 'executed':
        remember(con, 'episode', data['agent'],
                 f"تنفيذ #{data['id']} ({data['action_type']})",
                 f"نُفّذ بعد موافقة المؤسس — المرجع {data.get('ref', '—')}",
                 tags=f"{data['action_type']} #{data['agent']} #حلقة",
                 source=f"engine:executed#{data['id']}", importance=.4)
    elif event == 'approved_manual':
        remember(con, 'episode', data['agent'],
                 f"موافقة يدوية #{data['id']} ({data['action_type']})",
                 'سجّل المؤسس موافقته والتنفيذ بقي يدويًا — لا كود ينشر أو يراسل.',
                 tags=f"{data['action_type']} #{data['agent']} #حلقة",
                 source=f"engine:manual#{data['id']}", importance=.5)


# ── التدريب من GitHub: ملفات memory/*.md ──────────────────────
def ingest(con, root):
    """يقرأ أسطر التدريب: `- نوع | مالك | موضوع | نص | #وسوم`."""
    n = 0
    for path in sorted(glob.glob(os.path.join(root, 'memory', '*.md'))):
        # التصدير لقطةٌ لا تدريب: إعادة التهامه تبعث قرارات مبطلة من الموت
        if os.path.basename(path).startswith('export-'):
            continue
        src = 'repo:' + os.path.relpath(path, root).replace(os.sep, '/')
        for line in open(path, encoding='utf-8'):
            line = line.strip()
            if not line.startswith('- ') or line.count('|') < 3:
                continue
            parts = [p.strip() for p in line[2:].split('|')]
            kind, owner, subject, text = parts[0], parts[1], parts[2], parts[3]
            tags = parts[4] if len(parts) > 4 else ''
            if kind not in KINDS:
                continue
            dup = con.execute('SELECT 1 FROM memories WHERE source=? AND'
                              ' subject=? AND text=?', (src, subject, text)
                              ).fetchone()
            if dup:
                continue
            remember(con, kind, owner, subject, text, tags, source=src)
            n += 1
    return n


def ensure(con, root):
    """إن كانت الذاكرة فارغة (قاعدة بكر) يلتهم التدريب من المستودع."""
    n = con.execute('SELECT COUNT(*) c FROM memories').fetchone()['c']
    if n:
        return 0
    return ingest(con, root)


# ── التصدير عودةً إلى المستودع ────────────────────────────────
def export_md(con, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = all_memories(con)
    by = {}
    for r in rows:
        by.setdefault(r['kind'], []).append(r)
    lines = ['# الذاكرة المصدَّرة — لا تُمحى، تُستبدل فقط', '']
    for kind in KINDS:
        lines.append(f'## {KIND_AR[kind]} ({len(by.get(kind, []))})')
        for r in by.get(kind, []):
            dead = ' [مُبطَلة → #%d]' % r['superseded_by'] if r['superseded_by'] else ''
            lines.append(f"- {kind} | {r['owner']} | {r['subject']} | {r['text']}"
                         f" | {r['tags']}  <!-- {r['source']} @ {r['created_at']}{dead} -->")
        lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return len(rows)
