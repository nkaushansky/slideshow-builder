#!/usr/bin/env node
'use strict';
// bin/add-item — the only sanctioned way to change the set.
//   copies the file into slideshow-handoff/media/ as <date>_<name>, reads orientation-corrected dimensions and
//   duration, appends (or replaces) the media.csv row with the right type/precision/featured, updates features.txt,
//   and runs bin/prep for that one file. A Live Photo is two files with the same stem (still + video).
// Usage: bin/add-item <file> [<live-photo-companion>] <YYYY-MM-DD|YYYY-MM|YYYY> [--featured] [--replace <filename>] [--tag <tag>] [--dry-run]
//        bin/add-item --replace <filename> [--dry-run]            a drop: the file leaves, nothing is added
//   --replace <filename>  take that file (and its Live Photo companion) out of the set: moved to slideshow-handoff/_removed/,
//                         rows removed from media.csv and features.txt, a row appended to cut-list.csv (reason: swapped,
//                         or removed when nothing replaces it)
//   --reason <word>       cut-list reason for what leaves (default swapped, or removed on a drop); bin/redate uses `redated`
//   --source <path>       original_source_path for the new row(s), one per input in order (default: the input path)
//   --year-source <word>  media.csv year_source for the new row(s) (default owner-added)
//   An input that already carries a YYYY-MM-DD_ prefix (a cut-list file) gets the given date in place of it, not on top.
//   An input that is a cut-list file is promoted: its cut-list.csv row is dropped and its original_source_path carried
//   over, so media.csv + cut-list.csv keep accounting for every file exactly once.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const C = require('./common');

const USAGE = 'usage: bin/add-item <file> [<live-photo-companion>] <YYYY-MM-DD|YYYY-MM|YYYY> [--featured] [--replace <filename>] [--tag <tag>] [--dry-run]\n' +
              '       bin/add-item --replace <filename> [--dry-run]   (drop only)';
function die(msg) { console.error('add-item: ' + msg); process.exit(2); }

const opt = { files: [], date: null, featured: false, replace: null, tag: '', dryRun: false, reason: '', sources: [], yearSource: 'owner-added' };
{
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--featured') opt.featured = true;
    else if (a[i] === '--replace') opt.replace = a[++i];
    else if (a[i] === '--tag') opt.tag = a[++i] || '';
    else if (a[i] === '--reason') opt.reason = a[++i] || '';          // cut-list reason for the file(s) leaving (default swapped / removed)
    else if (a[i] === '--source') opt.sources.push(a[++i] || '');     // original_source_path per input file, in order (default: the input path)
    else if (a[i] === '--year-source') opt.yearSource = a[++i] || 'owner-added';
    else if (a[i] === '--dry-run') opt.dryRun = true;
    else if (a[i] === '-h' || a[i] === '--help') { console.log(USAGE); process.exit(0); }
    else if (a[i].startsWith('--')) die('unknown option ' + a[i] + '\n' + USAGE);
    else if (/^\d{4}(-\d{2}){0,2}$/.test(a[i]) && !fs.existsSync(a[i])) opt.date = a[i];
    else opt.files.push(a[i]);
  }
}
const removeOnly = opt.files.length === 0 && !!opt.replace;
if (removeOnly) {
  if (opt.date || opt.featured || opt.tag) die('a drop (--replace with no file) takes no date, --featured or --tag\n' + USAGE);
} else {
  if (!opt.date) die('missing date (YYYY-MM-DD, YYYY-MM or YYYY)\n' + USAGE);
  if (opt.files.length < 1 || opt.files.length > 2) die('give one file, or a Live Photo still + video\n' + USAGE);
}
if (opt.replace && /[\\/]/.test(opt.replace)) opt.replace = path.basename(opt.replace);

// ---- date -> media.csv convention
let year = 0, precision = '', date = '';
if (!removeOnly) {
  const dm = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(opt.date);
  let mo = dm[2], da = dm[3];
  if (da === '00') da = undefined;                                              // media.csv writes unknown parts as 00,
  if (mo === '00') { if (da) die('a day without a month (YYYY-00-DD) makes no sense'); mo = undefined; } // so accept that form too
  year = +dm[1];
  const month = mo ? +mo : 0, day = da ? +da : 0;
  if (year < 2000 || year > 2030) die('implausible year ' + year);
  if (mo && (month < 1 || month > 12)) die('bad month');
  if (da && (day < 1 || day > 31)) die('bad day');
  precision = da ? 'day' : mo ? 'month' : 'year';
  date = `${dm[1]}-${mo || '00'}-${da || '00'}`;
  if (year < 2012 || year > 2026) console.warn(`add-item: note, ${year} is outside the 2012-2026 range of the show`);
}

