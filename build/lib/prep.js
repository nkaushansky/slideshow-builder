#!/usr/bin/env node
'use strict';
// bin/prep — derive display assets from handoff/media into the project's build/. Never touches media/.
//   build/tiles/<stem>.jpg      plain stills (Live Photo stills are never shown), JPEG q90, display height <= 1640
//   build/clips/<stem>.mp4      Live Photo .MP4 halves, standalone videos, GIFs -> H.264 muted, display height <= 1640
//   build/prep-manifest.json    per-file facts that build/render rely on (clip durations, slow-motion, HDR, dims)
//   build/prep-report.txt       verification report; build/prep.log has the per-file lines
// Idempotent: existing outputs are skipped unless --force. Outputs are written to a temp name and renamed.
// Usage: bin/prep [--only <filename>]... [--force] [--tiles-only|--clips-only] [--verify-only] [--jobs N] [--quiet]

const fs = require('fs');
const os = require('os');
const path = require('path');
const C = require('./common');

const USAGE = 'usage: bin/prep [--only <filename>]... [--force] [--tiles-only|--clips-only] [--verify-only] [--jobs N] [--quiet]';
const opt = { only: [], force: false, tiles: true, clips: true, verifyOnly: false, jobs: 0, quiet: false };
{
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--only') opt.only.push(a[++i]);
    else if (a[i] === '--force') opt.force = true;
    else if (a[i] === '--tiles-only') opt.clips = false;
    else if (a[i] === '--clips-only') opt.tiles = false;
    else if (a[i] === '--verify-only') opt.verifyOnly = true;
    else if (a[i] === '--jobs') opt.jobs = Number(a[++i]);
    else if (a[i] === '--quiet') opt.quiet = true;
    else if (a[i] === '-h' || a[i] === '--help') { console.log(USAGE); process.exit(0); }
    else { console.error('unknown argument: ' + a[i] + '\n' + USAGE); process.exit(2); }
  }
}
const JOBS = opt.jobs || os.cpus().length || 4;
const OPTIONS_FILE = path.join(__dirname, '..', 'prep-options.json');

const exists = p => { try { return fs.statSync(p).size > 0; } catch (_) { return false; } };
const rm = p => { try { fs.unlinkSync(p); } catch (_) { /* ignore */ } };

let logStream = null;
const report = [];
function log(line) { if (!opt.quiet) console.log(line); if (logStream) logStream.write(line + '\n'); }
function say(line) { console.log(line); if (logStream && opt.quiet) logStream.write(line + '\n'); }
function note(line) { report.push(line); }
function warn(line) { report.push('WARN  ' + line); say('  ! ' + line); }
let fatal = 0;
function error(line) { fatal++; report.push('ERROR ' + line); say('  X ' + line); }

function loadOptions() {
  try { return JSON.parse(fs.readFileSync(OPTIONS_FILE, 'utf8')); } catch (_) { return {}; }
}

