/* مركز العمليات — طرف الدردشة. بلا تبعيات، بلا خطوط خارجية. */
'use strict';
const $ = s => document.querySelector(s);
const app = $('#app');
let CUR = null;            // المحادثة المفتوحة
let LAST = {};             // آخر معرّف رسالة لكل محادثة
let READ = {};             // ما قرأته — للشارة
let THREADS = [];
let POLL = null;

const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt != null) n.textContent = txt;
  return n;
};
const hhmm = iso => (iso || '').slice(11, 16);
/* أيقونة متجهية من الطقم — لا إيموجي في الواجهة */
const ic = n => {
  const d = document.createElement('span');
  d.className = 'icw';
  d.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  return d;
};
const eli = (tag, cls, icon, txt) => {
  const n = el(tag, cls);
  n.append(ic(icon), document.createTextNode(txt));
  return n;
};
/* أفاتار حرفي (Monogram) كسلاك وجوجل: حروف الاسم لا رسم إيموجي */
const mono = n => {
  const w = (n || '').trim().split(/\s+/).map(x => x.replace(/^ال/, '') || x);
  return w.length > 1 ? w[0][0] + w[1][0] : (w[0] || '؟').slice(0, 2);
};
const dzd = n => (n == null ? '—' : Number(n).toLocaleString('ar-DZ')) + ' دج';

class NoServer extends Error {}
let DEMO = false;

async function api(path, opts) {
  if (DEMO) return demoApi(path, opts);
  try {
    const r = await fetch(path, opts);
    if (!r.ok && (r.status === 404 || r.status === 501)) throw new NoServer();
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.status);
    return j;
  } catch (e) {
    // استضافة ثابتة (فيرسل) بلا خادم: وضع معاينة ببيانات عينة — لا اختلاق في الوضع الحي
    if (e instanceof NoServer || e instanceof TypeError) {
      DEMO = true;
      demoBanner();
      return demoApi(path, opts);
    }
    throw e;
  }
}

