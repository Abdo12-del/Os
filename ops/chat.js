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
const dzd = n => (n == null ? '—' : Number(n).toLocaleString('ar-DZ')) + ' دج';

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
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
  for (const t of THREADS) {
    const row = el('div', 't-row' + (t.revoked_at ? ' revoked' : ''));
    row.setAttribute('role', 'listitem');
    row.dataset.id = t.id;
    const av = el('span', 'avatar ' + t.grad, t.emoji);
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
  $('#head-av').textContent = t.emoji || '🧭';
  $('#head-av').className = 'avatar sm ' + (t.grad || 'g1');
  $('#head-name').textContent = t.name || id;
  $('#head-status').textContent = t.revoked_at
    ? '⛔ موقوف منذ ' + t.revoked_at.slice(0, 16).replace('T', ' ')
    : (t.role || '');
  $('#revoke-btn').textContent = t.revoked_at ? '▶️' : '⛔';
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
  box.scrollTop = box.scrollHeight;
}

/* ── رسم الرسائل حسب نوعها ── */
function render(m) {
  const wrap = el('div', 'msg ' + (m.sender === 'user' ? 'me'
    : m.sender === 'system' ? 'sys' : 'ag'));
  if (m.sender === 'agent') {
    const t = THREADS.find(x => x.id === m.thread) || {};
    wrap.append(el('span', 'avatar ' + (t.grad || 'g1'), t.emoji || '🧭'));
  }
  const b = el('div', 'bub');
  KIND[m.kind] ? KIND[m.kind](b, m.payload, m) : (b.textContent = m.payload.text || m.kind);
  b.append(el('span', 'time', hhmm(m.created_at)));
  wrap.append(b);
  return wrap;
}

const kv = (b, k, v) => {
  const r = el('div', 'kv');
  r.append(el('span', null, k), el('b', null, v));
  b.append(r);
};
const riskChip = r => el('span', 'risk ' + (r || 'green'),
  r === 'red' ? '🔴 حرج' : r === 'yellow' ? '🟡 انتبه' : '🟢 سليم');

