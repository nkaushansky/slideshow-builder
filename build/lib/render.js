#!/usr/bin/env node
'use strict';
// bin/render — deterministic mp4 from player.html?render=1.
//   1. bin/frames (frame sequences for moving tiles at their row heights; skipped if present)
//   2. serve the project over http://127.0.0.1 (a file:// page would taint the canvas) and open the player in headless Chrome
//   3. warm the scheduler through one full loop so frame 0 already sits in a periodic state (seamless wrap)
//   4. per frame: page updates to t = k/60, draws the visible tiles into a canvas, JPEG-encodes it (q 0.95) and sends it over
//      a WebSocket; we pipe it into ffmpeg (image2pipe -> libx264) and ack once ffmpeg accepted it (backpressure)
//   5. verify: frame count, size, fps, no audio; wrap check = PSNR between frame 0 and the frame after the last one
// Usage: bin/render [--seconds N] [--from SECONDS] [--out FILE] [--preset slow|medium|...] [--crf N] [--q 0.95] [--skip-frames] [--x3] [--warm-loops N]
//   default renders exactly one loop to build/slideshow.mp4; --seconds 60 is the quick test render; --from 470 --seconds 40
//   renders a window from inside the loop (the scheduler is stepped up to that point without drawing, so the state is right).

const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { spawn } = require('child_process');
const C = require('./common');
const { generateFrames } = require('./frames');

const opt = { seconds: 0, from: 0, out: '', preset: 'slow', crf: 18, q: 0.95, skipFrames: false, x3: false, jobs: 0, warmLoops: 8 };
{
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
    else if (a[i] === '--x3') opt.x3 = true;
    else if (a[i] === '--jobs') opt.jobs = Number(a[++i]);
    else { console.error('usage: bin/render [--seconds N] [--from SECONDS] [--out FILE] [--preset P] [--crf N] [--q 0.95] [--skip-frames] [--x3] [--warm-loops N]'); process.exit(2); }
  }
  if (opt.from && !opt.seconds) { console.error('--from needs --seconds N (a partial render starting there)'); process.exit(2); }
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

async function main() {
  const t0 = Date.now();
  const manifest = JSON.parse(fs.readFileSync(path.join(C.BUILD, 'manifest.json'), 'utf8'));
  const fps = manifest.config.renderFps;
  const total = opt.seconds ? Math.round(opt.seconds * fps) : manifest.loop.frames;
  const k0 = Math.round(opt.from * fps);
  const out = path.resolve(opt.out || path.join(C.BUILD, opt.seconds ? `test-${opt.from ? opt.from + 's-' : ''}${opt.seconds}s.mp4` : 'slideshow.mp4'));
  log(`render: ${total} frames at ${fps} fps (${fmtTime(total / fps)})${k0 ? ` from frame ${k0} (t=${fmtTime(k0 / fps)})` : ''} -> ${path.relative(C.ROOT, out)}; loop ${manifest.loop.frames} frames = ${fmtTime(manifest.loop.seconds)} at ${manifest.loop.speed.toFixed(3)} px/s; x264 ${opt.preset} crf ${opt.crf}, jpeg q ${opt.q}`);
  if (!fs.existsSync(path.join(C.ROOT, 'player.html'))) throw new Error('player.html missing; run bin/build');

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
    const p = path.join(C.ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!p.startsWith(C.ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
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
    '-c:v', 'libx264', '-preset', opt.preset, '-crf', String(opt.crf), '-pix_fmt', 'yuv420p', '-r', String(fps),
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709',
    '-movflags', '+faststart', out];
  ffmpeg = spawn(C.FFMPEG, ffArgs, { stdio: ['pipe', 'ignore', 'pipe'] });
  ffmpeg.stderr.on('data', d => { ffmpegErr += d; });
  ffmpegDone = new Promise(r => ffmpeg.on('close', r));
  ffmpeg.stdin.on('error', e => log('ffmpeg stdin error: ' + e.message));

  // 4. browser
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: manifest.config.viewportW, height: manifest.config.viewportH }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', e => log('page error: ' + e.message));
  await page.goto(`${base}/player.html?render=1&q=${opt.q}`);
  await page.evaluate(() => window.__ready);
  const info = await page.evaluate(() => window.__renderInfo());
  if (info.loop.frames !== manifest.loop.frames) throw new Error('player.html is out of date with build/manifest.json; run bin/build');
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

  // 6. verify
  const probe = await C.probeVideo(out);
  const dur = probe.duration, nb = probe.nbFrames;
  log(`output: ${probe.width}x${probe.height} ${probe.codec} ${probe.avgFps.toFixed(3)} fps, ${nb} frames, ${dur.toFixed(3)} s, audio ${probe.hasAudio ? 'YES (bad)' : 'none'}, ${(fs.statSync(out).size / 1e6).toFixed(1)} MB`);
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

  // 7. x3
  if (opt.x3 && !problems.length) {
    const list = path.join(C.BUILD, 'concat-list.txt');
    fs.writeFileSync(list, Array(3).fill(`file '${out.replace(/'/g, "'\\''")}'`).join('\n') + '\n');
    const x3 = out.replace(/\.mp4$/, '-x3.mp4');
    const r = await C.run(C.FFMPEG, ['-hide_banner', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', '-movflags', '+faststart', x3]);
    if (r.code !== 0) problems.push('concat failed: ' + r.err.trim()); else log(`x3: ${path.relative(C.ROOT, x3)} (${(fs.statSync(x3).size / 1e6).toFixed(1)} MB)`);
  }
  fs.writeFileSync(path.join(C.BUILD, 'render-log.txt'), logLines.join('\n') + '\n');
  if (problems.length) { log('PROBLEMS:'); for (const p of problems) log('  X ' + p); process.exit(1); }
  log('render OK');
}
main().catch(e => { log('FAILED: ' + (e.stack || e)); try { fs.writeFileSync(path.join(C.BUILD, 'render-log.txt'), logLines.join('\n') + '\n'); } catch (_) {} process.exit(1); });
