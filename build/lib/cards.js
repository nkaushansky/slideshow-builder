// Title and end cards: the words that open and close the show.
//
// The cards are NOT drawn over the mosaic. The loop's frames are the ones the layout was proved against (the wrap
// check compares the frame at the end of the loop with the frame at its start), so a card painted into that stream
// would break the proof and change every frame's timing. Instead each card is encoded as its own short segment and
// the three parts are joined with the concat demuxer, copying the streams: title, loop, end. The soundtrack is muxed
// over the joined file afterwards, so the music covers the cards too.
//
// The card's picture comes from the player page itself (`player.html?card=title`), screenshotted at the output size.
// That way one piece of code decides how a card looks, the live player and the video agree, and no font has to be
// found on the machine for a drawtext filter.
//
// Every function here writes only inside the project's build folder and returns what it wrote, so bin/render can
// print a plan for --dry-run without calling any of them.
'use strict';
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const C = require('./common');

const CARDS_DIR = path.join(C.BUILD, 'cards');
const WHICH = ['title', 'end'];

// What the manifest says the cards are, with the defaults a show.json from before 0.4 implies (no cards at all).
function cardsOf(manifest) {
  const c = (manifest && manifest.cards) || {};
  const text = v => String(v == null ? '' : v).replace(/\s+$/, '');
  const seconds = Number(c.seconds) > 0 ? Number(c.seconds) : 6;
  const fade = Number(c.fade_s) >= 0 ? Math.min(Number(c.fade_s), seconds / 2) : Math.min(1, seconds / 2);
  const playback = (manifest && manifest.playback) === 'once' ? 'once' : 'loop';
  // a "loop" show never reaches its end card: the file is played on repeat, so an end card would land mid-show
  return { title: text(c.title), end: playback === 'once' ? text(c.end) : '', seconds, fade, playback };
}

// The segments a render will put around the loop, in play order, as { which, text, seconds, png, mp4 }.
function plan(manifest, target) {
  const cards = cardsOf(manifest);
  const stem = path.parse(target).name;
  return WHICH.filter(w => cards[w]).map(w => ({
    which: w, text: cards[w], seconds: cards.seconds, fade: cards.fade,
    png: path.join(CARDS_DIR, `${stem}-${w}.png`), mp4: path.join(CARDS_DIR, `${stem}-${w}.mp4`),
  }));
}

function run(bin, args, what) {
  return new Promise((resolve, reject) => {
    let err = '';
    const p = spawn(bin, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    p.stderr.on('data', d => { err += d; });
    p.on('error', e => reject(new Error(`${what}: ${e.message}`)));
    p.on('close', code => code === 0 ? resolve() : reject(new Error(`${what} failed (exit ${code})${err ? ': ' + err.trim().split('\n').slice(-3).join(' | ') : ''}`)));
  });
}

// One card's picture, from the player page at the output size. `pageUrl` is the render server's player.html.
async function shoot(page, pageUrl, card, width, height) {
  fs.mkdirSync(CARDS_DIR, { recursive: true });
  await page.goto(`${pageUrl}?card=${card.which}`);
  await page.waitForFunction(() => window.__cardReady === true, null, { timeout: 30000 });
  const seen = await page.evaluate(() => document.getElementById('cardText').textContent);
  if (String(seen).replace(/\s+$/, '') !== card.text) {
    throw new Error(`the ${card.which} card on the page reads ${JSON.stringify(seen)}, the manifest says ${JSON.stringify(card.text)}; run bin/build`);
  }
  await page.screenshot({ path: card.png, clip: { x: 0, y: 0, width, height } });
  if (!(fs.existsSync(card.png) && fs.statSync(card.png).size > 0)) throw new Error(`the ${card.which} card screenshot is empty (${C.rel(card.png)})`);
  return card.png;
}

// One card's segment: the still held for its seconds, faded in and out, encoded exactly like the loop so the three
// parts can be joined by copying. Same size, frame rate, pixel format, preset, crf and (for tv-usb) profile and level.
async function encode(card, { width, height, fps, preset, crf, levelArgs = [] }) {
  const frames = Math.round(card.seconds * fps);
  const fade = card.fade > 0
    ? `,fade=t=in:st=0:d=${card.fade.toFixed(3)},fade=t=out:st=${Math.max(0, card.seconds - card.fade).toFixed(3)}:d=${card.fade.toFixed(3)}`
    : '';
  const args = ['-hide_banner', '-nostdin', '-v', 'error', '-y', '-loop', '1', '-framerate', String(fps), '-i', card.png, '-an',
    '-vf', `scale=${width}:${height}:flags=lanczos,format=rgb24${fade},scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd,format=yuv420p`,
    '-frames:v', String(frames),
    '-c:v', 'libx264', '-preset', preset, '-crf', String(crf), ...levelArgs, '-pix_fmt', 'yuv420p', '-r', String(fps),
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709',
    '-movflags', '+faststart', card.mp4];
  await run(C.FFMPEG, args, `encoding the ${card.which} card`);
  return { file: card.mp4, frames };
}

// Join the parts into one file by copying the streams. The list file quotes each path the way the concat demuxer
// expects, so a project folder with a quote or a space in its name still works.
async function join(parts, out) {
  const list = path.join(CARDS_DIR, path.parse(out).name + '.concat.txt');
  fs.mkdirSync(CARDS_DIR, { recursive: true });
  fs.writeFileSync(list, parts.map(f => `file '${String(f).replace(/'/g, "'\\''")}'`).join('\n') + '\n');
  await run(C.FFMPEG, ['-hide_banner', '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list,
    '-c', 'copy', '-movflags', '+faststart', out], 'joining the cards and the loop');
  fs.unlinkSync(list);
  return out;
}

module.exports = { CARDS_DIR, cardsOf, plan, shoot, encode, join };