const KIND = {
  text(b, p) {
    b.append(el('div', null, p.text || ''));
    if (p.manual) {
      b.append(el('div', 'warnbox', '⚠️ إجراء موجّه لإنسان — لا يوجد له تنفيذ آلي، '
        + 'ولن يوجد. التنفيذ يدك.'));
    }
    if (p.draft) {
      const d = el('div', 'draft', p.draft);
      const cp = el('button', 'b-cp', '📋 انسخ النص');
      cp.onclick = () => navigator.clipboard?.writeText(p.draft)
        .then(() => cp.textContent = '✅ نُسخ');
      const acts = el('div', 'acts'); acts.append(cp); b.append(d, acts);
    }
  },
  result(b, p) { KIND.text(b, p); },

  brief(b, p) {
    b.append(el('h4', null, `🌅 ملخص ${p.date} — متأخر ${p.overdue_count}`));
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
        b.append(el('h4', null,
          `🧠 على كتفك ${M.open_decisions.length} قرارات مفتوحة`));
        for (const d of M.open_decisions)
          b.append(el('div', 'case', `• ${d.subject} — اكتب «قررت …» لتزيحه`));
      }
      for (const pr of M.promises || [])
        b.append(el('div', 'case', `🤝 وعد محفوظ: ${pr.text}`));
      for (const l of M.recent_lessons || [])
        b.append(el('div', 'case', `📌 درس: ${l.subject}`));
    }
  },

  cases(b, p) {
    b.append(el('h4', null,
      `💰 المطابقة — فرق صافي ${dzd(p.net_difference)} تحت ${p.case_count} حالات`));
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
    b.append(el('h4', null, `🧑‍🏫 مستند ${p.alias || p.teacher_id} — ${p.group || ''}`));
    kv(b, 'حصص مُقدَّمة', String(p.sessions_delivered ?? '—'));
    kv(b, 'تجارب مجانية', String(p.free_trials ?? '—'));
    kv(b, 'نسبة الأستاذ', p.share_pct == null ? '—' : p.share_pct + '%');
    kv(b, 'الأساس', p.basis || '⚠️ غير محسوم');
    kv(b, 'المستحق', p.amount_due == null ? 'لا أحسبه بلا أساس' : dzd(p.amount_due));
    if (p.basis_memory) {
      b.append(el('div', 'memnote',
        `🧠 الأساس من قرارك المحفوظ (#${p.basis_memory.id}): ${p.basis_memory.text}`));
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
    b.append(el('h4', null, '📣 قمع التسويق'));
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
    b.append(el('h4', null,
      `💬 ${p.never_replied} من ${p.total_leads} (${p.rate_pct}%) لم يُردَّ عليهم`));
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
      b.append(el('div', 'warnbox', '⚠️ موافقتك تُسجَّل ولا تُنفَّذ: لا يوجد كود ينشر '
        + 'أو يراسل أولياء الأمور. التنفيذ من حسابك.'));
    }
    if (p.memory_note) b.append(el('div', 'memnote', '🧠 ' + p.memory_note));
    if (p.payload && p.payload.text) b.append(el('div', 'draft', p.payload.text));
    if (p.executed || p.status !== 'pending') {
      b.append(el('div', 'done-tag', 'حُسم: ' + p.status
        + (p.executed ? ' · نُفّذ' : '')));
      return;
    }
    const acts = el('div', 'acts');
    const ok = el('button', 'b-ok', '✓ موافقة');
    const no = el('button', 'b-no', '✗ رفض');
    ok.onclick = () => act(m.thread, {op: 'approve', id: p.id}, acts);
    no.onclick = () => askReason(m.thread, p.id, acts);
    acts.append(ok, no);
    b.append(acts);
  },

  memory(b, p) {
    b.append(el('h4', null, '🧠 ' + (p.title || 'الذاكرة')));
    for (const it of p.items || []) {
      const d = el('div', 'case');
      d.append(el('span', 'mchip ' + it.kind, it.kind_ar || it.kind));
      d.append(el('b', null, ' ' + it.subject + ' '));
      d.append(el('span', null, '— ' + it.text));
      b.append(d);
      b.append(el('div', 'msrc',
        `${it.source || ''} · ${hhmm(it.created_at)} · صلة ${it.score ?? ''}`
        + (it.superseded_by ? ' · ⤴ مُبطَلة' : '')));
    }
  },

  websearch(b, p) {
    b.append(el('h4', null, '🌐 ' + (p.title || 'بحث في الإنترنت')));
    for (const it of p.items || []) {
      const d = el('div', 'case');
      const a = document.createElement('a');
      a.href = it.url; a.target = '_blank'; a.rel = 'noopener';
      a.textContent = it.title || it.url;
      d.append(a);
      if (it.snippet) d.append(el('div', 'msrc', it.snippet));
      b.append(d);
    }
    if (p.note) b.append(el('div', 'msrc', '⚖️ ' + p.note));
  },

  audit(b, p) {
    b.append(el('h4', null, '📜 آخر السجل — لا يُمحى ولا يُعدَّل'));
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
function chips() {
  const box = $('#chips');
  box.textContent = '';
  for (const c of (CHIPS[CUR] || [])) {
    const b = el('button', null, c);
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
  try { localStorage.setItem('ops-theme', t); } catch (e) { /* خاص */ }
  _themeBtn.textContent = t === 'dark' ? '☀️' : '🌙';
  const mt = document.querySelector('meta[name="theme-color"]');
  if (mt) mt.content = t === 'dark' ? '#12142b' : '#eef0fb';
}
let _savedTheme = null;
try { _savedTheme = localStorage.getItem('ops-theme'); } catch (e) { /* خاص */ }
setTheme(_savedTheme
  || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
_themeBtn.onclick = () =>
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

loadThreads();
