/* مركز العمليات — بلا مكتبات. Vanilla JS فقط. */
'use strict';

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
const n = v => v == null ? '—' : Number(v).toLocaleString('en-US');
const dzd = v => v == null ? '—' : Number(v).toLocaleString('en-US') + ' دج';

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
const post = (p, b) => api(p, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(b || {})
});

let toastT;
function toast(msg, err) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = err ? 'on err' : 'on';
  clearTimeout(toastT);
  toastT = setTimeout(() => t.className = '', 3800);
}

/* ─────────── الساعة ─────────── */
function clock() {
  const d = new Date();
  $('#clock').textContent = d.toLocaleTimeString('en-GB',
    { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
setInterval(clock, 1000); clock();

/* ─────────── التبويبات ─────────── */
const LOADERS = { brief: loadBrief, pending: loadPending, money: loadMoney,
  marketing: loadMarketing, agents: loadAgents, audit: loadAudit };

$$('#tabs button').forEach(b => b.addEventListener('click', () => {
  $$('#tabs button').forEach(x => x.classList.remove('on'));
  $$('main section').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  $('#' + b.dataset.t).classList.add('on');
  (LOADERS[b.dataset.t] || (() => {}))();
}));

/* ─────────── جدول → بطاقات على الهاتف ─────────── */
function table(cols, rows) {
  if (!rows.length) return '<p class="empty">لا شيء هنا.</p>';
  const head = cols.map(c => `<th>${esc(c[1])}</th>`).join('');
  const body = rows.map(r => '<tr>' + cols.map(c => {
    const v = typeof c[2] === 'function' ? c[2](r) : r[c[0]];
    const cls = c[3] ? ` class="${c[3]}"` : '';
    return `<td${cls} data-label="${esc(c[1])}">${v == null ? '' : v}</td>`;
  }).join('') + '</tr>').join('');
  return `<div class="tbl"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

const RISK = { red: ['red', '🔴 أحمر'], yellow: ['amber', '🟡 أصفر'],
  green: ['green', '🟢 أخضر'] };
const riskTag = r => {
  const [c, l] = RISK[r] || ['grey', r || '—'];
  return `<span class="tag ${c}">${esc(l)}</span>`;
};

/* ═══════════ 1. الملخص اليومي ═══════════ */
async function loadBrief() {
  const el = $('#brief-body');
  el.innerHTML = '<p class="loading">…</p>';
  try {
    const b = await api('/api/brief');
    const s = b.sections;
    let h = `<div class="card"><div class="crow"><h3>📋 ملخص ${esc(b.date)}</h3>
      ${b.overdue_count ? `<span class="tag red">⚠ ${b.overdue_count} متأخر</span>`
                        : '<span class="tag green">لا متأخرات</span>'}</div></div>`;

    h += '<h3>١) ما حدث</h3>';
    h += s.happened.length ? s.happened.map(x => `
      <div class="card ${esc(x.risk)}"><div class="crow">
        <b>${esc(x.item)}</b>${riskTag(x.risk)}</div>
        <p class="det">${esc(x.detail)}</p></div>`).join('')
      : '<p class="empty">لا شيء.</p>';

    h += '<h3>٢) يحتاج قرارك</h3>';
    h += s.needs_decision.length ? s.needs_decision.map(x => `
      <div class="card ${esc(x.risk)}">
        <div class="crow"><b>${esc(x.reason || x.action_type)}</b>${riskTag(x.risk)}</div>
        <p class="det">${esc(x.agent)}${x.source_ref ? ' • ' + esc(x.source_ref) : ''}</p>
        ${x.impact ? `<p class="det"><b>${esc(x.impact)}</b></p>` : ''}
        <p class="meta">${x.days_open == null
          ? 'قرار مؤسسي معلّق — لا يُقاس بالأيام'
          : `days_open = ${x.days_open}${x.overdue ? '  ⚠ متأخر (≥3 أيام)' : ''}`}</p>
      </div>`).join('')
      : '<p class="empty">لا شيء يحتاج قرارك.</p>';

    h += '<h3>٣) ماذا تعطّل / ماذا ينقصني</h3>';
    if (s.broken.length) {
      h += s.broken.map(x => `<div class="card red"><b>⛔ ${esc(x.component)}</b>
        <p class="det mono">${esc(x.error)}</p></div>`).join('');
    } else {
      h += '<div class="card green"><b>لا شيء معطّل.</b></div>';
    }
    h += `<div class="card amber"><b>ينقصني (${b.missing.length})</b>` +
      (b.missing.length ? '<ul>' + b.missing.map(m =>
        `<li><b>${esc(m.field)}</b>: ${esc(m.question)}${m.impact
          ? `<br><span class="det">${esc(m.impact)}</span>` : ''}</li>`).join('') + '</ul>'
        : '<p class="det">لا شيء.</p>') + '</div>';

    h += '<h3>٤) ماذا سأفعل الآن (بانتظار موافقتك)</h3><div class="card">' +
      '<ul>' + s.prepared.map(p => `<li>${esc(p)}</li>`).join('') + '</ul></div>';

    el.innerHTML = h;
  } catch (e) { el.innerHTML = `<div class="card red">⛔ ${esc(e.message)}</div>`; }
}

/* ═══════════ 2. يحتاج قرارك ═══════════ */
async function loadPending() {
  const el = $('#pending-body');
  el.innerHTML = '<p class="loading">…</p>';
  try {
    const { pending, decided } = await api('/api/pending');
    $('#b-pending').textContent = pending.length;

    let h = `<p class="det"><b>${pending.length}</b> معلّق •
      <b>${decided.length}</b> قُرِّر فيها</p>`;

    h += pending.length ? pending.map(card).join('')
      : '<div class="card green"><b>لا اقتراحات معلّقة.</b></div>';

    if (decided.length) {
      h += '<h2>قُرِّر فيها</h2>' + decided.map(x => `
        <div class="card"><div class="crow">
          <b>#${x.id} ${esc(x.action_type)}</b>
          <span class="tag ${x.status === 'approved' ? 'green' : 'grey'}">
            ${x.status === 'approved' ? '✅ وافقت' : '❌ رفضت'}</span></div>
          <p class="det">${esc(x.reason || '')}</p>
          <p class="meta">executed_at = ${x.executed_at ? esc(x.executed_at) : 'NULL'}
            ${x.manual_only ? ' • يدوي دائمًا — لا يُنفَّذ آليًا' : ''}
            ${x.rejection_reason ? ' • سبب رفضك: ' + esc(x.rejection_reason) : ''}</p>
        </div>`).join('');
    }
    el.innerHTML = h;
    wire(el);
  } catch (e) { el.innerHTML = `<div class="card red">⛔ ${esc(e.message)}</div>`; }
}

function card(x) {
  const p = x.payload || {};
  const body = p.text
    ? `<pre class="txt">${esc(p.text)}</pre>`
    : `<pre class="txt mono">${esc(JSON.stringify(p, null, 2))}</pre>`;
  return `
  <div class="card ${esc(x.risk)}" data-id="${x.id}">
    <div class="crow">
      <b>#${x.id} — ${esc(x.agent)} • ${esc(x.action_type)}</b>${riskTag(x.risk)}
    </div>
    ${x.reason ? `<p class="det">${esc(x.reason)}</p>` : ''}
    ${body}
    <p class="meta">source_ref = ${esc(x.source_ref || 'NULL')} •
      idempotency = ${esc(x.idempotency_key)} •
      days_open = ${x.days_open}${x.overdue ? ' ⚠' : ''}</p>
    ${x.manual_only ? `<div class="manual">⚠️ <b>لا يُنفَّذ آليًا حتى بعد موافقتك.</b>
      الموافقة تُسجَّل ويبقى <code>executed_at = NULL</code> — لا يوجد endpoint نشر أو إرسال.</div>` : ''}
    <div class="acts">
      <button class="btn ok sm" data-act="approve" data-id="${x.id}">✅ وافق</button>
      <button class="btn bad sm" data-act="reject" data-id="${x.id}">❌ ارفض</button>
    </div>
  </div>`;
}

function wire(root) {
  $$('[data-act]', root).forEach(b => b.addEventListener('click', async () => {
    const id = Number(b.dataset.id);
    b.disabled = true;
    try {
      if (b.dataset.act === 'approve') {
        const r = await post('/api/approve', { id });
        if (r.executed) toast(`✅ #${id} نُفّذ في تطبيقك`);
        else if (r.manual_instruction)
          toast(`✅ #${id} موافَق عليه — والتنفيذ يدوي من حسابك`);
        else toast(`⚠️ #${id}: ${r.error || 'لم يُنفَّذ'}`, true);
      } else {
        openReject(id); return;
      }
      loadPending();
    } catch (e) { toast(e.message, true); b.disabled = false; }
  }));
}

