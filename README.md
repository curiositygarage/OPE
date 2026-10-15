# OPE — On-Page Editor

**A tiny, zero-dependency editing layer you attach to a plain HTML page, so the person
who cares about how it looks can change it themselves — without a CMS, a build step, a
framework, or a developer in the loop.**

Two files (`ope.js`, `serve.py`) sit next to your HTML. Open the page through the bundled
server and a small **✏️ Edit Mode** pill appears in the corner. Click it and you can
**drag blocks** to new positions and **rewrite the wording inline**, then **save straight
back to the file on disk** — with a change log and an automatic backup of the previous
version.

> MIT License — see [LICENSE](LICENSE). Copyright (c) 2026 OPE Project Authors.

---

## OPE is not an application

This is the most important thing to understand about the project, and it is why OPE is
small enough to read in one sitting.

**OPE is not an app you install, deploy, or run as a service.** It has no database, no
accounts, no admin panel, no dashboard, no config format, no plugin ecosystem, no
installation step, no dependencies, and no build. There is nothing to host and nothing to
maintain.

**OPE is a capability you attach to a page you already have.** It is two files copied
beside your HTML, and one `<script>` tag. That's the entire integration. Delete the two
files and your page is exactly as it was — no residue, no lock-in, no migration to undo.

Think of it less as software and more as *giving the page a handle*: the HTML stays the
single source of truth, and OPE is a temporary grip on it for the duration of an edit.

### What OPE is not

| Not this | Because |
|---|---|
| A CMS | There is no content store. The HTML file **is** the content store. |
| A website builder | It edits an existing page's blocks and wording; it does not compose pages. |
| A design tool | It moves blocks and rewrites text. It does **not** change colours, fonts, sizes, or spacing — those stay in your CSS. |
| A live-editing framework | It is ~1 file of vanilla JS with no runtime dependency. |
| A hosted service | It runs on your machine, bound to localhost by default. |
| A replacement for your editor | It handles the *last mile*. Anything structural still belongs in your code. |

### Why it exists

Static HTML is the highest-fidelity way to hand someone a finished artefact — an
infographic, a one-off report, a profile page, a dashboard. But a static HTML file has a
bad property: **the moment the recipient wants to nudge something, they are stuck.**

Their options are all bad. They can ask a developer (slow, and a whole round-trip for a
nudge). They can open the file in a code editor and hunt through markup (fine for us, a
non-starter for everyone else). Or they can be given a CMS (enormous, stateful, and it
takes ownership of the page away from the file).

OPE is the fourth option. It assumes the person with the opinion about the layout is
**not** the person who wrote the markup, and it hands them exactly the two controls they
actually ask for — *"move this there"* and *"say it like this instead"* — then gets out of
the way.

### What it actually changes

So the scope is honest: OPE records exactly **two** kinds of change.

| Change type | What it does | Stored as |
|---|---|---|
| `move` | Free-drags a configured block to a new position | inline `position` + `left`/`top` on the element |
| `text` | Rewrites a configured element's wording inline | the element's new text content |