/* ── وضع المعاينة: عينة من بيانات المستودع حين لا يوجد خادم حي ── */
function demoBanner() {
  if (document.querySelector('.demo-flag')) return;
  document.body.classList.add('demo');
  const d = el('div', 'demo-flag');
  d.append(ic('eye'), document.createTextNode(
    ' معاينة بعينة بيانات — لا خادم حي هنا. الحيّ على جهازك: python3 ops/server.py'));
  document.body.prepend(d);
}
const _now = () => new Date().toISOString();
const DEMO_THREADS = [
  {id: 'head_of_ops', name: 'رئيس العمليات', emoji: '🧭', grad: 'g1',
   role: 'التوزيع والمتابعة والتصعيد', last_preview: 'شغّلتُ أربعة وكلاء…',
   last_at: _now(), pending_count: 2, last_id: 7, revoked_at: null},
  {id: 'accountant', name: 'المحاسب', emoji: '🧮', grad: 'g2',
   role: 'حقيقة المال', last_preview: 'طابقتُ المرجعين…',
   last_at: _now(), pending_count: 1, last_id: 5, revoked_at: null},
  {id: 'marketing', name: 'خبير التسويق', emoji: '📣', grad: 'g3',
   role: 'الزاوية المعتمدة', last_preview: 'القمع: 27 مهتمًا…',
   last_at: _now(), pending_count: 0, last_id: 4, revoked_at: null},
  {id: 'lead_nurturer', name: 'متابع المهتمين', emoji: '💬', grad: 'g4',
   role: 'الرد الأول', last_preview: '12 مهتمًا لم يُردَّ عليهم…',
   last_at: _now(), pending_count: 0, last_id: 3, revoked_at: null},
];
const DEMO_MSGS = {
  head_of_ops: [
    {id: 1, sender: 'user', kind: 'text', payload: {text: 'الملخص'}, created_at: _now()},
    {id: 2, sender: 'agent', kind: 'brief', created_at: _now(), payload: {
      date: '2026-11-04', overdue_count: 2,
      sections: {
        happened: [{item: 'طابق المحاسب المرجعين', detail: 'فرق صافي 500 دج تحت 6 حالات'}],
        needs_decision: [{reason: 'أساس مستحق الأستاذ', action_type: 'correct_payment', days_open: 4}],
        broken: []},
      memory: {open_decisions: [{subject: 'نسبة الأستاذ: محصَّل أم مستحق؟'}],
               recent_lessons: [{subject: 'لا وعد بعلاج'}]}}},
  ],
  accountant: [
    {id: 3, sender: 'user', kind: 'text', payload: {text: 'المطابقة'}, created_at: _now()},
    {id: 4, sender: 'agent', kind: 'cases', created_at: _now(), payload: {
      net_difference: 500, case_count: 6,
      totals: {accounting: {count: 11, sum: 34500}, parents: {count: 11, sum: 34000}},
      arrears: [{alias_name: 'ط-نور'}],
      cases: [{risk: 'red', kind: 'في المحاسبة دون الأولياء', note: 'S-112 — 500 دج'},
              {risk: 'yellow', kind: 'مبلغ مختلف', note: 'دفعة 2700 مقابل 2500'}]}},
    {id: 5, sender: 'agent', kind: 'proposal', created_at: _now(), payload: {
      id: 12, action_type: 'correct_payment', risk: 'yellow',
      reason: 'فرق 500 دج في دفعة S-112', days_open: 4, overdue: true,
      status: 'pending', manual_only: false}},
  ],
  marketing: [
    {id: 6, sender: 'agent', kind: 'websearch', created_at: _now(), payload: {
      title: 'بحث في الإنترنت عن «أنشطة ثقة للأطفال» — المزوّد: ddgs (كاش)',
      items: [{title: 'ألعاب الثقة للنشاط الجماعي', url: 'https://example.test/1',
               snippet: 'مقتطف توضيحي في وضع المعاينة.'}],
      note: 'قراءة فقط — هذه اقتراحات لك: لا مراسلة، لا نشر، ولا قرار بدونك.'}},
  ],
  lead_nurturer: [
    {id: 7, sender: 'agent', kind: 'leads', created_at: _now(), payload: {
      never_replied: 12, total_leads: 27, rate_pct: 44.4,
      queue: [{alias: 'م-سارة', topic: 'فرط الحركة', days_waiting: 6, overdue: true,
               suggested_reply: 'أهلًا سارة. حصة تعريفية مجانية موجودة — تشاهدون بعينكم.',
               has_placeholder: false}]}},
  ],
};
let _demoId = 100;
function demoApi(path, opts) {
  const body = opts && opts.body ? JSON.parse(opts.body) : {};
  if (path.startsWith('/api/threads')) return {threads: DEMO_THREADS};
  if (path.startsWith('/api/messages')) {
    const t = (path.match(/thread=([\w-]+)/) || [])[1];
    const since = Number((path.match(/since=(\d+)/) || [])[1] || 0);
    const msgs = (DEMO_MSGS[t] || []).filter(m => m.id > since);
    return {messages: msgs};
  }
  if (path === '/api/chat') {
    const t = body.thread, q = body.text || '';
    const card = (kind, payload) => ({messages: [{id: ++_demoId, thread: t,
      sender: 'agent', kind, created_at: _now(), payload}]});
    const src = (DEMO_MSGS[t] || []).find(m => m.kind !== 'text');
    if (/مطابق|مال|دفعات/.test(q) && t === 'accountant' || /مطابق/.test(q))
      return card('cases', (DEMO_MSGS.accountant[1] || {}).payload || {});
    if (/ملخص|بريف/.test(q))
      return card('brief', (DEMO_MSGS.head_of_ops[1] || {}).payload || {});
    if (/قمع/.test(q))
      return card('funnel', {stages: [
        {stage: 'مهتم', count: 27}, {stage: 'حجز', count: 11},
        {stage: 'حضر', count: 8}, {stage: 'سجّل', count: 6}],
        priorities: [{rank: 1, issue: '12 مهتمًا بلا رد', action: 'الرد الأول اليوم'}],
        routed: []});
    if (/ردود|مهتم/.test(q))
      return card('leads', (DEMO_MSGS.lead_nurturer[0] || {}).payload || {});
    if (/ابحث|دور/.test(q))
      return card('websearch', (DEMO_MSGS.marketing[0] || {}).payload || {});
    if (/تذكر|ذاكر/.test(q))
      return card('memory', {title: 'عينة من الذاكرة', items: [
        {kind: 'lesson', kind_ar: 'درس', subject: 'لا وعد بعلاج',
         text: 'أي نص يوحي بعلاج فرط الحركة يُرفض.', source: 'memory/lessons-seed.md',
         created_at: _now(), score: 0.8}]});
    if (src) return card(src.kind, src.payload);
    return {messages: [{id: ++_demoId, thread: t, sender: 'agent',
      kind: 'text', created_at: _now(),
      payload: {text: 'وضع المعاينة: لا خادم حي هنا — ما تراه عينة من بيانات '
                + 'المستودع. جرّب: «المطابقة» · «الملخص» · «القمع» · «الردود» · '
                + '«ابحث عن …». وعلى جهازك: python3 ops/server.py ثم افتح '
                + 'نفس الشاشة فتصير حقيقية.'}}]};
  }
  return {messages: [{id: ++_demoId, thread: body.thread, sender: 'agent',
    kind: 'text', created_at: _now(),
    payload: {text: 'سُجّل في المعاينة فقط — لا تنفيذ ولا تدقيق حي هنا.'}}]};
}
const post = (path, body) => api(path, {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify(body),
});

