#!/usr/bin/env python3
"""test_hardening.py — regression gates for the OPE /save hardening.

Runs the real serve.py in a THROWAWAY copy and exercises:
  S1  CSRF: a cross-origin "simple request" (text/plain, no preflight) must NOT write.
  S3  bounded read: a hostile Content-Length must not park a thread.
  Regression: the legit JSON path still saves, .bak still written, traversal still 403.

Usage: python3 scripts/test_hardening.py          # exit 0 = all gates pass
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = None          # assigned per run from an ephemeral bind — see free_port()
results = []


def free_port():
    """Bind :0, let the OS pick a free port, release it.

    A hardcoded port makes this gate fail ENVIRONMENTALLY (anything already holding it, or a
    slow first start) rather than LOGICALLY — and a gate that fails for reasons unrelated to
    the thing it tests is a gate people learn to ignore. Same pattern as test_traversal.py.
    """
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))


def raw_post(host, port, path, headers, body, timeout=6):
    """Raw socket POST so we can send illegal Content-Length values."""
    req = f"POST {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n"
    for k, v in headers.items():
        req += f"{k}: {v}\r\n"
    req += "\r\n"
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        s.sendall(req.encode() + (body if isinstance(body, bytes) else body.encode()))
        chunks = []
        s.settimeout(timeout)
        while True:
            try:
                b = s.recv(65536)
            except socket.timeout:
                return None, b"<no response: thread parked>"
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}".encode()
    finally:
        s.close()


def status_of(resp):
    if isinstance(resp, tuple):      # (resp, err) from raw_post
        resp = resp[0]
    if not resp:
        return None
    try:
        return int(resp.split(b"\r\n", 1)[0].split()[1])
    except Exception:
        return None


def main():
    global PORT
    PORT = free_port()
    work = Path(tempfile.mkdtemp(prefix="ope-hardening-"))
    for f in ("serve.py", "ope.js", "LICENSE"):
        shutil.copy(REPO / f, work / f)
    (work / "index.html").write_text(
        '<!DOCTYPE html><html><body><h1>t</h1><!-- ope-ver: 2 --></body></html>')
    # an escape target sitting NEXT to the served dir (the sibling-prefix trap)
    evil = work.parent / (work.name + "-evil")
    evil.mkdir(exist_ok=True)

    proc = subprocess.Popen([sys.executable, "serve.py", str(PORT), "127.0.0.1"],
                            cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=2)
                c.request("GET", "/")
                if c.getresponse().status == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            print(f"server failed to start on ephemeral port {PORT}"); return 2

        def post(hdrs, body, path="/save?file=index.html"):
            return raw_post("127.0.0.1", PORT, path, hdrs, body)

        good = json.dumps({"html": '<!DOCTYPE html><html><body><h1>t</h1><!-- ope-ver: 2 --></body></html>',
                           "ope_ver": 2, "page": "index.html", "changes": []})

        print("S1 — CSRF (cross-origin simple request must be refused)")
        before = (work / "index.html").read_text()
        r = post({"Content-Type": "text/plain", "Content-Length": str(len(good)),
                  "Origin": "https://evil.example"}, good)
        check("text/plain + Origin: evil -> 415, not 200", status_of(r) == 415,
              f"got {status_of(r)}")
        check("file untouched by the CSRF attempt", (work / "index.html").read_text() == before)
        r = post({"Content-Type": "", "Content-Length": str(len(good))}, good)
        check("no Content-Type -> 415", status_of(r) == 415, f"got {status_of(r)}")
        r = post({"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site",
                  "Content-Length": str(len(good))}, good)
        check("json + Sec-Fetch-Site: cross-site -> 415", status_of(r) == 415, f"got {status_of(r)}")
        r = post({"Content-Type": "text/plain", "Content-Length": str(len(good))}, good)
        check("raw HTML body (legacy path) -> 415", status_of(r) == 415, f"got {status_of(r)}")

        print("S3 — bounded read (no parked thread)")
        t0 = time.time()
        r = post({"Content-Type": "application/json", "Content-Length": "1000000000"}, b"{")
        dt = time.time() - t0
        check("Content-Length 1e9 -> 413 promptly (no park)", status_of(r) == 413 and dt < 5,
              f"got {status_of(r)} after {dt:.1f}s")
        r = post({"Content-Type": "application/json", "Content-Length": "-1"}, b"")
        check("Content-Length -1 -> 413", status_of(r) == 413, f"got {status_of(r)}")
        r = post({"Content-Type": "application/json", "Content-Length": "abc"}, b"")
        check("Content-Length abc -> 400", status_of(r) == 400, f"got {status_of(r)}")
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3); c.request("GET", "/")
        check("server still serving after the hostile reads", c.getresponse().status == 200)

        print("Regression — the legit path still works")
        r = post({"Content-Type": "application/json", "Content-Length": str(len(good))}, good)
        check("application/json save -> 200", status_of(r) == 200, f"got {status_of(r)}")
        check(".bak written (target existed)", (work / "index.html.bak").exists())
        r = post({"Content-Type": "application/json", "Content-Length": str(len(b"notjson!"))}, b"notjson!")
        check("non-JSON body -> 400 (no silent raw fallback)", status_of(r) == 400, f"got {status_of(r)}")
        r = post({"Content-Type": "application/json", "Content-Length": "2"}, b"{}")
        check("json without html -> 400", status_of(r) == 400, f"got {status_of(r)}")

        print("Regression — path guard still closed")
        for name, path in [("plain ../", "/save?file=../" + evil.name + "/pwn.html"),
                           ("encoded %2e%2e%2f", "/save?file=%2e%2e%2f" + evil.name + "%2fpwn.html"),
                           ("absolute path", "/save?file=/etc/passwd.html")]:
            r = post({"Content-Type": "application/json", "Content-Length": str(len(good))}, good, path)
            check(f"{name} -> 403", status_of(r) == 403, f"got {status_of(r)}")
        check("nothing escaped into the sibling dir", not any(evil.iterdir()))
    finally:
        proc.terminate(); proc.wait(timeout=10)
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(evil, ignore_errors=True)

    n_fail = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{len(results) - n_fail}/{len(results)} checks passed")
    if n_fail:
        print("FAILED:")
        for n, ok, d in results:
            if not ok:
                print(f"  - {n}  [{d}]")
    print("HARDENING GATES: " + ("ALL PASS" if n_fail == 0 else f"{n_fail} FAILED"))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
