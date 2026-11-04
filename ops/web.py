#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
وكيل الإنترنت — بحث مجاني بالكامل، بلا بطاقة ولا التزام.

بحث شديد (نوفمبر 2026) قبل الاختيار:
- **ddgs** (DuckDuckGo، PyPI — كان اسمه duckduckgo-search): مجاني
  بالكامل، **بلا مفتاح ولا تسجيل** — وهو الأساسي هنا.
- **Wikipedia API**: رسمي ومجاني وبلا مفتاح، urllib القياسية فقط —
  الاحتياطي المعرفي إن غاب ddgs أو تعطّل.
- **Tavily**: ألف بحث شهريًا مجانًا بلا بطاقة، لكنه يحتاج تسجيلًا —
  **اختياري**: ضع TAVILY_API_KEY في البيئة فيتقدّم السلسلة.
- **Brave Search API**: مرفوض — خطته المجانية أُلغيت للمشتركين الجدد
  (فبراير 2026) وصارت تتطلب بطاقة ائتمان، وشرط المؤسس «مجاني بالكامل».

القواعد كما هي: البحث **قراءة فقط** — لا مراسلة ولي أمر، لا نشر، لا
مال. النتائج بطاقة اقتراح، والقرار للمؤسس دائمًا. وكل بحث يُخزَّن في
`web_cache`: تدقيق، وتوفير في المعدل (ddgs يخنق الطلبات المتلاحقة)،
وعرض لاحق بلا إنترنت. وإن انقطع الإنترنت نقولها بصدق — لا نختلق
نتائج أبدًا.
"""
import json
import os
import time
import urllib.parse
import urllib.request

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:                                  # pragma: no cover
    DDGS = None
    HAS_DDGS = False

TTL = 3600          # ساعة للكاش — ddgs يخنق التكرار
UA = 'AcademyOs/1.0 (founder-operated agents; Ouargla DZ)'   # ويكيبيديا تشترط UA


def ensure(con):
    con.execute('CREATE TABLE IF NOT EXISTS web_cache ('
                'q TEXT PRIMARY KEY, provider TEXT, payload TEXT,'
                ' created REAL)')
    con.commit()


# ── المزوّدون ────────────────────────────────────────────────
def _ddg(q, n):
    rows = DDGS().text(q, max_results=n, safesearch='moderate')
    return [{'title': r.get('title', ''), 'url': r.get('href', ''),
             'snippet': r.get('body', '')} for r in rows]


def _wiki(q, n):
    url = ('https://ar.wikipedia.org/w/api.php?' + urllib.parse.urlencode(
        {'action': 'query', 'list': 'search', 'srsearch': q, 'srlimit': n,
         'format': 'json', 'utf8': 1}))
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    d = json.load(urllib.request.urlopen(req, timeout=10))
    out = []
    for h in d.get('query', {}).get('search', []):
        snip = (h.get('snippet', '')
                .replace('<span class="searchmatch">', '').replace('</span>', ''))
        out.append({'title': h['title'],
                    'url': 'https://ar.wikipedia.org/wiki/'
                           + urllib.parse.quote(h['title'].replace(' ', '_')),
                    'snippet': snip})
    return out


def _tavily(q, n):
    key = os.environ.get('TAVILY_API_KEY')
    req = urllib.request.Request(
        'https://api.tavily.com/search',
        data=json.dumps({'api_key': key, 'query': q, 'max_results': n,
                         'search_depth': 'basic'}).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': UA})
    d = json.load(urllib.request.urlopen(req, timeout=15))
    return [{'title': r.get('title', ''), 'url': r.get('url', ''),
             'snippet': (r.get('content') or '')[:300]}
            for r in d.get('results', [])]


def providers():
    """مفتاحك المجاني إن سجّلت، ثم ddgs بلا مفتاح، ثم ويكيبيديا دائمًا."""
    chain = []
    if os.environ.get('TAVILY_API_KEY'):
        chain.append(('tavily', _tavily))
    if HAS_DDGS:
        chain.append(('ddgs', _ddg))
    chain.append(('wikipedia', _wiki))
    return chain


# ── البحث ────────────────────────────────────────────────────
def search(con, q, n=5, fresh=False):
    qn = ' '.join(q.split())
    now = time.time()
    row = con.execute('SELECT provider, payload, created FROM web_cache'
                      ' WHERE q=?', (qn,)).fetchone()
    if row and not fresh and now - row['created'] < TTL:
        return {'query': qn, 'provider': row['provider'] + ' (كاش)',
                'results': json.loads(row['payload']), 'cached': True}
    errors = []
    for name, fn in providers():
        try:
            res = fn(qn, n)
            if res:
                con.execute('INSERT OR REPLACE INTO web_cache (q, provider,'
                            ' payload, created) VALUES (?,?,?,?)',
                            (qn, name, json.dumps(res, ensure_ascii=False),
                             now))
                con.commit()
                return {'query': qn, 'provider': name, 'results': res,
                        'cached': False}
            errors.append(f'{name}: صفر نتائج')
        except Exception as e:                          # noqa: BLE001
            errors.append(f'{name}: {e.__class__.__name__}')
    return {'query': qn, 'provider': None, 'results': [],
            'error': 'ما وصلت للإنترنت الآن (' + '، '.join(errors) + '). '
                     'لم أختلق نتائج — أعد المحاولة أو تحقق من الاتصال.'}
