#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بناء موقع الويب من وثائق المستودع.

بلا تبعيات: لا npm، لا pip، لا CDN. Python القياسية فقط.
    python3 tools/build_site.py            → يبني في site/dist/
    python3 tools/build_site.py --check    → يبني ويبلغ عن أي فشل ولا يكتب

لماذا هذا الملف موجود:
    GitHub على الهاتف يكسر الجداول العريضة (positioning.md فيه جداول بـ 6 أعمدة).
    الموقع يحوّل كل جدول على الشاشات الصغيرة إلى بطاقات مسمّاة — نفس المحتوى،
    بلا تمرير أفقي.
"""
import os, re, sys, html, json, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'site', 'dist')

# ─────────────────────────────────────────────────────────────
# ترتيب المجموعات — نفس مجموعات START-HERE.md «اقرأ هذا حين…»
# ─────────────────────────────────────────────────────────────
GROUPS = [
    ('ابدأ من هنا', [
        ('START-HERE.md', 'الساعة الأولى'),
        ('OPEN-QUESTIONS.md', 'القرارات المعلّقة'),
        ('README.md', 'فهرس النظام'),
    ]),
    ('التسويق — تستعمله اليوم', [
        ('marketing/first-reply-playbook.md', 'دليل الرد الأول ★'),
        ('marketing/posts-week1.md', 'منشورات الأسبوع الأول'),
        ('marketing/positioning.md', 'التموضع والممنوعات'),
    ]),
    ('المحاسبة', [
        ('knowledge/06-accounting-setup.md', 'إعداد المحاسبة'),
        ('finance/README.md', 'مجلد التقارير'),
        ('tests/fixtures/accounting-october-2026.md', 'بيانات اختبار أكتوبر'),
    ]),
    ('الوكلاء والأنظمة', [
        ('01-org-chart.md', 'الهيكل التنظيمي'),
        ('02-agent-cards.md', 'بطاقات الوكلاء'),
        ('03-head-of-operations.md', 'رئيس العمليات'),
        ('04-communication-layer.md', 'طبقة الاتصال'),
        ('05-rules.md', 'القواعد الإحدى عشرة'),
        ('06-build-roadmap.md', 'خارطة البناء'),
        ('08-test-checklist.md', 'قائمة الاختبار'),
        ('09-operating-rhythm.md', 'الإيقاع التشغيلي'),
    ]),
    ('أنظمة تشغيل الوكلاء (انسخ والصق)', [
        ('07-prompts/00-head-of-operations.md', 'رئيس العمليات'),
        ('07-prompts/01-marketing-expert.md', 'خبير التسويق'),
        ('07-prompts/02-parent-secretary.md', 'سكرتير الأولياء'),
        ('07-prompts/03-attendance-chaser.md', 'متابع الحضور'),
        ('07-prompts/04-accountant.md', 'المحاسب'),
        ('07-prompts/05-curriculum-expert.md', 'خبير المناهج'),
        ('07-prompts/06-content-writer.md', 'كاتب المحتوى'),
        ('07-prompts/07-lead-nurturer.md', 'متابع المهتمين'),
    ]),
    ('المناهج والقوالب', [
        ('knowledge/07-curriculum-framework.md', 'إطار المنهج'),
        ('curriculum/README.md', 'قواعد المنهج'),
        ('curriculum/group-agreements.md', 'قواعد المجموعة الخمس'),
        ('curriculum/activity-bank-v0.md', 'بنك الأنشطة'),
        ('curriculum/stage-1/README.md', 'المرحلة الأولى (معلّقة)'),
        ('templates/parent-consent.md', 'إذن ولي الأمر'),
        ('templates/teacher-agreement.md', 'اتفاق الأستاذ'),
        ('templates/monthly-progress-report.md', 'دليل التقدّم الشهري'),
    ]),
    ('يعمل الآن — مركز العمليات', [
        ('ops/README.md', '★ محرّك يعمل، لا وثيقة'),
        ('memory/00-architecture.md', '★ العقل الثاني: معمارية الذاكرة'),
        ('memory/facts-business.md', 'تدريب: حقائق العمل'),
        ('memory/decisions-open.md', 'تدريب: القرارات المفتوحة'),
        ('memory/lessons-seed.md', 'تدريب: الدروس الأولى'),
        ('memory/synonyms.md', 'تدريب: عنقود المترادفات — الفهم الدلالي'),
    ]),
    ('البنية التقنية (أنت المبرمج)', [
        ('tech/01-schema.sql', 'مخطط قاعدة البيانات'),
        ('tech/02-api-contracts.md', 'عقود الـ API'),
        ('tech/03-integrations.md', 'بوت تيليجرام + MCP'),
    ]),
    ('معرفة واختبارات', [
        ('knowledge/01-prices-and-levels.md', 'الأسعار والمستويات'),
        ('knowledge/02-weekly-schedule.md', 'الجدول الأسبوعي'),
        ('knowledge/03-faq-and-reply-rules.md', 'الأسئلة الشائعة'),
        ('knowledge/04-payment-policy.md', 'سياسة الدفع'),
        ('knowledge/05-marketing-brief.md', 'ملخص التسويق'),
        ('tests/fixtures/README.md', 'كيف تُستخدم البيانات'),
        ('tests/fixtures/marketing-scenarios.md', 'سيناريوهات التسويق'),
        ('tests/fixtures/seed_staging.sql', 'بيانات الإقلاع'),
        ('exports/README.md', 'مجلد التصديرات'),
    ]),
]

SKIP = {'log.md'}
SKIP_DIR = {'memory/exports'}   # لقطات مولّدة، لا صفحات


# ─────────────────────────────────────────────────────────────
# محوّل Markdown → HTML
# ─────────────────────────────────────────────────────────────
def inline(text):
    """تنسيق داخل السطر. الترتيب مهم: الكود أولًا فيُحمى مما بعده."""
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f'\x00{len(codes)-1}\x00'

    text = re.sub(r'`([^`]+)`', stash, text)
    text = html.escape(text, quote=False)
    # روابط — تُحوَّل قبل الخط العريض كي لا يبتلعها
    text = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)',
                  lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', text)

    def unstash(m):
        return f'<code>{html.escape(codes[int(m.group(1))], quote=False)}</code>'

    return re.sub(r'\x00(\d+)\x00', unstash, text)


def slug(text):
    s = re.sub(r'[^\w\u0600-\u06FF\s-]', '', text).strip()
    return re.sub(r'\s+', '-', s)[:60] or 'section'


def convert(md):
    """Markdown → (html, toc). يغطي كل ما تستخدمه وثائق هذا المستودع."""
    lines = md.replace('\r\n', '\n').split('\n')
    out, toc = [], []
    i, n = 0, len(lines)

    def is_table_start(k):
        return (k + 1 < n and lines[k].strip().startswith('|')
                and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[k + 1]))

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── كتلة كود ──
        if stripped.startswith('```'):
            lang = stripped[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith('```'):
                buf.append(lines[i]); i += 1
            i += 1
            code = html.escape('\n'.join(buf), quote=False)
            cls = f' class="lang-{lang}"' if lang else ''
            out.append(f'<pre><code{cls} dir="ltr">{code}</code></pre>')
            continue

        # ── عنوان ──
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            sid = slug(text)
            if 2 <= level <= 3:
                toc.append((level, sid, re.sub(r'[`*]', '', text)))
            out.append(f'<h{level} id="{sid}">{inline(text)}</h{level}>')
            i += 1
            continue

        # ── فاصل أفقي ──
        if re.match(r'^\s*(-{3,}|\*{3,}|_{3,})\s*$', line):
            out.append('<hr>')
            i += 1
            continue

        # ── جدول ──
        if is_table_start(i):
            def cells(row):
                r = row.strip()
                if r.startswith('|'): r = r[1:]
                if r.endswith('|'): r = r[:-1]
                return [c.strip() for c in r.split('|')]

            head = cells(lines[i])
            i += 2
            body = []
            while i < n and lines[i].strip().startswith('|'):
                body.append(cells(lines[i])); i += 1
            # data-label على كل خلية → CSS يحوّل الجدول إلى بطاقات على الهاتف
            t = ['<div class="tbl"><table><thead><tr>']
            t += [f'<th>{inline(c)}</th>' for c in head]
            t.append('</tr></thead><tbody>')
            for row in body:
                t.append('<tr>')
                for idx, c in enumerate(row):
                    lbl = head[idx] if idx < len(head) else ''
                    t.append(f'<td data-label="{html.escape(re.sub(r"[`*]", "", lbl), quote=True)}">{inline(c)}</td>')
                t.append('</tr>')
            t.append('</tbody></table></div>')
            out.append(''.join(t))
            continue

        # ── اقتباس ──
        if stripped.startswith('>'):
            buf = []
            while i < n and lines[i].strip().startswith('>'):
                buf.append(re.sub(r'^\s*>\s?', '', lines[i])); i += 1
            inner, _ = convert('\n'.join(buf))
            out.append(f'<blockquote>{inner}</blockquote>')
            continue

        # ── قائمة (مرتّبة أو غير مرتّبة، مع تداخل) ──
        if re.match(r'^\s*([-*+]|\d+[.)])\s+', line):
            items, i = parse_list(lines, i, n)
            out.append(render_list(items))
            continue

        # ── سطر فارغ ──
        if not stripped:
            i += 1
            continue

        # ── فقرة ──
        buf = [line]
        i += 1
        while (i < n and lines[i].strip()
               and not re.match(r'^(#{1,6}\s|\s*([-*+]|\d+[.)])\s|>|```|\|)', lines[i])
               and not re.match(r'^\s*(-{3,}|\*{3,})\s*$', lines[i])):
            buf.append(lines[i]); i += 1
        out.append(f'<p>{inline(" ".join(x.strip() for x in buf))}</p>')

    return '\n'.join(out), toc


def parse_list(lines, i, n):
    """يجمع عناصر القائمة مع تداخلها. يُرجع [(indent, marker, text)] وقائمة فرعية."""
    items = []
    while i < n:
        line = lines[i]
        m = re.match(r'^(\s*)([-*+]|\d+[.)])\s+(.*)$', line)
        if not m:
            # سطر متمّم للعنصر السابق (مزوَّد بمسافة)
            if items and line.strip() and line.startswith(('  ', '\t')):
                items[-1]['text'] += ' ' + line.strip()
                i += 1
                continue
            break
        indent = len(m.group(1).replace('\t', '    '))
        marker = 'ol' if re.match(r'\d', m.group(2)) else 'ul'
        items.append({'indent': indent, 'marker': marker, 'text': m.group(3)})
        i += 1
    return items, i


def render_list(items):
    """يبني قائمة متداخلة من عناصر بمسافات بادئة مختلفة."""
    if not items:
        return ''
    base = min(it['indent'] for it in items)
    marker = items[0]['marker']
    out, buf = [], []

    def flush():
        if buf:
            out.append(''.join(buf))
            buf.clear()

    k = 0
    while k < len(items):
        it = items[k]
        if it['indent'] > base:
            # اجمع الفرعي
            sub = []
            while k < len(items) and items[k]['indent'] > base:
                sub.append(items[k]); k += 1
            if buf:
                buf[-1] = buf[-1][:-5] + render_list(sub) + '</li>'
            else:
                out.append(render_list(sub))
            continue
        buf.append(f'<li>{inline(it["text"])}</li>')
        k += 1
    flush()
    return f'<{marker}>{"".join(out)}</{marker}>'


# ─────────────────────────────────────────────────────────────
# القالب
# ─────────────────────────────────────────────────────────────
CSS = """
:root{
  --bg:#eef0fb; --fg:#252838; --mut:#7c8098; --line:rgba(120,110,200,.16);
  --card:rgba(255,255,255,.66); --acc:#7c5cff; --acc-bg:rgba(124,92,255,.10);
  --red:#e11d48; --red-bg:rgba(225,29,72,.10); --amber:#b45309; --amber-bg:rgba(217,119,6,.12);
  --green:#15803d; --green-bg:rgba(22,163,74,.12);
}
@media (prefers-color-scheme:dark){
  :root{--bg:#12142b;--fg:#eceaf8;--mut:#9a9dbb;--line:rgba(255,255,255,.10);
        --card:rgba(24,26,52,.66);--acc:#a78bfa;--acc-bg:rgba(124,92,255,.16);
        --red:#fda4af;--red-bg:rgba(244,63,94,.16);--amber:#fcd34d;--amber-bg:rgba(245,158,11,.16);
        --green:#86efac;--green-bg:rgba(34,197,94,.16);}
  body{background:linear-gradient(150deg,#12142b,#1a1030 55%,#0e1c33)}
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;color:var(--fg);
  background:linear-gradient(150deg,#eef0fb,#f7eef8 55%,#eaf6ff);
  background-attachment:fixed;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans Arabic",
              "Noto Naskh Arabic",Tahoma,"Geeza Pro",sans-serif;
  font-size:17px;line-height:1.85;
}
a{color:var(--acc);text-decoration:none;border-bottom:1px solid transparent}
a:hover{border-bottom-color:var(--acc)}

/* ── الهيكل ── */
.wrap{display:flex;min-height:100vh;align-items:flex-start}
nav{
  width:17rem;flex:none;position:sticky;top:0;height:100vh;overflow-y:auto;
  background:var(--card);backdrop-filter:blur(18px) saturate(1.3);
  -webkit-backdrop-filter:blur(18px) saturate(1.3);
  border-inline-end:1px solid var(--line);padding:1.25rem 1rem 3rem;
}
main{flex:1;min-width:0;padding:2rem clamp(1rem,4vw,3.5rem) 6rem}
.doc{max-width:46rem;margin:0 auto}

/* ── القائمة ── */
nav .brand{font-weight:800;font-size:1.05rem;margin-bottom:.15rem;line-height:1.5}
nav .sub{color:var(--mut);font-size:.78rem;margin-bottom:1.1rem}
nav h4{
  font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);
  margin:1.35rem 0 .4rem;font-weight:700;
}
nav a{display:block;padding:.28rem .5rem;border-radius:6px;font-size:.875rem;
      border-bottom:0;color:var(--fg);line-height:1.6}
nav a:hover{background:var(--acc-bg)}
nav a.on{background:var(--acc-bg);color:var(--acc);font-weight:700}
nav .filter{width:100%;padding:.45rem .6rem;margin-bottom:.5rem;border:1px solid var(--line);
            border-radius:8px;background:var(--bg);color:var(--fg);font:inherit;font-size:.85rem}

/* ── المحتوى ── */
h1{font-size:1.75rem;line-height:1.4;margin:0 0 1rem;font-weight:800}
h2{font-size:1.3rem;line-height:1.5;margin:2.4rem 0 .8rem;font-weight:800;
   padding-bottom:.35rem;border-bottom:1px solid var(--line)}
h3{font-size:1.08rem;margin:1.8rem 0 .5rem;font-weight:700}
h4{font-size:.98rem;margin:1.4rem 0 .4rem;font-weight:700;color:var(--mut)}
h5,h6{font-size:.92rem;margin:1.2rem 0 .3rem;font-weight:700;color:var(--mut)}
p{margin:.85rem 0}
hr{border:0;border-top:1px solid var(--line);margin:2.2rem 0}
ul,ol{margin:.85rem 0;padding-inline-start:1.4rem}
li{margin:.3rem 0}
li>ul,li>ol{margin:.25rem 0}
strong{font-weight:800}

blockquote{
  margin:1.2rem 0;padding:.85rem 1.1rem;background:var(--acc-bg);
  border-inline-start:3px solid var(--acc);border-radius:0 8px 8px 0;
}
blockquote p{margin:.4rem 0}

code{
  font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  font-size:.86em;background:var(--acc-bg);padding:.12em .38em;border-radius:4px;
  direction:ltr;unicode-bidi:embed;
}
pre{
  background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:.95rem 1.1rem;overflow-x:auto;margin:1.2rem 0;
}
pre code{background:none;padding:0;font-size:.82rem;line-height:1.7;display:block}

/* ── الجداول: بطاقات على الهاتف ── */
.tbl{overflow-x:auto;margin:1.2rem 0;border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{padding:.6rem .75rem;text-align:start;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--acc-bg);font-weight:800;font-size:.82rem;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--acc-bg)}

@media (max-width:760px){
  .wrap{display:block}
  nav{width:auto;height:auto;position:static;border-inline-end:0;
      border-bottom:1px solid var(--line)}
  main{padding:1.5rem 1rem 5rem}
  body{font-size:16.5px}
  h1{font-size:1.45rem} h2{font-size:1.18rem}

  /* الجدول → بطاقات مسمّاة، بلا تمرير أفقي */
  .tbl{overflow:visible;border:0}
  table,thead,tbody,tr,th,td{display:block;width:auto}
  thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
  tbody tr{border:1px solid var(--line);border-radius:10px;padding:.5rem .75rem;
           margin-bottom:.75rem;background:var(--card)}
  td{border:0;padding:.4rem 0}
  td::before{
    content:attr(data-label);display:block;font-size:.72rem;font-weight:800;
    color:var(--mut);margin-bottom:.1rem;
  }
  td:empty::before{content:none}
}

/* ── شريط علوي ثابت على الهاتف ── */
.topbar{display:none}
@media (max-width:760px){
  .topbar{
    display:flex;align-items:center;gap:.6rem;position:sticky;top:0;z-index:20;
    background:var(--card);backdrop-filter:blur(14px);
    -webkit-backdrop-filter:blur(14px);
    border-bottom:1px solid var(--line);
    padding:.6rem 1rem;margin:-1.5rem -1rem 1.2rem;
  }
  .topbar b{font-size:.9rem;flex:1}
  .topbar a{font-size:.8rem;white-space:nowrap}
}

/* ── فهرس الصفحة ── */
.toc{background:var(--card);backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:16px;
     padding:.85rem 1.1rem;margin:1.4rem 0;font-size:.88rem}
.toc b{display:block;margin-bottom:.4rem;font-size:.8rem;color:var(--mut)}
.toc a{display:inline-block;margin-inline-end:.9rem;line-height:2}
.toc .l3{padding-inline-start:1rem;color:var(--mut)}

/* ── الصفحة الرئيسية ── */
.hero{background:var(--card);backdrop-filter:blur(16px) saturate(1.3);
      -webkit-backdrop-filter:blur(16px) saturate(1.3);
      border:1px solid var(--line);border-radius:24px;
      padding:1.6rem;margin-bottom:1.8rem;
      box-shadow:0 2px 6px rgba(40,35,90,.06),0 14px 34px rgba(40,35,90,.10)}
.cta{display:inline-block;margin:.5rem 0 .3rem;padding:.75rem 1.5rem;border-radius:999px;
     background:linear-gradient(135deg,#7c5cff,#a78bfa);color:#fff !important;
     font-weight:700;border-bottom:0 !important;font-size:1rem;
     box-shadow:0 6px 18px rgba(124,92,255,.35)}
.cta:hover{filter:brightness(1.07)}
.hero h1{margin-bottom:.5rem}
.badge{display:inline-block;background:var(--acc-bg);color:var(--acc);
       border-radius:99px;padding:.15rem .7rem;font-size:.75rem;font-weight:700;
       margin-inline-end:.4rem;margin-bottom:.4rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(15rem,1fr));gap:.8rem;margin:1.2rem 0}
.gcard{background:var(--card);backdrop-filter:blur(10px);border:1px solid var(--line);
       border-radius:18px;padding:.9rem 1rem}
.gcard h3{margin:.1rem 0 .5rem;font-size:.98rem}
.gcard a{display:block;font-size:.86rem;padding:.18rem 0;border-bottom:0;line-height:1.6}
.warn{background:var(--red-bg);color:var(--red);border-inline-start:3px solid var(--red);
      padding:.7rem 1rem;border-radius:0 8px 8px 0;margin:1rem 0;font-size:.9rem}
.foot{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
      color:var(--mut);font-size:.8rem;text-align:center}
"""

PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<style>{css}</style>
</head>
<body>
<div class="wrap">
<nav>
  <div class="brand">نظام تشغيل الأكاديمية</div>
  <div class="sub">تنمية شخصية الطفل — ليست دعمًا مدرسيًا</div>
  <input class="filter" type="search" placeholder="ابحث في الملفات…" aria-label="بحث">
  {nav}
</nav>
<main>
  <div class="topbar"><b>☰ نظام التشغيل</b><a href="index.html">الفهرس</a></div>
  <div class="doc">
{body}
    <div class="foot">{foot}</div>
  </div>
</main>
</div>
<script>
// تصفية القائمة — بلا مكتبات
document.querySelectorAll('nav .filter').forEach(function(box){{
  box.addEventListener('input', function(){{
    var q = box.value.trim().toLowerCase();
    document.querySelectorAll('nav .navsec').forEach(function(sec){{
      var shown = 0;
      sec.querySelectorAll('a').forEach(function(a){{
        var hit = !q || a.textContent.toLowerCase().indexOf(q) > -1;
        a.style.display = hit ? '' : 'none';
        if (hit) shown++;
      }});
      sec.style.display = shown ? '' : 'none';
    }});
  }});
}});
</script>
</body>
</html>"""


def build_nav(current):
    parts = []
    for title, entries in GROUPS:
        rows = []
        for path, label in entries:
            href = out_name(path)
            on = ' class="on"' if path == current else ''
            rows.append(f'<a href="{href}"{on}>{html.escape(label)}</a>')
        parts.append(f'<div class="navsec"><h4>{html.escape(title)}</h4>{"".join(rows)}</div>')
    return '\n'.join(parts)


def out_name(path):
    """مسار الوثيقة → اسم ملف الخرج. الجذر يبقى في الجذر."""
    if path.endswith('.sql'):
        path = path + '.md'          # SQL يُعرض كصفحة موثّقة
    return path.replace('/', '--')[:-3] + '.html'


def render_toc(toc):
    if len(toc) < 3:
        return ''
    rows = []
    for level, sid, text in toc[:40]:
        cls = ' class="l3"' if level == 3 else ''
        rows.append(f'<a href="#{sid}"{cls}>{html.escape(text[:60])}</a>')
    return f'<div class="toc"><b>في هذه الصفحة</b>{"".join(rows)}</div>'


def source_of(path):
    """يقرأ الوثيقة. ملفات SQL تُغلَّف بـ markdown كي تُعرض ككود."""
    full = os.path.join(ROOT, path)
    with open(full, encoding='utf-8') as f:
        raw = f.read()
    if path.endswith('.sql'):
        title = os.path.basename(path)
        return f'# {title}\n\n> هذا مخطط قاعدة البيانات — يُنفَّذ في نظامك، لا يُقرأ هنا فقط.\n\n```sql\n{raw}\n```\n'
    return raw


def main():
    check = '--check' in sys.argv
    errors = []
    built = []
    stamp = datetime.date.today().isoformat()

    for path, label in [(p, l) for _, es in GROUPS for p, l in es]:
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            errors.append(f'مذكور في GROUPS وغير موجود: {path}')
            continue
        raw = source_of(path)
        body, toc = convert(raw)

        m = re.search(r'^#\s+(.*)$', raw, re.M)
        title = re.sub(r'[`*]', '', m.group(1)).strip() if m else label
        first_p = re.search(r'^([^\n#>|`\-].{20,150})$', raw, re.M)
        desc = re.sub(r'[`*#]', '', first_p.group(1)).strip() if first_p else label

        prev_next = nav_buttons(path)
        page = PAGE.format(
            title=html.escape(f'{title} — نظام تشغيل الأكاديمية'),
            desc=html.escape(desc[:150]),
            css=CSS,
            nav=build_nav(path),
            body=f'<h1>{html.escape(title)}</h1>\n<div class="badge">{html.escape(path)}</div>\n'
                 f'{render_toc(toc)}\n{body}\n{prev_next}',
            foot=f'مبني من المستودع — {stamp} • هذه وثائق تشغيل، لا تطبيق يعمل',
        )
        built.append((out_name(path), page))

    # الصفحة الرئيسية
    built.append(('index.html', index_page(stamp)))

    # تحقق: كل وثيقة في المستودع مغطّاة في الموقع؟
    covered = {p for _, es in GROUPS for p, _ in es} | SKIP
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in ('.git', 'site', 'tools', '__pycache__')]
        for fn in sorted(filenames):
            if fn.startswith('.'):
                continue
            if not (fn.endswith('.md') or fn.endswith('.sql')):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, '/')
            if rel.split('/')[0:2] and '/'.join(rel.split('/')[:2]) in SKIP_DIR:
                continue                      # لقطة مولّدة: ليست وثيقة
            if rel not in covered:
                errors.append(f'غير مغطّى في الموقع: {rel}')

    if errors:
        print('⚠️ مشاكل:')
        for e in errors:
            print('   ', e)
        if check:
            return 1

    if not check:
        os.makedirs(OUT, exist_ok=True)
        for name, content in built:
            with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
                f.write(content)
        # واجهة الدردشة تُنسخ كما هي: على استضافة ثابتة تعمل بوضع معاينة
        # بعينة بيانات من المستودع، وعلى جهازك بخادم حيّ تصير حقيقية.
        import shutil
        for f in ('chat.html', 'chat.css', 'chat.js'):
            shutil.copy(os.path.join(ROOT, 'ops', f), os.path.join(OUT, f))
    print(f'✅ {len(built)} صفحة → {os.path.relpath(OUT, ROOT)}/')
    return 0


