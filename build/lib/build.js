#!/usr/bin/env node
'use strict';
// bin/build — media.csv + build/prep-manifest.json -> items -> date keys -> chapters -> spacing -> justified rows
//   -> build/manifest.json, build/sequence.txt, player.html (player.template.html with the manifest inlined).
// Deterministic: no randomness is used (CONFIG.seed is reserved). Prints row counts, feature share and the acceptance checks.
// Usage: bin/build [--speed N] [--quiet]

const fs = require('fs');
const path = require('path');
const C = require('./common');

// ---------------- tuning knobs (the one config block) ----------------
const CONFIG = {
  scrollSpeed: 100,        // px/s; 120 is the other candidate the owner compares by eye
  baseRowHeight: 520,      // target height of a base row
  featureRowHeight: 820,   // target height of a feature row
  anchorLookahead: 6,      // positions an item may be pulled/nudged within its chapter
  pullMaxGap: 1.25,        // years: an item is pulled forward into a row only if it is at most this far ahead of the item it jumps past (owner, first run: featured stills pulled 1.5 yr forward read as out of place; 1.0 costs another 45 s of loop and 63% feature rows)
  gutter: 8,
  chapters: 10,
  seed: 20260905,          // reserved; nothing random is used today
  movingCap: 4,            // runtime: max tiles animating at once (3 in the spec; 4 since the first run so Live Photos get turns even with three videos on screen)
  rotateSlots: true,       // runtime: a Live Photo/GIF hands its slot on after `rotatePlays` full plays when another tile is waiting (owner, first run)
  rotatePlays: 1,
  maxWait: 4,              // runtime: seconds a tile may wait for its first turn before the longest-running Live Photo is frozen to make room
  videoPriority: true,     // runtime: a standalone video entering the viewport takes a slot immediately, freezing the longest-running Live Photo where it is
  startVisibleFrac: 1,     // runtime: a Live Photo/GIF asks for a slot only once this fraction of its row is on screen (1 = fully in view; 0 = the old any-pixel rule); standalone videos always ask on entry. Owner, first run: Live Photos were finishing before they had fully scrolled on
  disorderWeight: 2000,    // spacing pass: penalty for backward date jumps > 0.5 yr between neighbours; 2000 = chronology first, consecutive video rows accepted (owner, first run)
  livePhotoHold: 1.5,      // s, hold on the last frame before a Live Photo / GIF restarts
  videoMinRowGap: 2,       // row-index distance between two video rows (2 = never adjacent)
  videoNudge: 12,          // positions a standalone video may move within its chapter to keep video rows apart (videos cluster in 2022-23)
  maxBaseMoving: 2,        // no base row with more than this many moving tiles
  wideAloneRatio: 2.4,     // an item wider than this takes a row alone
  minFill: 0.9,            // a base row may stop short of an anchor only when this full (natural width / row width)
  fillBias: 0.1,           // when an item straddles the row edge, prefer including it (shorter row) unless it is this much worse in log-height
  viewportW: 2560,
  viewportH: 1440,
  background: '#07070F',
  frameFps: 30,            // render-mode frame sequences
  renderFps: 60,
};
const OVERRIDES_FILE = path.join(__dirname, '..', 'overrides.json');
const TEMPLATE = path.join(__dirname, '..', 'player.template.html');
const PLAYER_OUT = path.join(C.ROOT, 'player.html');

const opt = { quiet: false };
{
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--speed') CONFIG.scrollSpeed = Number(a[++i]);
    else if (a[i] === '--lookahead') CONFIG.anchorLookahead = Number(a[++i]);
    else if (a[i] === '--video-nudge') CONFIG.videoNudge = Number(a[++i]);
    else if (a[i] === '--disorder') CONFIG.disorderWeight = Number(a[++i]);
    else if (a[i] === '--start-visible') CONFIG.startVisibleFrac = Number(a[++i]);
    else if (a[i] === '--pull-gap') CONFIG.pullMaxGap = Number(a[++i]);
    else if (a[i] === '--feature-height') CONFIG.featureRowHeight = Number(a[++i]);
    else if (a[i] === '--base-height') CONFIG.baseRowHeight = Number(a[++i]);
    else if (a[i] === '--quiet') opt.quiet = true;
    else if (a[i] === '-h' || a[i] === '--help') { console.log('usage: bin/build [--speed N] [--lookahead N] [--feature-height N] [--base-height N] [--quiet]'); process.exit(0); }
    else { console.error('unknown argument ' + a[i]); process.exit(2); }
  }
}
const say = s => console.log(s);
const problems = [];
const warnings = [];