/* ── جهات الاتصال ── */
async function loadThreads() {
  const d = await api('/api/threads');
  THREADS = d.threads;
  const box = $('#threads');
  box.textContent = '';
  const pend = THREADS.reduce((s, t) => s + t.pending_count, 0);
  $('#sub').textContent = `${THREADS.length} وكلاء يعملون عندك · ${pend} بانتظار قرارك`;
  const pill = $('#pend-pill');
  pill.textContent = '';
  pill.append(ic(pend > 0 ? 'clock' : 'checkc'),
    document.createTextNode(pend > 0 ? ` ${pend} بانتظار قرارك` : ' لا معلّق اليوم'));
  pill.onclick = () => openThread('head_of_ops');
  const row = $('#agent-row');
  row.textContent = '';
  for (const t of THREADS) {
    const cell = el('button', 'agent-cell');
    cell.title = t.name;
    const orb = el('span', 'agent-orb ' + t.grad, mono(t.name));
    const unread = t.last_id - (READ[t.id] || 0);
    if (unread > 0 && t.id !== CUR) orb.append(el('span', 'badge', String(unread)));
    if (t.revoked_at) orb.classList.add('off');
    cell.append(orb, el('span', 'agent-name', t.name));
    cell.onclick = () => openThread(t.id);
    row.append(cell);
  }
  for (const t of THREADS) {
    const unread0 = t.last_id - (READ[t.id] || 0);
    const row = el('div', 't-row' + (t.revoked_at ? ' revoked' : '')
      + (unread0 > 0 ? ' unred' : ''));
    row.setAttribute('role', 'listitem');
    row.dataset.id = t.id;
    const av = el('span', 'avatar ' + t.grad, mono(t.name));
    const tx = el('div', 'tx');
    const nm = el('div', 'nm');
    nm.append(el('b', null, t.name), el('time', null, hhmm(t.last_at)));
    tx.append(nm, el('div', 'pv', t.last_preview));
    row.append(av, tx);
    const unread = t.last_id - (READ[t.id] || 0);
    if (unread > 0 && t.id !== CUR) row.append(el('span', 'badge', String(unread)));
    row.onclick = () => openThread(t.id);
    box.append(row);
  }
}

/* ── فتح محادثة ── */
async function openThread(id) {
  CUR = id;
  const t = THREADS.find(x => x.id === id) || {};
  app.classList.add('show-chat');
  $('#pane-chat').classList.remove('hidden');
  $('#head-av').textContent = mono(t.name || '؟');
  $('#head-av').className = 'avatar sm ' + (t.grad || 'g1');
  $('#head-name').textContent = t.name || id;
  $('#head-status').textContent = t.revoked_at
    ? 'موقوف منذ ' + t.revoked_at.slice(0, 16).replace('T', ' ')
    : (t.role || '');
  $('#revoke-btn').textContent = '';
    $('#revoke-btn').append(ic(t.revoked_at ? 'play' : 'ban'));
  $('#msgs').textContent = '';
  LAST[id] = 0;
  const d = await api('/api/messages?thread=' + id);
  append(d.messages);
  READ[id] = LAST[id];
  chips();
  loadThreads();
}

