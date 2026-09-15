#!/usr/bin/env node
'use strict';
// bin/render — deterministic mp4 from player.html?render=1.
//   1. bin/frames (frame sequences for moving tiles at their row heights; skipped if present)
//   2. serve the project over http://127.0.0.1 (a file:// page would taint the canvas) and open the player in headless Chrome
//   3. warm the scheduler through one full loop so frame 0 already sits in a periodic state (seamless wrap)
//   4. per frame: page updates to t = k/fps, draws the visible tiles into a canvas, JPEG-encodes it (q 0.95) and sends it over
//      a WebSocket; we pipe it into ffmpeg (image2pipe -> libx264) and ack once ffmpeg accepted it (backpressure)
//   5. verify: frame count, size, fps, no audio; wrap check = PSNR between frame 0 and the frame after the last one
//   6. with music (show.json audio.enabled): the prepared tracks become one playlist, cut to the file's length with the
//      fades and the volume, and are muxed over the verified render, both streams copied. The render itself then keeps
//      -silent before .mp4 (slideshow-silent.mp4) and the muxed file takes the plain name the launchers look for.
// Chromium: [tools] chrome from config.toml, else Playwright's bundled build, else installed Google Chrome (common.launchBrowser).
// Size and fps come from build/manifest.json (bin/build took them from handoff/show.json); the x264 preset/crf default from
// show.json's output.quality (final: slow/18, draft: veryfast/23) and the concat copy count from output.concat_copies;
// [machines] player = "tv-usb" adds an H.264 level for the stick's decoder and warns about files a FAT32 stick refuses.
// Usage: bin/render [--seconds N] [--from SECONDS] [--out FILE] [--preset slow|medium|...] [--crf N] [--q 0.95] [--skip-frames] [--labels] [--concat] [--dry-run] [--warm-loops N]
//   default renders exactly one loop to build/slideshow.mp4; --seconds 60 is the quick test render; --from 470 --seconds 40
//   renders a window from inside the loop (the scheduler is stepped up to that point without drawing, so the state is right).
//   --labels draws the review labels (filename, date, row, chapter) into every frame and names the file -labels, for an owner
//   who is not at the machine; --concat (alias --x3) also writes slideshow-x<N>.mp4, N copies back to back, for the launchers
//   (with music: N silent copies joined, then one soundtrack over the whole file, so the music runs across the seams).
//   --dry-run prints the whole plan (frames, output names, the playlist junctions, the soundtrack and every ffmpeg command)
//   and writes nothing at all: no frames, no mp4, no playlist, no soundtrack, no render log.
// A muxed file that fails its check is renamed BAD-<name>.mp4 and an older file of the plain name left by a failed mux is
// renamed OLD-<name>.mp4, because the launchers play slideshow-x*.mp4 and slideshow.mp4 and must never play either.

const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { spawn } = require('child_process');
const C = require('./common');
const cards = require('./cards');
const { generateFrames } = require('./frames');