def nav_buttons(path):
    flat = [(p, l) for _, es in GROUPS for p, l in es]
    idx = next((k for k, (p, _) in enumerate(flat) if p == path), None)
    if idx is None:
        return ''
    out = ['<hr><p style="display:flex;gap:1rem;flex-wrap:wrap;font-size:.88rem">']
    if idx > 0:
        p, l = flat[idx - 1]
        out.append(f'<a href="{out_name(p)}">→ السابق: {html.escape(l)}</a>')
    if idx < len(flat) - 1:
        p, l = flat[idx + 1]
        out.append(f'<a href="{out_name(p)}">التالي: {html.escape(l)} ←</a>')
    out.append('</p>')
    return ''.join(out)


def index_page(stamp):
    cards = []
    for title, entries in GROUPS:
        rows = ''.join(
            f'<a href="{out_name(p)}">{html.escape(l)}</a>' for p, l in entries)
        cards.append(f'<div class="gcard"><h3>{html.escape(title)}</h3>{rows}</div>')
    body = f"""
<div class="hero">
<h1>نظام تشغيل الأكاديمية</h1>
<p>أكاديمية أونلاين <strong>لتنمية شخصية الطفل</strong> — علميًا واجتماعيًا، والثقة، وحرية التعبير.
<strong>ليست دعمًا مدرسيًا.</strong> مؤسسها واحد، وهو المبرمج الذي بنى نظاميها.</p>
<div class="warn"><strong>القاعدة الذهبية:</strong> الذكاء الاصطناعي يعمل، وأنت تقرّر.
لا شيء يخرج لولي أمر أو يُنشر على منصة بدونك.</div>
<p><span class="badge">46 ملفًا</span><span class="badge">8 أنظمة تشغيل</span>
<span class="badge">14 وكيلًا</span><span class="badge">11 قاعدة</span>
<span class="badge">85/85 اختبارًا</span></p>
<p><a class="cta" href="chat.html">💬 افتح واجهة الدردشة — معاينة حيّة بعينة بيانات</a></p>
<p style="font-size:.85rem;color:var(--mut)">على الاستضافة الثابتة تعمل الواجهة بوضع
معاينة بعينة من بيانات المستودع. على جهازك تشغّل الخادم الحي:
<code>python3 ops/server.py</code> ثم تفتح نفس الشاشة فتصير حقيقية.</p>
</div>

<h2>الساعة الأولى</h2>
<p>لا تقرأ كل شيء. ابدأ من <a href="{out_name('START-HERE.md')}"><strong>START-HERE</strong></a> —
خمس خطوات مرتّبة. وأعلى خطوة مردودًا اليوم:
<a href="{out_name('marketing/first-reply-playbook.md')}"><strong>دليل الرد الأول</strong></a> —
8 ردود جاهزة تعمل من هاتفك بلا وكيل ولا كود.</p>

<h2>كل الملفات</h2>
<div class="grid">{''.join(cards)}</div>

<h2>ماذا ينقص قبل التشغيل</h2>
<p>ستة قرارات لم تُحسم بعد، وهي تعطّل البناء —
في <a href="{out_name('OPEN-QUESTIONS.md')}"><strong>OPEN-QUESTIONS</strong></a>.
أهمها: نسبة الأستاذ على المحصَّل أم المستحق.</p>

<h2>هذا الموقع والواجهة الحيّة</h2>
<p>هذه وثائق تشغيل تُقرأ، وفوقها زر الواجهة: messenger زجاجي بكل الوكلاء
والموافقات والذاكرة والبحث. على الاستضافة الثابتة يفتح بوضع معاينة بعينة
بيانات؛ والتشغيل الحقيقي على جهازك: <code>python3 ops/server.py</code> —
خادم بايثون بلا تبعيات، بقاعدة SQLite وتدقيق لا يُمحى.</p>
"""
    return PAGE.format(
        title=html.escape('نظام تشغيل الأكاديمية — AI Workforce OS'),
        desc=html.escape('وثائق تشغيل أكاديمية أونلاين لتنمية شخصية الطفل: 14 وكيلًا، 8 أنظمة تشغيل، 11 قاعدة'),
        css=CSS, nav=build_nav(None), body=body,
        foot=f'مبني من المستودع — {stamp} • هذه وثائق تشغيل، لا تطبيق يعمل')


if __name__ == '__main__':
    sys.exit(main())