// ---------------- items ----------------
function loadItems() {
  const { rows } = C.readMediaCsv();
  const byName = new Map(rows.map(r => [r.filename, r]));
  const manifest = C.readPrepManifest() || { tiles: {}, clips: {} };
  let overrides = {};
  try { overrides = JSON.parse(fs.readFileSync(OVERRIDES_FILE, 'utf8')).items || {}; } catch (_) { /* none */ }
  const items = [];
  for (const r of rows) {
    if (r.type === 'livephoto-still') continue;
    const kind = r.type === 'still' ? 'still' : r.type === 'livephoto-video' ? 'live' : r.type === 'video' ? 'video' : 'gif';
    const m = kind === 'still' ? manifest.tiles[r.filename] : manifest.clips[r.filename];
    if (!m) warnings.push(`${r.filename}: no prep output yet, using media.csv dimensions/duration`);
    const w = m ? m.width : +r.width, h = m ? m.height : +r.height;
    const companion = r.companion ? byName.get(r.companion) : null;
    const featured = r.featured === 'yes' || (companion && companion.featured === 'yes');
    const o = overrides[r.filename] || {};
    const duration = kind === 'still' ? 0 : (m ? m.duration : +r.duration_s);
    items.push({
      id: r.filename, stem: C.stemOf(r.filename), kind, w, h, aspect: w / h,
      src: m ? m.path : path.relative(C.ROOT, kind === 'still' ? C.tilePath(r.filename) : C.clipPath(r.filename)),
      featured: !!featured, anchor: !!featured || kind === 'video', moving: kind !== 'still',
      wide: w / h > CONFIG.wideAloneRatio,
      duration, start: +o.start || 0, trimStart: +o.trimStart || 0, trimEnd: +o.trimEnd || 0,
      slow: m && m.slow ? m.slow : 1, hdr: !!(m && m.hdr),
      date: r.date, precision: r.precision, key: C.dateKey(r.date, r.precision),
    });
  }
  return items;
}

