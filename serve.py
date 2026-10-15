#!/usr/bin/env python3
"""OPE v2 — local preview server + save endpoint for on-page editing.

- Serves static files (HTML/SVG/JS) from the project directory.
- POST /save?file=<page> accepts JSON {html, ope_ver, changes, page}, validates the
  path stays inside the project, rejects stale tabs with HTTP 409, auto-bumps the
  ope-ver marker, writes a .bak before overwriting, and appends a change log.
- POST /save REQUIRES Content-Type: application/json. A cross-origin form or fetch
  can send text/plain WITHOUT a preflight (a CORS "simple request"), so requiring
  JSON means the browser preflights, we never answer, and a third-party page cannot
  rewrite files here. The legacy raw-HTML body was removed for exactly that reason:
  it was the CSRF vector.

Cache rules (hard-won):
- HTML pages AND /ope.js MUST be served with Cache-Control: no-cache.
  SimpleHTTPRequestHandler sends Last-Modified with 1s granularity and no
  Cache-Control, so browsers heuristically cache the main document: after a
  save the file on disk is updated but a reload gets 304 (same-second mtime)
  and shows OLD content. Symptom: "save succeeded but reload shows no changes."

Security defaults:
- Binds 127.0.0.1 only. Pass a host (or set OPE_HOST) to expose it on the LAN.
- Writes are restricted to .html/.htm files inside this directory.
- POST /save requires Content-Type: application/json (forces a preflight, so no
  cross-site writes) and rejects Sec-Fetch-Site: cross-site; the body is bounded.
- EXPOSURE NOTE: everything in the served directory is readable by anyone who can
  reach the port — including <page>.bak and changes.md. Do not serve a directory
  holding private files; changes.md accumulates the human's edited wording.
"""
import http.server
import socketserver
import os
import sys
import shutil
import json
import re
import datetime

BASE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)

CHANGES_FILE = os.path.join(BASE, 'changes.md')
# Optional: set OPE_NOTIFY_DIR to a directory where a JSON notification is
# dropped after every save (e.g. a notification inbox or sync folder). Unset = off.
NOTIFY_DIR = os.environ.get('OPE_NOTIFY_DIR') or None

MAX_BODY = 32 * 1024 * 1024   # a page edit is kBs; 32 MB is a ceiling, not a target
SOCK_TIMEOUT = 30             # per-connection, so an unbounded read cannot park a thread forever

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('OPE_PORT', '8899'))
HOST = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('OPE_HOST', '127.0.0.1')