function append(msgs) {
  const box = $('#msgs');
  for (const m of msgs) {
    box.append(render(m));
    LAST[m.thread] = Math.max(LAST[m.thread] || 0, m.id);
  }
  regroup(box);
  box.scrollTop = box.scrollHeight;
}

/* لغة تلجرام: الذيل لآخر رسالة في السطر فقط، والزوايا القريبة 6px للمجمعة */
function regroup(box) {
  const kids = [...box.children];
  const sideOf = k => k.classList.contains('sys') ? null
    : (k.classList.contains('me') ? 'me' : 'ag');
  for (let i = 0; i < kids.length; i++) {
    const side = sideOf(kids[i]);
    if (!side) continue;               /* شريحة التاريخ تقطع السطر */
    kids[i].classList.toggle('gnx', sideOf(kids[i + 1]) === side);
    kids[i].classList.toggle('gpv', sideOf(kids[i - 1]) === side);
  }
}

/* ── رسم الرسائل حسب نوعها ── */
function render(m) {
  const wrap = el('div', 'msg ' + (m.sender === 'user' ? 'me'
    : m.sender === 'system' ? 'sys' : 'ag'));
  const b = el('div', 'bub');
  KIND[m.kind] ? KIND[m.kind](b, m.payload, m) : (b.textContent = m.payload.text || m.kind);
  /* الوقت — والصحّان لحظيًا — داخل الفقاعة كما في التطبيقات الحقيقية */
  const tm = el('span', 'time', hhmm(m.created_at) + (m.sender === 'user' ? ' ' : ''));
  if (m.sender === 'user') tm.append(ic('ticks'));
  b.append(tm);
  wrap.append(b);
  return wrap;
}

const kv = (b, k, v) => {
  const r = el('div', 'kv');
  r.append(el('span', null, k), el('b', null, v));
  b.append(r);
};
const riskChip = r => {
  const s2 = el('span', 'risk ' + (r || 'green'));
  s2.append(el('span', 'dot ' + (r || 'green')),
    document.createTextNode(r === 'red' ? ' حرج' : r === 'yellow' ? ' انتبه' : ' سليم'));
  return s2;
};

