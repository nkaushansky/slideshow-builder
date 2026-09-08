#!/usr/bin/env node
'use strict';
// bin/frames — render-mode frame sequences for every moving tile placement in build/manifest.json.
//   build/frames/<stem>/h<rowHeight>/%04d.jpg  JPEG frames at 30 fps, scaled (and tone-mapped) to the row height the
//   item landed in; Live Photos and GIFs in full, standalone videos from `start` for the visible window + 1 s.
// Idempotent: a placement whose directory holds a .done marker with the right frame count is skipped.
// Usage: bin/frames [--force] [--jobs N] [--quiet]      (bin/render runs this first)

const fs = require('fs');
const os = require('os');
const path = require('path');
const C = require('./common');

async function generateFrames(opts = {}) {
  const jobs = opts.jobs || os.cpus().length || 4;
  const say = s => { if (!opts.quiet) console.log(s); };
  const manifest = JSON.parse(fs.readFileSync(path.join(C.BUILD, 'manifest.json'), 'utf8'));
  const prep = C.readPrepManifest();
  if (!prep) throw new Error('build/prep-manifest.json missing; run bin/prep first');
  const tasks = [];
  for (const row of manifest.rows) {
    for (const e of row.items) {
      if (!e.frameDir) continue;
      const it = manifest.items[e.item];
      const clip = prep.clips[it.id];
      if (!clip) { console.warn(`frames: ${it.id} has no prep clip entry`); continue; }
      tasks.push({ it, e, row, clip, dir: path.join(C.ROOT, e.frameDir) });
    }
  }
  const results = { made: 0, skipped: 0, failed: 0, frames: 0, failures: [], padded: [] };
  const t0 = Date.now();
  let n = 0;
  await C.pool(tasks, jobs, async task => {
    const { it, e, clip, dir } = task;
    const marker = path.join(dir, '.done');
    if (!opts.force && fs.existsSync(marker)) {
      try { const d = JSON.parse(fs.readFileSync(marker, 'utf8')); if (d.frameCount === e.frameCount && d.files >= e.frameCount) { results.skipped++; results.frames += e.frameCount; return; } } catch (_) { /* regenerate */ }
    }
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    const probe = { avgFps: clip.sourceFps, nbFrames: clip.sourceFrames, hdr: clip.hdr, duration: clip.sourceDuration };
    const plan = C.clipPlan({ W: clip.sourceWidth, H: clip.sourceHeight, maxH: task.row.h, probe, realtime: clip.slow === 1 && clip.sourceFps >= C.SLOWMO_MIN_FPS });
    const slow = clip.slow || 1;
    const from = e.frameFrom, to = e.frameTo;
    // plan.vf ends with format=yuv420p; frames are JPEGs, so finish in full range instead. Sample at 30 fps before scaling.
    const vf = plan.vf.replace(/,?format=yuv420p$/, '').replace(/^setpts=[^,]+,?/, '') ;
    const chain = [];
    // Slow motion: stretch the timestamps like the clip does and let ffmpeg's constant-rate output (-r 30, as prep does)
    // pick the frames. The fps filter would instead duplicate a frame at every gap in these variable-rate captures.
    if (slow !== 1) chain.push(`setpts=PTS*${slow.toFixed(6)}`);
    else chain.push(`fps=${manifest.config.frameFps}`);
    if (vf) chain.push(vf);
    chain.push('format=yuvj420p');
    const args = ['-hide_banner', '-nostdin', '-v', 'error', '-y'];
    if (from > 0) args.push('-ss', (from / slow).toFixed(4));            // input seek: source seconds
    // -t after -i is an output duration, measured on the (stretched) output timestamps, so it is in display seconds.
    // 2026-09-03: dividing it by `slow` cut every slow-motion sequence to ~3 s and the padding below froze the rest.
    args.push('-i', path.join(C.MEDIA, it.id), '-t', (to - from + 0.2).toFixed(4), '-an', '-vf', chain.join(','));
    if (slow !== 1) args.push('-fps_mode', 'cfr', '-r', String(manifest.config.frameFps));
    args.push('-q:v', '3', '-start_number', '1', '-frames:v', String(e.frameCount + 2), path.join(dir, '%04d.jpg'));
    const res = await C.run(C.FFMPEG, args);
    n++;
    let files = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => /^\d{4}\.jpg$/.test(f)).sort() : [];
    if (res.code !== 0 || files.length === 0) {
      results.failed++; results.failures.push(`${it.id} h${task.row.h}: ${res.err.trim().split('\n').pop()}`);
      say(`  [frames ${n}/${tasks.length}] ${it.id} FAILED`);
      return;
    }
    // the fps filter can come up a frame short at the end: pad by repeating the last frame so every index exists.
    // More than a few padded frames means the sequence is short and the tile would freeze: fail loudly (see 2026-09-03).
    const padded = Math.max(0, e.frameCount - files.length);
    if (padded > C.FRAMES_PAD_MAX) {
      results.failed++; results.failures.push(`${it.id} h${task.row.h}: ffmpeg wrote ${files.length} of ${e.frameCount} frames (${padded} short); the tile would freeze`);
      say(`  [frames ${n}/${tasks.length}] ${it.id} h${task.row.h} SHORT: ${files.length}/${e.frameCount} frames`);
      return;
    }
    if (padded > 3) results.padded.push(`${it.id} h${task.row.h}: ${padded} frames padded`);
    while (files.length < e.frameCount) {
      const next = String(files.length + 1).padStart(4, '0') + '.jpg';
      fs.copyFileSync(path.join(dir, files[files.length - 1]), path.join(dir, next));
      files.push(next);
    }
    fs.writeFileSync(marker, JSON.stringify({ frameCount: e.frameCount, files: files.length, from, to, height: task.row.h, slow, hdr: clip.hdr }));
    results.made++; results.frames += e.frameCount;
    say(`  [frames ${n}/${tasks.length}] ${it.id} h${task.row.h} ${files.length} frames (${(to - from).toFixed(1)}s)${clip.hdr ? ' HDR->SDR' : ''}${slow !== 1 ? ' slow' : ''}`);
  });
  results.seconds = (Date.now() - t0) / 1000;
  results.placements = tasks.length;
  return results;
}

if (require.main === module) {
  const opt = { force: false, jobs: 0, quiet: false };
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--force') opt.force = true;
    else if (a[i] === '--jobs') opt.jobs = Number(a[++i]);
    else if (a[i] === '--quiet') opt.quiet = true;
    else { console.error('usage: bin/frames [--force] [--jobs N] [--quiet]'); process.exit(2); }
  }
  generateFrames(opt).then(r => {
    console.log(`frames: ${r.placements} placements, ${r.made} made, ${r.skipped} already there, ${r.failed} failed, ${r.frames} frames total, ${r.seconds.toFixed(0)}s`);
    for (const f of r.failures) console.log('  FAILED ' + f);
    for (const p of r.padded) console.log('  padded ' + p);
    process.exit(r.failed ? 1 : 0);
  }).catch(e => { console.error(e); process.exit(1); });
}
module.exports = { generateFrames };
