'use strict';
// Shared helpers for the build scripts: paths, CSV, probing, process pool.
// Nothing here ever writes into handoff/media/ (add-item is the one sanctioned writer).

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');   // the repository: player.template.html, curate/, tools/, .venv/
const TOOLS = path.join(ROOT, 'tools');               // optional local toolchain (gitignored): tools/ffmpeg, tools/node
const IS_WIN = process.platform === 'win32';
const IS_MAC = process.platform === 'darwin';

// ---------- the project folder ----------
// Every build tool works on one project folder: the one the intake created, holding config.toml. It is found from
// --project <folder> on the command line (removed from argv here, so the scripts never see it), else SLIDESHOW_PROJECT,
// else the nearest config.toml at or above the current directory. SLIDESHOW_HANDOFF and SLIDESHOW_BUILD override the two
// folders explicitly. There is deliberately no fallback into this repository: the build must never write into the code.
function readTomlStrings(file) {
  // Minimal reader: quoted string values inside [section] blocks. Enough for [project] and [tools]; nothing else is read here.
  const cfg = {};
  let section = '';
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const sec = /^\[([^\]]+)\]/.exec(line);
    if (sec) { section = sec[1].trim(); continue; }
    const kv = /^([A-Za-z0-9_.-]+)\s*=\s*"((?:[^"\\]|\\.)*)"/.exec(line);
    if (kv && section) (cfg[section] = cfg[section] || {})[kv[1]] = kv[2].replace(/\\(.)/g, '$1');
  }
  return cfg;
}
function findProject() {
  const i = process.argv.indexOf('--project');
  if (i >= 0) {
    const p = process.argv[i + 1];
    if (!p || p.startsWith('--')) throw new Error('--project needs a folder');
    process.argv.splice(i, 2);
    return path.resolve(p);
  }
  if (process.env.SLIDESHOW_PROJECT) return path.resolve(process.env.SLIDESHOW_PROJECT);
  let d = process.cwd();
  for (;;) {
    if (fs.existsSync(path.join(d, 'config.toml'))) return d;
    const up = path.dirname(d);
    if (up === d) return null;
    d = up;
  }
}
const PROJECT = findProject();
if (PROJECT && !fs.existsSync(path.join(PROJECT, 'config.toml'))) throw new Error(`no config.toml in ${PROJECT}; run the intake first (it writes the project config)`);
if (PROJECT) process.env.SLIDESHOW_PROJECT = PROJECT;   // child processes (add-item, prep) land on the same project
const CFG = PROJECT ? readTomlStrings(path.join(PROJECT, 'config.toml')) : {};
const cfgProject = CFG.project || {}, cfgTools = CFG.tools || {};
function projectDir(envName, key) {
  if (process.env[envName]) return path.resolve(process.env[envName]);
  if (PROJECT) return path.resolve(PROJECT, cfgProject[key] || key);
  throw new Error(`no project folder: pass --project <folder>, set SLIDESHOW_PROJECT, or run inside a folder that holds config.toml (${envName} overrides the ${key} folder alone)`);
}
const HANDOFF = projectDir('SLIDESHOW_HANDOFF', 'handoff');
const BUILD = projectDir('SLIDESHOW_BUILD', 'build');
const MEDIA = path.join(HANDOFF, 'media');
const TILES = path.join(BUILD, 'tiles');
const CLIPS = path.join(BUILD, 'clips');
const FRAMES = path.join(BUILD, 'frames');
const MEDIA_CSV = path.join(HANDOFF, 'media.csv');
const FEATURES_TXT = path.join(HANDOFF, 'features.txt');
const CUT_LIST_CSV = path.join(HANDOFF, 'cut-list.csv');
const PREP_MANIFEST = path.join(BUILD, 'prep-manifest.json');

