# ruff: noqa: E501
"""Static preview website for the ticker: one self-contained ``index.html``.

``write_index(out_dir, manifest)`` embeds the manifest as a ``<script>`` constant (no fetch(),
no CDN) so the page works from GitHub Pages and from ``file://``. The pixel inspector draws
each frame from the manifest's ``pixels`` hex string into a ``<canvas>`` itself, because
reading PNG pixels back is blocked on ``file://``.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_TITLE = "Sportsticker preview"

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>__TITLE__</title>
<link rel="icon" href="data:,">
<style>
:root{--bg:#000;--panel:#0c0c0e;--panel2:#141417;--line:#26262b;--text:#e9e9ec;--muted:#8d8d96;--accent:#ffb23e;--accent-dim:#3a2a10}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{color-scheme:dark;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;overflow-x:hidden}
body.modal-open{overflow:hidden}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:clamp(22px,4.5vw,32px);line-height:1.15;margin:0 0 6px;letter-spacing:.01em}
h2{font-size:19px;margin:34px 0 4px}
h3{font-size:15px;margin:18px 0 8px;color:var(--text)}
p{margin:0 0 8px}
.muted{color:var(--muted)}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;color:var(--muted);font-size:13px;margin-bottom:10px}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;border:1px solid var(--line);font-size:12px;color:var(--text);background:var(--panel2)}
.pill.live{border-color:#1f6b3a;color:#6ee79a}
.pill.replay{border-color:#2d4f86;color:#8db8ff}
.pill.fake-live{border-color:#7a5a1a;color:var(--accent)}
.note{border-left:3px solid var(--accent);background:var(--panel);padding:8px 12px;margin:12px 0;border-radius:0 6px 6px 0}
.rotation{margin:18px 0 0;background:#000;border:1px solid var(--line);border-radius:8px;padding:10px;text-align:center}
.rotation img{max-width:100%;height:auto;display:block;margin:0 auto}
.rotation figcaption{margin-top:6px;font-size:13px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:14px;margin-top:12px}
.card{all:unset;box-sizing:border-box;display:block;cursor:pointer;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;transition:border-color .12s,transform .12s}
.card:hover{border-color:#4a4a52}
.card:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.card .thumb{display:block;background:#000;aspect-ratio:2/1;overflow:hidden}
.card .thumb img{display:block;width:100%;height:100%;object-fit:contain}
.card .thumb img.px{image-rendering:pixelated}
.card .body{display:block;padding:9px 12px 11px}
.card .t{display:block;font-weight:600;overflow-wrap:anywhere}
.card .s{display:block;font-size:13px;color:var(--muted);overflow-wrap:anywhere}
.card .tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}
.badge{font-size:11px;padding:1px 7px;border-radius:4px;border:1px solid var(--accent-dim);color:var(--accent);text-transform:uppercase;letter-spacing:.04em}
.badge.dim{border-color:var(--line);color:var(--muted);text-transform:none}
.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:10px}
.cmp figure{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.cmp img{display:block;width:100%;height:auto;background:#000}
.cmp figcaption{padding:5px 10px;font-size:13px;color:var(--muted)}
.cmp figcaption b{color:var(--accent);margin-right:6px}
footer{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
noscript p{color:var(--accent)}
/* inspector */
.overlay{position:fixed;inset:0;z-index:10;background:#040405;overflow-y:auto;overscroll-behavior:contain}
.overlay[hidden]{display:none}
.panel{max-width:1120px;margin:0 auto;padding:12px 16px 28px;outline:none}
.ph{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}
.ph h2{margin:0;font-size:20px;overflow-wrap:anywhere}
.ph p{margin:0;color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.nav{display:flex;gap:6px;align-items:center;flex:none}
.nav span{font-size:13px;color:var(--muted);min-width:46px;text-align:center;font-variant-numeric:tabular-nums}
button,.btn{font:inherit;font-size:14px;color:var(--text);background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:6px 12px;cursor:pointer;text-decoration:none;display:inline-block;line-height:1.3}
button:hover,.btn:hover{border-color:#5a5a62}
button:focus-visible,.btn:focus-visible,summary:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.nav button{padding:4px 11px;font-size:18px;line-height:1.2}
.views{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 8px}
.views button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#000;font-weight:600}
.readout{display:flex;align-items:center;gap:10px;height:34px;margin:2px 0 8px;font:13px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--text);white-space:nowrap;overflow:hidden}
.sw{flex:none;width:22px;height:22px;border-radius:4px;border:1px solid #444;background:#000}
.readout .dim{color:var(--muted)}
.stage{width:100%;background:#000;border:1px solid var(--line);border-radius:6px;overflow:hidden;line-height:0}
.stage canvas{display:block;touch-action:pan-y;cursor:crosshair}
.stage img.fallback{display:block;width:100%;height:auto}
.stage .msg{line-height:1.4;padding:8px 12px;color:var(--muted);font-size:13px}
.actual{display:flex;flex-wrap:wrap;gap:18px 26px;align-items:flex-end;padding:14px;line-height:1.3}
.actual figure{margin:0;max-width:100%}
.actual canvas{image-rendering:pixelated;border:1px solid #222;max-width:100%;height:auto;cursor:crosshair}
.actual figcaption{font-size:12px;color:var(--muted);margin-top:4px}
.actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0}
.actions .links{margin-left:auto;font-size:13px;color:var(--muted);display:flex;gap:12px}
.actions .links a{color:var(--accent)}
details{margin-top:8px;border:1px solid var(--line);border-radius:6px;background:var(--panel)}
summary{cursor:pointer;padding:8px 12px;font-size:14px}
.txtbox{padding:0 12px 12px}
pre{margin:0 0 10px;padding:8px;overflow-x:auto;background:#000;border:1px solid var(--line);border-radius:4px;font:11.5px/1.35 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#cfcfd4;max-width:100%}
.pal{display:flex;flex-wrap:wrap;gap:4px 14px;font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--muted)}
.pal span{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.pal i{display:inline-block;width:12px;height:12px;border:1px solid #444;border-radius:2px}
.pal b{color:var(--text);font-weight:600}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
@media (max-width:520px){
 .wrap{padding:14px 16px 32px}
 .panel{padding:10px 16px 24px}
 .actions .links{margin-left:0;width:100%}
 .ph h2{font-size:18px}
}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1 id="h-title">__TITLE__</h1>
<div class="meta" id="h-meta"></div>
<p class="muted" id="h-what">Exact pixels of a 64&times;32 LED panel. Click any slide to inspect pixels.</p>
<div id="h-note"></div>
</header>
<noscript><p>This page needs JavaScript to show the slides and the pixel inspector.</p></noscript>
<main id="main"></main>
<footer id="foot"></footer>
</div>

<div id="modal" class="overlay" hidden>
<div class="panel" id="panel" role="dialog" aria-modal="true" aria-labelledby="m-title" tabindex="-1">
 <div class="ph">
  <div><h2 id="m-title"></h2><p id="m-sub"></p></div>
  <div class="nav">
   <button type="button" id="m-prev" aria-label="Previous slide" title="Previous (Left arrow)">&lsaquo;</button>
   <span id="m-count" aria-live="polite"></span>
   <button type="button" id="m-next" aria-label="Next slide" title="Next (Right arrow)">&rsaquo;</button>
   <button type="button" id="m-close" aria-label="Close inspector" title="Close (Esc)">&times;</button>
  </div>
 </div>
 <div class="views" role="group" aria-label="View mode" id="views">
  <button type="button" data-view="led" aria-pressed="true">LED</button>
  <button type="button" data-view="grid" aria-pressed="false">Grid</button>
  <button type="button" data-view="actual" aria-pressed="false">Actual size</button>
  <button type="button" data-view="gif" aria-pressed="false" id="v-gif" hidden>Animation</button>
 </div>
 <div class="readout" id="readout" aria-live="polite"><span class="sw" id="r-sw"></span><span id="r-txt"></span></div>
 <div class="stage" id="stage"></div>
 <div class="actions">
  <button type="button" id="b-copy">Copy pixel array</button>
  <a class="btn" id="b-dl" download="pixels.json" href="#">Download .json</a>
  <span class="links" id="m-links"></span>
 </div>
 <details id="txt">
  <summary>Pixel array as text</summary>
  <div class="txtbox">
   <p class="muted" style="font-size:13px">Each pixel is a 2-character token: <code>..</code> is off, anything else is a palette entry below. Rows are y, columns are x, grouped by 8.</p>
   <pre id="txt-pre" tabindex="0"></pre>
   <div class="pal" id="txt-pal"></div>
  </div>
 </details>
</div>
</div>

<script>const MANIFEST = __MANIFEST__;</script>
<script>
(function () {
"use strict";
var M = (typeof MANIFEST === "object" && MANIFEST) || {};
var W = +M.width || 64, H = +M.height || 32;
var $ = function (s) { return document.querySelector(s); };

function el(tag, props) {
  var e = document.createElement(tag);
  if (props) for (var k in props) {
    var v = props[k];
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (var i = 2; i < arguments.length; i++) {
    var c = arguments[i];
    if (c != null && c !== false) e.append(c);
  }
  return e;
}
function pad2(n) { return String(n).padStart(2, "0"); }
function fmtTime(s, tz) {
  var d = new Date(s);
  if (isNaN(d)) return String(s);
  var base = { dateStyle: "medium", timeStyle: "short" };
  try { return d.toLocaleString("en-US", Object.assign({ timeZone: tz || undefined, timeZoneName: "short" }, base)); }
  catch (e) { try { return d.toLocaleString("en-US", base); } catch (e2) { return String(s); } }
}
function store(k, v) { try { if (v === undefined) return localStorage.getItem("st-" + k); localStorage.setItem("st-" + k, v); } catch (e) {} return null; }

/* ---------- flatten items ---------- */
var items = [];
(M.sections || []).forEach(function (s) {
  (s.items || []).forEach(function (it) { it._sec = s.title || ""; it._id = it.id || ("item-" + items.length); items.push(it); });
});
var N = items.length;

/* ---------- header ---------- */
(function header() {
  var meta = $("#h-meta");
  if (M.generated_at) {
    meta.append(el("span", null, "Generated ", el("time", { datetime: M.generated_at, text: fmtTime(M.generated_at, M.timezone) })));
  }
  if (M.source) meta.append(el("span", null, "Source ", el("span", { class: "pill " + M.source, text: String(M.source).replace(/-/g, " ") })));
  meta.append(el("span", { text: W + "×" + H + " px" }));
  if (M.note) $("#h-note").append(el("p", { class: "note", text: M.note }));
})();

/* ---------- page body ---------- */
var main = $("#main");
(function body() {
  var r = M.rotation;
  if (r && r.gif) {
    var cap = [];
    if (r.slides) cap.push(r.slides + " slides");
    if (r.seconds) cap.push(r.seconds + " s per rotation");
    main.append(el("figure", { class: "rotation" },
      el("img", { src: r.gif, alt: "Animated GIF of the full slide rotation as it plays on the panel" }),
      el("figcaption", { text: "Full rotation as it plays on the panel" + (cap.length ? " · " + cap.join(" · ") : "") })));
  }
  var cmps = (M.comparisons || []).filter(function (c) { return c && c.images; });
  if (cmps.length) {
    var sec = el("section", null, el("h2", { text: "Layout comparison" }),
      el("p", { class: "muted", text: "The same game in each layout." }));
    cmps.forEach(function (c) {
      sec.append(el("h3", { text: c.title || "" }));
      var g = el("div", { class: "cmp" });
      Object.keys(c.images).forEach(function (k) {
        var label = k.length <= 1 ? k.toUpperCase() : k.charAt(0).toUpperCase() + k.slice(1);
        g.append(el("figure", null,
          el("img", { src: c.images[k], alt: (c.title || "Slide") + ", layout " + label, loading: "lazy" }),
          el("figcaption", null, el("b", { text: label }))));
      });
      sec.append(g);
    });
    main.append(sec);
  }
  var idx = 0;
  (M.sections || []).forEach(function (s) {
    var sec = el("section", null, el("h2", { text: s.title || "Slides" }));
    if (s.description) sec.append(el("p", { class: "muted", text: s.description }));
    var g = el("div", { class: "grid" });
    (s.items || []).forEach(function (it) {
      var i = idx++;
      var src = it.led || it.grid || it.raw;
      var alt = (it.title || it._id) + (it.subtitle ? ", " + it.subtitle : "");
      var tags = el("span", { class: "tags" });
      if (it.layout) tags.append(el("span", { class: "badge", text: "Layout " + it.layout }));
      if (it.duration) tags.append(el("span", { class: "badge dim", text: it.duration + " s" }));
      if (it.gif) tags.append(el("span", { class: "badge dim", text: "animation" }));
      var thumb = el("span", { class: "thumb" }, src ? el("img", { src: src, alt: alt, loading: "lazy", class: !it.led && !it.grid ? "px" : "" }) : null);
      g.append(el("button", { type: "button", class: "card", "data-i": i, "aria-label": "Inspect pixels: " + alt },
        thumb, el("span", { class: "body" },
          el("span", { class: "t", text: it.title || it._id }),
          it.subtitle ? el("span", { class: "s", text: it.subtitle }) : null, tags)));
    });
    sec.append(g);
    main.append(sec);
  });
  if (!N && !cmps.length && !(r && r.gif)) main.append(el("p", { class: "muted", text: "No slides in this snapshot." }));
  if (!M.logos) $("#foot").textContent = "Logos are not shown on this public page.";
  main.addEventListener("click", function (ev) {
    var b = ev.target.closest(".card");
    if (b) openAt(+b.getAttribute("data-i"), b);
  });
})();

/* ---------- pixel data ---------- */
function decode(it) {
  if (it._px !== undefined) return it._px;
  var p = it.pixels, out = null;
  if (typeof p === "string" && p.length === W * H * 6 && /^[0-9a-fA-F]+$/.test(p)) {
    out = new Uint8Array(W * H * 3);
    for (var i = 0; i < out.length; i++) out[i] = parseInt(p.substr(i * 2, 2), 16);
  }
  it._px = out;
  return out;
}
function hexAt(px, i) {
  var h = "#";
  for (var k = 0; k < 3; k++) h += pad2(px[i * 3 + k].toString(16));
  return h;
}
function derive(it) {
  if (it._d) return it._d;
  var px = decode(it);
  if (!px) return null;
  var hexes = [], counts = new Map(), i;
  for (i = 0; i < W * H; i++) {
    var h = hexAt(px, i);
    hexes.push(h);
    counts.set(h, (counts.get(h) || 0) + 1);
  }
  var lit = Array.from(counts).filter(function (e) { return e[0] !== "#000000"; })
    .sort(function (a, b) { return b[1] - a[1] || (a[0] < b[0] ? -1 : 1); });
  var tok = new Map([["#000000", ".."]]);
  lit.forEach(function (e, n) { tok.set(e[0], n < 1295 ? pad2((n + 1).toString(36).toUpperCase()) : "??"); });
  var rows = [];
  for (var y = 0; y < H; y++) rows.push(hexes.slice(y * W, (y + 1) * W));
  var json = "[\n" + rows.map(function (r) { return " " + JSON.stringify(r); }).join(",\n") + "\n]\n";
  return (it._d = { hexes: hexes, lit: lit, tok: tok, rows: rows, json: json, off: counts.get("#000000") || 0 });
}
function textView(d) {
  var head = "   ", y, g;
  for (g = 0; g < W; g += 8) head += (g ? "  " : "") + String(g).padEnd(Math.min(8, W - g) * 3 - 1);
  var lines = [head];
  for (y = 0; y < H; y++) {
    var line = pad2(y) + " ";
    for (g = 0; g < W; g += 8) {
      line += (g ? "  " : "") + d.rows[y].slice(g, g + 8).map(function (h) { return d.tok.get(h); }).join(" ");
    }
    lines.push(line);
  }
  return lines.join("\n");
}

/* ---------- inspector ---------- */
var modal = $("#modal"), stage = $("#stage"), cur = -1, opener = null;
var view = store("view") || "led";
var pinned = null, hover = null, geom = null, cv = null, base = document.createElement("canvas");
var dlUrl = null;

function effView(it) { return view === "gif" && !it.gif ? "led" : view; }

function readout() {
  var it = items[cur], px = it && decode(it), p = hover || pinned;
  var sw = $("#r-sw"), t = $("#r-txt");
  t.textContent = "";
  if (!px) { sw.style.background = "#000"; t.append(el("span", { class: "dim", text: "No pixel data in this manifest." })); return; }
  if (!p) { sw.style.background = "#000"; t.append(el("span", { class: "dim", text: "Hover or tap a pixel" })); return; }
  var i = p.y * W + p.x, h = hexAt(px, i), off = h === "#000000";
  sw.style.background = off ? "#000" : h;
  t.append("x " + p.x + ", y " + p.y + "  ", el("b", { text: off ? "off" : h }));
  if (!off) t.append(el("span", { class: "dim", text: "  rgb(" + px[i * 3] + ", " + px[i * 3 + 1] + ", " + px[i * 3 + 2] + ")" }));
  if (!hover && pinned) t.append(el("span", { class: "dim", text: "  pinned" }));
}

function layout() {
  var cssW = Math.floor(stage.clientWidth);
  if (cssW < 60) return false;
  var dpr = Math.min(window.devicePixelRatio || 1, 3);
  var cell0 = cssW / W, font = Math.max(10, Math.min(13, cell0 * 0.7)), m = Math.round(font + 9);
  var cell = (cssW - m) / W, cssH = Math.round(m + cell * H);
  geom = { cssW: cssW, cssH: cssH, dpr: dpr, font: font, m: m, cell: cell };
  cv.width = base.width = Math.round(cssW * dpr);
  cv.height = base.height = Math.round(cssH * dpr);
  cv.style.width = cssW + "px";
  cv.style.height = cssH + "px";
  return true;
}
function drawBase(it) {
  var px = decode(it), g = base.getContext("2d"), q = geom, m = q.m, c = q.cell, x, y;
  g.setTransform(q.dpr, 0, 0, q.dpr, 0, 0);
  g.fillStyle = "#000";
  g.fillRect(0, 0, q.cssW, q.cssH);
  var led = effView(it) === "led";
  for (y = 0; y < H; y++) for (x = 0; x < W; x++) {
    var i = y * W + x, on = px[i * 3] | px[i * 3 + 1] | px[i * 3 + 2];
    var col = on ? "rgb(" + px[i * 3] + "," + px[i * 3 + 1] + "," + px[i * 3 + 2] + ")" : (led ? "#1b1b1b" : "#000");
    g.fillStyle = col;
    if (led) {
      g.beginPath();
      g.arc(m + (x + 0.5) * c, m + (y + 0.5) * c, c * 0.43, 0, 6.2832);
      g.fill();
    } else {
      g.fillRect(m + x * c, m + y * c, c, c);
    }
  }
  if (!led) {
    var minor = [], major = [];
    for (x = 0; x <= W; x++) (x % 8 ? minor : major).push(x);
    g.lineWidth = 1;
    var lines = function (list, color, horiz) {
      g.strokeStyle = color; g.beginPath();
      list.forEach(function (n) {
        if (horiz) { var yy = Math.round(m + n * c) + 0.5; g.moveTo(m, yy); g.lineTo(m + W * c, yy); }
        else { var xx = Math.round(m + n * c) + 0.5; g.moveTo(xx, m); g.lineTo(xx, m + H * c); }
      });
      g.stroke();
    };
    var minY = [], majY = [];
    for (y = 0; y <= H; y++) (y % 8 ? minY : majY).push(y);
    if (c >= 5) { lines(minor, "#2b2b2b", false); lines(minY, "#2b2b2b", true); }
    lines(major, "#686868", false); lines(majY, "#686868", true);
  }
  g.fillStyle = "#8d8d96"; g.strokeStyle = "#555"; g.lineWidth = 1;
  g.font = q.font + "px ui-monospace,Menlo,Consolas,monospace";
  g.textBaseline = "alphabetic";
  g.beginPath();
  for (x = 0; x < W; x += 8) {
    g.fillText(String(x), m + x * c + 2, m - 5);
    g.moveTo(Math.round(m + x * c) + 0.5, m - 4); g.lineTo(Math.round(m + x * c) + 0.5, m);
  }
  for (y = 0; y < H; y += 8) {
    g.fillText(String(y), 1, m + y * c + q.font);
    g.moveTo(m - 4, Math.round(m + y * c) + 0.5); g.lineTo(m, Math.round(m + y * c) + 0.5);
  }
  g.stroke();
}
function paint() {
  if (!cv || !geom) return;
  var g = cv.getContext("2d"), q = geom, c = q.cell, m = q.m;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.drawImage(base, 0, 0);
  g.setTransform(q.dpr, 0, 0, q.dpr, 0, 0);
  var mark = function (p, color, w) {
    g.fillStyle = "rgba(255,255,255,0.09)";
    g.fillRect(m, m + p.y * c, W * c, c);
    g.fillRect(m + p.x * c, m, c, H * c);
    g.fillStyle = "rgba(255,178,62,0.45)";
    g.fillRect(m + p.x * c, 0, c, m - 1);
    g.fillRect(0, m + p.y * c, m - 1, c);
    g.strokeStyle = color; g.lineWidth = w;
    g.strokeRect(m + p.x * c + w / 2, m + p.y * c + w / 2, c - w, c - w);
  };
  if (pinned && hover && (pinned.x !== hover.x || pinned.y !== hover.y)) mark(pinned, "#ffb23e", 2);
  var p = hover || pinned;
  if (p) mark(p, "#fff", 2);
}
function redraw() {
  var it = items[cur];
  if (!cv || !it || !decode(it) || !stage.contains(cv)) return;
  if (layout()) { drawBase(it); paint(); }
}

function setHover(p, pin) {
  var changed = !hover !== !p || (p && hover && (p.x !== hover.x || p.y !== hover.y));
  hover = p;
  if (pin && p) { pinned = p; changed = true; }
  if (changed) { readout(); paint(); }
}
function bindPicker(canvas, locate) {
  var pick = function (ev) { return locate(ev, canvas.getBoundingClientRect()); };
  canvas.addEventListener("pointermove", function (ev) { setHover(pick(ev), false); });
  canvas.addEventListener("pointerdown", function (ev) { setHover(pick(ev), true); });
  canvas.addEventListener("pointerleave", function () { setHover(null, false); });
  canvas.addEventListener("pointercancel", function () { setHover(null, false); });
}
function inRange(x, y) { return x >= 0 && y >= 0 && x < W && y < H ? { x: x, y: y } : null; }

function renderStage() {
  var it = items[cur], v = effView(it), px = decode(it);
  stage.textContent = "";
  cv = null;
  Array.prototype.forEach.call(document.querySelectorAll("#views button"), function (b) {
    b.setAttribute("aria-pressed", String(b.getAttribute("data-view") === v));
  });
  if (v === "gif") {
    stage.append(el("img", { class: "fallback", src: it.gif, alt: (it.title || "") + " animation" }));
  } else if (!px) {
    var src = it.led || it.grid || it.raw;
    if (src) stage.append(el("img", { class: "fallback", src: src, alt: it.title || "" }));
    stage.append(el("div", { class: "msg", text: "This manifest has no pixel data for this slide, so the inspector can only show the PNG." }));
  } else if (v === "actual") {
    var tmp = document.createElement("canvas");
    tmp.width = W; tmp.height = H;
    var data = new ImageData(W, H);
    for (var i = 0; i < W * H; i++) {
      data.data[i * 4] = px[i * 3]; data.data[i * 4 + 1] = px[i * 3 + 1]; data.data[i * 4 + 2] = px[i * 3 + 2]; data.data[i * 4 + 3] = 255;
    }
    var wrap = el("div", { class: "actual" });
    [1, 2, 4].forEach(function (k) {
      var c = el("canvas", { width: W, height: H, role: "img", "aria-label": (it.title || "slide") + " at " + k + "x" });
      c.getContext("2d").putImageData(data, 0, 0);
      c.style.width = W * k + "px";
      bindPicker(c, function (ev, r) { return inRange(Math.floor((ev.clientX - r.left) / r.width * W), Math.floor((ev.clientY - r.top) / r.height * H)); });
      wrap.append(el("figure", null, c, el("figcaption", { text: k + "×  (" + W * k + "×" + H * k + " px)" })));
    });
    stage.append(wrap);
  } else {
    cv = el("canvas", { role: "img", "aria-label": (it.title || "slide") + " pixel view" });
    stage.append(cv);
    bindPicker(cv, function (ev, r) {
      if (!geom) return null;
      var s = r.width / geom.cssW;
      return inRange(Math.floor(((ev.clientX - r.left) / s - geom.m) / geom.cell), Math.floor(((ev.clientY - r.top) / s - geom.m) / geom.cell));
    });
    redraw();
  }
  readout();
}

function renderText() {
  var it = items[cur], d = derive(it), pre = $("#txt-pre"), pal = $("#txt-pal");
  pal.textContent = "";
  if (!d) { pre.textContent = "No pixel data."; return; }
  pre.textContent = textView(d);
  pal.append(el("span", null, el("i", { style: "background:#000" }), el("b", { text: ".." }), " off ×" + d.off));
  d.lit.forEach(function (e) {
    pal.append(el("span", null, el("i", { style: "background:" + e[0] }), el("b", { text: d.tok.get(e[0]) }), " " + e[0] + " ×" + e[1]));
  });
}

function show(i) {
  cur = i;
  var it = items[i], d = derive(it);
  pinned = hover = null;
  $("#m-title").textContent = it.title || it._id;
  $("#m-sub").textContent = [it.subtitle, it.layout ? "Layout " + String(it.layout).toUpperCase() : "", it.duration ? it.duration + " s" : "", it._sec].filter(Boolean).join(" · ");
  $("#m-count").textContent = (i + 1) + " / " + N;
  $("#v-gif").hidden = !it.gif;
  var links = $("#m-links");
  links.textContent = "";
  [["raw", "raw PNG"], ["led", "LED PNG"], ["grid", "grid PNG"], ["gif", "GIF"]].forEach(function (p) {
    if (it[p[0]]) links.append(el("a", { href: it[p[0]], target: "_blank", rel: "noopener", text: p[1] }));
  });
  $("#b-copy").disabled = $("#b-dl").hidden = !d;
  $("#b-copy").textContent = "Copy pixel array";
  if (dlUrl) { URL.revokeObjectURL(dlUrl); dlUrl = null; }
  var dl = $("#b-dl");
  if (d) {
    dlUrl = URL.createObjectURL(new Blob([d.json], { type: "application/json" }));
    dl.href = dlUrl;
    dl.download = it._id + ".json";
  }
  if ($("#txt").open) renderText();
  renderStage();
  try { history.replaceState(null, "", "#" + encodeURIComponent(it._id)); } catch (e) {}
}
function openAt(i, from) {
  if (!N) return;
  if (modal.hidden) {
    opener = from || document.activeElement;
    modal.hidden = false;
    document.body.classList.add("modal-open");
  }
  show(((i % N) + N) % N);
  $("#panel").focus({ preventScroll: true });
  modal.scrollTop = 0;
}
function closeModal() {
  if (modal.hidden) return;
  modal.hidden = true;
  document.body.classList.remove("modal-open");
  try { history.replaceState(null, "", location.pathname + location.search); } catch (e) {}
  if (opener && opener.focus) opener.focus({ preventScroll: true });
}

$("#m-close").addEventListener("click", closeModal);
$("#m-prev").addEventListener("click", function () { openAt(cur - 1); });
$("#m-next").addEventListener("click", function () { openAt(cur + 1); });
modal.addEventListener("click", function (ev) { if (ev.target === modal) closeModal(); });
$("#views").addEventListener("click", function (ev) {
  var b = ev.target.closest("button[data-view]");
  if (!b) return;
  view = b.getAttribute("data-view");
  store("view", view);
  renderStage();
});
$("#txt").addEventListener("toggle", function () { if (this.open && cur >= 0) renderText(); });
$("#b-copy").addEventListener("click", function () {
  var d = derive(items[cur]), btn = this;
  if (!d) return;
  var done = function (ok) {
    btn.textContent = ok ? "Copied!" : "Copy failed";
    setTimeout(function () { btn.textContent = "Copy pixel array"; }, 1600);
  };
  var fallback = function () {
    var ta = el("textarea", { class: "sr", "aria-hidden": "true" });
    ta.value = d.json;
    document.body.append(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) {}
    ta.remove();
    done(ok);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(d.json).then(function () { done(true); }, fallback);
  else fallback();
});
document.addEventListener("keydown", function (ev) {
  if (modal.hidden || ev.altKey || ev.ctrlKey || ev.metaKey) return;
  if (ev.key === "Escape") { ev.preventDefault(); closeModal(); }
  else if (ev.key === "ArrowLeft") { ev.preventDefault(); openAt(cur - 1); }
  else if (ev.key === "ArrowRight") { ev.preventDefault(); openAt(cur + 1); }
});
if (typeof ResizeObserver === "function") new ResizeObserver(function () { if (!modal.hidden) redraw(); }).observe(stage);
else window.addEventListener("resize", function () { if (!modal.hidden) redraw(); });

if (location.hash.length > 1) {
  var want = "";
  try { want = decodeURIComponent(location.hash.slice(1)); } catch (e) {}
  for (var k = 0; k < N; k++) if (items[k]._id === want) { openAt(k); break; }
}
})();
</script>
</body>
</html>
"""

_PLACEHOLDER = re.compile(r"__(TITLE|MANIFEST)__")


def manifest_json(manifest: dict[str, Any]) -> str:
    """JSON safe to embed inside an inline <script> element."""
    text = json.dumps(manifest, separators=(",", ":"), ensure_ascii=True, default=str)
    # Keep the HTML parser from seeing "</script>" or "<!--" inside string literals.
    return text.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def render_index(manifest: dict[str, Any]) -> str:
    """Return the full text of index.html for ``manifest``."""
    title = str(manifest.get("title") or DEFAULT_TITLE)
    values = {"TITLE": html.escape(title), "MANIFEST": manifest_json(manifest)}
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], _TEMPLATE)


def write_index(out_dir: Path, manifest: dict[str, Any]) -> Path:
    """Write ``out_dir/index.html`` (creating ``out_dir``) and return its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(render_index(manifest), encoding="utf-8")
    return path