class H(http.server.SimpleHTTPRequestHandler):
    timeout = SOCK_TIMEOUT   # StreamRequestHandler applies this to the connection socket

    def log_message(self, *a):
        pass  # quiet

    def end_headers(self):
        # Never cache HTML pages or ope.js — stale cache makes saved edits
        # "disappear" on reload. Always fresh.
        if self.path.startswith('/ope.js') or self.path.endswith(('.html', '.htm')):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def _send(self, code, body, ctype='text/plain'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.end_headers()
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.wfile.write(body)

    def do_POST(self):
        """POST /save?file=<page> — body: JSON {html, ope_ver, changes, page}; requires Content-Type: application/json."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        fname = (qs.get('file') or ['index.html'])[0]
        # Safety: only allow editing html files inside the project dir
        target = os.path.realpath(os.path.join(BASE, fname))
        # Path-boundary check. A plain target.startswith(BASE) is UNSAFE: a sibling
        # directory whose NAME merely prefixes BASE (".../ope-evil" vs ".../ope")
        # passes it, and the write escapes the project directory. Compare real
        # paths on a path-component boundary instead.
        if os.path.commonpath([BASE, target]) != BASE or os.path.splitext(target)[1] not in ('.html', '.htm'):
            self._send(403, 'forbidden')
            return

        # --- CSRF gate ------------------------------------------------------------
        # text/plain is a CORS *simple request*: no preflight is sent, so any page the
        # human visits while this server runs could rewrite files here. application/json
        # is NOT simple, so the browser preflights; we never answer a preflight and the
        # cross-origin write is refused before it leaves the browser. The real client
        # (ope.js) already sends application/json.
        ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if ctype != 'application/json' or (self.headers.get('Sec-Fetch-Site') or '').lower() == 'cross-site':
            self._send(415, 'Content-Type: application/json required — cross-site writes are refused')
            return

        # --- bounded read (a parked thread is not a DoS) --------------------------
        try:
            length = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            self._send(400, 'bad Content-Length')
            return
        if not 0 <= length <= MAX_BODY:
            self._send(413, f'payload too large (limit {MAX_BODY} bytes)')
            return
        body = self.rfile.read(length)

        # Parse payload: JSON (OPE v2). Raw-HTML bodies were removed with the CSRF fix.
        try:
            j = json.loads(body.decode('utf-8'))
        except Exception:
            self._send(400, 'body must be a JSON object {html, ope_ver, changes, page}')
            return
        if not isinstance(j.get('html'), str):
            self._send(400, 'json body must carry an "html" string')
            return
        data = j['html'].encode('utf-8')
        changes = j.get('changes') or []
        page = j.get('page') or fname

        def opever(b):
            m = re.search(rb'<!--\s*ope-ver:\s*(\d+)\s*-->', b)
            return int(m.group(1)) if m else 0

        cur_ver = opever(open(target, 'rb').read()) if os.path.exists(target) else 0
        new_ver = opever(data)
        if new_ver < cur_ver:
            self._send(409, f'STALE SAVE REJECTED (tab is v{new_ver}, disk is v{cur_ver}) — hard-refresh the page (Ctrl+Shift+R) then save again')
            return

        # Auto-bump version marker so stale tabs always 409 after this save
        bumped = re.sub(rb'<!--\s*ope-ver:\s*\d+\s*-->', f'<!-- ope-ver: {cur_ver + 1} -->'.encode(), data, count=1)
        if os.path.exists(target):
            shutil.copy(target, target + '.bak')
        with open(target, 'wb') as f:
            f.write(bumped)

        # Write change log (append-only)
        self._log_changes(page, cur_ver, cur_ver + 1, changes)

        # Optional external notification (inbox / sync folder)
        self._notify(page, cur_ver + 1, changes)

        self._send(200, json.dumps({'ok': True, 'file': fname, 'version': cur_ver + 1, 'changes': len(changes)}), 'application/json')

    def _log_changes(self, page, old_ver, new_ver, changes):
        if not changes:
            return
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        lines = [f'\n## {ts} — {page} (v{old_ver} → v{new_ver})']
        for c in changes:
            ctype = c.get('type', '?')
            label = (c.get('label') or '?').replace('\n', ' ')[:60]
            if ctype == 'move':
                lines.append(f"- **MOVE** {label}: {c.get('before')} → {c.get('after')}")
            elif ctype == 'text':
                before = (c.get('before') or '').replace('\n', ' ')[:120]
                after = (c.get('after') or '').replace('\n', ' ')[:120]
                lines.append(f"- **TEXT** {label}: \"{before}\" → \"{after}\"")
            else:
                lines.append(f"- **{ctype.upper()}** {label}: {c.get('before')} → {c.get('after')}")
        with open(CHANGES_FILE, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

    def _notify(self, page, version, changes):
        """Optional file-based notification after each save (disabled by default)."""
        if not NOTIFY_DIR:
            return
        try:
            os.makedirs(NOTIFY_DIR, exist_ok=True)
            ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')
            fname = f"ope_changes_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            n_changes = len(changes)
            content = f"Page {page} edited via OPE (saved v{version}) with {n_changes} change(s). See changes.md for the diff."
            msg = {
                "delivered_at": ts,
                "message": {
                    "from": "ope",
                    "to": "listener",
                    "type": "ope_change",
                    "content": content,
                    "payload": {"type": "ope_change", "page": page, "version": version, "changes": n_changes},
                    "timestamp": ts
                }
            }
            with open(os.path.join(NOTIFY_DIR, fname), 'w', encoding='utf-8') as f:
                json.dump(msg, f, indent=2)
        except Exception as e:
            print(f"[ope] notify failed: {e}")


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with S((HOST, PORT), H) as httpd:
    print(f"📊 OPE pages at http://{HOST}:{PORT}/")
    print(f"   Save endpoint: POST /save?file=index.html (Content-Type: application/json)")
    print(f"   Change log: {CHANGES_FILE}")
    httpd.serve_forever()