// ---- inspect the inputs
for (const f of opt.files) { if (!fs.existsSync(f) || !fs.statSync(f).isFile()) die('not a file: ' + f); if (!C.extClass(f)) die('unsupported extension: ' + f); }
const inputs = opt.files.map(f => ({ src: path.resolve(f), base: path.basename(f), origBase: path.basename(f), cls: C.extClass(f) }));
for (const inp of inputs) {
  // a cut-list file arrives as YYYY-MM-DD_<name>; the given date takes the place of that prefix instead of stacking on it
  const pre = /^(\d{4}-\d{2}-\d{2})_(.+)$/.exec(inp.base);
  if (pre) {
    if (pre[1] !== date) console.warn(`add-item: note, ${inp.base} carries the date prefix ${pre[1]} but is being added as ${date}; the given date wins`);
    inp.base = pre[2];
  }
  inp.newName = `${date}_${inp.base}`; inp.stem = C.stemOf(inp.newName);
}
if (inputs.length === 2) {
  const classes = inputs.map(i => i.cls).sort().join('+');
  if (classes !== 'still+video') die('a Live Photo is one still plus one video');
  if (inputs[0].stem !== inputs[1].stem) die(`Live Photo halves must share a stem: ${inputs[0].base} vs ${inputs[1].base}`);
}

function isoToCsv(s) {
  // "2023-07-03T21:30:00-0400" or "2023-07-04T01:30:00.000000Z" -> "2023-07-03 21:30:00"
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/.exec(s || '');
  return m ? `${m[1]} ${m[2]}` : (s || '');
}
async function inspectStill(inp) {
  let stored, orientation = 1, exifDate = '';
  if (C.isHeicLike(inp.src)) {
    stored = await C.sipsDims(inp.src);
    // sips keeps the EXIF block (orientation, dates) when converting; a tiny JPEG is enough to read it.
    const tmp = path.join(os.tmpdir(), `add-item-${process.pid}-${inp.stem}.jpg`);
    const r = await C.run(C.SIPS, ['-Z', '64', '-s', 'format', 'jpeg', inp.src, '--out', tmp]);
    if (r.code === 0 && fs.existsSync(tmp)) {
      const info = C.jpegInfo(fs.readFileSync(tmp));
      if (info) { orientation = info.orientation || 1; exifDate = C.exifDateToCsv(info.dateTimeOriginal); }
      fs.unlinkSync(tmp);
    } else console.warn(`add-item: could not read EXIF of ${inp.base}; assuming no rotation`);
  } else {
    const info = C.jpegInfo(fs.readFileSync(inp.src));
    if (info && info.width) { stored = { width: info.width, height: info.height }; orientation = info.orientation || 1; exifDate = C.exifDateToCsv(info.dateTimeOriginal); }
    else stored = await C.sipsDims(inp.src);
  }
  const d = C.displayedDims(stored, orientation);
  return { width: d.width, height: d.height, orientation, exifDate, duration: null, codec: '', hasAudio: null };
}
async function inspectVideo(inp) {
  const p = await C.probeVideo(inp.src);
  return { width: p.width, height: p.height, rotation: p.rotation, exifDate: isoToCsv(p.creation), duration: p.duration, codec: p.codec, hasAudio: p.hasAudio, avgFps: p.avgFps, hdr: p.hdr };
}