const KIND = {
  text(b, p) {
    b.append(el('div', null, p.text || ''));
    if (p.manual) {
      b.append(eli('div', 'warnbox', 'alert', ' إجراء موجّه لإنسان — لا يوجد له تنفيذ آلي، '
        + 'ولن يوجد. التنفيذ يدك.'));
    }
    if (p.draft) {
      const d = el('div', 'draft', p.draft);
      const cp = eli('button', 'b-cp', 'copy', ' نسخ النص');
      cp.onclick = () => navigator.clipboard?.writeText(p.draft)
        .then(() => { cp.textContent = ''; cp.append(ic('checkc'), document.createTextNode(' نُسخ')); });
      const acts = el('div', 'acts'); acts.append(cp); b.append(d, acts);
    }
  },
  result(b, p) { KIND.text(b, p); },

  brief(b, p) {
    b.append(eli('h4', null, 'sunrise', ` ملخص ${p.date} — متأخر ${p.overdue_count}`));
    const S = p.sections || {};
    const sec = (title, rows, fmt) => {
      b.append(el('h4', null, title));
      if (!rows || !rows.length) { b.append(el('div', 'case', 'لا شيء.')); return; }
      for (const r of rows) b.append(el('div', 'case', fmt(r)));
    };
    sec('ما حدث', S.happened, r => `• ${r.item}${r.detail ? ' — ' + r.detail : ''}`);
    sec('يحتاج قرارك', S.needs_decision,
      r => `• ${r.reason} (${r.action_type}) — مفتوح ${r.days_open} يومًا`);
    sec('ما تعطّل', S.broken, r => `• ${r.component}: ${r.error}`);
    if (p.missing && p.missing.length) {
      b.append(el('h4', null, 'لا أعرف'));
      for (const x of p.missing)
        b.append(el('div', 'case', `• ${x.field}: ${x.question}`));
    }
    const M = p.memory;
    if (M) {
      if (M.open_decisions && M.open_decisions.length) {
        b.append(eli('h4', null, 'brain',
          ` على كتفك ${M.open_decisions.length} قرارات مفتوحة`));
        for (const d of M.open_decisions)
          b.append(el('div', 'case', `• ${d.subject} — اكتب «قررت …» لتزيحه`));
      }
      for (const pr of M.promises || [])
        b.append(eli('div', 'case', 'users', ` وعد محفوظ: ${pr.text}`));
      for (const l of M.recent_lessons || [])
        b.append(eli('div', 'case', 'pin', ` درس: ${l.subject}`));
    }
  },

  cases(b, p) {
    b.append(eli('h4', null, 'cash',
      ` المطابقة — فرق صافي ${dzd(p.net_difference)} تحت ${p.case_count} حالات`));
    kv(b, 'نظام المحاسبة', `${p.totals.accounting.count} دفعة · ${dzd(p.totals.accounting.sum)}`);
    kv(b, 'نظام الأولياء', `${p.totals.parents.count} دفعة · ${dzd(p.totals.parents.sum)}`);
    kv(b, 'متأخرات', p.arrears && p.arrears.length
      ? p.arrears.map(a => a.alias_name).join('، ') : 'لا شيء');
    for (const c of p.cases || []) {
      const d = el('div', 'case');
      d.append(el('span', 'dot ' + c.risk), el('span', null,
        `${c.kind}: ${c.note}`));
      b.append(d);
    }
  },

  teacher(b, p) {
    b.append(eli('h4', null, 'users', ` مستند ${p.alias || p.teacher_id} — ${p.group || ''}`));
    kv(b, 'حصص مُقدَّمة', String(p.sessions_delivered ?? '—'));
    kv(b, 'تجارب مجانية', String(p.free_trials ?? '—'));
    kv(b, 'نسبة الأستاذ', p.share_pct == null ? '—' : p.share_pct + '%');
    kv(b, 'الأساس', p.basis || 'غير محسوم');
    kv(b, 'المستحق', p.amount_due == null ? 'لا أحسبه بلا أساس' : dzd(p.amount_due));
    if (p.basis_memory) {
      b.append(eli('div', 'memnote', 'brain',
        ` الأساس من قرارك المحفوظ (#${p.basis_memory.id}): ${p.basis_memory.text}`));
    }
    if (p.candidates && p.candidates.length) {
      b.append(el('h4', null, `الأسس الثلاثة — الفارق ${dzd(p.spread_dzd)}`));
      for (const c of p.candidates)
        b.append(el('div', 'case', `• ${c.label}: ${dzd(c.amount)}`));
      b.append(el('div', 'warnbox', 'أي أساس أعتمد؟ قرارك أنت — حتى تحسمه '
        + 'أقول لا أعرف ولا أخترق رقمًا.'));
    }
  },

  funnel(b, p) {
    b.append(eli('h4', null, 'mega', ' قمع التسويق'));
    const top = (p.stages[0] || {}).count || 1;
    for (const s of p.stages || []) {
      const row = el('div', 'stage');
      row.append(el('span', null, `${s.stage} · ${s.count}`));
      const bar = el('span', 'bar'); const i = el('i');
      i.style.width = Math.round(100 * s.count / top) + '%';
      bar.append(i); row.append(bar);
      row.append(el('span', null, (s.rate_pct == null ? '' : s.rate_pct + '%')));
      b.append(row);
    }
    for (const pr of p.priorities || [])
      b.append(el('div', 'case', `${pr.rank}. ${pr.issue} — ${pr.action}`));
    for (const r of p.routed || [])
      b.append(el('div', 'case', `↪ ${r.issue} → ${r.route_to}`));
  },

  leads(b, p) {
    b.append(eli('h4', null, 'chat',
      ` ${p.never_replied} من ${p.total_leads} (${p.rate_pct}%) لم يُردَّ عليهم`));
    for (const q of (p.queue || []).slice(0, 5)) {
      const d = el('div', 'case');
      d.append(el('span', 'dot ' + (q.overdue ? 'red' : 'yellow')),
        el('span', null, `${q.alias || q.lead_id} · ${q.topic} · ينتظر ${q.days_waiting} يومًا`));
      b.append(d);
      b.append(el('div', 'draft', q.suggested_reply
        + (q.has_placeholder ? '\n【تحقّق】 فيها موضع تأكّد منه قبل الإرسال.' : '')));
    }
    b.append(el('div', 'warnbox', 'الإرسال لولي أمر بدون إذنك: لا يوجد له تنفيذ '
      + 'في هذا النظام. المسوّدات من دليل الرد الأول — لا تأليف.'));
  },

  proposal(b, p, m) {
    const head = el('div', null);
    head.append(el('b', null, `#${p.id} ${p.action_type}`), riskChip(p.risk));
    b.append(head);
    if (p.reason) b.append(el('div', null, p.reason));
    if (p.source_ref) b.append(el('div', 'case', 'المرجع: ' + p.source_ref));
    b.append(el('div', 'case', `مفتوح منذ ${p.days_open} يومًا`
      + (p.overdue ? ' — متأخر عن إيقاعك (3 أيام)' : '')));
    if (p.manual_only) {
      b.append(eli('div', 'warnbox', 'alert', ' موافقتك تُسجَّل ولا تُنفَّذ: لا يوجد كود ينشر '
        + 'أو يراسل أولياء الأمور. التنفيذ من حسابك.'));
    }
    if (p.memory_note) b.append(eli('div', 'memnote', 'brain', ' ' + p.memory_note));
    if (p.payload && p.payload.text) b.append(el('div', 'draft', p.payload.text));
    if (p.executed || p.status !== 'pending') {
      b.append(el('div', 'done-tag', 'حُسم: ' + p.status
        + (p.executed ? ' · نُفّذ' : '')));
      return;
    }
    const acts = el('div', 'acts');
    const ok = eli('button', 'b-ok', 'check', ' موافقة');
    const no = eli('button', 'b-no', 'x', ' رفض');
    ok.onclick = () => act(m.thread, {op: 'approve', id: p.id}, acts);
    no.onclick = () => askReason(m.thread, p.id, acts);
    acts.append(ok, no);
    b.append(acts);
  },

  memory(b, p) {
    b.append(eli('h4', null, 'brain', ' ' + (p.title || 'الذاكرة')));
    for (const it of p.items || []) {
      const d = el('div', 'case');
      d.append(el('span', 'mchip ' + it.kind, it.kind_ar || it.kind));
      d.append(el('b', null, ' ' + it.subject + ' '));
      d.append(el('span', null, '— ' + it.text));
      b.append(d);
      b.append(el('div', 'msrc',
        `${it.source || ''} · ${hhmm(it.created_at)} · صلة ${it.score ?? ''}`
        + (it.superseded_by ? ' · مُبطَلة' : '')));
    }
  },

  websearch(b, p) {
    b.append(eli('h4', null, 'globe', ' ' + (p.title || 'بحث في الإنترنت')));
    for (const it of p.items || []) {
      const d = el('div', 'case');
      const a = document.createElement('a');
      a.href = it.url; a.target = '_blank'; a.rel = 'noopener';
      a.textContent = it.title || it.url;
      d.append(a);
      if (it.snippet) d.append(el('div', 'msrc', it.snippet));
      b.append(d);
    }
    if (p.note) b.append(eli('div', 'msrc', 'scale', ' ' + p.note));
  },

  audit(b, p) {
    b.append(eli('h4', null, 'file', ' آخر السجل — لا يُمحى ولا يُعدَّل'));
    for (const r of p.rows || [])
      b.append(el('div', 'case',
        `${hhmm(r.ts)} · ${r.agent} · ${r.action} · ${r.outcome}`
        + (r.note ? ' — ' + r.note : '')));
  },
};

