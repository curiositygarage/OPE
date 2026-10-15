#!/usr/bin/env python3
"""OPE v2 REAL verification — reads raw HTML via fetch into a global, then sync eval.
- live DOM: exactly 1 injected bar/pill/style
- raw source: ZERO baked toolbar/pill/style
- config entity counts match page
"""
import sys, time, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_helpers import CDP

c = CDP(port=18800, timeout=45)
# Pages under test — point this at YOUR project's pages (must be served on :8899).
PAGES = ['demo.html']
ok = True

EVAL = """
(() => {
  const raw = window.__rawsrc || '';
  const barsLive = document.querySelectorAll('#ope-editbar').length;
  const pillsLive = document.querySelectorAll('#ope-view-toggle').length;
  const stylesLive = document.querySelectorAll('style#ope-v2-style').length;
  const bakedBar = (raw.match(/id="ope-editbar"/g) || []).length;
  const bakedPill = (raw.match(/id="ope-view-toggle"/g) || []).length;
  const bakedStyle = (raw.match(/id="ope-v2-style"/g) || []).length;
  const verRaw = (raw.match(/ope-ver:\\s*(\\d+)/) || [,'none'])[1];
  const cfg = window.OPE_CONFIG;
  const d = cfg ? cfg.draggable.reduce((n,s)=>n+document.querySelectorAll(s).length,0) : -1;
  const e = cfg ? cfg.editable.reduce((n,s)=>n+document.querySelectorAll(s).length,0) : -1;
  return JSON.stringify({barsLive, pillsLive, stylesLive, bakedBar, bakedPill, bakedStyle, verRaw, d, e});
})()
"""

for p in PAGES:
    c.send("Page.navigate", {"url": f"http://127.0.0.1:8899/{p}?real=" + str(int(time.time()))})
    time.sleep(3)
    c.eval("window.__rawsrc = null; fetch(window.location.href.split('?')[0] + '?raw=' + Date.now()).then(r=>r.text()).then(t=>window.__rawsrc=t)")
    time.sleep(1.5)
    s = json.loads(c.eval(EVAL))
    issues = []
    if s['barsLive'] != 1: issues.append(f"live-bars={s['barsLive']}")
    if s['pillsLive'] != 1: issues.append(f"live-pills={s['pillsLive']}")
    if s['stylesLive'] != 1: issues.append(f"live-styles={s['stylesLive']}")
    if s['bakedBar'] > 0: issues.append(f"BAKED-bar={s['bakedBar']}")
    if s['bakedPill'] > 0: issues.append(f"BAKED-pill={s['bakedPill']}")
    if s['bakedStyle'] > 0: issues.append(f"BAKED-style={s['bakedStyle']}")
    if s['d'] <= 0: issues.append(f"drag={s['d']}")
    if s['e'] <= 0: issues.append(f"edit={s['e']}")
    status = "OK" if not issues else "FAIL " + ",".join(issues)
    if issues: ok = False
    print(f"{p:38s} {status}  raw-v{s['verRaw']} live={s['barsLive']}/{s['pillsLive']}/{s['stylesLive']} baked={s['bakedBar']}/{s['bakedPill']}/{s['bakedStyle']} drag={s['d']} edit={s['e']}")

print("\nRESULT:", "ALL PASS" if ok else "ISSUES")
c.close()
