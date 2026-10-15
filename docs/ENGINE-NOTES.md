# OPE v2 — Engine Notes (hard-won rules)

How the engine actually behaves, and the rules that keep it from breaking. These were learned the expensive way (bug reports, lost edits, duplicated toolbars) — **do not regress them**.

---

## Architecture

```
ope.js                      ← shared engine: injects CSS + toolbar, drag, contenteditable text, change tracking
serve.py                    ← static server + JSON save endpoint, auto version bump, changes.md writer, optional notify
each page:
  <!-- ope-ver: 1 -->       ← version marker in <head> (stale-tab guard)
  <script>window.OPE_CONFIG={...}</script>
  <script src="ope.js"></script>
changes.md                  ← append-only edit log (auto-written by serve.py)
```

The engine is a single IIFE. It injects its own `<style>` (`style#ope-v2-style`), toolbar (`#ope-editbar`), and view-mode pill (`#ope-view-toggle`) at runtime — **the page HTML itself never contains the editor UI**.

---

## The 4 hard-won rules (DO NOT regress)

### 0. Strip the OPE UI before serializing

`doSave()` must snapshot `#ope-editbar`, `#ope-view-toggle`, and `style#ope-v2-style`,
remove them from the DOM, serialize `outerHTML`, then restore them. Otherwise the toolbar
**bakes into the saved HTML** and the page renders **2 bars / 2 pills / 2 styles** on next load.

Also strip transient `data-ope-id` + `contenteditable` attributes before serializing.

**Order matters (fixed 2026-08-19):** snapshot the UI FIRST, then strip, then serialize,
then restore. Stripping first leaves the snapshot empty and the toolbar vanishes from the
live page after save.

Verify on the RAW served HTML (fetch the URL, count `id="ope-editbar"` === 0). The live DOM
always has exactly 1 injected copy — that's correct.

**CDP test cache trap:** `?cachebust=` on the page URL does NOT bust the `ope.js`
subresource — a stale cached engine keeps old behaviour. Send `Network.setCacheDisabled` +
`Network.enable` before testing, or version the script src.

### 1. Scope EVERY selector in state CSS

When building `body.ope-dragging <list>` rules, prefix **each** comma-separated selector
with the state class (see the `scoped()` helper in ope.js). A naive `'body.' + list` only
scopes the first selector — the rest become unconditional and their outlines/grabs **leak
into View Mode**.

Verified: View Mode must have 0 elements with a dashed outline.

### 2. Edit-mode affordances must NEVER paint the element

Only `outline` + cursor. No `background` (green tint), no `border-radius` overrides.
Buttons must keep their exact gradient/shadow in edit mode — painting them breaks the
"this is still the real page" illusion.

### 3. Drag baselines

- Static flow elements baseline at `(0,0)` — never `offsetTop` (document-relative, it
  compounds and flies off-page).
- Elements with inline `left`/`top` already set → use those.
- Absolutely-positioned cards/pills → `offsetLeft`/`offsetTop`.

### 4. Save must strip edit state

Remove `ope-dragging` / `ope-view` / `ope-texting` body classes, reset the buttons, and
remove `contenteditable` before serializing — or the saved file is born stuck in edit mode.

---

## Engine behaviour

### Modes

- **View Mode (default on load)** — page is presentation-clean: toolbar hidden, only the
  ✏️ pill visible. After a successful save, the page returns to View Mode.
- **Edit Mode** — toolbar appears (View Mode · Drag Elements · Edit Text · Save · Reload).
- **Drag mode** — `body.ope-dragging`; draggable blocks get blue dashed outline + move on
  mousedown/move/up (HTML: `left`/`top`; SVG: `cx`/`cy`/`x`/`y` per `[data-mi]` group).
- **Text mode** — `body.ope-texting`; editable blocks get green dashed outline +
  `contenteditable`; text changes are diffed on **input** (not just blur) so mid-edit saves
  don't lose changes and synthetic focus/blur (CDP tests) still work.

Drag mode and text mode are **mutually exclusive** — they fight over mousedown vs selection.

### Mouse mechanics

- `MIN_DRAG = 3px` — a mousedown that moves less than 3px is a click, not a drag.
- SVG groups move as a unit via `data-mi` id (circle `cx`/`cy`, text `x`/`y`, line `x1`/`y1`).
- When SVG drag is enabled, drag mode lifts the SVG above cards (`z-index:100;
  pointer-events:none` on the SVG layer, `pointer-events:auto` on `[data-mi]` groups); flow
  elements that should sit above the timeline get `z-index:200`.

### Change tracking

Every editable element gets a transient `data-ope-id`. Text changes are diffed on input
(before/after `innerText`), moves are recorded on mouseup (before/after `left`/`top`).
Changes ride along with the save payload:

```json
{
  "html": "<!DOCTYPE html>\n…",
  "ope_ver": 3,
  "changes": [
    { "type": "move", "id": "card-0", "label": "Example card",
      "before": "left -99px, top 150px", "after": "left -80px, top 140px" },
    { "type": "text", "id": "entity-1", "label": "Example entity",
      "before": "Old heading text", "after": "New heading text" }
  ],
  "page": "index.html"
}
```

### Save flow (client)