// ---------- set verification (the HANDOFF.md checks plus a few of our own) ----------
function verifySet(rows) {
  const byName = new Map(rows.map(r => [r.filename, r]));
  const onDisk = new Set(fs.readdirSync(C.MEDIA).filter(f => !f.startsWith('.') && !C.IGNORED_FILES.has(f)));
  const missing = rows.filter(r => !onDisk.has(r.filename)).map(r => r.filename);
  const extra = [...onDisk].filter(f => !byName.has(f));
  const counts = {};
  for (const r of rows) counts[r.type] = (counts[r.type] || 0) + 1;
  const items = rows.filter(r => r.type !== 'livephoto-still').length;
  note(`media.csv rows ${rows.length}; files on disk ${onDisk.size}; items ${items}; ` +
    Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(', '));
  if (missing.length) (opt.only.length ? warn : error)(`${missing.length} media.csv rows missing on disk: ${missing.slice(0, 5).join(', ')}${missing.length > 5 ? ' ...' : ''}`);
  if (extra.length) warn(`${extra.length} files on disk not in media.csv (ignored): ${extra.slice(0, 5).join(', ')}`);
  if (new Set(rows.map(r => r.filename)).size !== rows.length) error('duplicate filenames in media.csv');
  for (const r of rows) {
    if (r.companion) {
      const c = byName.get(r.companion);
      if (!c) error(`${r.filename}: companion ${r.companion} not in media.csv`);
      else if (c.companion !== r.filename) error(`${r.filename}: companion link not symmetric`);
      if (!r.type.startsWith('livephoto')) error(`${r.filename}: has a companion but type is ${r.type}`);
    } else if (r.type.startsWith('livephoto')) error(`${r.filename}: ${r.type} without companion`);
    if (!/^\d{4}-\d{2}-\d{2}_/.test(r.filename)) error(`${r.filename}: no date prefix`);
    else if (r.filename.slice(0, 10) !== r.date) error(`${r.filename}: filename prefix differs from date ${r.date}`);
    if (!['day', 'month', 'year'].includes(r.precision)) error(`${r.filename}: bad precision ${r.precision}`);
    if (!(+r.width > 0 && +r.height > 0)) error(`${r.filename}: missing dimensions`);
    if (C.CLIP_TYPES.has(r.type) && !(+r.duration_s > 0)) error(`${r.filename}: missing duration`);
  }
  const { names: feats } = C.readFeatures();
  const featYes = new Set(rows.filter(r => r.featured === 'yes').map(r => r.filename));
  for (const f of feats) {
    const r = byName.get(f);
    if (!r) error(`features.txt: ${f} not in media.csv`);
    else if (!['still', 'livephoto-still'].includes(r.type)) error(`features.txt: ${f} is ${r.type}, not a still`);
  }
  const onlyCsv = [...featYes].filter(f => !feats.includes(f));
  if (onlyCsv.length) error(`featured=yes but not in features.txt: ${onlyCsv.join(', ')}`);
  if (new Set(feats).size !== feats.length) error('features.txt has duplicate lines');
  note(`features.txt ${feats.length} lines, featured=yes ${featYes.size}`);
  for (const [label, list] of [['stills', rows.filter(r => r.type === 'still')], ['clips', rows.filter(r => C.CLIP_TYPES.has(r.type))]]) {
    const seen = new Map();
    for (const r of list) { const s = C.stemOf(r.filename); if (seen.has(s)) error(`${label}: stem collision ${seen.get(s)} / ${r.filename}`); seen.set(s, r.filename); }
  }
  try {
    const cut = C.readCsvObjects(C.CUT_LIST_CSV).rows.length;
    note(`cut-list.csv rows ${cut}; media + cut = ${rows.length + cut}`);
  } catch (e) { warn('cut-list.csv unreadable: ' + e.message); }
}

// ---------- tiles ----------
async function makeTile(r) {
  const src = path.join(C.MEDIA, r.filename);
  const out = C.tilePath(r.filename);
  const tmp = out + '.tmp';
  const W = +r.width, H = +r.height;
  if (!opt.force && exists(out)) return { status: 'skipped' };
  if (!exists(src)) return { status: 'failed', error: 'source missing' };
  const t = Date.now();
  let rotated = false;
  try {
    const info = await C.imageInfo(src);
    const stored = { width: info.storedWidth, height: info.storedHeight };
    if (stored.width === W && stored.height === H) rotated = false;
    else if (stored.width === H && stored.height === W) rotated = true;
    else warn(`${r.filename}: stored ${stored.width}x${stored.height} is neither media.csv ${W}x${H} nor its transpose`);
  } catch (e) { return { status: 'failed', error: e.message }; }
  const needResize = H > C.MAX_TILE_H;
  const isJpeg = /\.jpe?g$/i.test(r.filename);
  rm(tmp);
  if (!needResize && isJpeg) {
    fs.copyFileSync(src, tmp);
  } else {
    try { await C.makeJpeg(src, tmp, { maxHeight: needResize ? C.MAX_TILE_H : 0, quality: 90, storedRotated: rotated }); }
    catch (e) { rm(tmp); return { status: 'failed', error: e.message }; }
    if (!exists(tmp)) { rm(tmp); return { status: 'failed', error: 'converter wrote nothing' }; }
  }
  fs.renameSync(tmp, out);
  return { status: 'done', ms: Date.now() - t, rotated, resized: needResize };
}
function verifyTile(r) {
  const out = C.tilePath(r.filename);
  if (!exists(out)) return { ok: false, error: 'missing' };
  const info = C.jpegInfo(fs.readFileSync(out));
  if (!info || !info.width) return { ok: false, error: 'unreadable JPEG' };
  const d = C.displayedDims(info, info.orientation);
  const W = +r.width, H = +r.height;
  const expectH = Math.min(C.MAX_TILE_H, H);
  const problems = [];
  if (Math.abs(d.width / d.height - W / H) / (W / H) > 0.006) problems.push(`aspect ${d.width}x${d.height} vs csv ${W}x${H}`);
  if (Math.abs(d.height - expectH) > 1) problems.push(`height ${d.height}, expected ${expectH}`);
  return { ok: problems.length === 0, error: problems.join('; '), width: d.width, height: d.height, storedRotated: info.orientation >= 5, orientation: info.orientation };
}

