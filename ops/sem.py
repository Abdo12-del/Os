#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
طبقة الفهم الدلالي — تميّز الكلمة مهما اختلفت مفرداتها.

سؤال المؤسس: «نموذج مفتوح المصدر يعطي الوكلاء قدرة تمييز الكلمات مهما
اختلفت مفرداتها.» بحثت: أقوى متجهات عربية مفتوحة (**aravec** ★429،
github.com/bakrianoo/aravec) أوزانها خارج جتهاب (HuggingFace/Drive) —
لا تصلها يدي ولا يعمل بها هاتفك بلا إنترنت، والمستودعات التي تفحصتها
لا تحمل إلا بيانات أو دفاتر. فبُني الفهم هنا من أربع طبقات مفتوحة
وبلا أوزان خارجية:

١. **المورفولوجيا** — Tashaphyne (linuxscout/tashaphyne، PyPI): تجذير
   وتقطيع خفيف، مع مقطيع احتياطي إن غاب. «يتحركون/الحركة/حركته» ← حرك.
٢. **عنقود المترادفات** — `memory/synonyms.md` يتدرّب من جتهاب كسائر
   التدريب: «فرط الحركة | كثير الحركة | ما يركز». لهجاتك ومفرداتك أنت.
٣. **متجهات توزيعية مدرَّبة على نصوصك** — PPMI من كل وثائق المستودع:
   كلمتان تتجاوران في سياقك تتقاربان. تُبنى بـ«درّب الفهم» وتُحفظ json.
٤. **تحمل الخطأ الإملائي** — «خبر التسويق» تفهمها «خبير التسويق»
   بمسافة تحرير ١ على الجذع.

