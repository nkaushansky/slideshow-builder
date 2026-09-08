#!/usr/bin/env node
'use strict';
// bin/redate <filename> <YYYY-MM-DD|YYYY-MM|YYYY> [--dry-run] — move one item (and its Live Photo companion) to a new date.
// Built on add-item so the bookkeeping is the same as any other change: the current file(s) leave the set (-> _removed/,
// cut-list reason `redated`) and the same bytes come back under the new date prefix, keeping featured, tag and the
// original_source_path. Everything lands in changes.log.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const C = require('./common');

const args = process.argv.slice(2);
const dry = args.includes('--dry-run');
const pos = args.filter(a => !a.startsWith('--'));
if (pos.length !== 2) { console.error('usage: bin/redate <filename> <YYYY-MM-DD|YYYY-MM|YYYY> [--dry-run]'); process.exit(2); }
const name = path.basename(pos[0]), date = pos[1];
if (!/^\d{4}(-\d{2}){0,2}$/.test(date)) { console.error(`redate: bad date ${date} (YYYY-MM-DD, YYYY-MM or YYYY; 00 = unknown)`); process.exit(2); }

const { rows } = C.readMediaCsv();
const row = rows.find(r => r.filename === name);
if (!row) { console.error(`redate: ${name} is not in media.csv`); process.exit(1); }
const group = [row];
if (row.companion) { const c = rows.find(r => r.filename === row.companion); if (c) group.push(c); }
group.sort((a, b) => (C.extClass(a.filename) === 'still' ? 0 : 1) - (C.extClass(b.filename) === 'still' ? 0 : 1)); // still first
if (group.every(r => r.date === date.replace(/^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/, (m, y, mo, d) => `${y}-${mo || '00'}-${d || '00'}`))) { console.log(`redate: ${name} is already dated ${date}`); process.exit(0); }

// stage copies under their bare names; add-item puts the new date prefix on
const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'redate-'));
const staged = group.map(r => { const p = path.join(stage, r.filename.replace(/^\d{4}-\d{2}-\d{2}_/, '')); fs.copyFileSync(path.join(C.MEDIA, r.filename), p); return p; });
const cmd = [path.join(__dirname, 'add-item.js'), ...staged, date, '--replace', name, '--reason', 'redated', '--date-source', 'owner', '--witness', `redated by the owner; was ${row.date} (${row.precision})`];
for (const r of group) cmd.push('--source', r.original_source_path || path.join(C.MEDIA, r.filename));
if (group.some(r => r.featured === 'yes')) cmd.push('--featured');
const tag = group.map(r => r.tag).find(Boolean); if (tag) cmd.push('--tag', tag);
if (dry) cmd.push('--dry-run');
console.log(`redate ${group.map(r => `${r.filename} (${r.date})`).join(' + ')} -> ${date}`);
const res = spawnSync(process.execPath, cmd, { stdio: 'inherit' });
fs.rmSync(stage, { recursive: true, force: true });
process.exit(res.status == null ? 1 : res.status);
