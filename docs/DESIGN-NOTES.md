# Design-Scale Normalization Pass

A mechanical, repeatable pass that turns "hand-made dense" HTML pages into "designed,
restrained" pages. Proven on a 6-page infographic set (index v11→v13, five pages v1→v2,
scores 7/10 → 9/10, ~62% pixel change).

Apply when a page looks amateur/cluttered, or after any OPE wiring, or before showing a
deliverable to a human who expects design craft.

---

## When to run

- The user asks to "make this look professional", "improve the design", "clean up the layout".
- A page has off-scale font sizes (9px, 9.5px, 11.5px, 12.5px, 13.5px), arbitrary
  padding/margin values, or a scattered border-radius set (10+ distinct values).
- Before delivery — the design-craft layer is expected now, not optional.

Load the refactoring/UX-heuristics mindset BEFORE the pass (design principles: hierarchy,
spacing scale, restraint).

---

## Step 1 — Audit (ground the pass, don't guess)

Collect the offenders per page:

```bash
grep -oE "font-size:[0-9.]+px" <page>.html | sort -u
grep -oE "(padding|margin)[:-][0-9.]+px" <page>.html | grep -oE "[0-9.]+px" | sort -u
grep -oE "border-radius:[0-9.]+px" <page>.html | sort -u
```

Score against an 8-point design diagnostic: hierarchy reads clearly? works in
grayscale? enough white space? labels vs values distinguished? spacing on a scale? width
constrained? contrast? shadows? Report the score before/after — the score delta is the
proof of maturity.

---

## Step 2 — Snap to scales

### Type scale (compact infographic variant)

`10, 11, 12, 14, 15, 16, 18, 20, 24`

- H1 → 24px (hero), media-query H1 → 20px
- The money-line callout → **16px** (must dominate; was 12.5px — the #1 hierarchy fix)
- Card entity / country name → 15-18px bold
- Body / kv / points → 14px
- Metadata (sub, when, tags) → 12-14px
- Micro labels (duration badge, metric chips, confidence badges) → 10-11px
- **NO sub-10px text anywhere** (was 9px/9.5px — readability red flag)

### Spacing scale

`4, 8, 16, 24, 32, 48, 64` only. Snap: 3→4, 5→4/8, 6→8, 7→8, 10→8/12, 11→12, 12→12,
13→16, 14→16, 18→16/24, 20→24, 22→24, 26→24/32, 28→32, 30→32, 34→32, 38→32/48, 40→48.

Header padding 28/40 → 32/48. Card body 10/14/12 → 16 uniform. Section padding 28→32.

### Border-radius set

`{12, 16, 999}` (+ 6 for tiny chips/badges). Cards: 12→16 for big containers, 12 for
medium, 999 for pills/buttons/tags. **10+ distinct radii → 3.**

### Hierarchy rebuild (blur test)

Blur the page / squint: what is the ONE thing it must say? Make that dominate.
Money line > section title > entity > metadata — by size/weight/color, not color alone.
Bump the money-line callout and card entity; de-emphasize metadata with smaller/lighter.

---

## Step 3 — Apply (discipline)

1. `cp <page>.html <page>.html.pre-refactor-YYYYMMDD` — zero destruction; backups are the lineage.
2. Bump `<!-- ope-ver: N -->` in the file yourself (direct edits bypass /save).
3. Edit CSS only — preserve palette/theme (dark pages keep their colors; the scale fix is theme-agnostic).
4. One style-block rewrite per page is faster and more auditable than 20 micro-patches.

---

## Step 4 — Verify (CDP, prove it)

1. **curl FIRST** — `curl -s http://127.0.0.1:8899/<page> | grep -o 'ope-ver: [0-9]*'` proves the SERVER has the new file (browser cache lies).
2. **Cache-bust** — navigate to `url?cb=<timestamp>` (a byte-identical screenshot = cache artifact, NOT "nothing changed").
3. **Computed styles** — eval `getComputedStyle` on the money-line/entity/card/button: confirm 16px/15px/12px/999px actually applied.
4. **OPE single-injection** — on every page: `document.querySelectorAll('#ope-editbar').length === 1`, same for `#ope-view-toggle` and `style#ope-v2-style`.
5. **Selector resolution** — all draggable/editable groups still resolve in the DOM (config selectors unchanged by CSS edits).
6. **No horizontal overflow** — `document.body.scrollWidth <= window.innerWidth`.
7. **Pixel-diff** — sample before/after screenshots (e.g. stride 4): expect 40-65% changed pixels for a real pass.
8. Log every page change in `changes.md` with DESIGN entries.

---

## Reference results

- index: design-diagnostic score 7/10 → 9/10, heuristic-usability pass 7/10 → 9/10, 62.2% pixel change.
- All pages: type scale normalized, spacing snapped, radius `{12,16,999}`, versions bumped, backups kept.
- Dark pages got the same pass with palette preserved.