(async () => {
  const { header, rows, eol } = C.readMediaCsv();
  const feats = C.readFeatures();
  const byName = new Map(rows.map(r => [r.filename, r]));
  const actions = [];

  // ---- inputs that come from the cut list are promoted out of it (exact name first, then same year + same bare name)
  const cut = C.readCsvObjects(C.CUT_LIST_CSV);
  const promoted = [];
  for (const inp of inputs) {
    let m = cut.rows.filter(r => r.filename === inp.newName || r.filename === inp.origBase);
    if (!m.length) m = cut.rows.filter(r => { const p = /^(\d{4})-\d{2}-\d{2}_(.+)$/.exec(r.filename); return p && p[1] === String(year) && p[2] === inp.base; });
    if (m.length === 1) { inp.cutRow = m[0]; promoted.push(m[0]); }
    else if (m.length > 1) console.warn(`add-item: ${inp.origBase} matches ${m.length} cut-list rows; leaving cut-list.csv alone and recording the folder path as the source`);
  }

  // ---- what leaves the set
  const removed = [];
  if (opt.replace) {
    const old = byName.get(opt.replace);
    if (!old) die(`--replace ${opt.replace}: not in media.csv`);
    removed.push(old);
    if (old.companion) { const c = byName.get(old.companion); if (c) removed.push(c); }
  }
  const removedNames = new Set(removed.map(r => r.filename));

  // ---- collisions and Live Photo pairing with an existing row
  const pairWith = new Map(); // inp.newName -> existing row to upgrade
  for (const inp of inputs) {
    if (byName.has(inp.newName) && !removedNames.has(inp.newName)) die(`${inp.newName} is already in the set (use --replace ${inp.newName} to swap a new version in)`);
    if (fs.existsSync(path.join(C.MEDIA, inp.newName)) && !removedNames.has(inp.newName)) die(`${inp.newName} already exists in media/ but is not in media.csv; resolve that first`);
    if (inputs.length === 1) {
      const other = rows.find(r => !removedNames.has(r.filename) && C.stemOf(r.filename) === inp.stem && r.filename !== inp.newName);
      if (other) {
        const otherCls = C.extClass(other.filename);
        const complementary = (inp.cls === 'still' && otherCls === 'video') || (inp.cls === 'video' && otherCls === 'still');
        if (!complementary) die(`${inp.newName} collides with ${other.filename} (same stem)`);
        if (other.companion) die(`${other.filename} already has a Live Photo companion (${other.companion})`);
        pairWith.set(inp.newName, other);
      }
    }
  }

  // ---- probe
  for (const inp of inputs) inp.info = inp.cls === 'still' ? await inspectStill(inp) : await inspectVideo(inp);
  if (opt.featured && !inputs.some(i => i.cls === 'still')) die('--featured needs a still (features.txt lists stills)');

  // ---- build rows
  const isPair = inputs.length === 2 || pairWith.size > 0;
  const newRows = [];
  for (const inp of inputs) {
    const i = inp.info;
    let type = inp.cls === 'gif' ? 'animated-gif' : inp.cls;
    let companion = '';
    if (inputs.length === 2) { type = inp.cls === 'still' ? 'livephoto-still' : 'livephoto-video'; companion = inputs.find(o => o !== inp).newName; }
    else if (pairWith.has(inp.newName)) { type = inp.cls === 'still' ? 'livephoto-still' : 'livephoto-video'; companion = pairWith.get(inp.newName).filename; }
    const row = Object.fromEntries(header.map(h => [h, '']));
    Object.assign(row, {
      filename: inp.newName, type, companion, width: String(i.width), height: String(i.height),
      duration_s: i.duration != null ? i.duration.toFixed(2) : '', exif_datetime_original: i.exifDate || '',
      inferred_year: String(year), year_source: opt.yearSource, date, precision, tag: opt.tag || '',
      featured: (opt.featured && inp.cls === 'still') ? 'yes' : '',
      video_codec: inp.cls === 'video' ? (i.codec || '') : '', has_audio: inp.cls === 'video' ? (i.hasAudio ? 'yes' : 'no') : '',
      crisp_6across_5k: i.width >= 840 ? 'yes' : 'NO', fills_1080p: Math.min(i.width, i.height) >= 1080 ? 'yes' : 'NO',
      original_source_path: inp.cutRow ? inp.cutRow.original_source_path : (opt.sources[inputs.indexOf(inp)] || inp.src),
    });
    newRows.push(row);
    actions.push(`add    ${inp.newName}  type=${type}${companion ? ' companion=' + companion : ''}  ${i.width}x${i.height}${i.duration != null ? ` ${i.duration.toFixed(2)}s ${i.codec}${i.hdr ? ' HDR' : ''}${i.avgFps >= C.SLOWMO_MIN_FPS ? ` ${Math.round(i.avgFps)}fps->slow-motion` : ''}` : ''}  date=${date}/${precision}${row.featured ? '  FEATURED' : ''}${i.exifDate ? '  exif=' + i.exifDate : ''}${inp.cutRow ? `  from cut-list (${inp.cutRow.reason}): ${inp.cutRow.original_source_path}` : ''}`);
  }
  for (const r of promoted) actions.push(`cut    ${r.filename} leaves cut-list.csv (now in the set)`);
  for (const [newName, other] of pairWith) {
    actions.push(`pair   ${other.filename} becomes ${other.type === 'still' ? 'livephoto-still' : 'livephoto-video'} with companion ${newName}`);
  }
  const cutReason = opt.reason || (removeOnly ? 'removed' : 'swapped');
  for (const r of removed) actions.push(`remove ${r.filename}  -> slideshow-handoff/_removed/, ${cutReason === 'redated' ? 'redated (no cut-list row)' : 'cut-list.csv reason=' + cutReason}${feats.names.includes(r.filename) ? ', dropped from features.txt' : ''}`);

  console.log((opt.dryRun ? 'DRY RUN — would do:\n' : 'Plan:\n') + actions.map(a => '  ' + a).join('\n'));
  if (opt.dryRun) return;

  // ---- apply: files first (so a failure leaves the CSV untouched), then the index files
  const removedDir = path.join(C.HANDOFF, '_removed');
  for (const r of removed) {
    const from = path.join(C.MEDIA, r.filename), to = path.join(removedDir, r.filename);
    if (fs.existsSync(from)) { fs.mkdirSync(removedDir, { recursive: true }); if (fs.existsSync(to)) die(`${to} already exists`); fs.renameSync(from, to); }
    for (const p of [C.tilePath(r.filename), C.clipPath(r.filename)]) { try { fs.unlinkSync(p); } catch (_) { /* none */ } }
    try { for (const d of fs.readdirSync(C.FRAMES)) if (d.startsWith(C.stemOf(r.filename))) fs.rmSync(path.join(C.FRAMES, d), { recursive: true, force: true }); } catch (_) { /* no frames dir */ }
  }
  for (const inp of inputs) fs.copyFileSync(inp.src, path.join(C.MEDIA, inp.newName), fs.constants.COPYFILE_EXCL);

  // media.csv
  let out = rows.filter(r => !removedNames.has(r.filename));
  for (const [newName, other] of pairWith) {
    other.type = other.type === 'still' ? 'livephoto-still' : 'livephoto-video';
    other.companion = newName;
    try { fs.unlinkSync(C.tilePath(other.filename)); } catch (_) { /* a still upgraded to a Live Photo still is no longer tiled */ }
  }
  for (const row of newRows) {
    let idx = out.findIndex(r => r.filename > row.filename);
    if (idx < 0) idx = out.length;
    out.splice(idx, 0, row);
  }
  C.writeCsvObjects(C.MEDIA_CSV, header, out, eol);

  // features.txt
  let names = feats.names.filter(n => !removedNames.has(n));
  for (const row of newRows) if (row.featured === 'yes') { let idx = names.findIndex(n => n > row.filename); if (idx < 0) idx = names.length; names.splice(idx, 0, row.filename); }
  if (names.join('\n') !== feats.names.join('\n')) C.writeFeatures(names, feats.eol);

  // cut-list.csv: removed files join it, promoted cut-list files leave it. A redated file is not leaving the set (the same
  // bytes come straight back under the new name), so it gets no cut-list row; changes.log and _removed/ keep the audit trail.
  const leaving = cutReason === 'redated' ? [] : removed;
  if (leaving.length || promoted.length) {
    cut.rows = cut.rows.filter(r => !promoted.includes(r));
    for (const r of leaving) {
      const row = Object.fromEntries(cut.header.map(h => [h, '']));
      Object.assign(row, { filename: r.filename, location: '_removed', reason: cutReason, original_source_path: r.original_source_path || '' });
      cut.rows.push(row);
    }
    C.writeCsvObjects(C.CUT_LIST_CSV, cut.header, cut.rows, cut.eol);
  }

  // changes.log
  const stamp = new Date().toISOString();
  fs.appendFileSync(path.join(C.HANDOFF, 'changes.log'), actions.map(a => `${stamp}  ${a}`).join('\n') + '\n');

  const total = out.length, items = out.filter(r => r.type !== 'livephoto-still').length;
  console.log(`media.csv now ${total} rows / ${items} items; features.txt ${names.length} lines.`);

  // prep just these files
  if (inputs.length) {
    const prepArgs = [path.join(__dirname, 'prep.js'), '--quiet'];
    for (const inp of inputs) prepArgs.push('--only', inp.newName);
    console.log('Running prep for the new file(s)...');
    const res = spawnSync(process.execPath, prepArgs, { stdio: 'inherit' });
    if (res.status !== 0) { console.error('add-item: prep reported a problem (see build/prep-report.txt). The set was changed; fix and re-run bin/prep.'); process.exit(1); }
  }
  console.log('Next: bin/build, then look at it in the live player.');
})().catch(e => { console.error('add-item: ' + (e.stack || e)); process.exit(1); });
