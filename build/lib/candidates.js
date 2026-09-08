#!/usr/bin/env node
'use strict';
// bin/candidates <filename>... — for each item you want to swap out, list files from cut-list.csv shot within
// ±45 days that were cut only for the per-year cap (reason over-cap), with their source paths.
const fs = require('fs');
const path = require('path');
const C = require('./common');
const names = process.argv.slice(2);
if (!names.length) { console.error('usage: bin/candidates <filename>...'); process.exit(2); }
const media = C.readMediaCsv().rows; const byName = new Map(media.map(r => [r.filename, r]));
const cut = C.readCsvObjects(C.CUT_LIST_CSV).rows;
const day = s => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s); if (!m || m[1] === '9999' || m[2] === '00') return null; return Date.UTC(+m[1], +m[2] - 1, +(m[3] === '00' ? 15 : m[3])) / 864e5; };
const out = [];
for (const n of names) {
  const r = byName.get(n);
  if (!r) { out.push(`${n}: not in media.csv`); continue; }
  const d0 = day(r.date);
  const same = cut.filter(c => { const d = day(c.filename); return d != null && d0 != null && Math.abs(d - d0) <= 45; })
    .map(c => ({ ...c, dist: Math.abs(day(c.filename) - d0) })).sort((a, b) => (a.reason === 'over-cap' ? 0 : 1) - (b.reason === 'over-cap' ? 0 : 1) || a.dist - b.dist);
  out.push(`\n== ${n}  (${r.type}, ${r.date}${r.tag ? ', tag ' + r.tag : ''}${r.featured === 'yes' ? ', FEATURED' : ''})  — ${same.length} cut files within ±45 days`);
  for (const c of same.slice(0, 25)) out.push(`   ${c.reason.padEnd(9)} ${c.filename.padEnd(60)} ${c.original_source_path}`);
  if (same.length > 25) out.push(`   ... ${same.length - 25} more`);
}
const text = out.join('\n') + '\n';
console.log(text);
fs.appendFileSync(path.join(C.BUILD, 'replacement-candidates.txt'), `# ${new Date().toISOString()}\n` + text);
console.log(`(also appended to build/replacement-candidates.txt)`);