Everything else — colour, typeface, type scale, spacing rhythm, borders, shadows — is
authored in the page's HTML/CSS **before** OPE is attached. If you need those adjustable
by a non-developer, the pattern is to pre-author the variants and let OPE place and
word them (see [For AI agents](#-for-ai-agents)).

---

## Quickstart (5 steps)

### 1. Copy the two files

Put `ope.js` and `serve.py` into your project folder, next to the HTML page you want to
edit.

```
your-project/
├── index.html     ← your page
├── ope.js         ← the editor engine
└── serve.py       ← the local server + save endpoint
```

### 2. Add a version marker to your page

Somewhere in `<head>`:

```html
<!-- ope-ver: 1 -->
```

The server uses this marker to detect stale tabs. It is auto-bumped on every save — you
never touch it again.

### 3. Add the OPE config + script

Just before `</body>`:

```html
<!-- ===== ON-PAGE EDITOR v2 ===== -->
<script>
window.OPE_CONFIG = {
  page: 'index.html',                            // filename for /save
  draggable: ['.card', '.header', '.callout'],   // blocks to drag
  editable:  ['.title', '.body', '.btn', '.tag'],// text blocks to edit inline
  svg: false                                     // true if your SVG has [data-mi] groups
};
</script>
<script src="ope.js"></script>
```

That's it — the editor is wired to your page.

### 4. Start the server

```bash
python3 serve.py 8899
```

```
📊 OPE pages at http://127.0.0.1:8899/
   Save endpoint: POST /save?file=index.html (Content-Type: application/json)
   Change log: /path/to/your-project/changes.md
```

### 5. Open the page

Browse to **http://localhost:8899/demo.html** and click the **✏️ Edit Mode** pill in the
bottom-right corner.

---

## Editing UX

### View Mode (default)

The page loads presentation-clean — no toolbar, no outlines, exactly what your audience
sees. The only OPE element is the small **✏️ Edit Mode** pill in the bottom-right corner.

### Edit Mode

Click the pill to open the toolbar:

| Control | What it does |
|---|---|
| 👁 **View Mode** | Exit editing, return to the clean presentation view |
| 🖐 **Drag Elements** | Configured blocks get a blue dashed outline and can be dragged |
| ✍️ **Edit Text** | Configured blocks get a green dashed outline; click one to rewrite it inline |
| 💾 **Save to Server** | Write changes to disk, append to `changes.md`, bump the version |
| ↩️ **Reload (undo)** | Reload the page, discarding unsaved changes |

Drag mode and text mode are **mutually exclusive** — enabling one disables the other.

After a save the page returns to View Mode and reports
`✅ saved v2 (3 changes logged)`.

---

## `OPE_CONFIG` reference

```js
window.OPE_CONFIG = {
  // (required) filename used by the /save?file= endpoint.
  page: 'index.html',

  // (required) CSS selectors for blocks that should be DRAGGABLE.
  // The outermost containers a human would grab — cards, sections, headers.
  draggable: ['.card', '.header', '.callout', 'nav'],

  // (required) CSS selectors for elements whose TEXT is editable inline.
  // The smallest element that holds the exact wording.
  editable: ['.title', '.body', '.btn', '.tag', 'footer'],

  // (optional, default false) Enable only if the page has an SVG containing
  // groups marked data-mi="..." — lets those groups be moved as a unit.
  svg: false
};
```

Every selector must exist in the page's DOM — if a selector matches nothing, the human
simply never gets a handle on that element. See below.

---

## Finding your selectors

1. Open your page in any modern browser.
2. Press **F12** → **Elements / Inspector**.
3. Click the **inspect cursor** (top-left of DevTools) and click the block you want
   draggable.
4. Note its `class`. An element with `class="card blue"` has the selector `.card`.
5. Add it to `draggable`. Repeat for text elements and add them to `editable`.

**Rules of thumb**

- **Draggable = outermost container.** If grabbing a card should move the whole card,
  select the card — not the text inside it.
- **Editable = smallest text element.** An `<h1>`, `<td>`, or `<span>` holding the exact
  wording. Selecting a container makes the human edit too much at once.
- **Skip zero-size elements.** Anything `display:none` or collapsed can't be grabbed.
- **If a button can't be edited, the class is missing from `editable`.** That is almost
  always the cause.

---

## 🤖 For AI agents

This section is written for an AI coding agent (or any automation) that produces HTML
**for a human to look at**. It covers what OPE changes about your workflow, and the two
ways you can drive it.

### Why an agent should attach OPE to the HTML it produces

An agent can generate a beautiful page, but it **cannot see the human's screen**, and it
cannot feel the thing that actually matters at the end: *does this look right to you?*
The usual result is a slow loop — the human describes a nudge in words
("move the date up a bit, make the heading shorter"), the agent re-renders the whole page,
and both sides repeat this five times for what was a two-second drag.

**OPE deletes that loop.** You ship the page wired for editing, and the human makes the
placement and wording calls themselves, directly on the rendered result. You get the
change back as structured data, not as a paragraph of description.

Concretely, attaching OPE turns an N-round-trip conversation into one delivery plus one
file read.

### The division of labour

| You (the agent) own | The human owns |
|---|---|
| Markup and structure | Where blocks sit on the page |
| The design system — colour, type, spacing, hierarchy | The exact wording of text |
| Choosing *which* elements become draggable/editable | Final placement and copy |
| Correct, valid, self-contained HTML | Whether it looks right |

You are not handing over control of the design. You are handing over **position and
copy** — the two things a human can judge instantly and you cannot guess.

### Workflow A — wire the page (the normal case)

Ship three things together: the page, the two OPE files beside it, and a running server.

**Checklist:**

1. Put `ope.js` and `serve.py` next to the HTML.
2. Add `<!-- ope-ver: 1 -->` in `<head>`.
3. Set `window.OPE_CONFIG` before `</body>` with `page`, `draggable`, `editable`.
4. **Verify every selector matches something.** A selector matching nothing is a control
   the human silently never receives — the single most common wiring bug.
5. Start `python3 serve.py <port>`.
6. Send the human `http://localhost:<port>/<page>.html`.

**Choosing selectors — the part that determines whether this works.** Pick
`draggable` as the outermost visual containers and `editable` as the smallest element
holding exact wording:

```js
window.OPE_CONFIG = {
  page: 'report.html',
  // containers a human would pick up and move
  draggable: ['header', 'section.summary', '.card', 'footer'],
  // the exact text they would want to reword
  editable: ['header h1', 'header p', '.card h3', '.card p', '.card .tag', 'footer']
};
```

Two failure modes to avoid:

- **Too coarse on `editable`** — if you mark a whole `<section>` editable, the human gets
  one giant text blob instead of the four elements they wanted to tweak separately.
- **Too fine on `draggable`** — marking inner elements draggable makes blocks shatter
  apart instead of moving as a unit. Drag targets should be containers.

### Workflow B — save programmatically (no browser needed)

You do not need a browser to publish an updated page. `serve.py` exposes the same save
path over HTTP, so an agent can push a revised version directly:

```bash
# JSON form — the payload's marker must not be behind the file on disk
curl -s -X POST 'http://127.0.0.1:8899/save?file=report.html' \
  -H 'Content-Type: application/json' \
  -d '{"html":"<full page HTML>","ope_ver":2,"changes":[],"page":"report.html"}'
```

```json
{"ok": true, "file": "report.html", "version": 3, "changes": 0}
```

A body that is not `Content-Type: application/json` is refused with **415**. The old
raw-HTML fallback is gone: `text/plain` needs no CORS preflight, so it would let any page
you happen to be browsing rewrite files here.

**⚠️ The version rule — read this before your automated write fails.** The guard is
`if payload_marker < disk_marker: reject with 409`. It is a *less-than* test, not an
equality test, and this produces one trap that catches agents:

**The marker is the `<!-- ope-ver: N -->` COMMENT inside `html` — nothing else. The JSON
`ope_ver` field in the payload is accepted and then IGNORED** (measured: `{"html": <no marker>,
"ope_ver": 99}` → **409 "v0"**, while `{"html": <marker 99>, "ope_ver": -5}` → **200**). Send it
for tidiness if you like, but it can never save you, and a 409 will quote a version you thought
you had sent. The table below is about the marker in the HTML:

| Marker in `html` | Disk marker | Result |
|---|---|---|
| absent — **you posted bare HTML with no `<!-- ope-ver: N -->`** | any | **409** — reads as `v0`, always stale |
| equal to disk | v2 | ✅ 200, saved as v3 |
| **higher** than disk | v2 | ✅ 200, saved as v3 — your number is ignored |
| lower than disk | v4 | 409 — a genuinely stale writer |

Two consequences worth internalising:

1. **A page that already exists must be re-posted *with* its marker intact.** If you strip
   the `ope-ver` comment — or generate a fresh page from a template that lacks it — the
   save is rejected as stale. Preserve the marker.
2. **The server always bumps from the file on disk**, never from the number you sent. So
   the returned `version` is authoritative, not your input.

This is the useful bit for an agent: **you inherit the same guardrails the human gets.**
Because the version check is enforced on your write too, an automated push cannot silently
clobber edits the human made in a browser tab.

### The loop you actually want: read `changes.md`

Every save that contains changes appends a human-readable entry to `changes.md` in the
project directory — *what* changed, and the before/after of each edit. (A save with an
empty change set is written but not logged.)

```markdown

## 2026-10-15 18:55 — report.html (v1 → v2)
- **MOVE** Q3 Regional Summary: left 0px, top 0px → left 48px, top 210px
- **TEXT** Regional Summary: "Draft heading" → "Q3 revenue up 12% YoY"
- **TEXT** Margin Note: "placeholder copy" → "Margin held at 41%."
```

*(Format: `## <date> <time> — <page> (v<old> → v<new>)`, then one bullet per change,
labelled `MOVE` or `TEXT`. MOVE coordinates are CSS pixels, space-separated —
`left 48px, top 210px` — and the label is whatever `labelFor(el)` resolved: either the text of a
heading inside the element (trimmed to 42 characters), or `<class-or-tag> #<internal-id>`.
**The block above is an example written to those two rules, not a captured run** — it does not
claim to be engine output. Save once and read your own `changes.md` for the real thing.)*

**Read that file.** It is the human telling you, in structured form, what they actually
wanted — the difference between the wording you chose and the wording they chose is a
direct signal about their voice and preferences. Fold it back into the source, and the
next page you generate needs less correction.

This is the highest-value part of the whole arrangement: an agent that reads its own
change log stops re-litigating the same copy decisions.

### Guardrails you should know about

| Behaviour | Why it matters to you |
|---|---|
| **Version-guarded saves** | A payload whose `ope_ver` marker is **lower** than the file's is rejected with **HTTP 409**. A tab (or an agent) holding an old copy cannot overwrite newer work. |
| **`<page>.bak` on every overwrite** | The previous version is always one file away — safe to be aggressive. The first save of a *new* file has nothing to back up, so no `.bak` appears until its second save. |
| **`changes.md` is append-only** | A durable audit trail of every edit, human or automated. |
| **The toolbar is never written into the page** | Re-reading the file after a save gives you clean HTML — the editor UI is injected at runtime only. |
| **Writes are confined to the project directory** | `/save` only writes `.html`/`.htm` inside the served directory; anything else is **403**. Symlinks are resolved before the check, so a link pointing outside is refused too. |
| **`/save` requires `Content-Type: application/json`** | A cross-origin form or `fetch` can only send `text/plain` without a CORS preflight — so requiring JSON means a third-party page you happen to be browsing **cannot rewrite your files**. A non-JSON body gets **415**. There is still no authentication (by design); this closes the drive-by write, not the local attacker. |
| **The served directory is readable** | Anything that can reach the port can read `*.bak` and `changes.md` — which holds the human's own edited wording. Don't serve a directory containing private files. |
| **Selectors are the whole contract** | If the human says "I couldn't move X", the cause is almost always a missing/incorrect selector in `OPE_CONFIG`. |

### A safe agent pattern

1. Generate the page and choose `draggable` / `editable` deliberately.
2. Serve it and hand the human the URL.
3. When they say it's done, **read `changes.md` and the saved page**.
4. Reconcile: bake their placement and copy into your next revision of the source, so the
   next page starts closer to right.
5. If you must overwrite programmatically, send the **current** `ope_ver` so the version
   guard protects any work in flight.

---

## Security notes

OPE is built for **local / trusted editing**, not hostile public hosting.

- **Localhost by default.** `serve.py` binds `127.0.0.1` only. Nothing on your network can
  reach it unless you explicitly expose it.
- **No authentication on the save endpoint — by design.** Anyone who can reach the port
  can save. This is the deliberate trade: OPE is a local convenience, not a hosted service.
- **Exposing on a LAN (optional):**

  ```bash
  # env vars
  OPE_HOST=0.0.0.0 OPE_PORT=8899 python3 serve.py
  # or positional args
  python3 serve.py 8899 0.0.0.0
  ```

  Only do this on a network you trust.
- **Writes are confined to the project directory.** `/save` only writes `.html`/`.htm`
  files that resolve *inside* the served directory. Everything else — parent escapes,
  sibling directories, absolute paths, percent-encoded traversal — is rejected with
  **HTTP 403**.

  One nuance the test suite asserts deliberately and this line does not: on POSIX,
  `..%5Cope-evil%5Cpwn.html` decodes to a single *literal filename* inside the base, so
  containment holds and nothing lands outside — but the status is **200, not 403**. Escape is
  prevented; the status code is not uniform across vectors. The suite asserts the escape, and
  separately asserts the status only where the vector is genuinely outside.
- **A header-less `application/json` save from the command line is accepted (200) — deliberately.**
  A request that sends no `Content-Type` is refused (415), and a cross-origin *browser* request
  cannot reach the JSON path at all without a CORS preflight, so the CSRF drive-by is closed. What
  stays open is the scripted path: a CLI client that sets `Content-Type: application/json` and sends
  no `Sec-Fetch-Site` saves normally. That is the intended non-browser save path, not a gap — a web
  page cannot reach it.

  This guard is regression-tested:

  ```bash
  python3 scripts/test_traversal.py
  ```

  The test covers the prefix-sibling case (`../ope-evil/`) that a naive
  `str.startswith()` check lets through, plus encoded variants and absolute paths. It
  asserts containment — that nothing is ever written outside the project directory.
- **Optional change notification.** Set `OPE_NOTIFY_DIR` to a directory and a JSON
  notification is dropped there after each save (useful for wiring into an inbox or sync
  folder). Unset = off:

  ```bash
  OPE_NOTIFY_DIR=/path/to/notifications python3 serve.py 8899
  ```

---

## Limitations

- **Static pages only.** OPE reads and writes plain HTML. It does not work on
  server-rendered or JS-generated pages — the saved HTML is whatever the DOM looks like
  at save time.
- **A server is required to save.** The page must be served by `serve.py` (or anything
  implementing `POST /save?file=<page>`). Opening the file directly over `file://` gives
  you drag and text editing, but saving will fail.
- **Position and wording only.** OPE does not change colour, typeface, size, or spacing.
  Those belong in the page's CSS, authored before OPE is attached. If a non-developer must
  control them, pre-author the variants and let OPE handle placement and copy.
- **Inline styles are the storage format.** A drag is saved as inline `position` /
  `left` / `top` on the element. Perfect for static pages; it is not a layout engine.
- **One editor per page.** The toolbar is injected at runtime and is never written into
  the saved HTML.
- **`.bak` recovery.** Every save copies the previous file to `<page>.bak`. If a save goes
  wrong, restore the `.bak` — or read `changes.md` to see exactly what changed.

---

## Project layout

```
ope.js                  ← the editor engine (single IIFE, no dependencies)
serve.py                ← static server + version-guarded save endpoint
demo.html               ← minimal pre-wired example page
changes.md              ← append-only change log (created on first save)
docs/
  ENGINE-NOTES.md       ← hard-won engineering rules — how the engine behaves and why
  DESIGN-NOTES.md       ← design-scale normalisation pass
scripts/
  test_traversal.py     ← regression test for the /save path-boundary guard
  test_hardening.py     ← regression test for the /save CSRF gate + bounded read
  ope_test.py           ← CDP end-to-end test suite (needs Chrome DevTools Protocol)
  cdp_helpers.py        ← CDP helper used by ope_test.py
```

### Running the tests

```bash
python3 scripts/test_traversal.py    # path-boundary guard — no browser needed
python3 scripts/test_hardening.py    # CSRF gate + bounded read — no browser needed
python3 scripts/ope_test.py          # full end-to-end UI suite — needs Chrome + CDP
```

**Prerequisites.** The first three are stdlib-only. `ope_test.py` additionally needs
`pip install websocket-client` and a Chrome running with `--remote-debugging-port=18800` (the
port is hardcoded in `cdp_helpers.py`); it talks to the server on `:8899` and its `PAGES` list
targets `demo.html`, so **the server it points at must actually serve this directory** — if
another project holds `:8899`, you get a 404 for a page that exists here. Its Save step writes
into the served tree, so run it against a scratch copy.

**Publishing.** This tree is the product — its docs and its product tests. Release hygiene
tooling (the leak gate) deliberately does **not** ship here: a gate that carries the names it
hunts for is itself the leak, so it lives outside the tree and is run against a candidate
release before publication. If you fork this, write your own gate rather than trusting ours.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 OPE Project Authors.
