/* ==========================================================================
 * OPE v2 — On-Page Editor (shared engine)
 * OPE Project Authors · 2026-08-02 · drag blocks, edit wording inline, changes logged to changes.md.
 *
 * Per-page config (define BEFORE this script in each page):
 *   window.OPE_CONFIG = {
 *     page: 'index.html',                       // filename for /save
 *     draggable: ['.card', '.panel', ...],      // blocks/boxes/cards to drag
 *     editable:  ['.title', '.body', ...],      // text blocks to edit inline
 *     svg: true                                 // drag SVG milestone groups ([data-mi])
 *   };
 *
 * Injects: toolbar (#ope-editbar), view-mode pill (#ope-view-toggle), CSS.
 * Save: POST /save?file=<page>  body=JSON {html, ope_ver, changes}
 * ========================================================================== */
(function () {
  'use strict';

  var CFG = window.OPE_CONFIG || {};
  var PAGE = CFG.page || 'index.html';
  var DRAGGABLE = (CFG.draggable || []).join(',');
  var EDITABLE = (CFG.editable || []).join(',');
  var HAS_SVG = !!CFG.svg;
  var MIN_DRAG = 3; // px before a mousedown counts as a move

  // ---------- state ----------
  var bar, dragBtn, textBtn, saveBtn, resetBtn, viewBtn, statusEl, viewToggle, dragOnEl;
  var dragOn = false, textOn = false;
  var dragging = null, startX = 0, startY = 0, startPos = null, moved = false;
  var changes = [];        // {type:'move'|'text', id, label, before, after}
  var textBefore = {};     // el._opeId -> innerText at edit start

  // ---------- css (injected) ----------
  // Selector-group helper: every selector in the comma list must be prefixed with
  // the state class (body.ope-dragging / body.ope-texting). Naive `'body.' + list`
  // only prefixes the FIRST selector -> the rest become UNCONDITIONAL and their
  // outlines/grabs leak into View Mode. Fixed 2026-08-02.
  function scoped(prefix, list) {
    return (list || []).map(function (s) {
      return prefix + ' ' + s.trim();
    }).join(',');
  }
  var css = '' +
    '#ope-editbar{position:fixed;top:12px;right:12px;z-index:99999;display:flex;flex-direction:column;gap:6px;' +
      'background:rgba(11,30,61,.94);border:1px solid rgba(255,255,255,.25);border-radius:12px;padding:10px;' +
      'box-shadow:0 8px 28px rgba(0,0,0,.35);backdrop-filter:blur(4px);max-width:210px;font-family:Segoe UI,Helvetica,Arial,sans-serif}' +
    '#ope-editbar .ope-title{color:#d6e0f5;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;text-align:center}' +
    '#ope-editbar button{display:block;width:100%;background:#1a4480;color:#fff;border:1px solid rgba(255,255,255,.25);' +
      'border-radius:8px;padding:7px 10px;font-size:11px;font-weight:700;cursor:pointer;transition:background .15s;font-family:inherit}' +
    '#ope-editbar button:hover{background:#2553a8}' +
    '#ope-editbar button.active{background:#059669;border-color:#10b981}' +
    '#ope-editbar .ope-hint{color:#bcc8e0;font-size:9.5px;line-height:1.4;text-align:center}' +
    '#ope-editbar .ope-status{color:#7ee2a8;font-size:10px;font-weight:700;text-align:center;min-height:14px}' +
    '#ope-editbar .ope-mode-note{color:#fbbf24;font-size:9.5px;text-align:center;font-weight:700;display:none}' +
    '#ope-view-toggle{position:fixed;bottom:14px;right:14px;z-index:99998;background:rgba(11,30,61,.85);color:#d6e0f5;' +
      'border:1px solid rgba(255,255,255,.25);border-radius:999px;padding:7px 14px;font-size:11px;font-weight:700;cursor:pointer;' +
      'backdrop-filter:blur(4px);box-shadow:0 6px 20px rgba(0,0,0,.3);display:none;transition:background .15s;font-family:inherit}' +
    '#ope-view-toggle:hover{background:#1a4480;color:#fff}' +
    'body.ope-view #ope-editbar{display:none}' +
    scoped('body.ope-dragging', CFG.draggable) + '{cursor:grab;outline:1px dashed rgba(37,99,235,.6);outline-offset:3px}' +
    scoped('body.ope-dragging', CFG.draggable) + ':active{cursor:grabbing}' +
    scoped('body.ope-texting', CFG.editable) + '{outline:1px dashed rgba(5,150,105,.55);outline-offset:2px;cursor:text}' +
    (HAS_SVG ? 'body.ope-dragging .tl-svg{position:relative;z-index:100;pointer-events:none}' +
               'body.ope-dragging .tl-svg [data-mi]{pointer-events:auto}' : '') +
    (HAS_SVG ? 'body.ope-dragging .callout,body.ope-dragging .sec-title,body.ope-dragging .tags,' +
               'body.ope-dragging .tl-card,body.ope-dragging header{position:relative;z-index:200}' : '') +
    '';
  var styleEl = document.createElement('style');
  styleEl.id = 'ope-v2-style';
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  // ---------- toolbar markup (injected) ----------
  function buildToolbar() {
    bar = document.createElement('div');
    bar.id = 'ope-editbar';
    bar.innerHTML =
      '<div class="ope-title">✏️ Edit Mode</div>' +
      '<button id="ope-view" type="button">👁 View Mode</button>' +
      '<button id="ope-drag" type="button">🖐 Drag Elements</button>' +
      '<div class="ope-mode-note" id="ope-dragmode-on">Drag ON — move blocks, then Save</div>' +
      '<button id="ope-text" type="button">✍️ Edit Text</button>' +
      '<div class="ope-mode-note" id="ope-textmode-on">Text ON — click wording to edit, then Save</div>' +
      '<button id="ope-save" type="button">💾 Save to Server</button>' +
      '<button id="ope-reset" type="button">↩️ Reload (undo)</button>' +
      '<div class="ope-hint">Click a green-outlined block to edit its wording. Drag blue-outlined blocks to move. Save writes the page + logs to changes.md.</div>' +
      '<div class="ope-status" id="ope-status"></div>';
    document.body.appendChild(bar);

    viewToggle = document.createElement('button');
    viewToggle.id = 'ope-view-toggle';
    viewToggle.type = 'button';
    viewToggle.textContent = '✏️ Edit Mode';
    document.body.appendChild(viewToggle);

    dragBtn = document.getElementById('ope-drag');
    textBtn = document.getElementById('ope-text');
    saveBtn = document.getElementById('ope-save');
    resetBtn = document.getElementById('ope-reset');
    viewBtn = document.getElementById('ope-view');
    statusEl = document.getElementById('ope-status');
    dragOnEl = document.getElementById('ope-dragmode-on');
    // text-mode note element
    window._opeTextOnEl = document.getElementById('ope-textmode-on');
  }

  // ---------- helpers ----------
  function setStatus(t, ok) {
    statusEl.textContent = t;
    statusEl.style.color = ok ? '#7ee2a8' : '#fca5a5';
    clearTimeout(setStatus._t);
    setStatus._t = setTimeout(function () { statusEl.textContent = ''; }, 5000);
  }

  function opeId(el) {
    if (!el._opeId) {
      var idx = 0;
      var sels = DRAGGABLE.split(',').concat(EDITABLE.split(','));
      for (var i = 0; i < sels.length; i++) {
        var s = sels[i].trim();
        if (!s) continue;
        var all = document.querySelectorAll(s);
        for (var j = 0; j < all.length; j++) {
          if (!all[j]._opeId) all[j]._opeId = (s.replace(/[^a-zA-Z0-9_-]/g, '') + '-' + j);
        }
      }
      if (!el._opeId) el._opeId = 'el-' + Math.floor(Math.random() * 1e6);
    }
    return el._opeId;
  }

  function labelFor(el) {
    // human label: prefer heading/entity text inside, else class+id
    var h = el.querySelector('h1,h2,h3,h4,.entity,.e-entity,.rname,.name');
    if (h && h.textContent.trim()) return h.textContent.trim().slice(0, 42);
    return (el.className || el.tagName) + ' #' + opeId(el);
  }

  function recordMove(el) {
    var id = opeId(el);
    var st = el._opeStart;
    if (!st) return;
    var cur = { left: parseFloat(el.style.left) || 0, top: parseFloat(el.style.top) || 0 };
    var dx = Math.abs(cur.left - st.left), dy = Math.abs(cur.top - st.top);
    if (dx < 1 && dy < 1) return; // no real move
    changes.push({
      type: 'move', id: id, label: labelFor(el),
      before: 'left ' + st.left + 'px, top ' + st.top + 'px',
      after: 'left ' + cur.left + 'px, top ' + cur.top + 'px'
    });
    el._opeStart = null;
  }

  function recordSvgMove(grp) {
    var els = document.querySelectorAll('[data-mi="' + grp + '"]');
    var parts = [];
    els.forEach(function (el) {
      var tag = el.tagName.toLowerCase();
      if (tag === 'circle') parts.push('cx ' + el.getAttribute('cx') + ' cy ' + el.getAttribute('cy'));
      else if (tag === 'text') parts.push('x ' + el.getAttribute('x') + ' y ' + el.getAttribute('y'));
      else if (tag === 'line') parts.push('x1 ' + el.getAttribute('x1') + ' y1 ' + el.getAttribute('y1'));
    });
    if (window._svgStart && window._svgStart[grp]) {
      changes.push({
        type: 'move', id: 'svg-' + grp, label: 'SVG milestone ' + grp,
        before: window._svgStart[grp], after: parts.join('; ')
      });
    }
    window._svgStart = window._svgStart || {};
    window._svgStart[grp] = parts.join('; ');
  }

  // ---------- view / edit mode ----------
  function setViewMode(view) {
    document.body.classList.toggle('ope-view', view);
    viewToggle.style.display = view ? 'block' : 'none';
    if (view) {
      dragOn = false; textOn = false;
      document.body.classList.remove('ope-dragging', 'ope-texting');
      if (dragBtn) { dragBtn.classList.remove('active'); dragBtn.textContent = '🖐 Drag Elements'; }
      if (textBtn) { textBtn.classList.remove('active'); textBtn.textContent = '✍️ Edit Text'; }
      if (dragOnEl) dragOnEl.style.display = 'none';
      if (window._opeTextOnEl) window._opeTextOnEl.style.display = 'none';
      endTextEdit();
    }
  }

  // ---------- text edit mode ----------
  // Field-edit bug (2026-08-20): typing one phrase logged 15+ TEXT changes in changes.md
  // ("THINGS" → "THINGS T" → "THINGS TO" → ...) because textBefore was overwritten on
  // EVERY input. Fix: keep textOrig (original at edit start) and UPSERT one change per
  // element — same id → update .after; new id → push {before: textOrig}.
  var textOrig = {};   // id -> original innerText at edit start (never overwritten)
  function upsertTextChange(id2, el) {
    var after = el.innerText;
    if (textOrig[id2] === after) return;
    for (var ci = 0; ci < changes.length; ci++) {
      if (changes[ci].type === 'text' && changes[ci].id === id2) {
        changes[ci].after = after;  // update in place — ONE entry per element per edit
        return;
      }
    }
    changes.push({ type: 'text', id: id2, label: labelFor(el), before: textOrig[id2], after: after });
  }
  function beginTextEdit() {
    if (!EDITABLE) return;
    document.body.classList.add('ope-texting');
    var els = document.querySelectorAll(EDITABLE);
    for (var i = 0; i < els.length; i++) {
      (function (el) {
        if (el.tagName === 'UL' || el.tagName === 'OL') return; // list containers edited via items
        var id = opeId(el);
        el.setAttribute('contenteditable', 'true');
        el.setAttribute('data-ope-id', id);
        textBefore[id] = el.innerText;
        textOrig[id] = el.innerText;  // ORIGINAL — do not overwrite on input
        // Capture on input — fires on every real keystroke; blur-only loses edits
        // when the user hits Save mid-edit or synthetic focus/blur never fires.
        el.addEventListener('input', function () {
          var id2 = el.getAttribute('data-ope-id');
          upsertTextChange(id2, el);
        });
        el.addEventListener('blur', function () {
          var id2 = el.getAttribute('data-ope-id');
          upsertTextChange(id2, el);
        });
      })(els[i]);
    }
  }

  function endTextEdit() {
    if (!EDITABLE) return;
    var els = document.querySelectorAll(EDITABLE);
    for (var i = 0; i < els.length; i++) {
      els[i].removeAttribute('contenteditable');
    }
  }

  // ---------- drag ----------
  function svgToUser(e) {
    var svg = document.querySelector('.tl-svg');
    if (!svg) return { x: 0, y: 0 };
    var pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    var m = svg.getScreenCTM().inverse();
    var p = pt.matrixTransform(m);
    return { x: p.x, y: p.y };
  }

  document.addEventListener('mousedown', function (e) {
    if (!dragOn) return;
    if (e.target.closest && e.target.closest('#ope-editbar')) return;
    e.preventDefault();

    // SVG group
    if (HAS_SVG) {
      var mi = e.target.closest ? e.target.closest('[data-mi]') : null;
      if (mi && mi.ownerSVGElement) {
        var grp = mi.getAttribute('data-mi');
        var els = document.querySelectorAll('[data-mi="' + grp + '"]');
        if (els.length) {
          dragging = { type: 'svg', grp: grp };
          startPos = {};
          els.forEach(function (el) {
            var tag = el.tagName.toLowerCase();
            if (tag === 'circle') startPos[el] = { x: parseFloat(el.getAttribute('cx')), y: parseFloat(el.getAttribute('cy')) };
            else if (tag === 'text') startPos[el] = { x: parseFloat(el.getAttribute('x')), y: parseFloat(el.getAttribute('y')) };
            else if (tag === 'line') startPos[el] = { x: parseFloat(el.getAttribute('x1')), y: parseFloat(el.getAttribute('y1')) };
          });
          startX = e.clientX; startY = e.clientY; moved = false;
          return;
        }
      }
    }

    var el = e.target.closest ? e.target.closest(DRAGGABLE) : null;
    if (!el) return;
    dragging = { type: 'html', el: el };
    moved = false;
    startX = e.clientX; startY = e.clientY;
    var cs = getComputedStyle(el);
    var wasStatic = (cs.position === 'static');
    if (wasStatic) el.style.position = 'relative';
    var il = parseFloat(el.style.left), it = parseFloat(el.style.top);
    if (!isNaN(il) && !isNaN(it)) {
      // Element already has explicit left/top (previously dragged + saved) — use as base
      startPos = { left: il, top: it };
    } else if (wasStatic || cs.position === 'relative') {
      // In-flow element (static OR position:relative): left/top are OFFSETS from
      // natural position, not absolute coordinates. Starting from offsetLeft/offsetTop
      // double-counts the grid/flow position and flings the box off-screen (drag
      // bug 08-20: "drag a box → it disappeared"). Start at 0,0 and apply delta only.
      startPos = { left: 0, top: 0 };
    } else {
      // Absolutely positioned element without inline left/top: offset is the base
      startPos = { left: el.offsetLeft, top: el.offsetTop };
    }
    el._opeStart = startPos;
    if (el.classList.contains('card-node')) el.style.transform = 'none';
  });

  document.addEventListener('mousemove', function (e) {
    if (!dragging) return;
    var dx = e.clientX - startX, dy = e.clientY - startY;
    if (Math.abs(dx) + Math.abs(dy) > MIN_DRAG) moved = true;
    if (dragging.type === 'svg') {
      var u = svgToUser(e);
      var p0 = svgToUser({ clientX: startX, clientY: startY });
      var udx = u.x - p0.x, udy = u.y - p0.y;
      document.querySelectorAll('[data-mi="' + dragging.grp + '"]').forEach(function (el) {
        var tag = el.tagName.toLowerCase();
        var s = startPos[el];
        if (!s) return;
        if (tag === 'circle') { el.setAttribute('cx', s.x + udx); el.setAttribute('cy', s.y + udy); }
        else if (tag === 'text') { el.setAttribute('x', s.x + udx); el.setAttribute('y', s.y + udy); }
        else if (tag === 'line') { el.setAttribute('x1', s.x + udx); el.setAttribute('y1', s.y + udy); }
      });
    } else {
      dragging.el.style.left = (startPos.left + dx) + 'px';
      dragging.el.style.top = (startPos.top + dy) + 'px';
    }
  });

  document.addEventListener('mouseup', function () {
    if (!dragging) return;
    if (moved) {
      if (dragging.type === 'html') recordMove(dragging.el);
      else recordSvgMove(dragging.grp);
      setStatus('Moved — click 💾 Save to write it', true);
    }
    dragging = null;
  });

  // ---------- save ----------
  function stripEditState() {
    // Remove OPE UI from the DOM so it is NOT serialized into the saved file.
    // The toolbar/pill/style are runtime-injected; next page load re-injects them.
    var ui = document.querySelectorAll('#ope-editbar, #ope-view-toggle, style#ope-v2-style');
    for (var i = 0; i < ui.length; i++) {
      if (ui[i] && ui[i].parentNode) ui[i].parentNode.removeChild(ui[i]);
    }
    document.body.classList.remove('ope-dragging', 'ope-view', 'ope-texting');
    dragOn = false; textOn = false;
    endTextEdit();
  }

  function currentVersion() {
    var m = document.documentElement.outerHTML.match(/<!--\s*ope-ver:\s*(\d+)\s*-->/);
    return m ? parseInt(m[1], 10) : 0;
  }

  function setVersionInDom(v) {
    var commentNodes = [];
    var walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_COMMENT, null, false);
    var n;
    while ((n = walker.nextNode())) commentNodes.push(n);
    commentNodes.forEach(function (c) {
      if (/ope-ver\s*:/.test(c.nodeValue)) c.nodeValue = ' ope-ver: ' + v + ' ';
    });
  }

  function doSave() {
    // capture any pending text edit (blur may not have fired)
    var active = document.activeElement;
    if (active && active.isContentEditable && active.blur) active.blur();

    // Snapshot the OPE UI FIRST, strip it from the serialized DOM (so the toolbar
    // + pill don't get baked into the saved HTML → 2 bars on next load), then
    // restore it so the live page keeps its toolbar. SNAPSHOT MUST COME BEFORE
    // stripEditState() — stripping first leaves uiSnap empty and the toolbar/pill
    // vanish from the live page after save (fixed 2026-08-19; reference bug was
    // the reverse order). ope.js re-injects on every page load.
    var uiSnap = [];
    var uiEls = document.querySelectorAll('#ope-editbar, #ope-view-toggle, style#ope-v2-style');
    for (var u = 0; u < uiEls.length; u++) {
      var elUi = uiEls[u];
      if (!elUi || !elUi.parentNode) continue;
      uiSnap.push({ el: elUi, parent: elUi.parentNode, next: elUi.nextSibling });
    }

    stripEditState();
    // Also strip transient edit attributes from the serialized DOM
    document.querySelectorAll('[data-ope-id]').forEach(function (el) { el.removeAttribute('data-ope-id'); });
    document.querySelectorAll('[contenteditable]').forEach(function (el) { el.removeAttribute('contenteditable'); });

    var html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;
    var ver = currentVersion();
    var payload = { html: html, ope_ver: ver, changes: changes, page: PAGE };

    // restore UI now (fetch is async; the page keeps its toolbar)
    for (var v = 0; v < uiSnap.length; v++) {
      var snap = uiSnap[v];
      if (snap.next && snap.next.parentNode) snap.parent.insertBefore(snap.el, snap.next);
      else snap.parent.appendChild(snap.el);
    }
    var barStill = document.getElementById('ope-editbar');
    if (barStill) { bar = barStill; dragBtn = document.getElementById('ope-drag'); textBtn = document.getElementById('ope-text'); saveBtn = document.getElementById('ope-save'); resetBtn = document.getElementById('ope-reset'); viewBtn = document.getElementById('ope-view'); statusEl = document.getElementById('ope-status'); dragOnEl = document.getElementById('ope-dragmode-on'); window._opeTextOnEl = document.getElementById('ope-textmode-on'); viewToggle = document.getElementById('ope-view-toggle'); }

    fetch('/save?file=' + encodeURIComponent(PAGE), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        if (r.status === 409) return r.text().then(function (t) { throw new Error(t); });
        return r.json().catch(function () { return { ok: false, error: 'bad response' }; });
      })
      .then(function (j) {
        if (j && j.ok) {
          setVersionInDom(j.version);
          changes = [];
          setStatus('✅ saved v' + j.version + ' (' + (j.changes || 0) + ' changes logged)', true);
        } else {
          setStatus('❌ ' + (j && j.error ? j.error : 'save failed'), false);
        }
        setViewMode(true);
      })
      .catch(function (err) {
        setStatus('❌ ' + err.message, false);
        setViewMode(true);
      });
  }


  // ---------- wire up ----------
  function init() {
    buildToolbar();

    viewBtn.addEventListener('click', function () { setViewMode(true); });
    viewToggle.addEventListener('click', function () { setViewMode(false); });

    dragBtn.addEventListener('click', function () {
      if (textOn) { // mutually exclusive
        textBtn.classList.remove('active');
        textBtn.textContent = '✍️ Edit Text';
        window._opeTextOnEl.style.display = 'none';
        document.body.classList.remove('ope-texting');
        endTextEdit();
        textOn = false;
      }
      dragOn = !dragOn;
      document.body.classList.toggle('ope-dragging', dragOn);
      dragBtn.classList.toggle('active', dragOn);
      dragBtn.textContent = dragOn ? '✋ Dragging (click to stop)' : '🖐 Drag Elements';
      dragOnEl.style.display = dragOn ? 'block' : 'none';
      if (!dragOn) setStatus('Drag OFF — layout locked', true);
    });

    textBtn.addEventListener('click', function () {
      if (dragOn) { // mutually exclusive
        dragBtn.classList.remove('active');
        dragBtn.textContent = '🖐 Drag Elements';
        dragOnEl.style.display = 'none';
        document.body.classList.remove('ope-dragging');
        dragOn = false;
      }
      textOn = !textOn;
      document.body.classList.toggle('ope-texting', textOn);
      textBtn.classList.toggle('active', textOn);
      textBtn.textContent = textOn ? '✍️ Editing (click to stop)' : '✍️ Edit Text';
      window._opeTextOnEl.style.display = textOn ? 'block' : 'none';
      if (textOn) beginTextEdit();
      else endTextEdit();
    });

    saveBtn.addEventListener('click', doSave);
    resetBtn.addEventListener('click', function () { location.reload(); });

    // Default: VIEW mode — page opens presentation-clean.
    setViewMode(true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