/* ── نافذة الرفض: السبب إلزامي ── */
let rejectId = null;
function openReject(id) {
  rejectId = id;
  $('#m-title').textContent = `رفض الاقتراح #${id}`;
  $('#m-text').textContent = 'السبب يعود للوكيل كتعليمة. بلا سبب لا يتحسّن شيء.';
  $('#m-reason').value = '';
  $('#modal').hidden = false;
  setTimeout(() => $('#m-reason').focus(), 50);
}
$('#m-cancel').addEventListener('click', () => { $('#modal').hidden = true; });
$('#m-ok').addEventListener('click', async () => {
  const reason = $('#m-reason').value.trim();
  if (!reason) { toast('السبب إلزامي — القاعدة 4', true); return; }
  try {
    await post('/api/reject', { id: rejectId, reason });
    $('#modal').hidden = true;
    toast(`❌ رُفض #${rejectId} وسُجِّل سببك`);
    loadPending();
  } catch (e) { toast(e.message, true); }
});

/* ═══════════ 3. المال ═══════════ */
async function loadMoney() {
  const r = $('#rec-body'), t = $('#t-body'), s = $('#sum-body');
  r.innerHTML = t.innerHTML = s.innerHTML = '<p class="loading">…</p>';
  try {
    const rec = await api('/api/reconcile');
    const tt = rec.totals;
    r.innerHTML = `
      <div class="card amber">
        <div class="crow"><b>الفرق الصافي: ${dzd(rec.net_difference)}</b>
          <span class="tag red">${rec.case_count} حالة تحته</span></div>
        <p class="det"><b>${esc(rec.warning)}</b></p>
      </div>
      <div class="card"><div class="crow"><span>نظام المحاسبة (مرجع المال)</span>
        <b>${tt.accounting.count} دفعة • ${dzd(tt.accounting.sum)}</b></div>
        <div class="crow"><span>نظام الأولياء (مرجع التقييمات)</span>
        <b>${tt.parents.count} دفعة • ${dzd(tt.parents.sum)}</b></div>
        <div class="crow"><span>المستحق</span><b>${dzd(tt.due)}</b></div>
        <div class="crow"><span>المتأخرات</span><b>${dzd(tt.arrears)}</b></div></div>
      <h3>الحالات</h3>` +
      rec.cases.map(c => `
        <div class="card ${esc(c.risk)}"><div class="crow">
          <b>${esc(c.kind)}</b>${riskTag(c.risk)}</div>
          <p class="det">${esc(c.note)}</p>
          <p class="meta">${esc(c.student_id || '')} ${esc(c.alias || '')}
            ${c.amount != null ? ' • ' + dzd(c.amount) : ''}
            ${c.delta != null ? ' • الفرق ' + dzd(c.delta) : ''}
            ${c.paid_at ? ' • ' + esc(c.paid_at) : ''}
            ${c.refs ? ' • ' + esc(c.refs) : ''}</p>
        </div>`).join('') +
      (rec.arrears.length ? '<h3>المتأخرات</h3>' + table(
        [['student_id', 'الطالب'], ['alias_name', 'الاسم المستعار'],
         ['group_name', 'المجموعة'], ['teacher_id', 'الأستاذ'],
         ['monthly_due', 'المستحق', r2 => dzd(r2.monthly_due), 'num']], rec.arrears)
        + '<p class="det">⚠️ لا تُكشف متأخرات ولي أمر لأحد — <b>ولا للأستاذ</b>.</p>' : '');

    const { teachers } = await api('/api/teachers');
    let th = '';
    for (const x of teachers) {
      const st = await api('/api/teacher/' + x.teacher_id);
      th += `<div class="card ${st.basis ? '' : 'red'}">
        <div class="crow"><b>${esc(st.alias)} — ${esc(st.group)}</b>
          ${st.basis ? `<span class="tag green">${esc(st.basis)}</span>`
                     : '<span class="tag red">الأساس غير محسوم</span>'}</div>
        <p class="det">${st.sessions_delivered} حصة منفَّذة •
          ${st.free_trials} تعريفية مجانية • ${st.sessions_cancelled} ملغاة •
          النسبة ${st.share_pct}%</p>
        <p class="det"><b>amount_due = ${st.amount_due === null ? 'NULL' : dzd(st.amount_due)}</b>
          — لا مبلغ على أساس غير مكتوب (القاعدة 10 للمحاسب)</p>
        ${table([['basis', 'الأسس المحتملة'], ['label', ''],
                 ['base', 'الأساس', r2 => dzd(r2.base), 'num'],
                 ['amount', 'المبلغ', r2 => dzd(r2.amount), 'num']], st.candidates)}
        <div class="card amber"><b>الفارق بين الأسس: ${dzd(st.spread_dzd)}</b>
          <p class="det">هذه كلفة عدم القرار، لأستاذ واحد، في شهر واحد.</p></div>
        ${st.free_trial_cost_note
          ? `<div class="manual">⚠️ ${esc(st.free_trial_cost_note)}</div>` : ''}
        ${st.missing.length ? '<p class="det"><b>ينقص:</b> ' + st.missing.map(m =>
          esc(m.question)).join(' • ') + '</p>' : ''}
      </div>`;
    }
    t.innerHTML = th;

    const sum = await api('/api/summary');
    const f = sum.flows;
    s.innerHTML = `
      <div class="card"><div class="crow"><span>١ إيراد من الأولياء</span>
        <b>${f.income_from_parents.count} دفعة • ${dzd(f.income_from_parents.sum)}</b></div>
        <div class="crow"><span>٢ مصاريف</span>
        <b>${f.expenses.count} • ${dzd(f.expenses.sum)}</b></div>
        <div class="crow"><span>٣ أجور أساتذة</span>
        <b style="color:var(--red)">${f.teacher_payouts === null
          ? 'NULL — لا يُخترع' : dzd(f.teacher_payouts)}</b></div></div>
      <p class="det">لا دفتر أستاذ مزدوج — عندك ثلاثة تدفقات لا قيود مدينة ودائن.</p>` +
      (sum.alerts.length ? '<h3>تنبيهات</h3>' + sum.alerts.map(a => `
        <div class="card ${esc(a.risk)}"><div class="crow"><b>${esc(a.kind)}</b>
          ${riskTag(a.risk)}</div><p class="det">${esc(a.note)}
          ${a.month ? ' • ' + esc(a.month) : ''}${a.label ? ' • ' + esc(a.label) : ''}
          ${a.amount ? ' • ' + dzd(a.amount) : ''}</p></div>`).join('') : '') +
      (sum.missing.length ? '<div class="card amber"><b>ينقص</b>' + sum.missing.map(m =>
        `<p class="det">${esc(m.question)} — ${esc(m.impact)}</p>`).join('') + '</div>' : '');
  } catch (e) { r.innerHTML = `<div class="card red">⛔ ${esc(e.message)}</div>`; }
}

