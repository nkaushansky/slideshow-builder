#!/usr/bin/env node
'use strict';
// bin/simsched [--loops N] — run the player's moving-tile scheduler through N loops in headless Chrome without drawing
// anything, and print window.__schedStats(): waits for a first turn, tiles never served, first plays started before the
// tile was fully on screen, first plays cut short by a freeze or by scrolling off. For comparing scheduler knobs:
//   bin/build --start-visible 0 && bin/simsched;  bin/build --start-visible 1 && bin/simsched
// Needs Google Chrome; run from a normal Terminal (headless Chrome does not start inside a sandbox).
const fs = require('fs');
const path = require('path');
const C = require('./common');
const i = process.argv.indexOf('--loops');
const loops = i >= 0 ? Number(process.argv[i + 1]) : 1;
(async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(C.BUILD, 'manifest.json'), 'utf8'));
  const cfg = manifest.config;
  const browser = await C.launchBrowser();
  const page = await browser.newPage({ viewport: { width: cfg.viewportW, height: cfg.viewportH } });
  await page.goto('file://' + path.join(C.BUILD, 'player.html') + '?render=1');
  await page.evaluate(() => window.__ready);
  const info = await page.evaluate(() => window.__renderInfo());
  const t0 = Date.now();
  await page.evaluate(s => window.__renderWarmup(s), info.loop.seconds * loops);
  const s = await page.evaluate(() => window.__schedStats());
  const knobs = ['movingCap', 'rotateSlots', 'rotatePlays', 'maxWait', 'videoPriority', 'startVisibleFrac', 'livePhotoHold', 'scrollSpeed'].map(k => `${k}=${cfg[k]}`).join(' ');
  console.log(`simsched: ${loops} loop(s) of ${info.loop.seconds.toFixed(1)} s in ${((Date.now() - t0) / 1000).toFixed(1)} s; ${knobs}`);
  const f = x => (typeof x === 'number' && !Number.isInteger(x) ? x.toFixed(2) : x);
  console.log(`  moving tiles entered ${s.entered}, served ${s.served}, never served ${s.neverServed}`);
  console.log(`  wait for first turn: mean ${f(s.waitMean)} s, p50 ${f(s.waitP50)}, p90 ${f(s.waitP90)}, max ${f(s.waitMax)}; over 2 s: ${s.waitOver2}, over 4 s: ${s.waitOver4}`);
  console.log(`  Live Photo/GIF first plays: started before fully on screen ${s.startedPartial}, completed ${s.firstPlayDone}, cut short by a freeze ${s.cutShort}, still mid-play when scrolled off ${s.exitMidPlay}`);
  console.log(`  handovers ${s.handovers}, preempts ${s.preempts}`);
  // wrap probe: does the scheduler state repeat from one loop to the next once warmed up? (what bin/render relies on)
  await page.reload(); await page.evaluate(() => window.__ready);
  const w = await page.evaluate(([sec, n]) => window.__renderWarmupLoops(sec, n), [info.loop.seconds, 10]);
  console.log(`  wrap: after 10 warm-up loops the scheduler state ${w.periodic ? 'REPEATS' : 'does NOT repeat'} loop to loop${w.periodicAfter >= 0 ? ` (first repeat at loop ${w.periodicAfter})` : ''}; bin/render warms up 8 loops by default (--warm-loops N)`);
  await browser.close();
})().catch(e => { console.error('simsched: ' + (e.stack || e)); process.exit(1); });
