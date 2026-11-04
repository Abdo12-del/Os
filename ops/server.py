#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مركز العمليات — خادم HTTP بلا تبعيات (مكتبة Python القياسية فقط).

    python3 ops/server.py            # على المنفذ 8080
    PORT=9000 python3 ops/server.py

يفصل بين دورين في كل طلب:
  قراءة الوكيل  ← اتصال بـ PRAGMA query_only   (لا يستطيع الكتابة ولو أراد)
  قرارات المؤسس ← اتصال عادي، لكن الحذف ما زال محظورًا بالـ trigger
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db          # noqa: E402
import engine      # noqa: E402
import agents      # noqa: E402
import chat        # noqa: E402
import memory      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # جذر المستودع — مجلد memory/ فيه
PORT = int(os.environ.get('PORT', '8080'))
HOST = os.environ.get('HOST', '0.0.0.0')

db.init()
_f = db.connect('founder')
chat.init(_f)
chat.seed(_f)
memory.ensure(_f, ROOT)                      # التدريب من ملفات memory/*.md
engine.ON_EVENT.append(memory.capture)       # كل رفض/تنفيذ يصير ذكرى
_f.close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'AcademyOps/1.0'

    # ── أدوات ──
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(
            body, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode('utf-8'))
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt, *args):      # سجلّ أنظف
        pass

    # ── GET ──
    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)

        if p in ('/', '/index.html', '/chat'):
            return self._file('chat.html', 'text/html; charset=utf-8')
        if p == '/chat.css':
            return self._file('chat.css', 'text/css; charset=utf-8')
        if p == '/chat.js':
            return self._file('chat.js', 'application/javascript; charset=utf-8')
        if p in ('/console', '/tables'):
            return self._file('console.html', 'text/html; charset=utf-8')
        if p == '/style.css':
            return self._file('console.css', 'text/css; charset=utf-8')
        if p == '/app.js':
            return self._file('console.js', 'application/javascript; charset=utf-8')

        # التحية الأولى كتابةٌ — فتسبق اتصال القراءة باتصال مؤسس
        if p in ('/api/threads', '/api/messages', '/api/brief', '/api/memory'):
            fc = db.connect('founder')       # البذر والتدريب كتابةٌ سابقة للقراءة
            try:
                chat.seed(fc)
                memory.ensure(fc, ROOT)
            finally:
                fc.close()

        # كل قراءة تالية يفتحها اتصال **وكيل** — قراءة فقط، مفروضة
        con = db.connect('agent')
        try:
            if p == '/api/brief':
                b = agents.daily_brief(con)
                b['memory'] = memory.brief_memory(con)   # العقل الثاني في الصباح
                return self._send(200, b)
            if p == '/api/pending':
                return self._send(200, {
                    'pending': engine.pending(con, 'pending'),
                    'decided': engine.pending(con, 'approved')
                    + engine.pending(con, 'rejected')})
            if p == '/api/reconcile':
                return self._send(200, agents.reconcile(con))
            if p == '/api/funnel':
                return self._send(200, agents.funnel(con))
            if p == '/api/leads':
                return self._send(200, agents.lead_nurturer_queue(con))
            if p == '/api/summary':
                return self._send(200, agents.finance_summary(con))
            if p.startswith('/api/teacher/'):
                tid = p.rsplit('/', 1)[-1]
                return self._send(200, memory.apply_decision_to_statement(
                    con, agents.teacher_statement(con, tid)))
            if p == '/api/teachers':
                return self._send(200, {'teachers': [
                    dict(r) for r in con.execute(
                        'SELECT teacher_id, alias_name, group_name, share_pct,'
                        ' share_basis, free_trials, sessions_cancelled'
                        ' FROM teachers ORDER BY teacher_id')]})
            if p == '/api/audit':
                a = qs.get('agent', [None])[0]
                return self._send(200, {'log': engine.audit_log(con, 200, a)})
            if p == '/api/agents':
                return self._send(200, {'agents': engine.agent_states(con),
                                        'manual_only': list(engine.MANUAL_ONLY),
                                        'executable': sorted(engine.EXECUTABLE)})
            if p == '/api/replies':
                return self._send(200, {'replies': agents.REPLIES,
                                        'never_write_reply': agents.NEVER_WRITE_REPLY})
            if p == '/api/threads':
                return self._send(200, {'threads': chat.threads_meta(con)})
            if p == '/api/messages':
                th = qs.get('thread', ['head_of_ops'])[0]
                since = int(qs.get('since', ['0'])[0])
                return self._send(200, {'messages': chat.messages(con, th, since)})
            if p == '/api/memory':
                q = qs.get('q', [''])[0]
                if qs.get('all', ['0'])[0] == '1':
                    return self._send(200, {'memories': memory.all_memories(con)})
                kinds = qs.get('kinds', [''])[0].split(',') if qs.get('kinds') else None
                kinds = [x for x in (kinds or []) if x] or None
                return self._send(200, {'memories': memory.recall(
                    con, q, kinds=kinds, k=int(qs.get('k', ['5'])[0]))})
            return self._send(404, {'error': f'لا نقطة بهذا المسار: {p}',
                                    'note': 'لا أخترع مسارًا غير معرَّف'})
        except Exception as e:                                    # noqa: BLE001
            return self._send(500, {'error': str(e), 'broken': True})
        finally:
            con.close()

    def _file(self, name, ctype):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            return self._send(404, {'error': f'{name} غير موجود'})
        with open(path, 'rb') as f:
            self._send(200, f.read(), ctype)

    # ── POST — قرارات المؤسس وحده ──
    def do_POST(self):
        p = urlparse(self.path).path
        body = self._body()
        con = db.connect('founder')       # الكتابة لا تُفتح للوكيل أبدًا
        try:
            if p == '/api/run':
                return self._send(200, engine.run_all(con))
            if p == '/api/approve':
                aid = body.get('id')
                if aid is None:
                    return self._send(400, {'error': 'id مطلوب'})
                return self._send(200, engine.approve(con, int(aid)))
            if p == '/api/reject':
                aid, reason = body.get('id'), body.get('reason')
                if aid is None:
                    return self._send(400, {'error': 'id مطلوب'})
                res = engine.reject(con, int(aid), reason or '')
                code = 400 if res.get('outcome') == 'refused' else 200
                return self._send(code, res)
            if p == '/api/revoke':
                a = body.get('agent')
                if not a:
                    return self._send(400, {'error': 'agent مطلوب'})
                return self._send(200, engine.revoke(con, a))
            if p == '/api/restore':
                a = body.get('agent')
                if not a:
                    return self._send(400, {'error': 'agent مطلوب'})
                return self._send(200, engine.restore(con, a))
            if p == '/api/memory/export':
                path = os.path.join(ROOT, 'memory', 'exports',
                                     f'export-{engine.NOW.date().isoformat()}.md')
                n = memory.export_md(con, path)
                return self._send(200, {'path': os.path.relpath(path, ROOT),
                                        'count': n})
            if p == '/api/chat':
                th, text = body.get('thread'), (body.get('text') or '').strip()
                if th not in chat.BY_ID:
                    return self._send(400, {'error': f'محادثة غير معروفة: {th}'})
                if not text:
                    return self._send(400, {'error': 'اكتب شيئًا — أو اضغط زرًّا'})
                uid = chat.post(con, th, 'user', 'text', {'text': text})
                new = chat.handle(con, th, text)
                return self._send(200, {'user_id': uid, 'messages': new})
            if p == '/api/chat/action':
                th, op = body.get('thread'), body.get('op')
                if th not in chat.BY_ID:
                    return self._send(400, {'error': f'محادثة غير معروفة: {th}'})
                new = chat.apply_action(con, th, op,
                                        id=body.get('id'),
                                        reason=body.get('reason'),
                                        agent=body.get('agent'))
                return self._send(200, {'messages': new})
            return self._send(404, {'error': f'لا نقطة بهذا المسار: {p}'})
        except Exception as e:                                    # noqa: BLE001
            return self._send(500, {'error': str(e)})
        finally:
            con.close()


if __name__ == '__main__':
    print(f'مركز العمليات — http://{HOST}:{PORT}')
    print(f'القاعدة: {db.DB_PATH}')
    print('القراءة عبر اتصال وكيل (query_only) — الكتابة عبر اتصال المؤسس فقط.')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