لا شيء هنا يخترع معنى: الطبقة توسّع الاستعلام، والقرار يبقى للاسترجاع
الموثَّق في memory.py.
"""
import glob
import json
import math
import os
import re
from collections import Counter, defaultdict

import nlg

VECPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'sem_vectors.json')

try:
    from tashaphyne.stemming import ArabicLightStemmer as _T
    _TASH = _T()
    HAS_TASHAPHYNE = True
except ImportError:                                  # pragma: no cover
    _TASH = None
    HAS_TASHAPHYNE = False

_STOP = set('من إلى في على عن أن إن ما لا هل ثم أو و لل بال كما لكن كل بعض '
            'هذا هذه ذلك تلك عند مع قد كان كانت يكون بعد قبل بين حتى الذي '
            'التي هو هي نحن أنت أنا'.split())

PRE = ('وال', 'بال', 'كال', 'فال', 'لل', 'ال', 'وس', 'سي', 'س', 'و', 'ف', 'ب',
       'ك', 'ل', 'يت', 'تس', 'ست', 'ن', 'ت', 'ي', 'أ', 'ا')
SUF = ('اتي', 'يات', 'ات', 'ون', 'ين', 'ان', 'ها', 'هم', 'هن', 'كم', 'كم',
       'نا', 'ه', 'ي', 'ك', 'ة', 'ات')


def my_stem(w):
    w = nlg.norm(w)
    for p in PRE:
        if w.startswith(p) and len(w) - len(p) >= 3:
            w = w[len(p):]
            break
    for s in SUF:
        if w.endswith(s) and len(w) - len(s) >= 3:
            w = w[:-len(s)]
            break
    return w


def stem_candidates(w):
    """كل الوجوه الممكنة للجذع — المطابقة على أي منها."""
    w = nlg.norm(w)
    out = {w, my_stem(w)}
    if HAS_TASHAPHYNE:
        try:
            t = _TASH.light_stem(w)
            if len(t) >= 3:
                out.add(t)
        except Exception:                             # noqa: BLE001
            pass
    return {x for x in out if len(x) >= 3}


# ── عنقود المترادفات: تدريب بشري من جتهاب ──
_CLUSTERS = []


def load_synonyms(root):
    global _CLUSTERS
    _CLUSTERS = []
    path = os.path.join(root, 'memory', 'synonyms.md')
    if not os.path.exists(path):
        return 0
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line.startswith('- ') or '|' not in line:
            continue
        members = {nlg.norm(x) for x in line[2:].split('|') if x.strip()}
        if len(members) >= 2:
            _CLUSTERS.append(members)
    return len(_CLUSTERS)


ALPHA = re.compile(r'^[\u0621-\u064A]+$')


def _closure_tokens(qt):
    """عنقود ينطبق إن ورد أي عضو فيه — كلمة أو عبارة — داخل الاستعلام."""
    out = set()
    for c in _CLUSTERS:
        hit = False
        for m in c:
            if set(m.split()) <= qt:
                hit = True
                break
        if hit:
            for m in c:
                out |= set(m.split())
    return out


# ── متجهات توزيعية من نصوصه هو ──
_VEC = {}
_VOCAB = set()


def load_vectors():
    global _VEC, _VOCAB
    if os.path.exists(VECPATH):
        try:
            d = json.load(open(VECPATH, encoding='utf-8'))
            if isinstance(d, dict) and 'vec' in d:
                _VEC = {k: dict(v) for k, v in d['vec'].items()}
                _VOCAB = set(d.get('vocab', _VEC))
            else:                                     # صيغة قديمة
                _VEC = {k: dict(v) for k, v in d.items()}
                _VOCAB = set(_VEC)
        except Exception:                             # noqa: BLE001
            _VEC, _VOCAB = {}, set()
    return len(_VEC)


def build_vectors(root, vocab_cap=4000, ctx_cap=12):
    """PPMI على سياقات وثائقه: كلمتان في سياق واحد تتقاربان."""
    texts = []
    for pat in ('*.md', 'memory/*.md', 'marketing/*.md', 'knowledge/*.md',
                '07-prompts/*.md', 'templates/*.md', 'curriculum/*/*.md',
                'finance/*.md', 'tech/*.md'):
        texts += glob.glob(os.path.join(root, pat))
    co = defaultdict(Counter)
    cnt = Counter()
    for path in texts:
        if 'exports' in path:
            continue
        words = [w for w in nlg.norm(
            open(path, encoding='utf-8').read()).split()
            if len(w) > 2 and w not in _STOP and ALPHA.match(w)]
        for i, w in enumerate(words):
            cnt[w] += 1
            for j in range(max(0, i - 4), min(len(words), i + 5)):
                if j != i:
                    co[w][words[j]] += 1
    vocab = [w for w, _ in cnt.most_common(vocab_cap)]
    vset = set(vocab)
    total = sum(cnt.values()) or 1
    vec = {}
    for w in vocab:
        row = {}
        tw = sum(co[w].values()) or 1
        for c, n in co[w].items():
            if c not in vset or n < 2:
                continue
            pmi = math.log((n * total) / (tw * cnt[c]), 2)   # pmi موجب فقط
            if pmi > 0:
                row[c] = round(pmi, 3)
        top = sorted(row.items(), key=lambda x: -x[1])[:ctx_cap]
        if top:
            vec[w] = dict(top)
    _VEC.clear()
    _VEC.update(vec)
    _VOCAB.clear()
    _VOCAB.update(vocab)
    with open(VECPATH, 'w', encoding='utf-8') as f:
        json.dump({'vocab': vocab, 'vec': vec}, f, ensure_ascii=False)
    return len(vec)


def _cos(a, b):
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values())) or 1
    nb = math.sqrt(sum(v * v for v in b.values())) or 1
    return sum(a[k] * b[k] for k in keys) / (na * nb)


def related(w, k=5):
    w = nlg.norm(w)
    if w not in _VEC:
        return []
    sc = [(o, _cos(_VEC[w], _VEC[o])) for o in _VEC if o != w]
    sc.sort(key=lambda x: -x[1])
    return [(o, round(s, 3)) for o, s in sc[:k] if s > 0]


def _lev(a, b, cap=1):
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _fuzzy(t, pool, dist=1, max_hits=2):
    hits = [c for c in pool if _lev(t, c, dist) <= dist]
    return hits[:max_hits]


def expand(tokens, use_vectors=True, thresh=.40):
    """توسيع استعلام: عنقود مترادفات + جيران توزيعيون + تحمل خطأ إملائي."""
    tokens = [re.sub(r'[^\u0621-\u064A]', '', nlg.norm(t)) for t in tokens]
    tokens = [t for t in tokens if ALPHA.match(t)]
    qt = set(tokens)
    out = set(qt) | _closure_tokens(qt)
    if use_vectors and _VEC:
        for t in tokens:
            for o, sc in related(t, 3):
                if sc >= thresh:
                    out.add(o)
        pool = list(_VOCAB or _VEC)                   # المفردات أوسع من المتجهات
        for t in tokens:
            # الرباعي فأطول فقط: الثلاثي جيرانه كثر ويضلّل
            if t not in pool and len(t) >= 4:
                st = my_stem(t)
                for w in pool:             # كل المرشحين: وزن الواحد .4 فلا يضر
                    if _lev(st, my_stem(w), 1) <= 1:
                        out.add(w)
    return out