// ffmpeg/ffprobe: [tools] in config.toml, else the repo's tools/ffmpeg/, else PATH.
function toolBin(name) {
  if (cfgTools[name]) return path.resolve(PROJECT || ROOT, cfgTools[name]);
  for (const cand of [path.join(TOOLS, 'ffmpeg', name + (IS_WIN ? '.exe' : '')), path.join(TOOLS, 'ffmpeg', name)]) if (fs.existsSync(cand)) return cand;
  return name;
}
const FFMPEG = toolBin('ffmpeg');
const FFPROBE = toolBin('ffprobe');
// HEIC and resizing: sips on macOS is the fast path; everywhere else curate/heic.py (pillow-heif) does the same job.
const SIPS = IS_MAC && fs.existsSync('/usr/bin/sips') ? '/usr/bin/sips' : null;
const HEIC_PY = path.join(ROOT, 'curate', 'heic.py');
function pythonBin() {
  const venv = IS_WIN ? path.join(ROOT, '.venv', 'Scripts', 'python.exe') : path.join(ROOT, '.venv', 'bin', 'python');
  if (fs.existsSync(venv)) return venv;
  return IS_WIN ? 'python' : 'python3';
}
// Paths for humans (logs) are relative to the project folder; paths for the browser are relative to build/ and use '/'.
function rel(p) { return path.relative(PROJECT || process.cwd(), p) || '.'; }
function webRel(from, p) { return path.relative(from, p).split(path.sep).join('/'); }

const STILL_EXT = new Set(['.jpg', '.jpeg', '.heic', '.heif', '.png']);
const VIDEO_EXT = new Set(['.mov', '.mp4', '.m4v']);
const GIF_EXT = new Set(['.gif']);
const MAX_TILE_H = 1640;   // 2x the feature row; keeps a 5K render possible later
const MAX_CLIP_H = 1640;   // live-mode clips, same cap
const SLOWMO_MIN_FPS = 100; // >= this average fps is a slow-motion capture; played at 30 fps
const FRAMES_PAD_MAX = 30;  // bin/frames: more than this many missing frames at the end of a sequence is a failure, not padding
const IGNORED_FILES = new Set(['Thumbs.db', '.DS_Store', 'desktop.ini']);

const CLIP_TYPES = new Set(['livephoto-video', 'video', 'animated-gif']);
const MOVING_TYPES = CLIP_TYPES;

function stemOf(filename) { return filename.slice(0, filename.length - path.extname(filename).length); }
function extClass(filename) {
  const e = path.extname(filename).toLowerCase();
  if (STILL_EXT.has(e)) return 'still';
  if (VIDEO_EXT.has(e)) return 'video';
  if (GIF_EXT.has(e)) return 'gif';
  return null;
}
function isHeicLike(filename) { const e = path.extname(filename).toLowerCase(); return e === '.heic' || e === '.heif' || e === '.png'; }
function tilePath(filename) { return path.join(TILES, stemOf(filename) + '.jpg'); }
function clipPath(filename) { return path.join(CLIPS, stemOf(filename) + '.mp4'); }

// ---------- CSV (RFC 4180, minimal quoting, preserves the file's line endings) ----------
function parseCsv(text) {
  const eol = text.includes('\r\n') ? '\r\n' : '\n';
  const rows = []; let row = []; let field = ''; let inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false; }
      else field += c;
      continue;
    }
    if (c === '"') inQ = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\r') { /* part of CRLF */ }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return { rows, eol };
}
function csvField(v) {
  v = v == null ? '' : String(v);
  return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}
function serializeCsv(header, rows, eol) {
  const lines = [header.map(csvField).join(',')];
  for (const r of rows) lines.push(header.map(h => csvField(r[h])).join(','));
  return lines.join(eol) + eol;
}
function readCsvObjects(file) {
  const { rows, eol } = parseCsv(fs.readFileSync(file, 'utf8'));
  const header = rows[0];
  const objects = rows.slice(1).filter(r => r.length > 1 || (r.length === 1 && r[0] !== '')).map(r => {
    const o = {}; header.forEach((h, i) => { o[h] = r[i] == null ? '' : r[i]; }); return o;
  });
  return { header, rows: objects, eol };
}
function writeCsvObjects(file, header, rows, eol) {
  atomicWrite(file, serializeCsv(header, rows, eol));
}
function readMediaCsv() { return readCsvObjects(MEDIA_CSV); }
function readFeatures() {
  const text = fs.readFileSync(FEATURES_TXT, 'utf8');
  const eol = text.includes('\r\n') ? '\r\n' : '\n';
  return { names: text.split(/\r?\n/).map(s => s.trim()).filter(Boolean), eol };
}
function writeFeatures(names, eol) { atomicWrite(FEATURES_TXT, names.join(eol) + eol); }
function atomicWrite(file, data) {
  const tmp = file + '.tmp-' + process.pid;
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, file);
}