/* ═══════════ 4. التسويق ═══════════ */
async function loadMarketing() {
  const f = $('#fun-body'), l = $('#leads-body');
  f.innerHTML = l.innerHTML = '<p class="loading">…</p>';
  try {
    const fu = await api('/api/funnel');
    const max = Math.max(...fu.stages.map(s => s.count), 1);
    f.innerHTML = '<div class="funnel">' + fu.stages.map(s => {
      const leak = s.stage.indexOf('لم يُرد') > -1;
      return `<div class="frow ${leak ? 'leak' : ''}">
        <span class="flabel">${esc(s.stage)}</span>
        <div class="fbar" style="width:${Math.max(2, s.count / max * 100)}%"></div>
        <span class="fval">${n(s.count)}${s.rate_pct != null
          ? ' (' + s.rate_pct + '%)' : ''}</span></div>`;
    }).join('') + '</div>';

    f.innerHTML += '<h3>الأولويات — ثلاث لا عشر</h3>' + fu.priorities.map(p => `
      <div class="card ${p.rank === 1 ? 'red' : 'amber'}">
        <div class="crow"><b>${p.rank}. ${esc(p.issue)}</b></div>
        <p class="det">${esc(p.why)}</p>
        <p class="det"><b>→ ${esc(p.action)}</b></p>
        ${p.ref ? `<p class="meta">${esc(p.ref)}</p>` : ''}
      </div>`).join('');

    if (fu.routed.length) {
      f.innerHTML += '<h3>يُسلَّم لوكيل آخر</h3>' + fu.routed.map(x => `
        <div class="card"><div class="crow"><b>${esc(x.issue)}</b>
          <span class="tag">→ ${esc(x.route_to)}</span></div>
          <p class="det">${esc(x.why)}</p></div>`).join('');
    }

    f.innerHTML += '<h3>حسب المصدر</h3>' + table(
      [['source', 'المصدر'], ['leads', 'مهتمون', r => n(r.leads), 'num'],
       ['never_replied', 'بلا رد', r => n(r.never_replied), 'num'],
       ['enrolled', 'سجّلوا', r => n(r.enrolled), 'num']], fu.by_source);
    f.innerHTML += `<div class="card amber"><b>ينقص</b>${fu.missing.map(m =>
      `<p class="det">${esc(m.question)} — ${esc(m.impact)}</p>`).join('')}</div>`;

    const q = await api('/api/leads');
    l.innerHTML = `<div class="card red"><div class="crow">
        <b>${q.never_replied} من ${q.total_leads} لم يُرد عليهم إطلاقًا</b>
        <span class="tag red">${q.rate_pct}%</span></div>
        <p class="det">${esc(q.note)}</p></div>` +
      q.queue.map(x => `
        <div class="card ${x.overdue ? 'red' : 'amber'}">
          <div class="crow"><b>${esc(x.lead_id)} — ${esc(x.reply_title || x.topic)}</b>
            <span class="tag red">${n(x.hours_waiting)} ساعة</span></div>
          <p class="meta">${esc(x.source)} • ${esc(x.first_msg_at)} •
            days_waiting = ${x.days_waiting}</p>
          ${x.suggested_reply ? `<pre class="txt">${esc(x.suggested_reply)}</pre>`
            : '<p class="det">لا مسوَّدة — يحتاج قرارًا منك</p>'}
          ${x.has_placeholder ? '<div class="manual">🔶 فيه <code>【تحقّق】</code> — '
            + 'لا يُرسل قبل حسمه. القرار 2 في OPEN-QUESTIONS.</div>' : ''}
          <div class="manual">⚠️ مسوَّدة فقط — <b>أرسلها من حسابك</b>.
            لا يوجد endpoint إرسال.</div>
        </div>`).join('') +
      `<h3>٦ حالات لا يُكتب فيها رد إطلاقًا — يُتّصل</h3><div class="card">
        <ul>${q.never_write_reply.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  } catch (e) { f.innerHTML = `<div class="card red">⛔ ${esc(e.message)}</div>`; }
}

/* ═══════════ 5. الوكلاء ═══════════ */
const AGENT_AR = { head_of_ops: 'رئيس العمليات', accountant: 'المحاسب',
  marketing: 'خبير التسويق', lead_nurturer: 'متابع المهتمين' };

async function loadAgents() {
  const el = $('#agents-body');
  el.innerHTML = '<p class="loading">…</p>';
  try {
    const d = await api('/api/agents');
    el.innerHTML = d.agents.map(a => `
      <div class="card ${a.revoked_at ? 'red' : 'green'}">
        <div class="crow"><b>${esc(AGENT_AR[a.agent] || a.agent)}
          <span class="mono">${esc(a.agent)}</span></b>
          ${a.revoked_at ? '<span class="tag red">⏸ موقوف</span>'
                         : '<span class="tag green">● يعمل</span>'}</div>
        <p class="meta">last_run_at = ${esc(a.last_run_at || 'NULL')}
          ${a.revoked_at ? ' • revoked_at = ' + esc(a.revoked_at) : ''}</p>
        <div class="acts">${a.revoked_at
          ? `<button class="btn sm" data-ag="${esc(a.agent)}" data-r="restore">↩ أعد تشغيله</button>`
          : `<button class="btn bad sm" data-ag="${esc(a.agent)}" data-r="revoke">⏸ /revoke — أوقفه فورًا</button>`}
        </div>
      </div>`).join('') +
      `<div class="card"><h3>ما يُنفَّذ آليًا</h3>
        <p class="det">${d.executable.map(x => `<code>${esc(x)}</code>`).join(' • ')}</p>
        <h3>ما لا يُنفَّذ آليًا — أبدًا، ولو بعد الموافقة</h3>
        <div class="manual">⚠️ ${d.manual_only.map(x => `<code>${esc(x)}</code>`).join(' • ')}
          <br>لا يوجد لهما endpoint. القرار مؤسسي ولا يُراجع.</div></div>
      <div class="card"><h3>كيف تُفرَض القواعد</h3>
        <p class="det">١. الوكيل يفتح اتصالًا بـ <code>PRAGMA query_only</code> —
          أي <code>INSERT</code>/<code>UPDATE</code>/<code>DELETE</code> يرفضها المحرّك.</p>
        <p class="det">٢. <code>trigger</code> يمنع الحذف على كل جدول بيانات —
          <b>ولو على اتصال المؤسس</b>. الطريق الوحيد <code>deleted_at</code>.</p>
        <p class="det">٣. سجلّ التدقيق له <code>trigger</code> يمنع <code>UPDATE</code>
          و<code>DELETE</code> — لا يُمحى أثر.</p>
        <p class="det">٤. <code>idempotency_key</code> فريد — الضغط مرتين لا ينفّذ مرتين.</p>
        <p class="det">٥. الرفض بلا سبب مرفوض — السبب يعود للوكيل كتعليمة.</p></div>`;
    $$('[data-r]', el).forEach(b => b.addEventListener('click', async () => {
      try {
        await post('/api/' + b.dataset.r, { agent: b.dataset.ag });
        toast(b.dataset.r === 'revoke'
          ? `⏸ ${b.dataset.ag} موقوف — لن يقترح شيئًا` : `↩ ${b.dataset.ag} يعمل`);
        loadAgents();
      } catch (e) { toast(e.message, true); }
    }));
  } catch (e) { el.innerHTML = `<div class="card red">⛔ ${esc(e.message)}</div>`; }
}

/* ═══════════ 6. السجلّ ═══════════ */
async function loadAudit() {
  const el = $('#audit-body');
  el.innerHTML = '<p class="loading">…</p>';
  try {
    const { log } = await api('/api/audit');
    const OC = { ok: 'green', refused: 'red', needs_approval: 'amber',
      unknown_asked: 'grey', error: 'red' };
    el.innerHTML = `<p class="det">${log.length} سطر — الأحدث أولًا.
      لا يُعدَّل ولا يُمحى.</p>` + table(
      [['ts', 'الوقت', r => `<span class="mono">${esc(r.ts)}</span>`],
       ['agent', 'الوكيل', r => esc(AGENT_AR[r.agent] || r.agent)],
       ['action', 'الفعل', r => `<code>${esc(r.action)}</code>`],
       ['target', 'الهدف', r => esc(r.target || '')],
       ['row_count', 'صفوف', r => n(r.row_count), 'num'],
       ['outcome', 'النتيجة', r => `<span class="tag ${OC[r.outcome] || 'grey'}">${esc(r.outcome)}</span>`],
       ['note', 'ملاحظة', r => esc(r.note || '')]], log);
  } catch (e) { el.innerHTML = `<div class="card red">⛔ ${esc(e.message)}</div>`; }
}

/* ═══════════ تشغيل الوكلاء ═══════════ */
$('#run').addEventListener('click', async () => {
  const b = $('#run');
  b.disabled = true; b.textContent = '… يعمل';
  try {
    const r = await post('/api/run');
    const parts = [];
    if (r.ran.length) parts.push(r.ran.length + ' وكيلًا عمل');
    if (r.proposed) parts.push(r.proposed + ' اقتراحًا جديدًا');
    if (r.skipped.length) parts.push(r.skipped.length + ' موقوف');
    if (r.broken.length) parts.push('⛔ ' + r.broken.length + ' تعطّل');
    toast(parts.join(' • ') || 'لا جديد');
    loadBrief(); loadPending();
  } catch (e) { toast(e.message, true); }
  b.disabled = false; b.textContent = '▶ شغّل الوكلاء';
});

/* ═══════════ الإقلاع ═══════════ */
loadBrief();
api('/api/pending').then(d => { $('#b-pending').textContent = d.pending.length; })
  .catch(() => {});