/* ── أفعال الفقاعات ── */
async function act(thread, body, actsEl) {
  for (const x of actsEl.querySelectorAll('button')) x.disabled = true;
  const d = await post('/api/chat/action', {thread, ...body});
  append(d.messages);
  loadThreads();
}
function askReason(thread, id, actsEl) {
  const box = el('div', 'reason-in');
  const inp = el('input'); inp.placeholder = 'السبب؟ (إلزامي)';
  const go = el('button', 'b-no', 'رفض');
  go.onclick = () => {
    if (!inp.value.trim()) { inp.focus(); return; }
    act(thread, {op: 'reject', id, reason: inp.value.trim()}, actsEl);
  };
  box.append(inp, go);
  actsEl.textContent = '';
  actsEl.append(box);
  inp.focus();
}

/* ── الأزرار السريعة ── */
const CHIPS = {
  head_of_ops: ['شغّل الوكلاء', 'الملخص', 'ما المعلّق؟', 'السجل', 'مساعدة'],
  accountant: ['المطابقة', 'مستند T-1', 'مستند T-2', 'ما المعلّق؟'],
  marketing: ['القمع', 'ما المعلّق؟'],
  lead_nurturer: ['الردود', 'ما المعلّق؟'],
};
const CHIP_ICON = {
  'شغّل الوكلاء': 'zap', 'الملخص': 'sunrise', 'ما المعلّق؟': 'clock', 'السجل': 'file',
  'مساعدة': 'help', 'المطابقة': 'cash', 'مستند T-1': 'file', 'مستند T-2': 'file',
  'القمع': 'mega', 'الردود': 'chat',
};
function chips() {
  const box = $('#chips');
  box.textContent = '';
  for (const c of (CHIPS[CUR] || [])) {
    const b = eli('button', null, CHIP_ICON[c] || 'chat', ' ' + c);
    b.onclick = () => send(c);
    box.append(b);
  }
}

