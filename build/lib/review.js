#!/usr/bin/env node
'use strict';
// bin/review — build/review.html: the whole sequence in display order with thumbnails, filenames, dates,
// row numbers, chapter markers and the time each row enters the screen. For matching what you saw to a filename.
const fs = require('fs');
const path = require('path');
const C = require('./common');

function fmtT(sec) { sec = Math.max(0, sec); const m = Math.floor(sec / 60); return `${m}m${String(Math.floor(sec - m * 60)).padStart(2, '0')}s`; }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }

function writeReview() {
  const m = JSON.parse(fs.readFileSync(path.join(C.BUILD, 'manifest.json'), 'utf8'));
  const sp = m.loop.speed;
  const parts = [];
  parts.push(`<!doctype html><meta charset="utf-8"><title>sequence review</title>
<style>
 body{margin:0;background:#111;color:#ddd;font:14px/1.35 -apple-system,Helvetica,sans-serif}
 h1{font-size:18px;margin:14px 16px 4px} .sub{margin:0 16px 10px;color:#aaa}
 h2{font-size:16px;margin:22px 16px 6px;color:#ffd27a;border-top:1px solid #333;padding-top:12px}
 .row{display:flex;gap:10px;padding:6px 16px;align-items:flex-start}
 .meta{flex:0 0 120px;color:#9ab;font-size:12px;padding-top:4px}
 .meta b{color:#fff;font-size:14px}
 .tiles{display:flex;gap:8px;flex-wrap:wrap}
 .tile{background:#1c1c24;border-radius:4px;padding:4px;width:196px}
 .tile img,.tile video{display:block;height:132px;max-width:188px;object-fit:contain;background:#000;margin:0 auto}
 .name{font-size:12px;word-break:break-all;margin-top:4px;color:#fff}
 .info{font-size:11px;color:#9ab}
 .feature .meta b{color:#ffd27a}
 .kind-video .name{color:#7fd4ff} .kind-live .name{color:#b8ff9e} .kind-gif .name{color:#ffb3e6}
 .star{color:#ffd27a}
</style>
<h1>Sequence review — ${m.items.length} items, ${m.rows.length} rows, loop ${fmtT(m.loop.seconds)} at ${sp.toFixed(0)} px/s</h1>
<p class="sub">Built ${esc(m.built)}. Order is display order, top to bottom. Time = when the row first enters the bottom of the screen at ${sp.toFixed(0)} px/s (add ~14 s for when it reaches the top). Blue names are videos, green Live Photos, pink GIFs, ★ featured. Use Cmd+F to search a filename. Swap with <code>bin/add-item &lt;new file&gt; &lt;date&gt; --replace &lt;filename&gt;</code>.</p>`);
  let lastChapter = -1;
  for (const r of m.rows) {
    if (r.chapter !== lastChapter) {
      lastChapter = r.chapter;
      const c = m.chapters[r.chapter];
      parts.push(`<h2>Chapter ${r.chapter + 1} — ${c.items} items, ${c.rows} rows, ${c.videos} videos</h2>`);
    }
    parts.push(`<div class="row ${r.type}"><div class="meta"><b>row ${r.i}</b><br>${r.type}<br>t=${fmtT((r.y - m.config.viewportH) / sp)}<br>h ${r.h}</div><div class="tiles">`);
    for (const e of r.items) {
      const it = m.items[e.item];
      let media;
      if (it.kind === 'still') media = `<img loading="lazy" src="${esc(path.relative(C.BUILD, path.join(C.ROOT, it.src)))}">`;
      else {
        // a mid-clip frame when the frame sequence for this row height exists, else the clip itself (Chrome shows its first frame)
        const dir = path.join(C.ROOT, e.frameDir);
        const mid = String(Math.max(1, Math.min(e.frameCount, Math.round(e.frameCount / 2)))).padStart(4, '0') + '.jpg';
        if (fs.existsSync(path.join(dir, mid))) media = `<img loading="lazy" src="${esc(path.relative(C.BUILD, path.join(dir, mid)))}">`;
        else media = `<video muted playsinline preload="metadata" src="${esc(path.relative(C.BUILD, path.join(C.ROOT, it.src)))}#t=0.5"></video>`;
      }
      parts.push(`<div class="tile kind-${it.kind}">${media}<div class="name">${it.featured ? '<span class="star">★</span> ' : ''}${esc(it.id)}</div><div class="info">${esc(it.date)} · ${it.kind}${it.kind !== 'still' ? ` · ${it.duration.toFixed(1)}s` : ''}${it.slow && it.slow !== 1 ? ' · slow-mo' : ''}${it.hdr ? ' · hdr' : ''}</div></div>`);
    }
    parts.push('</div></div>');
  }
  const out = path.join(C.BUILD, 'review.html');
  fs.writeFileSync(out, parts.join('\n'));
  return out;
}
if (require.main === module) { const out = writeReview(); console.log('wrote ' + path.relative(C.ROOT, out) + ' — open it in Chrome'); }
module.exports = { writeReview };