1. Blur any active `contenteditable` (captures pending text).
2. Snapshot the OPE UI (order matters — see rule 0).
3. `stripEditState()` — remove UI elements, body classes, `contenteditable`, `data-ope-id`.
4. Serialize `<!DOCTYPE html>\n` + `document.documentElement.outerHTML`.
5. `POST /save?file=<page>` with the JSON payload above.
6. On 409 → show the stale-tab error (user must hard-refresh then save again).
7. On 200 → `setVersionInDom(version)` (rewrites the `ope-ver` comment in the live DOM so
   the current tab stays fresh), clear the change buffer, show `✅ saved vN`, return to View Mode.

---

## Serve.py save endpoint

`POST /save?file=<page>` accepts **JSON** (OPE v2) only, and requires
`Content-Type: application/json`. The raw-HTML fallback was removed deliberately:
`text/plain` is a CORS *simple request* (no preflight), so any page the human browsed
while the server was running could rewrite files here. Requiring JSON forces a preflight,
which this server never answers.

```python
def do_POST(self):
    fname = (parse_qs(urlparse(self.path).query).get('file') or ['index.html'])[0]
    target = os.path.realpath(os.path.join(BASE, fname))
    # A plain target.startswith(BASE) is UNSAFE: a sibling directory whose NAME
    # merely prefixes BASE (".../ope-evil" vs ".../ope") passes it, and the write
    # escapes the project directory. Compare real paths on a path-component
    # boundary instead. (The normpath/startswith form above is the pre-release bug.)
    if os.path.commonpath([BASE, target]) != BASE or os.path.splitext(target)[1] not in ('.html', '.htm'):
        self._send(403, 'forbidden'); return
    # …read body, parse JSON if applicable…
    cur_ver = opever(open(target,'rb').read()) if os.path.exists(target) else 0
    new_ver = opever(data)
    if new_ver < cur_ver:
        self._send(409, 'STALE SAVE REJECTED …'); return
    bumped = re.sub(rb'<!--\s*ope-ver:\s*\d+\s*-->', f'<!-- ope-ver: {cur_ver+1} -->'.encode(), data, count=1)
    if os.path.exists(target): shutil.copy(target, target + '.bak')
    open(target, 'wb').write(bumped)
    self._log_changes(page, cur_ver, cur_ver + 1, changes)
    self._notify(page, cur_ver + 1, changes)
    self._send(200, json.dumps({'ok': True, 'file': fname, 'version': cur_ver + 1, 'changes': len(changes)}), 'application/json')
```

- **Version guard:** rejects when the incoming `ope-ver` is older than the disk version
  (409). Prevents an old tab from clobbering newer edits.
- **Auto-bump:** after a successful save the marker is bumped to `cur_ver + 1`, so every
  other open tab is now stale and will 409 on its next save.
- **Backup:** a save that overwrites an existing file copies the previous version to
  `<page>.bak` first. A first save of a *new* file has nothing to back up, so no `.bak` appears
  until its second save.
- **Change log:** appends to `changes.md`:

  ```
  ## 2026-08-02 11:30 — index.html (v10 → v11)
  - **MOVE** Example card: left -99px, top 150px → left -80px, top 140px
  - **TEXT** Example entity: "Old heading text" → "New heading text"
  ```

- **Optional notify:** if `OPE_NOTIFY_DIR` is set, a JSON notification
  (`ope_changes_<timestamp>.json`) is dropped into that directory after each save, shaped
  for an inbox/sync consumer:

  ```json
  {
    "delivered_at": "…",
    "message": {
      "from": "ope", "to": "listener", "type": "ope_change",
      "content": "Page index.html edited via OPE (saved v11) with 3 change(s). See changes.md for the diff.",
      "payload": {"type": "ope_change", "page": "index.html", "version": 11, "changes": 3},
      "timestamp": "…"
    }
  }
  ```

- **Cache rules:** HTML pages AND `/ope.js` MUST be served with `Cache-Control: no-cache`.
  `SimpleHTTPRequestHandler` sends `Last-Modified` with 1s granularity and no
  `Cache-Control`, so browsers heuristically cache the main document: after a save the file
  on disk is updated but a reload gets 304 (same-second mtime) and shows OLD content.
  Symptom: *"save succeeded but reload shows no changes."* The `end_headers` override in
  serve.py handles this — never remove it.

---

## Wiring checklist (per page)

1. Confirm `</body>` EXISTS first (`grep -c '</body>'`). If missing, patch it in before
   injecting — pages often end `</footer></html>`.
2. Add `<!-- ope-ver: 1 -->` marker in `<head>` if absent.
3. Inject `<script>window.OPE_CONFIG=…</script>` + `<script src="ope.js"></script>` before `</body>`.
4. VERIFY: `grep -c 'ope.js' <page>` must return ≥2 (config + src). Never skip this —
   silent injection failure is a real trap.
5. Audit selectors against the REAL page DOM. Every draggable/editable selector MUST exist
   and be visible. Sweep ALL `<a>` link/button elements and include their class in
   `editable` — containers alone are not enough.
6. Exclude hidden elements (`display:none`) from both lists — zero-rect elements can't be
   dragged/edited and fail tests.
7. End-to-end check: view mode default → edit mode → drag a block → text-edit a block →
   save → changes.md has entry → file has bumped ope-ver.

---

## Testing

`scripts/ope_test.py` runs against a page served by `serve.py`, driven via CDP:

- View default: pill visible, toolbar hidden, 0 dashed outlines.
- Edit toggle: toolbar appears.
- Drag: every draggable selector moves (inline left/top change).
- Text: every editable selector becomes contenteditable and accepts edits.
- Save: version bumped, changes.md grew, notify JSON dropped (when configured).
- **Save-then-restore:** tests that save pollute pages — always restore from `.bak` after,
  or test without saving.