// ---------- dates ----------
// media.csv convention: YYYY-MM-DD, YYYY-MM-00 (month), YYYY-00-00 (year). Key for ordering only.
function dateKey(date, precision) {
  const [y, m, d] = date.split('-');
  if (precision === 'year') return `${y}-07-01`;
  if (precision === 'month') return `${y}-${m}-15`;
  return `${y}-${m}-${d}`;
}

// ---------- processes ----------
function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    let out = '', err = '';
    let child;
    try {
      child = spawn(cmd, args, { cwd: opts.cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (e) { return resolve({ code: -1, out, err: String(e) }); }
    child.stdout.on('data', d => { out += d; });
    child.stderr.on('data', d => { err += d; });
    child.on('error', e => resolve({ code: -1, out, err: err + String(e) }));
    child.on('close', code => resolve({ code, out, err }));
  });
}
async function pool(items, concurrency, worker) {
  const results = new Array(items.length);
  let next = 0;
  async function lane() {
    for (;;) {
      const i = next++;
      if (i >= items.length) return;
      results[i] = await worker(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.max(1, Math.min(concurrency, items.length)) }, lane));
  return results;
}

// ---------- probing ----------
function fracToNum(s) {
  if (!s) return 0;
  const [a, b] = String(s).split('/').map(Number);
  return b ? a / b : a;
}
async function ffprobeJson(file) {
  const r = await run(FFPROBE, ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', file]);
  if (r.code !== 0) throw new Error(`ffprobe failed for ${path.basename(file)}: ${r.err.trim()}`);
  return JSON.parse(r.out);
}
// Orientation-corrected video facts. width/height are DISPLAY dimensions (rotation applied).
async function probeVideo(file) {
  const j = await ffprobeJson(file);
  const streams = j.streams || [];
  const v = streams.find(s => s.codec_type === 'video');
  if (!v) throw new Error('no video stream in ' + path.basename(file));
  const a = streams.find(s => s.codec_type === 'audio');
  let rotation = 0;
  for (const sd of v.side_data_list || []) if (sd.rotation != null) rotation = Number(sd.rotation);
  let width = v.width, height = v.height;
  if (Math.abs(rotation) % 180 === 90) [width, height] = [height, width];
  const duration = Number((j.format && j.format.duration) || v.duration || 0);
  const avgFps = fracToNum(v.avg_frame_rate) || fracToNum(v.r_frame_rate);
  const nbFrames = Number(v.nb_frames) || Math.round(duration * avgFps);
  const hdr = ['arib-std-b67', 'smpte2084'].includes(v.color_transfer) || v.color_primaries === 'bt2020';
  const tags = (j.format && j.format.tags) || {};
  const creation = tags['com.apple.quicktime.creationdate'] || tags.creation_time || '';
  return {
    codec: v.codec_name, width, height, storedWidth: v.width, storedHeight: v.height, rotation,
    duration, avgFps, nbFrames, pixFmt: v.pix_fmt, transfer: v.color_transfer || '', primaries: v.color_primaries || '',
    range: v.color_range || '', hdr, hasAudio: !!a, creation,
  };
}
// Stored (un-rotated) pixel dimensions as sips sees them. sips ignores orientation tags. macOS only.
async function sipsDims(file) {
  if (!SIPS) throw new Error('sips is macOS only; use imageInfo()');
  const r = await run(SIPS, ['-g', 'pixelWidth', '-g', 'pixelHeight', file]);
  const w = /pixelWidth: (\d+)/.exec(r.out), h = /pixelHeight: (\d+)/.exec(r.out);
  if (r.code !== 0 || !w || !h) throw new Error(`sips could not read ${path.basename(file)}: ${(r.err || r.out).trim()}`);
  return { width: +w[1], height: +h[1] };
}
async function heicPy(args) {
  const r = await run(pythonBin(), [HEIC_PY, ...args]);
  if (r.code !== 0) throw new Error(`heic.py ${args[0]} failed for ${path.basename(args[1])}: ${(r.err || r.out).trim().split('\n').pop()}`);
  return r;
}
// Facts about any still: displayed width/height (after EXIF orientation), stored dimensions, orientation, DateTimeOriginal.
// JPEG: pure JS. Anything else: sips (macOS fast path) or curate/heic.py. The three agree on every field.
async function imageInfo(file) {
  if (/\.jpe?g$/i.test(file)) {
    const info = jpegInfo(fs.readFileSync(file));
    if (info && info.width) {
      const d = displayedDims(info, info.orientation);
      return { width: d.width, height: d.height, storedWidth: info.width, storedHeight: info.height, orientation: info.orientation || 1, dateTimeOriginal: exifDateToCsv(info.dateTimeOriginal), tool: 'jpeg' };
    }
  }
  if (SIPS) {
    const stored = await sipsDims(file);
    let orientation = 1, dto = '';
    // sips keeps the EXIF block (orientation, dates) when converting; a tiny JPEG is enough to read it.
    const tmp = path.join(os.tmpdir(), `heic-info-${process.pid}-${Date.now()}.jpg`);
    const r = await run(SIPS, ['-Z', '64', '-s', 'format', 'jpeg', file, '--out', tmp]);
    if (r.code === 0 && fs.existsSync(tmp)) {
      const info = jpegInfo(fs.readFileSync(tmp));
      if (info) { orientation = info.orientation || 1; dto = exifDateToCsv(info.dateTimeOriginal); }
      fs.unlinkSync(tmp);
    }
    const d = displayedDims(stored, orientation);
    return { width: d.width, height: d.height, storedWidth: stored.width, storedHeight: stored.height, orientation, dateTimeOriginal: dto, tool: 'sips' };
  }
  const j = JSON.parse((await heicPy(['dims', file])).out);
  return { width: j.width, height: j.height, storedWidth: j.stored_width, storedHeight: j.stored_height, orientation: j.orientation || 1, dateTimeOriginal: exifDateToCsv(j.date_time_original || ''), tool: 'python' };
}
// A JPEG from any still, display height capped at maxHeight (0 = keep size). sips leaves the pixels stored-rotated and
// keeps the orientation tag; heic.py writes them upright with the tag cleared. Both verify through jpegInfo + displayedDims.
async function makeJpeg(src, out, { maxHeight = 0, quality = 90, storedRotated = false } = {}) {
  if (SIPS) {
    const a = ['-s', 'format', 'jpeg', '-s', 'formatOptions', String(quality)];
    // sips resamples the STORED image: for a stored-rotated file the displayed height is the stored width.
    if (maxHeight) a.push(storedRotated ? '--resampleWidth' : '--resampleHeight', String(maxHeight));
    a.push(src, '--out', out);
    const r = await run(SIPS, a);
    if (r.code !== 0 || !fs.existsSync(out)) throw new Error('sips: ' + (r.err || r.out).trim().split('\n').pop());
    return 'sips';
  }
  await heicPy(['convert', src, out, '--max-height', String(maxHeight || 0), '--quality', String(quality)]);
  return 'python';
}
// ---------- identity ----------
// media_id is the SHA-256 of the bytes (references/02); it is the first column of media.csv and cut-list.csv.
function sha256File(file) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256');
    fs.createReadStream(file).on('data', d => h.update(d)).on('error', reject).on('end', () => resolve(h.digest('hex')));
  });
}
function ensureMediaIdColumn(header) { if (!header.includes('media_id')) header.unshift('media_id'); }
// Fill media_id on rows that lack it, hashing the file resolveFile(row) points at when it exists. Returns the count filled.
async function ensureMediaIds(header, rows, resolveFile) {
  ensureMediaIdColumn(header);
  let n = 0;
  for (const r of rows) {
    if (r.media_id) continue;
    const f = resolveFile(r);
    if (f && fs.existsSync(f)) { r.media_id = await sha256File(f); n++; } else r.media_id = '';
  }
  return n;
}
// ---------- browser ----------
// Playwright's bundled Chromium first; installed Google Chrome (channel) when the bundle is missing or will not start.
async function launchBrowser(log = console.log) {
  const { chromium } = require('playwright');
  try { const b = await chromium.launch({ headless: true }); log('browser: Playwright Chromium'); return b; }
  catch (e) {
    const first = String(e.message || e).split('\n')[0];
    try { const b = await chromium.launch({ channel: 'chrome', headless: true }); log(`browser: Google Chrome via channel (bundled Chromium unavailable: ${first})`); return b; }
    catch (e2) { throw new Error(`no browser could start. Playwright Chromium: ${first}. Chrome channel: ${String(e2.message || e2).split('\n')[0]}. Run "npx playwright install chromium" in build/ or install Google Chrome.`); }
  }
}
// JPEG header facts: stored dims, EXIF Orientation, EXIF DateTimeOriginal. Pure JS, no subprocess.
function jpegInfo(buf) {
  if (!buf || buf.length < 4 || buf[0] !== 0xFF || buf[1] !== 0xD8) return null;
  const info = { width: 0, height: 0, orientation: 1, dateTimeOriginal: '' };
  let i = 2;
  while (i + 4 <= buf.length) {
    if (buf[i] !== 0xFF) { i++; continue; }
    const marker = buf[i + 1];
    if (marker === 0xFF) { i++; continue; }                       // fill byte
    if (marker === 0xD8 || marker === 0x01 || (marker >= 0xD0 && marker <= 0xD7)) { i += 2; continue; }
    if (marker === 0xD9 || marker === 0xDA) break;                 // EOI / start of scan
    const len = buf.readUInt16BE(i + 2);
    if (marker === 0xE1 && buf.toString('latin1', i + 4, i + 10) === 'Exif\0\0') {
      try { parseExif(buf.subarray(i + 10, i + 2 + len), info); } catch (_) { /* ignore broken EXIF */ }
    }
    if (marker >= 0xC0 && marker <= 0xCF && marker !== 0xC4 && marker !== 0xC8 && marker !== 0xCC) {
      info.height = buf.readUInt16BE(i + 5);
      info.width = buf.readUInt16BE(i + 7);
    }
    i += 2 + len;
  }
  return info;
}
function parseExif(t, info) {
  const le = t.toString('latin1', 0, 2) === 'II';
  const u16 = o => (le ? t.readUInt16LE(o) : t.readUInt16BE(o));
  const u32 = o => (le ? t.readUInt32LE(o) : t.readUInt32BE(o));
  const readIfd = (off, cb) => {
    if (off + 2 > t.length) return;
    const n = u16(off);
    for (let k = 0; k < n; k++) {
      const e = off + 2 + 12 * k;
      if (e + 12 > t.length) return;
      cb(u16(e), u16(e + 2), u32(e + 4), e + 8);
    }
  };
  let exifIfd = 0;
  readIfd(u32(4), (tag, type, count, valOff) => {
    if (tag === 0x0112) info.orientation = u16(valOff);
    if (tag === 0x8769) exifIfd = u32(valOff);
  });
  if (exifIfd) readIfd(exifIfd, (tag, type, count, valOff) => {
    if (tag === 0x9003 && type === 2) {
      const off = count > 4 ? u32(valOff) : valOff;
      info.dateTimeOriginal = t.toString('latin1', off, off + count - 1).trim();
    }
  });
}
function exifDateToCsv(s) {
  // "2013:01:12 16:24:34" -> "2013-01-12 16:24:34"
  const m = /^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}:\d{2}:\d{2})/.exec(s || '');
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}` : (s || '');
}
function displayedDims(stored, orientation) {
  return orientation >= 5 && orientation <= 8 ? { width: stored.height, height: stored.width } : { ...stored };
}

// ---------- clip planning (shared by prep and render so frames and clips agree) ----------
function even(n) { return Math.max(2, Math.round(n / 2) * 2); }
// Display-size and filter chain for a moving item. W/H are the orientation-corrected source dims.
function clipPlan({ W, H, maxH, probe, realtime }) {
  const oh = even(Math.min(maxH, H));
  const ow = even(W * oh / H);
  const slow = (!realtime && probe.avgFps >= SLOWMO_MIN_FPS) ? probe.avgFps / 30 : 1;
  const filters = [];
  if (slow !== 1) filters.push(`setpts=PTS*${slow.toFixed(6)}`);
  if (probe.hdr) {
    // 10-bit HLG/PQ -> SDR BT.709: resize first (cheaper), linearize, tone-map (hable), back to 709.
    filters.push(`zscale=w=${ow}:h=${oh}:f=lanczos`, 'zscale=t=linear:npl=100', 'format=gbrpf32le',
      'zscale=p=bt709', 'tonemap=tonemap=hable:desat=0', 'zscale=t=bt709:m=bt709:r=tv', 'format=yuv420p');
  } else {
    filters.push(`scale=${ow}:${oh}:flags=lanczos`, 'format=yuv420p');
  }
  const outFps = slow !== 1 ? 30 : probe.avgFps;
  const outDuration = slow !== 1 ? probe.nbFrames / 30 : probe.duration;
  return { ow, oh, vf: filters.join(','), slow, outFps, outDuration };
}

function ensureDirs() { for (const d of [BUILD, TILES, CLIPS, FRAMES]) fs.mkdirSync(d, { recursive: true }); }
function fmtSecs(ms) { return (ms / 1000).toFixed(1) + 's'; }
function readPrepManifest() {
  try { return JSON.parse(fs.readFileSync(PREP_MANIFEST, 'utf8')); } catch (_) { return null; }
}

module.exports = {
  FRAMES_PAD_MAX,
  ROOT, PROJECT, HANDOFF, MEDIA, BUILD, TOOLS, TILES, CLIPS, FRAMES, MEDIA_CSV, FEATURES_TXT, CUT_LIST_CSV, PREP_MANIFEST,
  FFMPEG, FFPROBE, SIPS, HEIC_PY, IS_WIN, IS_MAC, STILL_EXT, VIDEO_EXT, GIF_EXT, MAX_TILE_H, MAX_CLIP_H, SLOWMO_MIN_FPS, IGNORED_FILES,
  CLIP_TYPES, MOVING_TYPES,
  stemOf, extClass, isHeicLike, tilePath, clipPath, rel, webRel, pythonBin,
  parseCsv, serializeCsv, readCsvObjects, writeCsvObjects, readMediaCsv, readFeatures, writeFeatures, atomicWrite,
  dateKey, run, pool, ffprobeJson, probeVideo, sipsDims, imageInfo, makeJpeg, jpegInfo, exifDateToCsv, displayedDims,
  sha256File, ensureMediaIdColumn, ensureMediaIds, launchBrowser,
  clipPlan, even, ensureDirs, fmtSecs, readPrepManifest,
};

// `node lib/common.js --print build` prints one resolved path (the shell wrappers use it); --paths prints them all as JSON.
if (require.main === module) {
  const a = process.argv.slice(2);
  const all = { root: ROOT, project: PROJECT, handoff: HANDOFF, media: MEDIA, build: BUILD, tiles: TILES, clips: CLIPS, frames: FRAMES, ffmpeg: FFMPEG, ffprobe: FFPROBE, python: pythonBin(), sips: SIPS };
  const i = a.indexOf('--print');
  if (i >= 0) { const v = all[a[i + 1]]; if (v == null) { console.error('unknown path ' + a[i + 1] + '; one of ' + Object.keys(all).join(', ')); process.exit(2); } console.log(v); }
  else console.log(JSON.stringify(all, null, 1));
}
