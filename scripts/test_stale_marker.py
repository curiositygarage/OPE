#!/usr/bin/env python3
"""test_stale_marker.py — regression gates for the stale-tab guard arming itself.

The guard compares the marker inside the incoming `html` against the marker on disk. A page
with NO marker reads as v0 twice, so `new_ver < cur_ver` is `0 < 0` — false — and every stale
tab would be accepted while SKILL.md advertises 409 protection. These gates pin the fix:

  M1  first save on a marker-less page -> 200, marker inserted, doctype still first
  M2  a stale tab that still lacks a marker -> 409, file untouched
  M3  matching versions -> 200, bumped by exactly one
  M4  a tab carrying a HIGHER marker than disk -> 200, not downgraded

Usage: python3 scripts/test_stale_marker.py        # exit 0 = all gates pass
"""
import http.client
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
results = []


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))


def main():
    port = free_port()
    work = Path(tempfile.mkdtemp(prefix="ope-marker-"))
    for f in ("serve.py", "ope.js", "LICENSE"):
        shutil.copy(REPO / f, work / f)

    # a page with NO ope-ver marker: exactly what an agent-generated page looks like
    bare = ('<!DOCTYPE html>\n<html><head><title>t</title></head>'
            '<body><h1 class="title">hello</h1></body></html>')
    (work / "bare.html").write_text(bare)

    proc = subprocess.Popen([sys.executable, "serve.py", str(port), "127.0.0.1"],
                            cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                c.request("GET", "/")
                if c.getresponse().status == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            print(f"server failed to start on ephemeral port {port}")
            return 2

        def save(html, page="bare.html"):
            body = json.dumps({"html": html, "changes": [], "page": page})
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
            c.request("POST", f"/save?file={page}", body,
                      {"Content-Type": "application/json", "Content-Length": str(len(body))})
            r = c.getresponse()
            raw = r.read().decode("utf-8", "replace")
            c.close()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw

        print("M1 - first save on a marker-less page arms the guard")
        st, j = save(bare)
        on_disk = (work / "bare.html").read_text()
        check("marker-less save -> 200", st == 200, f"got {st} {j}")
        check("marker_inserted reported", isinstance(j, dict) and j.get("marker_inserted") is True)
        check("<!-- ope-ver: 1 --> now in the file", "<!-- ope-ver: 1 -->" in on_disk,
              on_disk.splitlines()[0][:40])
        check("doctype still the first thing (no quirks-mode comment)",
              on_disk.lstrip().lower().startswith("<!doctype"), on_disk[:30])

        print("M2 - the stale tab (still no marker) is now rejected")
        before = on_disk
        st, j = save(bare)
        check("stale marker-less save -> 409", st == 409, f"got {st} {j}")
        check("file untouched by the rejected save", (work / "bare.html").read_text() == before)

        print("M3 - matching versions bump by exactly one")
        v3 = bare.replace("</title>", "</title><!-- ope-ver: 3 -->")
        (work / "bare.html").write_text(v3)
        st, j = save(v3)
        check("v3 tab against v3 disk -> 200", st == 200, f"got {st} {j}")
        check("bumped to v4", isinstance(j, dict) and j.get("version") == 4, str(j))
        check("disk carries v4", "<!-- ope-ver: 4 -->" in (work / "bare.html").read_text())

        print("M4 - a tab NEWER than disk is not downgraded")
        (work / "bare.html").write_text(v3)
        v9 = bare.replace("</title>", "</title><!-- ope-ver: 9 -->")
        st, j = save(v9)
        check("v9 tab against v3 disk -> 200", st == 200, f"got {st} {j}")
        check("version becomes 10, not 4", isinstance(j, dict) and j.get("version") == 10, str(j))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