// ---------- clips ----------
async function makeClip(r, probe, realtime) {
  const src = path.join(C.MEDIA, r.filename);
  const out = C.clipPath(r.filename);
  const tmp = out + '.tmp';
  if (!opt.force && exists(out)) return { status: 'skipped' };
  if (!exists(src)) return { status: 'failed', error: 'source missing' };
  const t = Date.now();
  const plan = C.clipPlan({ W: +r.width, H: +r.height, maxH: C.MAX_CLIP_H, probe, realtime });
  const args = ['-hide_banner', '-nostdin', '-v', 'error', '-y', '-i', src, '-an', '-vf', plan.vf,
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart'];
  if (probe.hdr) args.push('-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709');
  if (plan.slow !== 1) args.push('-r', '30');
  args.push('-f', 'mp4', tmp);
  rm(tmp);
  const res = await C.run(C.FFMPEG, args);
  if (res.code !== 0 || !exists(tmp)) { rm(tmp); return { status: 'failed', error: res.err.trim().split('\n').slice(-2).join(' | ') }; }
  fs.renameSync(tmp, out);
  return { status: 'done', ms: Date.now() - t, plan };
}
async function verifyClip(r, probe, realtime) {
  const out = C.clipPath(r.filename);
  if (!exists(out)) return { ok: false, error: 'missing' };
  const plan = C.clipPlan({ W: +r.width, H: +r.height, maxH: C.MAX_CLIP_H, probe, realtime });
  let o;
  try { o = await C.probeVideo(out); } catch (e) { return { ok: false, error: e.message }; }
  const problems = [];
  if (o.width !== plan.ow || o.height !== plan.oh) problems.push(`dims ${o.width}x${o.height}, planned ${plan.ow}x${plan.oh}`);
  if (o.width % 2 || o.height % 2) problems.push('odd dimension');
  // a container can run longer than its video stream (audio tail / edit list); the stream length is what we can show
  const streamLen = probe.nbFrames && probe.avgFps ? probe.nbFrames / probe.avgFps : probe.duration;
  const expected = plan.slow !== 1 ? plan.outDuration : Math.min(plan.outDuration, streamLen);
  if (Math.abs(o.duration - expected) > 0.35) problems.push(`duration ${o.duration.toFixed(2)}, expected ${expected.toFixed(2)}`);
  if (o.codec !== 'h264') problems.push('codec ' + o.codec);
  if (o.hasAudio) problems.push('has audio');
  return { ok: problems.length === 0, error: problems.join('; '), width: o.width, height: o.height, duration: o.duration, fps: o.avgFps, nbFrames: o.nbFrames, plan };
}

async function main() {
  const t0 = Date.now();
  C.ensureDirs();
  logStream = fs.createWriteStream(path.join(C.BUILD, 'prep.log'), { flags: 'a' });
  log(`\n==== prep ${new Date().toISOString()} ${process.argv.slice(2).join(' ')}`);
  const options = loadOptions();
  const realtime = new Set(options.realtime || []);
  const { rows } = C.readMediaCsv();
  const byName = new Map(rows.map(r => [r.filename, r]));

  say('Verifying the set...');
  verifySet(rows);
  for (const f of opt.only) if (!byName.has(f)) error(`--only ${f}: not in media.csv`);
  if (fatal) { finish(t0, null); process.exit(1); }

  const stills = rows.filter(r => r.type === 'still');
  const clips = rows.filter(r => C.CLIP_TYPES.has(r.type));
  const pick = list => (opt.only.length ? list.filter(r => opt.only.includes(r.filename)) : list);
  const tally = list => { const c = { done: 0, skipped: 0, failed: 0 }; for (const x of list) c[x.status]++; return c; };
  const failures = [];

  // ---- tiles
  if (opt.tiles && !opt.verifyOnly) {
    const todo = pick(stills);
    say(`Tiles: ${todo.length} stills, ${JOBS} at a time -> ${C.rel(C.TILES)}`);
    let n = 0;
    const results = await C.pool(todo, JOBS, async r => {
      const res = await makeTile(r);
      n++;
      if (res.status === 'done') log(`  [tile ${n}/${todo.length}] ${r.filename} ${C.fmtSecs(res.ms)}${res.rotated ? ' (stored rotated)' : ''}${res.resized ? '' : ' (no resize)'}`);
      else if (res.status === 'failed') { log(`  [tile ${n}/${todo.length}] ${r.filename} FAILED: ${res.error}`); failures.push(`tile ${r.filename}: ${res.error}`); }
      return res;
    });
    const c = tally(results);
    say(`  tiles: ${c.done} made, ${c.skipped} already there, ${c.failed} failed`);
    note(`tiles: ${c.done} made, ${c.skipped} skipped, ${c.failed} failed`);
  }

  // ---- clips
  const probes = new Map();
  say(`Probing ${clips.length} clips...`);
  await C.pool(clips, 4, async r => {
    try { probes.set(r.filename, await C.probeVideo(path.join(C.MEDIA, r.filename))); }
    catch (e) { if (!opt.only.length || opt.only.includes(r.filename)) warn(`${r.filename}: ${e.message}`); }
  });
  for (const r of clips) {
    const p = probes.get(r.filename);
    if (!p) continue;
    if (p.width !== +r.width || p.height !== +r.height) warn(`${r.filename}: ffprobe ${p.width}x${p.height} (rotation ${p.rotation}) vs media.csv ${r.width}x${r.height}`);
    if (Math.abs(p.duration - +r.duration_s) > 0.3) warn(`${r.filename}: ffprobe duration ${p.duration.toFixed(2)} vs media.csv ${r.duration_s}`);
  }
  const hdr = clips.filter(r => probes.get(r.filename) && probes.get(r.filename).hdr);
  const slow = clips.filter(r => probes.get(r.filename) && probes.get(r.filename).avgFps >= C.SLOWMO_MIN_FPS && !realtime.has(r.filename));
  note(`HDR (tone-mapped to SDR): ${hdr.length} -> ${hdr.map(r => r.filename).join(', ')}`);
  note(`slow-motion (>= ${C.SLOWMO_MIN_FPS} fps source, played at 30 fps): ${slow.length} -> ` +
    slow.map(r => `${r.filename} (${r.duration_s}s real -> ${(probes.get(r.filename).nbFrames / 30).toFixed(1)}s)`).join(', '));
  if (realtime.size) note(`forced real-time by prep-options.json: ${[...realtime].join(', ')}`);

  if (opt.clips && !opt.verifyOnly) {
    const todo = pick(clips).filter(r => probes.has(r.filename));
    // heaviest first so the lanes stay balanced
    const work = r => { const p = probes.get(r.filename); return p.duration * Math.min(p.avgFps, 60) * (+r.width) * (+r.height) * (p.hdr ? 3 : 1); };
    todo.sort((a, b) => work(b) - work(a));
    const lanes = Math.max(1, Math.floor(JOBS / 2));
    say(`Clips: ${todo.length} to encode, ${lanes} at a time -> ${C.rel(C.CLIPS)}`);
    let n = 0;
    const results = await C.pool(todo, lanes, async r => {
      const res = await makeClip(r, probes.get(r.filename), realtime.has(r.filename));
      n++;
      if (res.status === 'done') log(`  [clip ${n}/${todo.length}] ${r.filename} ${C.fmtSecs(res.ms)} ${res.plan.ow}x${res.plan.oh}${res.plan.slow !== 1 ? ` slow x${res.plan.slow.toFixed(1)}` : ''}${probes.get(r.filename).hdr ? ' HDR->SDR' : ''}`);
      else if (res.status === 'failed') { log(`  [clip ${n}/${todo.length}] ${r.filename} FAILED: ${res.error}`); failures.push(`clip ${r.filename}: ${res.error}`); }
      return res;
    });
    const c = tally(results);
    say(`  clips: ${c.done} made, ${c.skipped} already there, ${c.failed} failed`);
    note(`clips: ${c.done} made, ${c.skipped} skipped, ${c.failed} failed`);
  }

  // ---- verify everything that exists, write the manifest
  say('Verifying outputs...');
  const manifest = { generatedAt: new Date().toISOString(), maxTileHeight: C.MAX_TILE_H, maxClipHeight: C.MAX_CLIP_H, tiles: {}, clips: {} };
  let tileOk = 0, tileBad = 0, tileMissing = 0;
  for (const r of stills) {
    const v = verifyTile(r);
    if (v.error === 'missing') { tileMissing++; continue; }
    if (!v.ok) { tileBad++; warn(`tile ${r.filename}: ${v.error}`); }
    else tileOk++;
    manifest.tiles[r.filename] = { path: C.webRel(C.BUILD, C.tilePath(r.filename)), width: v.width, height: v.height, storedRotated: v.storedRotated, ok: v.ok };
  }
  let clipOk = 0, clipBad = 0, clipMissing = 0;
  await C.pool(clips.filter(r => probes.has(r.filename)), 4, async r => {
    const p = probes.get(r.filename);
    const v = await verifyClip(r, p, realtime.has(r.filename));
    if (v.error === 'missing') { clipMissing++; return; }
    if (!v.ok) { clipBad++; warn(`clip ${r.filename}: ${v.error}`); } else clipOk++;
    manifest.clips[r.filename] = {
      path: C.webRel(C.BUILD, C.clipPath(r.filename)), width: v.width, height: v.height, duration: v.duration, fps: v.fps,
      slow: v.plan.slow, hdr: p.hdr, sourceDuration: p.duration, sourceFps: p.avgFps, sourceFrames: p.nbFrames, sourceCodec: p.codec,
      sourceWidth: p.width, sourceHeight: p.height, ok: v.ok,
    };
  });
  note(`verified tiles ok ${tileOk}, bad ${tileBad}, missing ${tileMissing}; clips ok ${clipOk}, bad ${clipBad}, missing ${clipMissing}`);
  say(`  tiles ok ${tileOk} / bad ${tileBad} / missing ${tileMissing}; clips ok ${clipOk} / bad ${clipBad} / missing ${clipMissing}`);
  fs.writeFileSync(C.PREP_MANIFEST, JSON.stringify(manifest, null, 1));
  for (const f of failures) note('FAILED ' + f);
  finish(t0, manifest);
  process.exit(failures.length || fatal ? 1 : 0);
}

function finish(t0, manifest) {
  const lines = [`prep report ${new Date().toISOString()} (${C.fmtSecs(Date.now() - t0)})`, ...report];
  fs.writeFileSync(path.join(C.BUILD, 'prep-report.txt'), lines.join('\n') + '\n');
  say(`Done in ${C.fmtSecs(Date.now() - t0)}. Report: ${C.rel(path.join(C.BUILD, 'prep-report.txt'))}` + (manifest ? `, manifest: ${C.rel(C.PREP_MANIFEST)}` : ''));
  const bad = report.filter(l => /^(WARN|ERROR|FAILED)/.test(l));
  if (bad.length) say(`${bad.length} warning/error line(s) in the report.`);
  if (logStream) logStream.end();
}

main().catch(e => { console.error(e); process.exit(1); });
