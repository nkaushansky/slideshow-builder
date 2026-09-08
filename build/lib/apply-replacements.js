#!/usr/bin/env node
'use strict';
// bin/apply-replacements <folder> — run add-item for every row of <folder>/replacements.csv
// columns: replaces, new_file, companion, date, featured, notes
//   replaces  : filename currently in media.csv that leaves the set (blank = plain add)
//   new_file  : file in <folder> (the still for a Live Photo); blank with replaces set = a drop, nothing added
//   companion : the Live Photo video half in <folder>, or blank
//   date      : YYYY-MM-DD, YYYY-MM or YYYY (blank on a drop row)
//   featured  : yes / blank
//   notes     : free text, ignored
// Every row is checked before anything runs; then add-item runs per row and stops at the first failure so the
// set is never half-applied. --dry-run runs add-item --dry-run per row, which prints the exact plan for each.
// On every run (dry or real, success or stop) the current media.csv and changes.log are copied into <folder>
// (<folder>/dry-run/ for a dry run): the return trip of references/02, so the round always carries the live index.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const C = require('./common');

const args = process.argv.slice(2);
const dry = args.includes('--dry-run');
const folder = args.find(a => !a.startsWith('--'));
if (!folder) { console.error('usage: bin/apply-replacements <folder> [--dry-run]'); process.exit(2); }
const csv = path.join(folder, 'replacements.csv');
if (!fs.existsSync(csv)) { console.error('missing ' + csv); process.exit(2); }
const { rows } = C.readCsvObjects(csv);
const media = new Set(C.readMediaCsv().rows.map(r => r.filename));
const ADD_ITEM = path.join(__dirname, 'add-item.js');

function fail(n, msg) { console.error(`row ${n}: ${msg}`); process.exit(1); }
function writeBack() {
  const dest = dry ? path.join(folder, 'dry-run') : folder;
  fs.mkdirSync(dest, { recursive: true });
  const copied = [];
  for (const [src, name] of [[C.MEDIA_CSV, 'media.csv'], [path.join(C.HANDOFF, 'changes.log'), 'changes.log']]) {
    if (fs.existsSync(src)) { fs.copyFileSync(src, path.join(dest, name)); copied.push(name); }
  }
  console.log(`write-back: ${copied.join(' and ') || 'nothing'} copied into ${dest}`);
}

// ---- pass 1: validate every row and build the commands
const plan = [];
const leaving = new Set();
rows.forEach((r, i) => {
  const n = i + 1;
  const get = k => (r[k] || r[k.toLowerCase()] || '').trim();
  const replaces = get('replaces'), file = get('new_file'), comp = get('companion'), date = get('date'), featured = /^y/i.test(get('featured'));
  if (!replaces && !file) return; // blank line
  if (replaces) {
    if (!media.has(replaces)) fail(n, `${replaces} is not in media.csv (already swapped?)`);
    if (leaving.has(replaces)) fail(n, `${replaces} leaves the set twice`);
    leaving.add(replaces);
  }
  const cmd = [ADD_ITEM];
  if (!file) {
    if (comp || date || featured) fail(n, 'a drop row (blank new_file) takes only replaces and notes');
    cmd.push('--replace', replaces);
  } else {
    if (!date) fail(n, 'date is required when new_file is set');
    if (!/^\d{4}(-\d{2}){0,2}$/.test(date)) fail(n, `date ${date} is not YYYY-MM-DD, YYYY-MM or YYYY`);
    const fp = path.join(folder, file);
    if (!fs.existsSync(fp)) fail(n, `${fp} not found`);
    cmd.push(fp);
    if (comp) { const cp = path.join(folder, comp); if (!fs.existsSync(cp)) fail(n, `${cp} not found`); cmd.push(cp); }
    cmd.push(date);
    if (featured) cmd.push('--featured');
    if (replaces) cmd.push('--replace', replaces);
  }
  plan.push({ n, cmd, label: file ? `${replaces ? replaces + ' -> ' : 'add '}${file}${comp ? ' + ' + comp : ''}` : `drop ${replaces}` });
});
if (!plan.length) { console.log('replacements.csv has no rows.'); process.exit(0); }

// ---- pass 2: run
for (const p of plan) {
  const cmd = dry ? [...p.cmd, '--dry-run'] : p.cmd;
  console.log(`\n[row ${p.n}] ${p.label}\n  ${cmd.map(a => (/\s/.test(a) ? `'${a}'` : a)).join(' ')}`);
  const res = spawnSync(process.execPath, cmd, { stdio: 'inherit' });
  if (res.status !== 0) { console.error(`stopped at row ${p.n}; fix and re-run (rows already applied are in handoff/changes.log)`); writeBack(); process.exit(1); }
}
writeBack();
console.log(`\n${dry ? 'would apply' : 'applied'} ${plan.length} row(s).${dry ? ' Re-run without --dry-run to apply.' : ' Next: bin/build, then bin/live.'}`);
