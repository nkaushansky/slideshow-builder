'use strict';
// Shared helpers for the build scripts: paths, CSV, probing, process pool.
// Nothing here ever writes into slideshow-handoff/media/ (add-item is the one sanctioned writer).

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const HANDOFF = process.env.SLIDESHOW_HANDOFF ? path.resolve(process.env.SLIDESHOW_HANDOFF) : path.join(ROOT, 'slideshow-handoff');
const MEDIA = path.join(HANDOFF, 'media');
const BUILD = process.env.SLIDESHOW_BUILD ? path.resolve(process.env.SLIDESHOW_BUILD) : path.join(ROOT, 'build');
const TOOLS = path.join(ROOT, 'tools');
const TILES = path.join(BUILD, 'tiles');
const CLIPS = path.join(BUILD, 'clips');
const FRAMES = path.join(BUILD, 'frames');
const MEDIA_CSV = path.join(HANDOFF, 'media.csv');
const FEATURES_TXT = path.join(HANDOFF, 'features.txt');
const CUT_LIST_CSV = path.join(HANDOFF, 'cut-list.csv');
const PREP_MANIFEST = path.join(BUILD, 'prep-manifest.json');

function toolBin(name) {
  const p = path.join(TOOLS, 'ffmpeg', name);
  return fs.existsSync(p) ? p : name;
}
const FFMPEG = toolBin('ffmpeg');
const FFPROBE = toolBin('ffprobe');
const SIPS = '/usr/bin/sips';

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
// Stored (un-rotated) pixel dimensions as sips sees them. sips ignores orientation tags.
async function sipsDims(file) {
  const r = await run(SIPS, ['-g', 'pixelWidth', '-g', 'pixelHeight', file]);
  const w = /pixelWidth: (\d+)/.exec(r.out), h = /pixelHeight: (\d+)/.exec(r.out);
  if (r.code !== 0 || !w || !h) throw new Error(`sips could not read ${path.basename(file)}: ${(r.err || r.out).trim()}`);
  return { width: +w[1], height: +h[1] };
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
  ROOT, HANDOFF, MEDIA, BUILD, TOOLS, TILES, CLIPS, FRAMES, MEDIA_CSV, FEATURES_TXT, CUT_LIST_CSV, PREP_MANIFEST,
  FFMPEG, FFPROBE, SIPS, STILL_EXT, VIDEO_EXT, GIF_EXT, MAX_TILE_H, MAX_CLIP_H, SLOWMO_MIN_FPS, IGNORED_FILES,
  CLIP_TYPES, MOVING_TYPES,
  stemOf, extClass, isHeicLike, tilePath, clipPath,
  parseCsv, serializeCsv, readCsvObjects, writeCsvObjects, readMediaCsv, readFeatures, writeFeatures, atomicWrite,
  dateKey, run, pool, ffprobeJson, probeVideo, sipsDims, jpegInfo, exifDateToCsv, displayedDims,
  clipPlan, even, ensureDirs, fmtSecs, readPrepManifest,
};