// x264 settings per show.json output.quality; --preset/--crf on the command line override either
const QUALITY = { final: { preset: 'slow', crf: 18 }, draft: { preset: 'veryfast', crf: 23 } };
const SHOW = C.SHOW;
const quality = SHOW ? String(SHOW.output.quality) : 'final';
const concatCopies = SHOW ? SHOW.output.concat_copies : 3;
const PLAYER = SHOW && SHOW.machines && SHOW.machines.player ? String(SHOW.machines.player) : 'vlc';
const AUDIO = C.audioSettings();    // a bad [audio] value stops here, before an hour of rendering
const opt = { seconds: 0, from: 0, out: '', preset: '', crf: null, q: 0.95, skipFrames: false, labels: false, concat: false, dryRun: false, jobs: 0, warmLoops: 8 };
{
  const usage = 'usage: bin/render [--seconds N] [--from SECONDS] [--out FILE] [--preset P] [--crf N] [--q 0.95] [--skip-frames] [--labels] [--concat] [--dry-run] [--warm-loops N]';
  if (!QUALITY[quality]) { console.error(`show.json output.quality "${quality}" is not final or draft; fix [output] quality in config.toml and run python curate/run.py show`); process.exit(2); }
  if (!(Number.isInteger(concatCopies) && concatCopies >= 1)) { console.error(`show.json output.concat_copies ${JSON.stringify(concatCopies)} is not a whole number of copies; fix [output] concat_copies in config.toml and run python curate/run.py show`); process.exit(2); }
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--seconds') opt.seconds = Number(a[++i]);
    else if (a[i] === '--from') opt.from = Number(a[++i]);
    else if (a[i] === '--warm-loops') opt.warmLoops = Number(a[++i]);
    else if (a[i] === '--out') opt.out = a[++i];
    else if (a[i] === '--preset') opt.preset = a[++i];
    else if (a[i] === '--crf') opt.crf = Number(a[++i]);
    else if (a[i] === '--q') opt.q = Number(a[++i]);
    else if (a[i] === '--skip-frames') opt.skipFrames = true;
    else if (a[i] === '--labels') opt.labels = true;
    else if (a[i] === '--concat' || a[i] === '--x3') opt.concat = true;
    else if (a[i] === '--dry-run') opt.dryRun = true;
    else if (a[i] === '--jobs') opt.jobs = Number(a[++i]);
    else { console.error(usage); process.exit(2); }
  }
  if (opt.from && !opt.seconds) { console.error('--from needs --seconds N (a partial render starting there)'); process.exit(2); }
  opt.tuned = !!opt.preset || opt.crf != null;
  if (!opt.preset) opt.preset = QUALITY[quality].preset;
  if (opt.crf == null) opt.crf = QUALITY[quality].crf;   // crf 0 (lossless) is a real choice, so null is the "not given" mark
}
const TYPES = { '.html': 'text/html', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.mp4': 'video/mp4', '.json': 'application/json' };
const logLines = [];
function log(s) { console.log(s); logLines.push(`${new Date().toISOString()} ${s}`); }

// ---------- minimal RFC 6455 server (binary frames in, text acks out) ----------
function wsAccept(key) { return crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64'); }
function wsSendText(sock, text) {
  const p = Buffer.from(text);
  const h = p.length < 126 ? Buffer.from([0x81, p.length]) : Buffer.from([0x81, 126, p.length >> 8, p.length & 255]);
  sock.write(Buffer.concat([h, p]));
}
function attachWs(sock, onMessage) {
  let head = Buffer.alloc(0), need = 0, got = 0, parts = [], mask = null, op = 0, fin = 0, inPayload = false, msgParts = [];
  sock.on('data', chunk => {
    let off = 0;
    while (off < chunk.length) {
      if (!inPayload) {
        head = head.length ? Buffer.concat([head, chunk.subarray(off)]) : chunk.subarray(off);
        if (head.length < 2) return;
        fin = head[0] & 0x80; op = head[0] & 0x0f; const masked = head[1] & 0x80; let len = head[1] & 0x7f, ho = 2;
        if (len === 126) { if (head.length < 4) return; len = head.readUInt16BE(2); ho = 4; }
        else if (len === 127) { if (head.length < 10) return; len = Number(head.readBigUInt64BE(2)); ho = 10; }
        if (masked) { if (head.length < ho + 4) return; mask = Buffer.from(head.subarray(ho, ho + 4)); ho += 4; } else mask = null;
        const rest = head.subarray(ho); head = Buffer.alloc(0);
        need = len; got = 0; parts = []; inPayload = true;
        chunk = rest; off = 0;
        if (!chunk.length) return;
        continue;
      }
      const take = Math.min(need - got, chunk.length - off);
      parts.push(chunk.subarray(off, off + take)); got += take; off += take;
      if (got === need) {
        inPayload = false;
        const payload = parts.length === 1 ? Buffer.from(parts[0]) : Buffer.concat(parts, need);
        if (mask) for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];
        if (op === 0x8) { sock.end(); return; }
        if (op === 0x9) { sock.write(Buffer.concat([Buffer.from([0x8a, payload.length]), payload])); continue; }
        msgParts.push(payload);
        if (fin) { const m = msgParts.length === 1 ? msgParts[0] : Buffer.concat(msgParts); msgParts = []; onMessage(m, op === 0x1); }
      }
    }
  });
}

function fmtTime(s) { const m = Math.floor(s / 60); return `${m}m${String(Math.round(s - m * 60)).padStart(2, '0')}s`; }
const withSuffix = (file, sfx) => { const p = path.parse(file); return path.join(p.dir, p.name + sfx + p.ext); };   // slideshow.mp4 + -silent -> slideshow-silent.mp4
const GIB = 1024 ** 3;

// ---------- the soundtrack (show.json audio) ----------
// After the silent render verifies: the prepared tracks (bin/prep, build/audio/NN-<stem>.m4a) are joined once per render
// into build/audio/playlist.m4a with a crossfade at every junction whose neighbours both outlast crossfade_s, the playlist
// is cut to the file's length with the volume and the fades applied (repeated when audio.loop is on; otherwise silence
// follows the last track, so the video is never shortened), and the result is muxed over the silent copy with both streams
// copied. Every step is probed afterwards; a length that is off by more than half a second is a PROBLEM.
const AAC = ['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart'];
const shellish = a => (/[\s'"$`\\]/.test(a) ? `"${a.replace(/(["$`\\])/g, '\\$1')}"` : a);
const cmdLine = args => [C.FFMPEG, ...args].map(shellish).join(' ');   // the command as --dry-run prints it

// A file that failed its check must not keep a name a launcher plays: they look for slideshow-x*.mp4 first, then
// slideshow.mp4, and neither pattern matches BAD-/OLD- in front of the name. The run still ends non-zero either way.
function setAside(file, prefix, why) {
  const p = path.parse(file);
  const aside = path.join(p.dir, `${prefix}-${p.name}${p.ext}`);
  try {
    if (fs.existsSync(aside)) fs.unlinkSync(aside);
    fs.renameSync(file, aside);
    log(`  ! ${why}: ${C.rel(file)} renamed to ${C.rel(aside)}, so no launcher picks it up (rename it back by hand if you want it)`);
  } catch (e) {
    log(`  ! ${why}: ${C.rel(file)} could NOT be moved out of the way (${e.message}); do not play it, the launchers would`);
    return null;
  }
  return aside;
}

// The playlist command and what it comes to, without running anything: --dry-run prints it and buildPlaylist runs it.
// Junction i joins the running mix with track i by acrossfade when both neighbours outlast the crossfade, else by a
// plain concat (a track no longer than the crossfade has nothing to fade across), and every such junction is named.
function playlistPlan(tracks) {
  const out = path.join(C.AUDIO, 'playlist.m4a');
  const cf = AUDIO.crossfade;
  const args = ['-hide_banner', '-nostdin', '-v', 'error', '-y'];
  for (const t of tracks) args.push('-i', t.abs);
  let expected = tracks.reduce((s, t) => s + t.duration, 0), faded = 0;
  const plain = [];
  if (tracks.length === 1) args.push('-map', '0:a:0', '-c:a', 'copy', '-movflags', '+faststart', out);
  else {
    const steps = []; let prev = '[0:a]';
    for (let i = 1; i < tracks.length; i++) {
      const next = i === tracks.length - 1 ? '[mix]' : `[j${i}]`;
      if (cf > 0 && tracks[i - 1].duration > cf && tracks[i].duration > cf) { steps.push(`${prev}[${i}:a]acrossfade=d=${cf}${next}`); faded++; expected -= cf; }
      else {
        steps.push(`${prev}[${i}:a]concat=n=2:v=0:a=1${next}`);
        const short = [tracks[i - 1], tracks[i]].filter(t => t.duration <= cf).map(t => `${path.posix.basename(t.path)} ${t.duration.toFixed(1)}s`);
        plain.push(`junction ${i} (${path.posix.basename(tracks[i - 1].path)} to ${path.posix.basename(tracks[i].path)}): plain concat, hard cut, no crossfade` +
          (cf > 0 ? ` (${short.join(' and ')} ${short.length > 1 ? 'are' : 'is'} not longer than the ${cf}s crossfade)` : ' (crossfade_s is 0)'));
      }
      prev = next;
    }
    args.push('-filter_complex', steps.join(';'), '-map', '[mix]', ...AAC, out);
  }
  const line = `playlist of ${tracks.length} track(s): ${tracks.map(t => `${path.posix.basename(t.path)} ${t.duration.toFixed(1)}s`).join(', ')}; ` +
    `${faded} crossfade(s) of ${cf}s` + (plain.length ? `; ${plain.join('; ')}` : '');
  return { out, args, expected, faded, plain, line };
}
async function buildPlaylist(tracks) {
  const plan = playlistPlan(tracks);
  const r = await C.run(C.FFMPEG, plan.args);
  if (r.code !== 0) throw new Error(`playlist: ffmpeg failed: ${r.err.trim().split('\n').pop()}`);
  const p = await C.probeAudio(plan.out);
  log(`soundtrack: ${plan.line} -> ${C.rel(plan.out)} ${p.duration.toFixed(1)}s`);
  if (Math.abs(p.duration - plan.expected) > 0.5) throw new Error(`playlist ${C.rel(plan.out)} is ${p.duration.toFixed(2)}s, expected ${plan.expected.toFixed(2)}s`);
  return { file: plan.out, duration: p.duration };
}
// The soundtrack command for one output file, likewise: the playlist cut to D with the volume and the fades.
function soundtrackPlan(playlist, D, target) {
  const out = path.join(C.AUDIO, path.parse(target).name + '.soundtrack.m4a');
  const F = AUDIO.fade, filters = [`volume=${AUDIO.volume}`];
  let fadeOutAt = Math.max(0, D - F), early = false;
  if (!AUDIO.loop && playlist.duration < D) { fadeOutAt = Math.max(0, playlist.duration - F); early = true; }
  if (F > 0) filters.push(`afade=t=in:st=0:d=${F}`, `afade=t=out:st=${fadeOutAt.toFixed(3)}:d=${F}`);
  filters.push('apad');   // silence after the music when it ends early, so -t always yields D and -shortest never cuts the video
  const args = ['-hide_banner', '-nostdin', '-v', 'error', '-y'];
  if (AUDIO.loop) args.push('-stream_loop', '-1');
  args.push('-i', playlist.file, '-t', D.toFixed(3), '-af', filters.join(','), ...AAC, out);
  const line = `${D.toFixed(3)}s for ${path.basename(target)}: playlist ${AUDIO.loop ? 'repeated' : 'once'}` +
    `${early ? ` (the music ends early, at ${playlist.duration.toFixed(1)}s of ${D.toFixed(1)}s; silence after)` : ''}, volume ${AUDIO.volume}, ` +
    `${F > 0 ? `fade in ${F}s from 0s, fade out ${F}s from ${fadeOutAt.toFixed(1)}s` : 'no fades'}`;
  return { out, args, filters, early, fadeOutAt, line };
}
async function makeSoundtrack(playlist, D, target) {
  const plan = soundtrackPlan(playlist, D, target);
  const r = await C.run(C.FFMPEG, plan.args);
  if (r.code !== 0) throw new Error(`soundtrack: ffmpeg failed: ${r.err.trim().split('\n').pop()}`);
  const p = await C.probeAudio(plan.out);
  log(`soundtrack: ${plan.line} -> ${C.rel(plan.out)} ${p.duration.toFixed(3)}s`);
  if (Math.abs(p.duration - D) > 0.5) throw new Error(`soundtrack ${C.rel(plan.out)} is ${p.duration.toFixed(2)}s, wanted ${D.toFixed(2)}s`);
  return plan.out;
}
// -shortest only guards against an encoder tail of a few milliseconds: the soundtrack is already cut to D. Returns the
// problems found by probing the result (the muxed file must carry every frame of the silent one and D seconds of AAC).
const muxArgs = (silent, soundtrack, out) => ['-hide_banner', '-nostdin', '-v', 'error', '-y', '-i', silent, '-i', soundtrack,
  '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'copy', '-shortest', '-movflags', '+faststart', '-f', 'mp4', out];
async function mux(silent, soundtrack, out, D, framesWanted) {
  const tmp = out + '.tmp';
  const r = await C.run(C.FFMPEG, muxArgs(silent, soundtrack, tmp));
  if (r.code !== 0 || !fs.existsSync(tmp)) {
    try { fs.unlinkSync(tmp); } catch (_) { /* nothing to remove */ }
    // nothing was written under `out`, so a file of that name is an earlier render: it must not be what plays on the day
    if (fs.existsSync(out)) setAside(out, 'OLD', 'the mux failed and this file is from an earlier render, not this one');
    throw new Error(`mux: ffmpeg failed: ${r.err.trim().split('\n').pop()}`);
  }
  fs.renameSync(tmp, out);
  const j = await C.ffprobeJson(out);
  const v = (j.streams || []).find(s => s.codec_type === 'video'), a = (j.streams || []).find(s => s.codec_type === 'audio');
  const vFrames = v ? Number(v.nb_frames) || 0 : 0, aDur = a ? Number(a.duration) || 0 : 0;
  log(`mux: ${path.basename(silent)} + soundtrack -> ${C.rel(out)}: video ${v ? v.codec_name : 'NONE'} ${vFrames} frames, audio ${a ? `${a.codec_name} ${a.channels} ch ${a.sample_rate} Hz ${aDur.toFixed(3)}s` : 'NONE'}, ${(fs.statSync(out).size / 1e6).toFixed(1)} MB`);
  const problems = [];
  if (!a) problems.push(`${C.rel(out)}: no audio stream after the mux`);
  else if (Math.abs(aDur - D) > 0.5) problems.push(`${C.rel(out)}: audio ${aDur.toFixed(2)}s differs from ${D.toFixed(2)}s by more than 0.5 s`);
  if (!v || vFrames !== framesWanted) problems.push(`${C.rel(out)}: ${vFrames} video frames after the mux, expected ${framesWanted}`);
  if (problems.length) {
    const aside = setAside(out, 'BAD', 'the muxed file failed its check');
    // the PROBLEMS list must name the file as it now is, not the name it lost
    if (aside) for (let i = 0; i < problems.length; i++) problems[i] = problems[i].split(C.rel(out)).join(C.rel(aside));
  }
  return problems;
}
function sizeNote(file) {   // tv-usb: a FAT32 stick refuses a file of 4 GiB or more; a warning, never a failure
  const size = fs.statSync(file).size;
  if (PLAYER === 'tv-usb' && size >= 4 * GIB) log(`  ! ${C.rel(file)} is ${(size / GIB).toFixed(2)} GiB: FAT32 sticks refuse files of 4 GiB and over; use quality draft, fewer concat copies, or an exFAT stick`);
}

// a mistake in the config or on the command line: the message is the whole story, so the stack is noise
function userError(msg) { const e = new Error(msg); e.user = true; return e; }

async function main() {
  const t0 = Date.now();
  const manifest = JSON.parse(fs.readFileSync(path.join(C.BUILD, 'manifest.json'), 'utf8'));
  const fps = manifest.config.renderFps;
  const total = opt.seconds ? Math.round(opt.seconds * fps) : manifest.loop.frames;
  const k0 = Math.round(opt.from * fps);
  const suffix = opt.labels ? '-labels' : '';           // a labelled render is never the file the launchers pick up
  const finalOut = path.resolve(opt.out || path.join(C.BUILD, opt.seconds ? `test-${opt.from ? opt.from + 's-' : ''}${opt.seconds}s${suffix}.mp4` : `slideshow${suffix}.mp4`));
  const out = AUDIO.enabled ? withSuffix(finalOut, '-silent') : finalOut;   // with music the render is the silent copy and the mux writes finalOut
  // Cards belong to the show, not to a window on it: only a whole-loop render gets them. The loop is rendered to its
  // own file so its frames (and the wrap check) are exactly what they always were, then title + loop + end are joined.
  // the cards come from manifest.json, which bin/build wrote from show.json: a card edited in config.toml and
  // pushed through `run.py show` without a rebuild would otherwise be rendered in its old words, silently
  if (SHOW) {
    const want = cards.cardsOf({ cards: (SHOW.show || {}).cards, playback: (SHOW.show || {}).playback });
    const have = cards.cardsOf(manifest);
    for (const k of ['title', 'end', 'seconds', 'fade', 'playback']) {
      if (want[k] !== have[k]) throw userError(`${C.rel(C.SHOW_JSON)} and build/manifest.json disagree about the show's ${k === 'playback' ? 'playback' : `${k} card setting`} (${JSON.stringify(have[k])} in the manifest, ${JSON.stringify(want[k])} in show.json); run bin/build`);
    }
  }
  const cardPlan = (opt.seconds || opt.from) ? [] : cards.plan(manifest, out);
  const cardFrames = cardPlan.reduce((n, c) => n + Math.round(c.seconds * fps), 0);
  const videoOut = cardPlan.length ? withSuffix(out, '-loop') : out;        // what the frame render writes
  const videoFrames = total + cardFrames;                                    // what `out` holds once the cards are on
  if (cardPlan.length && opt.concat && cards.cardsOf(manifest).playback === 'once') {
    throw userError('[show] playback = "once" with --concat: copies of a show that ends are not a show. Render without --concat, or set playback = "loop" in config.toml and run python curate/run.py show');
  }
  if (!cardPlan.length && (opt.seconds || opt.from)) {
    const c = cards.cardsOf(manifest);
    if (c.title || c.end) log('cards: skipped (they go on a full-loop render only)');
  }
  log(`render: ${total} frames at ${fps} fps (${fmtTime(total / fps)})${k0 ? ` from frame ${k0} (t=${fmtTime(k0 / fps)})` : ''} -> ${C.rel(videoOut)}${AUDIO.enabled ? ` (silent; the soundtrack goes into ${C.rel(finalOut)})` : ''}; loop ${manifest.loop.frames} frames = ${fmtTime(manifest.loop.seconds)} at ${manifest.loop.speed.toFixed(3)} px/s; x264 ${opt.preset} crf ${opt.crf} (quality ${quality}${opt.tuned ? ', --preset/--crf given' : ''}), jpeg q ${opt.q}${opt.labels ? '; labels on' : ''}`);
  if (!SHOW) log('handoff/show.json missing; quality final (x264 slow, crf 18) and 3 concat copies assumed; run `python curate/run.py show`');
  if (!fs.existsSync(path.join(C.BUILD, 'player.html'))) throw new Error('player.html missing; run bin/build');
  // the tracks are checked now, so a stale preparation stops the run before the frames, not after them
  const prepared = C.preparedAudio(C.readPrepManifest());
  if (AUDIO.enabled && !prepared.enabled) throw new Error(`audio: ${prepared.why}`);
  if (AUDIO.enabled) {
    log(`audio: ${prepared.tracks.length} track(s) (${prepared.tracks.map(t => path.posix.basename(t.path)).join(', ')}), ${AUDIO.loop ? 'repeated' : 'once through'}, crossfade ${AUDIO.crossfade}s, fade ${AUDIO.fade}s, volume ${AUDIO.volume}`);
    if (!(manifest.audio && manifest.audio.enabled)) log('  ! manifest.json has no music for the live player (built before the tracks were prepared?); run bin/build for player.html');
  }
  // tv-usb: a TV stick's hardware decoder wants a declared H.264 level; 4.1 covers 1080p30, 4.2 1080p60, 5.1 anything larger
  const levelArgs = [];
  if (PLAYER === 'tv-usb') {
    const w = manifest.config.viewportW, h = manifest.config.viewportH;
    const hd = Math.max(w, h) <= 1920 && Math.min(w, h) <= 1080;
    const level = !hd ? '5.1' : fps > 30 ? '4.2' : '4.1';
    levelArgs.push('-profile:v', 'high', '-level', level);
    log(`tv-usb: x264 profile high, level ${level} (${w}x${h} at ${fps} fps)`);
  }

  // --dry-run: the whole plan, then out. Nothing above this point has written anything, and nothing below runs.
  if (opt.dryRun) {
    log('dry run: nothing is written - no frame sequences, no mp4, no playlist, no soundtrack, no render log');
    log(`  video: ${total} frames at ${fps} fps = ${fmtTime(total / fps)}${k0 ? `, starting at frame ${k0} (t=${fmtTime(k0 / fps)})` : ''}, ` +
      `${manifest.config.viewportW}x${manifest.config.viewportH}, x264 ${opt.preset} crf ${opt.crf}${levelArgs.length ? ' ' + levelArgs.join(' ') : ''}, jpeg q ${opt.q}`);
    log(`  frames: ${opt.skipFrames ? 'left alone (--skip-frames)' : "bin/frames would generate or check the moving tiles' frame sequences first"}`);
    log(`  would write ${C.rel(cardPlan.length ? videoOut : out)}${cardPlan.length ? ` (the loop alone), joined with the cards into ${C.rel(out)}` : ''}${AUDIO.enabled ? ` (silent), then ${C.rel(finalOut)} with the music (the name the launchers play)` : ''}`);
    for (const c of cardPlan) {
      log(`  ${c.which} card: ${JSON.stringify(c.text)} for ${c.seconds}s (${Math.round(c.seconds * fps)} frames, fade ${c.fade}s) -> ${C.rel(c.png)}, ${C.rel(c.mp4)}`);
    }
    if (cardPlan.length) log(`  join: ${[...cardPlan.filter(c => c.which === 'title').map(c => path.basename(c.mp4)), path.basename(videoOut), ...cardPlan.filter(c => c.which === 'end').map(c => path.basename(c.mp4))].join(' + ')} -> ${C.rel(out)} (streams copied); ${videoFrames} frames in all`);
    if (AUDIO.enabled) {
      const pl = playlistPlan(prepared.tracks);
      log(`  ${pl.line} -> ${C.rel(pl.out)}, ${pl.expected.toFixed(1)}s expected`);
      log(`    ${cmdLine(pl.args)}`);
      const st = soundtrackPlan({ file: pl.out, duration: pl.expected }, videoFrames / fps, finalOut);
      log(`  soundtrack: ${st.line} -> ${C.rel(st.out)}`);
      log(`    ${cmdLine(st.args)}`);
      log(`  mux: ${C.rel(out)} + ${C.rel(st.out)} -> ${C.rel(finalOut)} (written as ${C.rel(finalOut)}.tmp and renamed, then probed)`);
      log(`    ${cmdLine(muxArgs(out, st.out, finalOut + '.tmp'))}`);
    }
    if (opt.concat) {
      const N = concatCopies;
      const xnSilent = withSuffix(out, `-x${N}`), xn = withSuffix(finalOut, `-x${N}`);
      log(`  concat: ${N} copies of ${path.basename(out)} -> ${C.rel(xnSilent)} (through ${C.rel(path.join(C.BUILD, 'concat-list.txt'))})`);
      if (AUDIO.enabled) {
        const pl2 = playlistPlan(prepared.tracks);
        const st2 = soundtrackPlan({ file: pl2.out, duration: pl2.expected }, N * videoFrames / fps, xn);
        log(`  soundtrack for the ${N} copies: ${st2.line} -> ${C.rel(st2.out)}`);
        log(`    ${cmdLine(st2.args)}`);
        log(`  mux: ${C.rel(xnSilent)} + ${C.rel(st2.out)} -> ${C.rel(xn)}; ${C.rel(xnSilent)} is removed once ${C.rel(xn)} verifies`);
        log(`    ${cmdLine(muxArgs(xnSilent, st2.out, xn + '.tmp'))}`);
      }
    }
    log('dry run: end of the plan; nothing was written');
    return;
  }

  // 1. frames
  if (!opt.skipFrames) {
    log('frames: generating/checking frame sequences for moving tiles...');
    const r = await generateFrames({ quiet: true, jobs: opt.jobs });
    log(`frames: ${r.placements} placements, ${r.made} made, ${r.skipped} already there, ${r.failed} failed, ${r.frames} frames, ${r.seconds.toFixed(0)}s`);
    for (const f of r.failures) log('  FAILED ' + f);
    for (const p of r.padded) log('  padded ' + p);
    if (r.failed) throw new Error('frame generation failed');
  }

  // 2. server: static files + websocket frame sink
  let ffmpeg = null, frameSock = null, received = 0, bytes = 0, ffmpegErr = '', ffmpegDone = null;
  let firstJpeg = null, lastJpeg = null, wrapJpeg = null, capturing = true;
  const server = http.createServer((req, res) => {
    const p = path.join(C.BUILD, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!p.startsWith(C.BUILD) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(p).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    fs.createReadStream(p).pipe(res);
  });
  server.on('upgrade', (req, sock) => {
    sock.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + wsAccept(req.headers['sec-websocket-key']) + '\r\n\r\n');
    sock.setNoDelay(true);
    frameSock = sock;
    attachWs(sock, (msg) => {
      if (!capturing) { wrapJpeg = msg; return wsSendText(sock, 'ok wrap'); }
      if (!(msg[0] === 0xFF && msg[1] === 0xD8)) return wsSendText(sock, 'not a jpeg');
      received++; bytes += msg.length;
      if (received === 1) firstJpeg = msg;
      lastJpeg = msg;
      if (!ffmpeg || ffmpeg.exitCode !== null) return wsSendText(sock, 'ffmpeg gone: ' + ffmpegErr.trim().split('\n').pop());
      ffmpeg.stdin.write(msg, err => wsSendText(sock, err ? 'write error ' + err.message : 'ok ' + received));
    });
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;

  // 3. ffmpeg: JPEG frames in, H.264 out. JPEG is full-range 601; the mp4 gets limited-range BT.709 via RGB.
  const ffArgs = ['-hide_banner', '-nostdin', '-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', 'pipe:0', '-an',
    '-vf', 'format=rgb24,scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd,format=yuv420p',
    '-c:v', 'libx264', '-preset', opt.preset, '-crf', String(opt.crf), ...levelArgs, '-pix_fmt', 'yuv420p', '-r', String(fps),
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709',
    '-movflags', '+faststart', videoOut];
  ffmpeg = spawn(C.FFMPEG, ffArgs, { stdio: ['pipe', 'ignore', 'pipe'] });
  ffmpeg.stderr.on('data', d => { ffmpegErr += d; });
  ffmpegDone = new Promise(r => ffmpeg.on('close', r));
  ffmpeg.stdin.on('error', e => log('ffmpeg stdin error: ' + e.message));

  // 4. browser
  const browser = await C.launchBrowser(log);
  const ctx = await browser.newContext({ viewport: { width: manifest.config.viewportW, height: manifest.config.viewportH }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', e => log('page error: ' + e.message));
  await page.goto(`${base}/player.html?render=1&q=${opt.q}${opt.labels ? '&labels=1' : ''}`);
  await page.evaluate(() => window.__ready);
  const info = await page.evaluate(() => window.__renderInfo());
  if (info.loop.frames !== manifest.loop.frames) throw new Error('player.html is out of date with manifest.json; run bin/build');
  await page.evaluate(u => window.__renderConnect(u), base.replace('http', 'ws') + '/frames');
  // warm up through whole loops so frame 0 carries the periodic scheduler state and the wrap is seamless; the page
  // reports whether the state repeated from one loop to the next (a few seconds per loop, no drawing)
  const warm = await page.evaluate(([s, n]) => window.__renderWarmupLoops(s, n), [manifest.loop.seconds, opt.warmLoops]);
  log(`warm-up through ${warm.loops} loops: scheduler state periodic ${warm.periodic ? 'yes' : 'NO'}${warm.periodicAfter >= 0 ? ` (repeats from loop ${warm.periodicAfter})` : ''}; active ${warm.active}, playing ${warm.playing}, queued ${warm.queued}`);
  if (!warm.periodic) log('  ! the scheduler state did not repeat loop to loop, so the wrap may not be seamless; try --warm-loops N larger or probe with bin/simsched');
  if (k0) {
    const has = await page.evaluate(() => typeof window.__renderSeek === 'function');
    if (!has) throw new Error('player.html has no __renderSeek (needed for --from); run bin/build');
    const s = await page.evaluate(ms => window.__renderSeek(ms), k0 * 1000 / fps);
    log(`seek: scheduler stepped to t=${fmtTime(s.t)} without drawing; active ${s.active}, playing ${s.playing}, queued ${s.queued}`);
  }

  // 5. frames
  let missingFrames = 0, maxPlaying = 0, lastReport = Date.now(), reportAt = 0;
  const tStart = Date.now();
  for (let k = 0; k < total; k++) {
    const r = await page.evaluate(ms => window.__renderFrame(ms, true), (k0 + k) * 1000 / fps);
    if (r.missing) missingFrames++;
    maxPlaying = Math.max(maxPlaying, r.playing);
    if (k + 1 === total || Date.now() - lastReport > 30000) {
      lastReport = Date.now();
      const done = k + 1, el = (Date.now() - tStart) / 1000, rate = done / el;
      log(`  frame ${done}/${total} (${(100 * done / total).toFixed(1)}%) ${rate.toFixed(1)} fps, ETA ${fmtTime((total - done) / rate)}, playing ${r.playing}, queued ${r.queued}, tiles drawn ${r.drawn}${r.missing ? ', MISSING ' + r.missing : ''}, avg ${(bytes / Math.max(1, received) / 1e6).toFixed(2)} MB/frame`);
    }
  }
  // wrap check: the frame that follows the last one must look like frame 0
  capturing = false;
  const wrap = await page.evaluate(ms => window.__renderFrame(ms, true), (k0 + total) * 1000 / fps);
  ffmpeg.stdin.end();
  const code = await ffmpegDone;
  await browser.close();
  server.close();
  if (code !== 0) throw new Error('ffmpeg failed: ' + ffmpegErr.trim());
  if (ffmpegErr.trim()) log('ffmpeg said: ' + ffmpegErr.trim());

  // 6. verify the loop, then put the cards around it
  const probe = await C.probeVideo(videoOut);
  const dur = probe.duration, nb = probe.nbFrames;
  log(`output: ${probe.width}x${probe.height} ${probe.codec} ${probe.avgFps.toFixed(3)} fps, ${nb} frames, ${dur.toFixed(3)} s, audio ${probe.hasAudio ? 'YES (bad)' : 'none'}, ${(fs.statSync(videoOut).size / 1e6).toFixed(1)} MB`);
  const problems = [];
  if (nb !== total) problems.push(`frame count ${nb} != ${total}`);
  if (probe.width !== manifest.config.viewportW || probe.height !== manifest.config.viewportH) problems.push('wrong size');
  if (Math.abs(probe.avgFps - fps) > 0.01) problems.push('wrong fps');
  if (probe.hasAudio) problems.push('has audio');
  if (missingFrames) problems.push(`${missingFrames} frames had a moving tile without its frame file`);
  if (maxPlaying > manifest.config.movingCap) problems.push(`max moving ${maxPlaying} > cap`);
  if (firstJpeg && wrapJpeg) {
    const tmpA = path.join(C.BUILD, 'wrap-first.jpg'), tmpB = path.join(C.BUILD, 'wrap-next.jpg'), tmpC = path.join(C.BUILD, 'wrap-last.jpg');
    fs.writeFileSync(tmpA, firstJpeg); fs.writeFileSync(tmpB, wrapJpeg); fs.writeFileSync(tmpC, lastJpeg);
    const psnr = async (a, b) => { const r = await C.run(C.FFMPEG, ['-v', 'error', '-i', a, '-i', b, '-lavfi', 'psnr=stats_file=-', '-f', 'null', '-']); const m = /psnr_avg:([\d.]+|inf)/.exec(r.out + r.err); return m ? m[1] : '?'; };
    const wrapPsnr = await psnr(tmpA, tmpB), stepPsnr = await psnr(tmpC, tmpB);
    log(`wrap check: frame 0 vs frame ${total} PSNR ${wrapPsnr} dB (identical = inf; the same content one frame apart is ~${stepPsnr} dB)${opt.seconds ? ' — partial render, the wrap only closes on a full loop' : ''}`);
    if (!opt.seconds && wrapPsnr !== 'inf' && Number(wrapPsnr) < 40) problems.push(`wrap PSNR ${wrapPsnr} dB: frame 0 does not continue the last frame`);
  }
  log(`max moving tiles in one frame: ${maxPlaying} (cap ${manifest.config.movingCap}); total ${fmtTime((Date.now() - t0) / 1000)}`);

  // 6b. the cards: each is a picture of the player's own card page, held for its seconds with a fade, encoded with
  //     the settings the loop used, then title + loop + end joined by copying. The loop file goes once the join
  //     verifies; nothing here touches the frames the wrap check just passed.
  if (cardPlan.length && !problems.length) {
    try {
      const browser = await C.launchBrowser(log);
      const ctx = await browser.newContext({ viewport: { width: manifest.config.viewportW, height: manifest.config.viewportH }, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      page.on('pageerror', e => log('card page error: ' + e.message));
      const pageUrl = 'file://' + path.join(C.BUILD, 'player.html');
      for (const c of cardPlan) {
        await cards.shoot(page, pageUrl, c, manifest.config.viewportW, manifest.config.viewportH);
        const seg = await cards.encode(c, { width: manifest.config.viewportW, height: manifest.config.viewportH, fps, preset: opt.preset, crf: opt.crf, levelArgs });
        log(`card: ${c.which} ${JSON.stringify(c.text.split('\n')[0])}${c.text.includes('\n') ? ' ...' : ''} ${c.seconds}s, fade ${c.fade}s -> ${C.rel(seg.file)} (${seg.frames} frames)`);
      }
      await browser.close();
      const order = [...cardPlan.filter(c => c.which === 'title').map(c => c.mp4), videoOut, ...cardPlan.filter(c => c.which === 'end').map(c => c.mp4)];
      await cards.join(order, out);
      const joined = await C.probeVideo(out);
      if (joined.nbFrames !== videoFrames) problems.push(`the cards and the loop came to ${joined.nbFrames} frames, expected ${videoFrames}`);
      else {
        log(`cards: ${order.map(f => path.basename(f)).join(' + ')} -> ${C.rel(out)}, ${joined.nbFrames} frames = ${fmtTime(joined.nbFrames / fps)}`);
        fs.unlinkSync(videoOut);
      }
    } catch (e) { problems.push('cards: ' + String(e.message || e)); }
  }
  const outFrames = cardPlan.length && !problems.length ? videoFrames : total;   // what `out` now holds

  // 7. the soundtrack: the playlist once per render, then one soundtrack of the file's length muxed over the verified
  //    silent copy; the muxed file takes the plain name the launchers pick up
  let playlist = null;
  if (AUDIO.enabled && !problems.length) {
    try {
      fs.mkdirSync(C.AUDIO, { recursive: true });
      playlist = await buildPlaylist(prepared.tracks);
      const soundtrack = await makeSoundtrack(playlist, outFrames / fps, finalOut);
      problems.push(...await mux(out, soundtrack, finalOut, outFrames / fps, outFrames));
    } catch (e) { problems.push(String(e.message || e)); }
  }
  if (!problems.length) sizeNote(finalOut);

  // 8. concat: N copies of the loop back to back (show.json output.concat_copies), so the player's own seam lands once
  //    per N loops; the launchers look for slideshow-x*.mp4 first. With music the silent copies are joined and one
  //    soundtrack of N x D runs over the whole file, across the seams; the silent join is only a step on the way
  if (opt.concat && !problems.length) {
    const N = concatCopies;
    const list = path.join(C.BUILD, 'concat-list.txt');
    fs.writeFileSync(list, Array(N).fill(`file '${out.replace(/'/g, "'\\''")}'`).join('\n') + '\n');
    const xnSilent = withSuffix(out, `-x${N}`), xn = withSuffix(finalOut, `-x${N}`);   // slideshow-x3.mp4; with music slideshow-silent-x3.mp4 then slideshow-x3.mp4
    const r = await C.run(C.FFMPEG, ['-hide_banner', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', '-movflags', '+faststart', xnSilent]);
    if (r.code !== 0) problems.push('concat failed: ' + r.err.trim());
    else {
      log(`concat: ${N} copies of ${path.basename(out)} -> ${C.rel(xnSilent)} (${(fs.statSync(xnSilent).size / 1e6).toFixed(1)} MB)`);
      if (AUDIO.enabled) {
        try {
          const soundtrack = await makeSoundtrack(playlist, N * outFrames / fps, xn);
          const ps = await mux(xnSilent, soundtrack, xn, N * outFrames / fps, N * outFrames);
          problems.push(...ps);
          if (!ps.length) { fs.unlinkSync(xnSilent); log(`concat: ${C.rel(xnSilent)} removed; ${C.rel(xn)} (with the music) is the file the launchers play`); }
        } catch (e) { problems.push(String(e.message || e)); }
      }
      if (!problems.length) sizeNote(xn);
    }
  }
  fs.writeFileSync(path.join(C.BUILD, 'render-log.txt'), logLines.join('\n') + '\n');
  if (problems.length) { log('PROBLEMS:'); for (const p of problems) log('  X ' + p); process.exit(1); }
  log('render OK');
}
main().catch(e => { log('FAILED: ' + (e.user ? e.message : (e.stack || e))); if (!opt.dryRun) { try { fs.writeFileSync(path.join(C.BUILD, 'render-log.txt'), logLines.join('\n') + '\n'); } catch (_) {} } process.exit(1); });