/* ── الإرسال ── */
async function send(text) {
  if (!text || !CUR) return;
  $('#inp').value = '';
  const me = {id: 0, thread: CUR, sender: 'user', kind: 'text',
    payload: {text}, created_at: new Date().toISOString()};
  append([me]);
  const d = await post('/api/chat', {thread: CUR, text});
  append(d.messages);
  READ[CUR] = LAST[CUR];
  loadThreads();
}

$('#composer').addEventListener('submit', e => {
  e.preventDefault();
  send($('#inp').value.trim());
});
$('#back').onclick = () => {
  app.classList.remove('show-chat');
  CUR = null;
  loadThreads();
};
$('#revoke-btn').onclick = async () => {
  const t = THREADS.find(x => x.id === CUR);
  if (!t) return;
  const op = t.revoked_at ? 'restore' : 'revoke';
  if (!confirm(op === 'revoke'
    ? `توقف ${t.name} الآن؟ لن يقترح شيئًا حتى تعيده.`
    : `تعيد ${t.name} إلى العمل؟`)) return;
  const d = await post('/api/chat/action', {thread: CUR, op, agent: CUR});
  append(d.messages);
  openThread(CUR);
};

/* ── نبض: رسائل جديدة + شارات ── */
setInterval(async () => {
  if (CUR) {
    const d = await api(`/api/messages?thread=${CUR}&since=${LAST[CUR] || 0}`);
    if (d.messages.length) { append(d.messages); READ[CUR] = LAST[CUR]; }
  }
  loadThreads();
}, 3000);

/* ── ليلي / نهاري — محفوظ في المتصفح، ويبدأ من تفضيل النظام ── */
const _themeBtn = $('#theme-btn');
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('ops-theme-v2', t); } catch (e) { /* خاص */ }
  _themeBtn.textContent = '';
  _themeBtn.append(ic(t === 'dark' ? 'sun' : 'moon'));
  const mt = document.querySelector('meta[name="theme-color"]');
  if (mt) mt.content = t === 'dark' ? '#12142b' : '#eef0fb';
}
let _savedTheme = null;
try { _savedTheme = localStorage.getItem('ops-theme-v2'); } catch (e) { /* خاص */ }
setTheme(_savedTheme || 'light');   // الـ pastel هو وجه النظام؛ الليلي بزرّه
_themeBtn.onclick = () =>
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

loadThreads();
