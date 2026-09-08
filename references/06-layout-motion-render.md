# Layout, motion and render

The build takes the frozen set and produces a browser player and a rendered video. Everything that moves is a pure function of elapsed time computed in the player's script, never a CSS animation, so the live player, the render and the scheduler simulator agree frame for frame. The numbers below are the first run's defaults; the intake and the owner's live-player round tune them.

## Output target

Render at the display's **logical** resolution (2560×1440 for a 27-inch 5K panel), 60 fps, H.264, no audio. At viewing distances of five feet or more the eye cannot resolve more, and a native-5K render would quadruple render time and exceed hardware-decode limits on older machines. The deliverable is an mp4 that loops in VLC; the browser player exists to produce that mp4 deterministically and to serve as a live fallback.

## Items and dates

- A Live Photo pair is one item; the video half is what is displayed. The still is never shown (switching between still and video pops, and at tile size the video frame is sharp enough).
- Ordering key: day precision uses the date; month precision the 15th; year precision July 1; ties by filename. Nothing displays a date.

## Sequence: mini-timelines

Viewers glance for a minute or two, so every two-minute window should span the whole range rather than one era.

1. Sort all items by date key.
2. Deal round-robin into `chapters` (default 10) so each chapter has about the same count and runs the whole span. Deal stratified: standalone videos, featured stills, other moving items and plain stills each dealt round-robin by date with one running cursor, so no chapter ends up with all the videos.
3. Concatenate. The sequence is a **ring**; the wrap from the last chapter to the first is just another chapter boundary, which is what makes the loop seam invisible.
4. Spacing pass, within a chapter only: standalone videos never in adjacent rows if the chronology allows (`videoMinRowGap` 2), no base row with more than 2 moving tiles, nudges within `anchorLookahead` positions except videos, which may move up to `videoNudge` (12). Deterministic greedy search.
5. **Chronology beats spacing.** A quadratic penalty (`disorderWeight` 2000) for any backward jump over half a year between neighbours means videos barely move and video rows are often consecutive; the owner on the first run preferred that to items pulled years out of order. Print the trade-off (adjacent video-row pairs versus backward jumps) for two or three weights and let the owner choose.
6. **Rows never straddle a chapter boundary.** A rebalancing pass shifts items between neighbouring rows of the same chapter to even heights; chapter tails are pooled and re-split. The reset from the last year to the first is a clean row-to-row cut.
7. A fixed `seed` for any randomness, so the sequence is reproducible and reviewable.

Loop length is an output: item count, scroll speed and the share of feature rows set it. Expect about 3 seconds per item at 100 px/s with the default row mix.

## Layout: justified rows

- Rows span the full width. Each item is scaled to the row's target height at its own aspect ratio; items are pulled until the row is full; the row is scaled to fill the width exactly. **No cropping, ever.** An item wider than about 2.4:1 takes a row alone.
- Two row types: **base** (`baseRowHeight` 520 px, typically 4 to 5 items) and **feature** (`featureRowHeight` 820 px, 2 to 3 items). A row ends when its natural width crosses the screen; the straddling item joins unless that makes the row more than `fillBias` (0.1 in log-height) worse than stopping, so rows err short.
- **Anchors** = the featured stills plus every standalone video. When the next item is an anchor, start a feature row; fill it by pulling further anchors from within `anchorLookahead` (6) positions, otherwise the next items in sequence. **Max one video per feature row.**
- Any pull is allowed only if the pulled item is at most `pullMaxGap` (1.25 years) ahead of the item it jumps past; the owner flagged featured stills pulled a year and a half forward as out of place.
- **Do the anchor arithmetic before building.** Anchors ÷ items sets the feature-row share. On the first run 129 anchors among 469 items (75 featured stills plus 54 videos) gave 83 feature rows of 134, or 62 percent, and a 15-minute loop where 12 had been expected. Print row counts and the share on every build.
- `gutter` 8 px; background a near-black chosen to match the event's identity.

## Media preparation

- **Stills:** HEIC to JPEG at quality 90, then every still resized to a maximum height of twice the feature row (1640 px). Compute the resize from the index dimensions, not from the file, because some tools keep rotation as a tag rather than rotating pixels. Use Pillow with its HEIC plugin so the step works on every platform.
- **Clips for live mode:** every Live Photo video, standalone video and GIF to H.264, `-preset veryfast -crf 20 -pix_fmt yuv420p`, no audio, faststart, display height capped like the stills. Do not rely on the browser's HEVC support.
- **HDR:** 10-bit HLG or PQ videos come out washed out; tone-map to SDR BT.709 (`zscale` plus `tonemap=hable`, chosen on a contact frame over mobius and clip).
- **Slow motion:** videos captured at 100 fps or more play at 30 fps, eight times slow, as the phone shows them; record the effective duration in the preparation manifest. A per-file real-time switch exists for the owner.
- **Frames for render mode:** per placement, JPEG frames at 30 fps scaled to the row height the item landed in; Live Photos and GIFs in full; standalone videos from their `start` offset for the visible window plus one second. For slow motion use `setpts` with constant-rate output, and give the `-t` window in **display** seconds, because an output-side `-t` is measured after `setpts`. Padding a missing frame or two is allowed; past a threshold of 30 the step fails and reports. A completion marker records counts; **verify by distinct frames**.
- Preparation is idempotent: outputs written under a temporary name and renamed, so an interrupted run resumes. Wrap it in the OS keep-awake tool.

## Motion rules

