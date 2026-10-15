#!/usr/bin/env python3
"""
test_traversal.py — regression test for serve.py's path-boundary guard.

WHY THIS EXISTS
---------------
serve.py originally guarded save paths with `target.startswith(BASE)`. That is a
STRING prefix test, not a path-boundary test. A sibling directory whose name
merely PREFIXES the project directory passes it:

    BASE   = /srv/site/ope
    target = /srv/site/ope-evil/pwn.html      <- "ope-evil".startswith("ope") == True

so `POST /save?file=../ope-evil/pwn.html` escaped the project directory and
wrote a file there. This test pins the correct behaviour so the guard cannot
silently regress.

RUN:  python3 scripts/test_traversal.py        (exit 0 = all blocked/allowed as expected)
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVE_PY = os.path.join(os.path.dirname(HERE), "serve.py")

PAGE = "<!DOCTYPE html>\n<!-- ope-ver: 1 -->\n<html><body>original</body></html>\n"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def post(port, fname, html, raw=False):
    """Return (status, body). Accepts any outcome without raising.

    raw=True sends `fname` into the query string VERBATIM (no client-side
    re-encoding), so a percent-encoded attack reaches the server exactly as a
    real attacker would send it and is decoded once, server-side.
    """
    q = fname if raw else urllib.parse.quote(fname, safe='')
    url = f"http://127.0.0.1:{port}/save?file={q}"
    body = json.dumps({"html": html, "ope_ver": 1, "changes": [], "page": fname}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:  # connection reset etc.
        return "ERR", str(e)[:200]


def main():
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))

    tmp = tempfile.mkdtemp(prefix="ope-traversal-")
    try:
        base = os.path.join(tmp, "ope")          # the project dir
        evil = os.path.join(tmp, "ope-evil")     # prefix-sibling — the attack target
        outside = os.path.join(tmp, "outside")   # plain sibling
        for d in (base, evil, outside):
            os.makedirs(d)
        shutil.copy(SERVE_PY, base)
        with open(os.path.join(base, "index.html"), "w") as f:
            f.write(PAGE)

        port = free_port()
        proc = subprocess.Popen(
            [sys.executable, "serve.py", str(port)],
            cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            # wait for readiness
            for _ in range(40):
                time.sleep(0.25)
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read()
                    break
                except Exception:
                    continue

            print("\n[1] legitimate in-project save must still WORK")
            code, body = post(port, "index.html", PAGE.replace("original", "EDITED"))
            check("legit save in-dir -> 200", code == 200, f"HTTP {code}")
            check("legit save actually wrote",
                  "EDITED" in open(os.path.join(base, "index.html")).read())

            print("\n[2] attacks must all be BLOCKED")
            # (label, path, raw) — raw=True bypasses client re-encoding so a
            # percent-encoded attack arrives exactly as an attacker would send it.
            attacks = [
                ("prefix-sibling (../ope-evil/pwn.html)", "../ope-evil/pwn.html", False),
                ("plain sibling (../outside/pwn.html)",   "../outside/pwn.html",   False),
                ("parent escape (../../pwn.html)",        "../../pwn.html",        False),
                ("absolute path",                          "/tmp/ope-absolute-pwn.html", False),
                ("encoded dots (%2e%2e%2f)",               "%2e%2e%2fope-evil%2fpwn.html", True),
                ("encoded, uppercase (%2E%2E%2F)",         "%2E%2E%2Fope-evil%2Fpwn.html", True),
                ("null-byte truncation",                    "index.html%00.py",             True),
            ]
            for label, fname, raw in attacks:
                code, body = post(port, fname, PAGE.replace("original", "PWNED"), raw=raw)
                check(f"blocked: {label}", code != 200, f"HTTP {code}")

            # POSIX note: on Linux a backslash is a LEGAL filename character, not a
            # separator. "..\ope-evil\pwn.html" is therefore a single filename that
            # resolves INSIDE base — a 200 here is correct, not a bypass. The
            # invariant that matters is containment, so assert escape, not status.
            code, _ = post(port, "..%5Cope-evil%5Cpwn.html", PAGE, raw=True)
            check("backslash variant does not ESCAPE (POSIX: literal char)",
                  not os.path.exists(os.path.join(evil, "pwn.html")) and
                  not os.path.exists(os.path.join(evil, "pwn.html.bak")),
                  f"HTTP {code}")

            print("\n[3] nothing may have landed outside the project dir")
            for d in (evil, outside):
                leaked = os.listdir(d)
                check(f"no file escaped into {os.path.basename(d)}/", leaked == [], str(leaked))
            check("no absolute-path file created",
                  not os.path.exists("/tmp/ope-absolute-pwn.html"))

            print("\n[4] non-HTML extension still rejected")
            code, _ = post(port, "evil.py", "print('x')")
            check("blocked: non-.html extension", code != 200, f"HTTP {code}")

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [r for r in results if not r[1]]
    print("\n" + "=" * 62)
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILED:")
        for n, _, d in failed:
            print(f"  - {n}  [{d}]")
        return 1
    print("BLOCKED — traversal guard holds on every vector. ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