// ---------------- sequence: sort, deal, ring ----------------
const byKey = (a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
// Round-robin deal by date, stratified so every chapter gets its share of videos, featured stills and Live Photos/GIFs
// (a plain deal left one chapter with 9 videos, where a two-row video gap is impossible). Each chapter stays date-ordered.
function dealChapters(items) {
  const strata = [
    items.filter(it => it.kind === 'video'),
    items.filter(it => it.kind !== 'video' && it.anchor),
    items.filter(it => !it.anchor && it.moving),
    items.filter(it => !it.anchor && !it.moving),
  ];
  const chapters = Array.from({ length: CONFIG.chapters }, () => []);
  let cursor = 0;
  for (const stratum of strata) for (const it of stratum.sort(byKey)) chapters[cursor++ % CONFIG.chapters].push(it);
  const seq = [];
  chapters.forEach((ch, k) => ch.sort(byKey).forEach(it => { it.chapter = k; it.orig = seq.length; seq.push(it); }));
  return seq;
}

// ---------------- layout: justified rows ----------------
const W = CONFIG.viewportW, G = CONFIG.gutter;
const natural = (items, T) => items.reduce((s, it) => s + it.aspect * T, 0) + G * Math.max(0, items.length - 1);
const justifiedHeight = items => (W - G * (items.length - 1)) / items.reduce((s, it) => s + it.aspect, 0);
const movingCount = items => items.reduce((n, it) => n + (it.moving ? 1 : 0), 0);
function betterWith(items, c, T) {
  const hWithout = justifiedHeight(items), hWith = justifiedHeight(items.concat(c));
  return Math.abs(Math.log(hWith / T)) <= Math.abs(Math.log(hWithout / T)) + CONFIG.fillBias;
}
// take items from the front of `work` into `items` until the row is full at target height T
function fill(items, work, T, { feature, hasVideo }) {
  for (;;) {
    if (!work.length) return hasVideo;
    const nat = natural(items, T);
    if (items.length && nat >= W) return hasVideo;
    const first = work[0];
    if (items.length && first.chapter !== items[0].chapter) return hasVideo;   // rows never straddle a chapter boundary
    // which items may join this row right now?
    const eligible = d => !d.wide && !(d.kind === 'video' && hasVideo) && (feature || !d.anchor)
      && !(!feature && d.moving && movingCount(items) >= CONFIG.maxBaseMoving);
    let take = -1;
    if (eligible(first)) take = 0;
    else if (!(!feature && first.anchor && nat >= CONFIG.minFill * W)) {
      // the next item is blocked (second video, third moving tile, anchor in a base row): pull the next eligible
      // item of the same chapter from the lookahead window instead, so the row still fills
      take = work.findIndex((d, i) => i > 0 && i <= CONFIG.anchorLookahead && d.chapter === first.chapter && eligible(d)
        && !(d.anchor && !feature) && yearOf(d) - yearOf(first) <= CONFIG.pullMaxGap);
    }
    if (take < 0) return hasVideo;
    const c = work[take];
    if (items.length && nat + G + c.aspect * T >= W) {
      if (betterWith(items, c, T)) { items.push(work.splice(take, 1)[0]); if (c.kind === 'video') hasVideo = true; }
      return hasVideo;
    }
    items.push(work.splice(take, 1)[0]);
    if (c.kind === 'video') hasVideo = true;
  }
}
function featureRow(work, lead) {
  const T = CONFIG.featureRowHeight;
  const items = lead ? lead.slice() : [];
  const anchor = work.shift();
  items.push(anchor);
  let hasVideo = anchor.kind === 'video';
  if (anchor.wide) return { type: 'feature', items };
  // pull further anchors from the lookahead window, same chapter only
  for (let k = 0; k < work.length && k < CONFIG.anchorLookahead;) {
    const c = work[k];
    if (c.chapter !== anchor.chapter) break;
    if (c.anchor && !c.wide && !(hasVideo && c.kind === 'video') && natural(items, T) + G + c.aspect * T < W * 1.02
      && yearOf(c) - yearOf(anchor) <= CONFIG.pullMaxGap) {                   // never pull an anchor far ahead of its time
      items.push(work.splice(k, 1)[0]);
      if (c.kind === 'video') hasVideo = true;
    } else k++;
  }
  fill(items, work, T, { feature: true, hasVideo });
  return { type: 'feature', items };
}
function baseRow(work) {
  const T = CONFIG.baseRowHeight;
  const items = [];
  if (work[0].wide) return { type: 'base', items: [work.shift()] };
  for (;;) {
    fill(items, work, T, { feature: false, hasVideo: false });
    if (!work.length) break;
    const c = work[0];
    if (items.length && c.chapter !== items[0].chapter) break;                 // chapter boundary: end the row here
    if (c.anchor && natural(items, T) < CONFIG.minFill * W) {
      // an anchor interrupts an underfilled base row: pull a non-anchor from the anchor's chapter, first within
      // lookahead, then from twice that window; with one or two stray items left, fold them into the feature row
      for (const win of [CONFIG.anchorLookahead, 2 * CONFIG.anchorLookahead, 3 * CONFIG.anchorLookahead]) {
        const k = work.findIndex((d, i) => i > 0 && i <= win && d.chapter === c.chapter && !d.anchor && !d.wide
          && !(d.moving && movingCount(items) >= CONFIG.maxBaseMoving) && yearOf(d) - yearOf(c) <= CONFIG.pullMaxGap);
        if (k > 0) { items.push(work.splice(k, 1)[0]); break; }
      }
      if (natural(items, T) < CONFIG.minFill * W) {
        // still short: fold a few stray items into the coming feature row rather than show a base row taller than a feature row
        if (items.length <= 2 || justifiedHeight(items) > 0.9 * CONFIG.featureRowHeight) return { type: 'lead', items };
        if (work[0].anchor) break;                                         // accept a somewhat taller base row
      }
      continue;
    }
    break;
  }
  return { type: 'base', items };
}
function layout(seq) {
  const work = seq.slice();
  const rows = [];
  while (work.length) {
    const before = work.length;
    if (work[0].anchor) { rows.push(featureRow(work)); if (work.length === before) throw new Error('layout made no progress at ' + work[0].id); continue; }
    const r = baseRow(work);
    if (r.type === 'lead') rows.push(featureRow(work, r.items));
    else rows.push(r);
    if (work.length === before) throw new Error('layout made no progress at ' + work[0].id);
  }
  // rows never cross a chapter boundary, so a chapter's last row can come out short and a portrait-heavy row can
  // come out tall: shift items between neighbouring rows (latest of the upper row down, earliest of the lower row up)
  // while that lowers the worse of the two heights. Neither move can worsen the date order at the boundary.
  rebalanceRows(rows);
  resplitChapterTails(rows);
  rebalanceRows(rows);
  // display order inside a row is chronological: pulled anchors and fillers otherwise read as out of order
  for (const r of rows) r.items.sort(byKey);
  // geometry
  let y = 0;
  for (const r of rows) {
    const h = justifiedHeight(r.items);
    r.h = Math.round(h);
    r.y = y;
    y += r.h + G;
    r.hasVideo = r.items.some(it => it.kind === 'video');
    r.moving = movingCount(r.items);
    r.chapter = r.items[0].chapter;
  }
  return rows;
}



function rowType(items) { return items.some(it => it.anchor) ? 'feature' : 'base'; }
function rowDev(items) { return Math.abs(Math.log(justifiedHeight(items) / (rowType(items) === 'feature' ? CONFIG.featureRowHeight : CONFIG.baseRowHeight))); }
function rowOk(items) {
  if (items.length < 2) return false;
  if (items.filter(it => it.kind === 'video').length > 1) return false;
  if (rowType(items) === 'base' && movingCount(items) > CONFIG.maxBaseMoving) return false;
  return true;
}
function rebalanceRows(rows) {
  for (let pass = 0; pass < 16; pass++) {
    let changed = false;
    for (let i = 0; i + 1 < rows.length; i++) {
      const A = rows[i], B = rows[i + 1];
      if (A.items[0].chapter !== B.items[0].chapter) continue;
      const cur = Math.max(rowDev(A.items), rowDev(B.items));
      if (cur < 0.12) continue;
      const As = A.items.slice().sort(byKey), Bs = B.items.slice().sort(byKey);
      const options = [];
      if (As.length > 2) options.push({ a: As.slice(0, -1), b: [As[As.length - 1]].concat(Bs) });
      if (Bs.length > 2) options.push({ a: As.concat([Bs[0]]), b: Bs.slice(1) });
      let best = null;
      for (const o of options) {
        if (!rowOk(o.a) || !rowOk(o.b)) continue;
        const d = Math.max(rowDev(o.a), rowDev(o.b));
        if (d < cur - 0.02 && (!best || d < best.d)) best = { a: o.a, b: o.b, d };
      }
      if (best) { A.items = best.a; B.items = best.b; A.type = rowType(A.items); B.type = rowType(B.items); changed = true; }
    }
    if (!changed) break;
  }
}

// ---------------- chapter tails ----------------
const targetOf = r => (r.type === 'feature' ? CONFIG.featureRowHeight : CONFIG.baseRowHeight);
function partCost(part) {
  const type = part.some(it => it.anchor) ? 'feature' : 'base';
  const T = type === 'feature' ? CONFIG.featureRowHeight : CONFIG.baseRowHeight;
  if (part.filter(it => it.kind === 'video').length > 1) return Infinity;
  let cost = Math.abs(Math.log(justifiedHeight(part) / T));
  if (part.length < 3) cost += 0.3;
  if (type === 'base' && movingCount(part) > CONFIG.maxBaseMoving) cost += 0.5;
  return cost;
}
// split `pool` (date-ordered) into m consecutive parts of >= 2 items minimising the summed height deviation
function bestSplit(pool, m) {
  const n = pool.length;
  if (n < 2 * m) return null;
  let best = null, bestCost = Infinity;
  const rec = (startIdx, partsLeft, acc, cost) => {
    if (cost >= bestCost) return;
    if (partsLeft === 1) {
      const part = pool.slice(startIdx);
      if (part.length < 2) return;
      const c = cost + partCost(part);
      if (c < bestCost) { bestCost = c; best = acc.concat([part]); }
      return;
    }
    for (let k = startIdx + 2; k <= n - 2 * (partsLeft - 1); k++) {
      const part = pool.slice(startIdx, k);
      rec(k, partsLeft - 1, acc.concat([part]), cost + partCost(part));
    }
  };
  rec(0, m, [], 0);
  return best;
}
function resplitChapterTails(rows) {
  for (let i = 0; i < rows.length; i++) {
    const lastOfChapter = i === rows.length - 1 || rows[i + 1].items[0].chapter !== rows[i].items[0].chapter;
    if (!lastOfChapter) continue;
    if (natural(rows[i].items, targetOf(rows[i])) >= CONFIG.minFill * W) continue;
    const dev = p => Math.abs(Math.log(justifiedHeight(p) / (p.some(it => it.anchor) ? CONFIG.featureRowHeight : CONFIG.baseRowHeight)));
    let best = null;                                   // pool 2, 3 or 4 rows; keep the split whose worst row deviates least
    for (let m = 2; m <= 4; m++) {
      const start = i - m + 1;
      if (start < 0 || rows[start].items[0].chapter !== rows[i].items[0].chapter) break;
      const pool = rows.slice(start, i + 1).flatMap(r => r.items).sort(byKey);
      const parts = bestSplit(pool, m);
      if (!parts) continue;
      const maxDev = Math.max(...parts.map(dev));
      if (!best || maxDev < best.maxDev - 1e-9) best = { start, m, parts, maxDev };
      if (maxDev < 0.2) break;
    }
    const current = Math.max(...rows.slice(Math.max(0, i - 3), i + 1).filter(r => r.items[0].chapter === rows[i].items[0].chapter).map(r => dev(r.items)));
    if (best && best.maxDev < current) {
      rows.splice(best.start, best.m, ...best.parts.map(p => ({ type: p.some(it => it.anchor) ? 'feature' : 'base', items: p })));
      i = best.start + best.parts.length - 1;
    }
  }
}

// ---------------- spacing pass ----------------
function chaptersContiguous(seq) {
  // ring-aware: each chapter must be one contiguous block around the ring
  let runs = 0;
  for (let i = 0; i < seq.length; i++) if (seq[i].chapter !== seq[(i + seq.length - 1) % seq.length].chapter) runs++;
  return runs === CONFIG.chapters;
}
const cyclicDist = (a, b, n) => { const d = Math.abs(a - b); return Math.min(d, n - d); };
const budgetOf = it => (it.kind === 'video' ? CONFIG.videoNudge : CONFIG.anchorLookahead);
// The ring has no natural start. If the final row comes out underfilled, its items move to the front of the
// sequence (a row that straddles the chapter-10 -> chapter-1 wrap, like any other boundary row) and we lay out again.
function rotateForWrap(seq) {
  for (let guard = 0; guard < 8; guard++) {
    const rows = layout(seq);
    const last = rows[rows.length - 1];
    const T = last.type === 'feature' ? CONFIG.featureRowHeight : CONFIG.baseRowHeight;
    if (natural(last.items, T) >= CONFIG.minFill * W) return seq;
    const ids = new Set(last.items.map(it => it.id));
    seq = last.items.concat(seq.filter(it => !ids.has(it.id)));
  }
  return seq;
}
function score(rows) {
  const N = rows.length;
  let adjacent = 0, over = 0;
  for (let i = 0; i < N; i++) {
    for (let d = 1; d < CONFIG.videoMinRowGap; d++) if (rows[i].hasVideo && rows[(i + d) % N].hasVideo) adjacent++;
    if (rows[i].type === 'base' && rows[i].moving > CONFIG.maxBaseMoving) over++;
  }
  // spread: within each chapter, video rows should sit at (j + 0.5) * R / n
  let spread = 0;
  for (let k = 0; k < CONFIG.chapters; k++) {
    const idx = []; let R = 0;
    rows.forEach(r => { if (r.chapter === k) { if (r.hasVideo) idx.push(R); R++; } });
    idx.forEach((p, j) => { const ideal = (j + 0.5) * R / idx.length; spread += ((p + 0.5 - ideal) / Math.max(1, R)) ** 2; });
  }
  // chronology: a backward date jump between neighbours in the same chapter (beyond half a year) costs quadratically,
  // so the optimizer only moves a video years out of place when nothing gentler separates two video rows
  let disorder = 0, prev = null;
  for (const r of rows) for (const it of r.items) {
    if (prev && prev.chapter === it.chapter) { const back = (yearOf(prev) - yearOf(it)) - 0.5; if (back > 0) disorder += back * back; }
    prev = it;
  }
  disorder *= CONFIG.disorderWeight;
  return { total: adjacent * 1000 + over * 100 + spread + disorder, adjacent, over, spread, disorder };
}
function yearOf(it) { if (it._y == null) { const [y, m, d] = it.key.split('-').map(Number); it._y = y + (m - 1) / 12 + (d - 1) / 365; } return it._y; }
function move(seq, from, to) {
  const s = seq.slice();
  const [it] = s.splice(from, 1);
  s.splice(to, 0, it);
  return s;
}
function videoDeviations(rows) {
  // per video row: how far it sits from its ideal evenly-spread slot within its chapter (in rows)
  const out = [];
  for (let k = 0; k < CONFIG.chapters; k++) {
    const vrows = []; let R = 0;
    rows.forEach(r => { if (r.chapter === k) { if (r.hasVideo) vrows.push({ r, pos: R }); R++; } });
    vrows.forEach((v, j) => { const ideal = (j + 0.5) * R / vrows.length; out.push({ row: v.r, dev: Math.abs(v.pos + 0.5 - ideal) }); });
  }
  return out;
}
function tryMoves(seq, it, best, minGain) {
  const n = seq.length, from = seq.indexOf(it), budget = budgetOf(it);
  let bestMove = null, bestScore = best;
  for (let d = -budget; d <= budget; d++) {
    if (!d) continue;
    const to = from + d;
    if (to < 0 || to >= n) continue;
    if (cyclicDist(to, it.orig, n) > budget) continue;
    const s2 = move(seq, from, to);
    if (!chaptersContiguous(s2)) continue;
    const sc = score(layout(s2));
    if (sc.total < bestScore.total - minGain) { bestScore = sc; bestMove = { it, from, to, s2, label: `${it.id}: ${from} -> ${to}` }; }
  }
  return { bestMove, bestScore };
}
function spacingPass(seq) {
  seq.forEach((it, i) => { it.orig = i; });
  let rows = layout(seq);
  let best = score(rows);
  const log = [];
  const N = () => rows.length;
  for (let iter = 0; iter < 150; iter++) {
    const candidates = new Set();
    rows.forEach((r, i) => {
      for (let d = 1; d < CONFIG.videoMinRowGap; d++) {
        const o = rows[(i + d) % N()];
        if (r.hasVideo && o.hasVideo) [r, o].forEach(x => x.items.filter(it => it.kind === 'video').forEach(it => candidates.add(it)));
      }
      if (r.type === 'base' && r.moving > CONFIG.maxBaseMoving) r.items.filter(it => it.moving).forEach(it => candidates.add(it));
    });
    const violations = candidates.size > 0;
    if (!violations) {
      // nothing broken: improve the spread of the six most misplaced video rows
      videoDeviations(rows).sort((a, b) => b.dev - a.dev).slice(0, 6)
        .forEach(v => v.row.items.filter(it => it.kind === 'video').forEach(it => candidates.add(it)));
    }
    let bestMove = null, bestScore = best;
    const minGain = violations ? 1e-9 : 0.02;
    for (const it of candidates) {
      const r = tryMoves(seq, it, bestScore, minGain);
      if (r.bestMove) { bestMove = r.bestMove; bestScore = r.bestScore; }
    }
    if (!bestMove) break;
    seq = bestMove.s2; rows = layout(seq); best = bestScore;
    log.push(`${bestMove.label} (score ${best.total.toFixed(3)})`);
  }
  // second pass: remaining adjacent video rows need both videos to move at once
  for (let iter = 0; iter < 40; iter++) {
    const pairs = [];
    rows.forEach((r, i) => { const o = rows[(i + 1) % N()]; if (r.hasVideo && o.hasVideo && r !== o) pairs.push([r.items.find(it => it.kind === 'video'), o.items.find(it => it.kind === 'video')]); });
    if (!pairs.length) break;
    let bestMove = null, bestScore = best;
    for (const [a, b] of pairs) {
      const n = seq.length, fa = seq.indexOf(a), ba = budgetOf(a), bb = budgetOf(b);
      for (let da = -ba; da <= ba; da++) {
        const ta = fa + da;
        if (ta < 0 || ta >= n || cyclicDist(ta, a.orig, n) > ba) continue;
        const s1 = move(seq, fa, ta);
        if (!chaptersContiguous(s1)) continue;
        const fb = s1.indexOf(b);
        for (let db = -bb; db <= bb; db++) {
          if (!da && !db) continue;
          const tb = fb + db;
          if (tb < 0 || tb >= n || cyclicDist(tb, b.orig, n) > bb) continue;
          const s2 = db ? move(s1, fb, tb) : s1;
          if (!chaptersContiguous(s2)) continue;
          const sc = score(layout(s2));
          if (sc.total < bestScore.total - 1e-9) { bestScore = sc; bestMove = { s2, label: `${a.id}: ${fa} -> ${ta} & ${b.id}: ${fb} -> ${tb}` }; }
        }
      }
    }
    if (!bestMove) break;
    seq = bestMove.s2; rows = layout(seq); best = bestScore;
    log.push(`${bestMove.label} (score ${best.total.toFixed(3)})`);
  }
  rows = layout(seq);
  best = score(rows);
  return { seq, rows, best, log };
}

// ---------------- output ----------------
function geometry(rows) {
  for (const r of rows) {
    const h = r.h;
    let x = 0;
    const n = r.items.length;
    r.placed = r.items.map((it, i) => {
      let w = Math.round(it.aspect * h);
      if (i === n - 1) w = W - x;                      // last item absorbs the rounding
      const p = { x, w, h }; x += w + G; return p;
    });
  }
}
function main() {
  const t0 = Date.now();
  const items = loadItems();
  const seq0 = dealChapters(items);
  const { seq, rows, best, log } = spacingPass(seq0);
  geometry(rows);
  const loopHeight = rows.reduce((s, r) => s + r.h + G, 0);
  const frames = Math.round(loopHeight / CONFIG.scrollSpeed * CONFIG.renderFps);
  const speed = loopHeight * CONFIG.renderFps / frames;          // tiny correction so one loop is a whole number of frames
  const loopSeconds = loopHeight / speed;

  // ---- acceptance checks
  const kinds = {}; items.forEach(it => { kinds[it.kind] = (kinds[it.kind] || 0) + 1; });
  const placedIds = rows.flatMap(r => r.items.map(it => it.id));
  if (placedIds.length !== items.length || new Set(placedIds).size !== items.length) problems.push(`placed ${placedIds.length} items (${new Set(placedIds).size} unique) for ${items.length}`);
  rows.forEach((r, i) => {
    const width = r.placed.reduce((s, p) => s + p.w, 0) + G * (r.items.length - 1);
    if (width !== W) problems.push(`row ${i} width ${width}`);
    if (r.type === 'feature' && r.items.filter(it => it.kind === 'video').length > 1) problems.push(`row ${i}: two videos`);
    r.items.forEach(it => { if (it.anchor && r.type !== 'feature') problems.push(`${it.id}: anchor in a base row`); });
    if (r.type === 'base' && r.moving > CONFIG.maxBaseMoving) problems.push(`row ${i}: ${r.moving} moving tiles in a base row`);
    for (let d = 1; d < CONFIG.videoMinRowGap; d++) if (r.hasVideo && rows[(i + d) % rows.length].hasVideo) warnings.unshift(`rows ${i} and ${(i + d) % rows.length}: video rows ${d} apart (largest gap reachable within videoNudge ${CONFIG.videoNudge}; not a failure)`);
  });
  if (!chaptersContiguous(seq)) problems.push('an item crossed a chapter boundary');
  { // the final rotation shifts every index by the same amount; measure displacement relative to that shift
    const n = seq.length, hist = new Map();
    seq.forEach((it, i) => { const k = ((i - it.orig) % n + n) % n; hist.set(k, (hist.get(k) || 0) + 1); });
    const shift = [...hist.entries()].sort((a, b) => b[1] - a[1])[0][0];
    seq.forEach((it, i) => { const d = cyclicDist(i, (it.orig + shift) % n, n); it.moved = d; if (d > budgetOf(it)) problems.push(`${it.id} moved ${d} positions (budget ${budgetOf(it)})`); });
  }
  rows.forEach((r, i) => {
    if (new Set(r.items.map(it => it.chapter)).size > 1) problems.push(`row ${i} mixes chapters`);
    const T = r.type === 'feature' ? CONFIG.featureRowHeight : CONFIG.baseRowHeight;
    if (natural(r.items, T) < 0.75 * W) warnings.push(`row ${i} (${r.type}, chapter ${r.chapter + 1}) is short: ${r.items.length} items, ${r.h} px tall`);
  });
  // max moving tiles in view at once (informational; runtime cap handles it)
  let maxInView = 0;
  for (let s = 0; s < loopHeight; s += 40) {
    let n = 0;
    for (const r of rows) for (const dy of [0, loopHeight, -loopHeight]) { const y = r.y + dy; if (y < s + CONFIG.viewportH && y + r.h > s) n += r.moving; }
    maxInView = Math.max(maxInView, n);
  }
  const feature = rows.filter(r => r.type === 'feature').length, base = rows.length - feature;
  const perChapter = Array.from({ length: CONFIG.chapters }, (_, k) => {
    const rs = rows.filter(r => r.chapter === k);
    return { rows: rs.length, feature: rs.filter(r => r.type === 'feature').length, videos: rs.filter(r => r.hasVideo).length, items: rs.reduce((s, r) => s + r.items.length, 0) };
  });

  // ---- manifest
  const itemIndex = new Map(items.map((it, i) => [it.id, i]));
  const manifest = {
    built: new Date().toISOString(), config: CONFIG,
    loop: { height: loopHeight, seconds: loopSeconds, frames, speed },
    items: items.map(it => ({
      id: it.id, stem: it.stem, kind: it.kind, w: it.w, h: it.h, src: it.src, duration: it.duration,
      start: it.start, trimStart: it.trimStart, trimEnd: it.trimEnd, featured: it.featured, anchor: it.anchor, moving: it.moving,
      chapter: it.chapter, date: it.date, precision: it.precision, slow: it.slow, hdr: it.hdr,
    })),
    rows: rows.map((r, i) => ({
      i, type: r.type, y: r.y, h: r.h, chapter: r.chapter,
      items: r.items.map((it, j) => {
        const p = r.placed[j];
        const e = { item: itemIndex.get(it.id), x: p.x, w: p.w };
        if (it.moving) {
          const visible = (CONFIG.viewportH + r.h) / speed;     // seconds the row is on screen
          e.frameDir = path.posix.join('build', 'frames', it.stem, 'h' + r.h);
          if (it.kind === 'video') { e.frameFrom = it.start; e.frameTo = Math.min(it.duration, it.start + visible + 1); }
          else { e.frameFrom = it.trimStart; e.frameTo = Math.max(it.trimStart + 0.1, it.duration - it.trimEnd); }
          e.frameCount = Math.max(1, Math.round((e.frameTo - e.frameFrom) * CONFIG.frameFps));
        }
        return e;
      }),
    })),
    chapters: perChapter.map((c, k) => ({ index: k, firstRow: rows.findIndex(r => r.chapter === k), ...c })),
  };
  fs.mkdirSync(C.BUILD, { recursive: true });
  fs.writeFileSync(path.join(C.BUILD, 'manifest.json'), JSON.stringify(manifest));

  // ---- sequence.txt
  const mark = it => (it.kind === 'video' ? '[V]' : it.kind === 'live' ? '[L]' : it.kind === 'gif' ? '[G]' : '   ') + (it.featured ? '[F]' : '   ');
  const lines = [
    `slideshow sequence, built ${manifest.built}`,
    `${items.length} items: ${Object.entries(kinds).map(([k, v]) => `${v} ${k}`).join(', ')}`,
    `${rows.length} rows: ${feature} feature (${(100 * feature / rows.length).toFixed(0)}%), ${base} base; loop ${loopHeight} px = ${fmtTime(loopSeconds)} at ${speed.toFixed(3)} px/s (${frames} frames at ${CONFIG.renderFps} fps); max moving tiles in view ${maxInView}`,
    `knobs: ${Object.entries(CONFIG).filter(([k]) => !['viewportW', 'viewportH', 'background', 'frameFps', 'renderFps'].includes(k)).map(([k, v]) => `${k}=${v}`).join(' ')}`,
    `spacing moves: ${log.length}${log.length ? '\n  ' + log.join('\n  ') : ''}`,
    '',
  ];
  let lastChapter = -1;
  rows.forEach((r, i) => {
    if (r.chapter !== lastChapter) { lastChapter = r.chapter; const c = perChapter[r.chapter]; lines.push(`== chapter ${r.chapter + 1}: ${c.items} items, ${c.rows} rows, ${c.feature} feature, ${c.videos} video rows ==`); }
    lines.push(`row ${String(i).padStart(3)} ${r.type === 'feature' ? 'FEATURE' : 'base   '} y=${String(r.y).padStart(6)} h=${String(r.h).padStart(4)}  ${r.items.map(it => `${mark(it)} ${it.id}`).join('   ')}`);
  });
  fs.writeFileSync(path.join(C.BUILD, 'sequence.txt'), lines.join('\n') + '\n');

  // ---- player.html
  let playerNote = 'no player.template.html yet, player.html not written';
  if (fs.existsSync(TEMPLATE)) {
    const tpl = fs.readFileSync(TEMPLATE, 'utf8');
    if (!tpl.includes('/*__MANIFEST__*/')) problems.push('player.template.html lacks the /*__MANIFEST__*/ placeholder');
    else {
      const inlined = tpl.replace('/*__MANIFEST__*/', 'const MANIFEST = ' + JSON.stringify(manifest) + ';');
      fs.writeFileSync(PLAYER_OUT, inlined);
      // review copy: same player with flagging forced on, because macOS `open` strips ?review=1 from file:// URLs.
      // It lives in build/, so its relative asset paths need one more level.
      const reviewPage = inlined.replace('const MANIFEST = ', 'window.__FORCE_REVIEW = true; const MANIFEST = ')
        .replace(/"src":"build\//g, '"src":"').replace(/"frameDir":"build\//g, '"frameDir":"');
      fs.writeFileSync(path.join(C.BUILD, 'player-review.html'), reviewPage);
      playerNote = `player.html written (${(fs.statSync(PLAYER_OUT).size / 1024).toFixed(0)} KB), build/player-review.html too`;
    }
  }

  // ---- report
  say(`build: ${items.length} items (${Object.entries(kinds).map(([k, v]) => `${v} ${k}`).join(', ')}), ${rows.length} rows: ${feature} feature = ${(100 * feature / rows.length).toFixed(0)}%, ${base} base`);
  say(`       loop ${loopHeight} px = ${fmtTime(loopSeconds)} at ${speed.toFixed(3)} px/s (${CONFIG.scrollSpeed} requested), ${frames} frames at ${CONFIG.renderFps} fps; max moving tiles in view ${maxInView} (cap ${CONFIG.movingCap})`);
  say(`       per chapter rows/feature/videoRows: ${perChapter.map(c => `${c.rows}/${c.feature}/${c.videos}`).join(' ')}`);
  const dist = kind => { const rs = rows.filter(r => r.type === kind); const hs = rs.map(r => r.h).sort((a, b) => a - b); const n = {}; rs.forEach(r => { n[r.items.length] = (n[r.items.length] || 0) + 1; }); return `${Object.entries(n).map(([k, v]) => `${v}x${k}`).join(' ')} items; h ${hs[0]}/${hs[hs.length >> 1]}/${hs[hs.length - 1]}`; };
  say(`       feature rows: ${dist('feature')}; base rows: ${dist('base')} (min/median/max)`);
  say(`       spacing: ${log.length} moves, ${best.adjacent} adjacent video rows, ${best.over} base rows over ${CONFIG.maxBaseMoving} moving, spread penalty ${best.spread.toFixed(3)}, disorder penalty ${best.disorder.toFixed(0)}`);
  { // biggest backward date jumps left inside chapters, for the review
    const jumps = []; let prev = null;
    rows.forEach((r, ri) => { for (const it of r.items) { if (prev && prev.chapter === it.chapter) { const back = yearOf(prev) - yearOf(it); if (back > 1.0) jumps.push({ back, s: `${back.toFixed(1)}y ${prev.id} -> ${it.id} (row ${ri})` }); } prev = it; } });
    jumps.sort((a, b) => b.back - a.back);
    say(`       backward date jumps inside chapters: ${jumps.filter(j => j.back > 1.5).length} over 1.5 yr, ${jumps.length} over 1 yr${jumps.length ? ' (largest: ' + jumps.slice(0, 3).map(j => j.s).join('; ') + ')' : ''}`);
  }
  say(`       ${playerNote}; build/manifest.json, build/sequence.txt written (${C.fmtSecs(Date.now() - t0)})`);
  const shown = warnings.filter(w => !/no prep output yet/.test(w));
  const missingPrep = warnings.length - shown.length;
  for (const w of shown.slice(0, 12)) say('  ! ' + w);
  if (missingPrep) say(`  ! ${missingPrep} item(s) have no prep output yet (run bin/prep); media.csv dimensions used for them`);
  if (problems.length) { say('ACCEPTANCE PROBLEMS:'); for (const p of problems.slice(0, 30)) say('  X ' + p); process.exit(1); }
  say('       acceptance checks: all pass');
}
function fmtTime(s) { const m = Math.floor(s / 60); return `${m}m${String(Math.round(s - m * 60)).padStart(2, '0')}s`; }
main();