- **Live Photos and GIFs:** play the full clip forward, no trim, hold the last frame for `livePhotoHold` (1.5 s), then restart. No ping-pong. Per-file trims exist and default to zero; change them only after the owner's review.
- **Standalone videos:** feature rows only, one per row, muted, a per-file `start` offset defaulting to zero, playing for the whole time the row is visible (about 23 s at 100 px/s) and looping if shorter. No pausing the scroll, no promotion to full screen.
- **Moving-tile cap:** at most `movingCap` (4) tiles animate at once. A scheduler grants a slot when a moving tile enters the viewport and releases it on exit; a tile without a slot shows its first frame. Grants are deterministic from the clock so live and render agree. Rules that the owner's review produced on the first run and that should be defaults: `videoPriority` (a video entering the viewport takes a slot from the longest-running Live Photo that has finished a play); `rotateSlots` with `rotatePlays` 1 (a Live Photo that has played once hands its slot on when another is waiting); `maxWait` 4 s; `startVisibleFrac` 1 (a Live Photo asks for a slot only once its row is fully on screen, a video asks the moment any of it appears). A scheduler simulator steps a loop in a fraction of a second and prints wait percentiles and how many first plays were cut short; use it instead of watching loops to answer scheduling questions.

## Player

One HTML file opened from `file://`, manifest inlined as a script array because `fetch` is blocked on `file://`. Scroll position is `scrollSpeed × t`; rows are positioned from it and recycled through the ring so memory stays flat. Two modes: `live` (muted video tiles, the scheduler) and `render` (moving tiles are image elements whose source is the frame index for the clock; no video elements). Keyboard in live mode: fullscreen, pause, speed up and down. Review aids behind URL parameters only: labels, click-to-flag with notes persisted locally, a start time. A review page lists the whole sequence with thumbnails, names and entry times.

## Render

- A headless browser driven by Playwright (bundled Chromium, else installed Chrome via `channel: 'chrome'`), viewport at the output resolution, device scale factor 1, page served over local HTTP because images loaded from `file://` taint a canvas.
- Per frame, the script calls the page with the exact time (k × 1000/60): the page sets its clock, updates rows and the scheduler, draws every visible tile into a canvas the size of the viewport, JPEG-encodes it and sends it over a WebSocket to the script, which pipes it into ffmpeg (`image2pipe`) and acknowledges once ffmpeg accepted it, so the page never runs ahead. **Why not screenshots:** the browser's screenshot path cost about 350 ms per frame on the first run's hardware, five hours per loop; the canvas path cost about 85 ms. Measure at Step 0.
- Before frame 0, step the scheduler through several whole loops without drawing and compare a canonical snapshot of its state loop to loop until it repeats, so frame 0 carries the periodic state and the wrap is seamless. Then render **exactly one loop**: frame count = loop seconds × 60, frame 0 being the frame that follows the last. Check the wrap by PSNR between frame 0 and the frame after the last: identical, or stop.
- Encode `libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 60`, full-range JPEG converted to limited-range BT.709 and tagged.
- **Always a 60-second test render first**, then window renders (`--from <seconds>`) around every special case. Only then the full render. Expect one to three hours on 2017-era hardware for a 15-minute loop; log the rate.
- Concatenate three copies with stream copy so the player's own loop seam lands every 45 minutes rather than every 15. Soak in VLC for the length of the event window and read its log for late frames. Then the owner's full watch.
- Playback: VLC, repeat one, fullscreen, OSD off, no audio, under the OS keep-awake tool; a desktop launcher that kills any running VLC and starts the file, with a fallback to a copy on a USB stick; the live player in the browser as the last resort.

## Tuning knobs

One config block at the top of the build script, each overridable from the command line for a quick try:

| Knob | Default | Trade-off |
|---|---|---|
| `scrollSpeed` | 100 px/s | slower reads easier and lengthens the loop; the owner compared 100 and 120 by eye |
| `baseRowHeight`, `featureRowHeight` | 520, 820 | tile size against items per screen |
| `chapters` | 10 | shorter chapters sweep the span more often but hold fewer items |
| `anchorLookahead` | 6 | packs anchors into feature rows; raises the share |
| `pullMaxGap` | 1.25 yr | fewer out-of-order pulls against more rows |
| `disorderWeight` | 2000 | chronology against video spacing |
| `videoMinRowGap`, `videoNudge` | 2, 12 | how hard spacing tries |
| `movingCap` | 4 | motion density against the sense of "occasional motion among stills" |
| `videoPriority`, `rotateSlots`, `rotatePlays`, `maxWait`, `startVisibleFrac` | on, on, 1, 4 s, 1 | who moves when; see motion rules |
| `livePhotoHold` | 1.5 s | the pause before a Live Photo restarts |
| `minFill`, `fillBias` | 0.9, 0.1 | how short a row may be |
| `gutter`, `seed` | 8 px, fixed | |

## Acceptance checks

- Every item in the sequence exactly once, Live Photos by their video half; counts printed.
- No row exceeds the width; nothing cropped; no feature row with two videos; every anchor in a feature row; no item across a chapter boundary.
- Feature-row share printed and within what the owner accepted at the live-player round.
- No frame with more than `movingCap` tiles moving.
- Frame count exact; wrap identical; output resolution, frame rate, codec and no audio as specified; VLC plays at full speed with late frames only at start or seam.
- The four special cases (slow motion, HDR, longest videos, the wrap) verified by content in window renders.
- Update these checks in the brief when a rule changes; on the first run two checks stayed in the brief after the owner had overruled them.
