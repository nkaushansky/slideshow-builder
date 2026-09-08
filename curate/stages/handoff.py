"""handoff: freeze the approved set as the index contract the build reads.

    python curate/run.py handoff [--project P] [--dry-run] [--force]

Copies every selected file (and its Live Photo companion) from work/ into handoff/media/
byte-identical, verified by size and SHA-256 against media_id, and writes media.csv,
features.txt, cut-list.csv, inventory.md and HANDOFF.md in the formats of
references/02-index-contract.md. Creates an empty changes.log when there is none and never
truncates an existing one. Prints the accounting invariant and exits non-zero if it does not
balance: rows in media.csv + rows in cut-list.csv = files in the index, every file exactly once.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import media_id, project, say, write_atomic  # noqa: E402
from stages._lenses import CUT_COLS, MEDIA_COLS, STILL_TYPES, fnum, inum, read_csv, write_csv  # noqa: E402


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


def _work_path(P, item: dict):
    loc = (item.get("location") or "work").replace("\\", "/")
    if loc != "work":
        return None
    return P.work / item["filename"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="handoff", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-hash every file in handoff/media even if it was verified before")
    a = ap.parse_args(argv)
    P = project()

    for need in ("items.csv", "selection.csv", "cut-list.csv"):
        if not (P.index / need).is_file():
            say(f"handoff: {P.index / need} missing; run the earlier stages first")
            return 2
    items = read_csv(P.index / "items.csv")
    byname = {r["filename"]: r for r in items}
    selection = read_csv(P.index / "selection.csv")
    sel_by_name = {r["filename"]: r for r in selection}
    cuts = read_csv(P.index / "cut-list.csv")
    people_path = P.index / "people.csv"
    people = {r["media_id"]: r for r in read_csv(people_path)} if people_path.is_file() else {}
    flags_path = P.index / "flags.csv"
    flags = [f for f in read_csv(flags_path) if not (f.get("resolved_by") or "").strip()] if flags_path.is_file() else []

    selected = [byname[r["filename"]] for r in selection if r["selected"] == "yes" and r["filename"] in byname]
    selected.sort(key=lambda r: r["filename"])
    missing_src, bad_loc = [], []
    for it in selected:
        p = _work_path(P, it)
        if p is None:
            bad_loc.append(it["filename"])
        elif not p.is_file():
            missing_src.append(it["filename"])
    if bad_loc or missing_src:
        for n in bad_loc[:10]:
            say(f"  ! selected file is not in work/: {n}")
        for n in missing_src[:10]:
            say(f"  ! selected file missing on disk: {n}")
        say(f"handoff: {len(bad_loc) + len(missing_src)} selected file(s) cannot be copied; fix the index or the selection")
        return 1

    # ---- the invariant, checked before anything is written
    # every FILE exactly once: keyed by filename, because a parked exact duplicate shares its keeper's media_id
    sel_ids = {r["filename"] for r in selected}
    cut_ids = [r["filename"] for r in cuts]
    problems = []
    dup_cut = [k for k, v in collections.Counter(cut_ids).items() if v > 1]
    if dup_cut:
        problems.append(f"{len(dup_cut)} media_id(s) appear twice in cut-list.csv")
    both = sel_ids & set(cut_ids)
    if both:
        problems.append(f"{len(both)} file(s) are both selected and cut")
    union = sel_ids | set(cut_ids)
    unaccounted = [r["filename"] for r in items if r["filename"] not in union]
    if unaccounted:
        problems.append(f"{len(unaccounted)} indexed file(s) are neither selected nor cut (e.g. {unaccounted[0]})")
    unknown = [m for m in cut_ids if m not in byname]
    if unknown:
        problems.append(f"{len(unknown)} cut-list row(s) are not in items.csv")
    for it in selected:
        c = it.get("companion", "")
        if c:
            other = byname.get(c)
            if other is None or other["filename"] not in sel_ids:
                problems.append(f"companion of {it['filename']} ({c}) is not in the set")
            elif other.get("companion", "") != it["filename"]:
                problems.append(f"companion link not symmetric: {it['filename']} <-> {c}")
    featured = [it for it in selected if sel_by_name.get(it["filename"], {}).get("featured") == "yes"]
    for it in featured:
        if it.get("type") not in STILL_TYPES:
            problems.append(f"featured item is not a still: {it['filename']}")
    n_media, n_cut, n_items = len(selected), len(cuts), len(items)
    balance = (n_media + n_cut == n_items) and not problems
    say(f"handoff: invariant: {n_media} media.csv rows + {n_cut} cut-list rows = {n_media + n_cut} of {n_items} indexed files "
        f"{'OK' if n_media + n_cut == n_items else 'MISMATCH'}")
    for p in problems:
        say("  !", p)
    if not balance:
        say("handoff: the accounting does not balance; nothing written. Re-run select, or fix the index.")
        return 1

    # ---- copy plan
    P.handoff.mkdir(parents=True, exist_ok=True) if not a.dry_run else None
    cache_path = P.handoff / ".verified.json"
    cache = {}
    if cache_path.is_file() and not a.force:
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    to_copy, verified = [], 0
    for it in selected:
        dst = P.media / it["filename"]
        if dst.is_file():
            st = dst.stat()
            c = cache.get(it["filename"])
            if c and c.get("bytes") == st.st_size and c.get("mtime") == int(st.st_mtime) and c.get("media_id") == it["media_id"]:
                verified += 1
                continue
            if not a.force and st.st_size == inum(it.get("bytes"), st.st_size) and media_id(dst) == it["media_id"]:
                cache[it["filename"]] = {"bytes": st.st_size, "mtime": int(st.st_mtime), "media_id": it["media_id"]}
                verified += 1
                continue
        to_copy.append(it)
    total_bytes = sum(inum(it.get("bytes")) for it in selected)
    say(f"  media/: {verified} already verified, {len(to_copy)} to copy, {_human(total_bytes)} in the set")
    if a.dry_run:
        say(f"handoff: dry run; would copy {len(to_copy)} file(s) and write media.csv ({n_media} rows), features.txt "
            f"({len(featured)} lines), cut-list.csv ({n_cut} rows), inventory.md, HANDOFF.md into {P.handoff}")
        return 0

    P.media.mkdir(parents=True, exist_ok=True)
    errors = []
    for i, it in enumerate(to_copy, 1):
        src, dst = _work_path(P, it), P.media / it["filename"]
        tmp = dst.with_name(dst.name + ".part")
        try:
            shutil.copy2(src, tmp)
            h = media_id(tmp)
            if h != it["media_id"] or tmp.stat().st_size != src.stat().st_size:
                tmp.unlink(missing_ok=True)
                errors.append(f"{it['filename']}: hash after copy {h[:12]} does not match media_id {it['media_id'][:12]}")
                continue
            os.replace(tmp, dst)
            st = dst.stat()
            cache[it["filename"]] = {"bytes": st.st_size, "mtime": int(st.st_mtime), "media_id": it["media_id"]}
        except OSError as e:
            tmp.unlink(missing_ok=True)
            errors.append(f"{it['filename']}: {e}")
        if i % 50 == 0 or i == len(to_copy):
            say(f"  copied {i}/{len(to_copy)}")
    write_atomic(cache_path, json.dumps(cache, indent=0))
    if errors:
        for e in errors[:10]:
            say("  !", e)
        say(f"handoff: {len(errors)} copy failure(s); media.csv not written. Re-run to retry.")
        return 1
    extra = sorted(n for n in os.listdir(P.media) if n not in {it["filename"] for it in selected}
                   and not n.startswith(".") and not n.endswith(".part"))
    if extra:
        say(f"  ! {len(extra)} file(s) in media/ are not in the set (left alone): {', '.join(extra[:5])}")

    # ---- media.csv, features.txt, cut-list.csv
    media_rows = []
    for it in selected:
        s = sel_by_name.get(it["filename"], {})
        media_rows.append(dict(
            media_id=it["media_id"], filename=it["filename"], type=it.get("type", ""), companion=it.get("companion", ""),
            width=it.get("width", ""), height=it.get("height", ""), duration_s=it.get("duration_s", ""),
            fps=it.get("fps", ""), hdr=it.get("hdr", ""), date=it.get("date", ""), precision=it.get("precision", ""),
            date_source=it.get("date_source", ""), date_witness=it.get("date_witness", ""),
            exif_datetime_original=it.get("exif_datetime_original", ""),
            people=people.get(it["media_id"], {}).get("people", ""), tag=s.get("tag", "") if s.get("tag") != "companion" else "",
            featured="yes" if s.get("featured") == "yes" else "", video_codec=it.get("video_codec", ""),
            has_audio=it.get("has_audio", ""), original_source_path=it.get("source_path", "")))
    write_csv(P.handoff / "media.csv", media_rows, MEDIA_COLS)
    write_atomic(P.handoff / "features.txt", "".join(it["filename"] + "\n" for it in sorted(featured, key=lambda r: r["filename"])))
    write_csv(P.handoff / "cut-list.csv", cuts, CUT_COLS)
    log = P.handoff / "changes.log"
    if not log.exists():
        log.write_text("", encoding="utf-8")

    # ---- inventory.md
    years = collections.Counter(r["date"][:4] or "undated" for r in media_rows)
    types = collections.Counter(r["type"] for r in media_rows)
    exts = collections.Counter(os.path.splitext(r["filename"])[1].lower() for r in media_rows)
    codecs = collections.Counter(r["video_codec"] for r in media_rows if r["video_codec"])
    precs = collections.Counter(r["precision"] or "none" for r in media_rows)
    srcs = collections.Counter(r["date_source"] or "none" for r in media_rows)
    reasons = collections.Counter(r["reason"] for r in cuts)
    ready = sum(1 for r in media_rows if min(inum(r["width"]), inum(r["height"])) >= 1080
                and max(inum(r["width"]), inum(r["height"])) >= 1920)
    pairs = sum(1 for r in media_rows if r["type"] == "livephoto-still")
    moments = len(media_rows) - sum(1 for r in media_rows if r["type"] == "livephoto-video")
    inv = [f"# Inventory of handoff/media", "",
           f"Generated {dt.datetime.now().isoformat(timespec='seconds')} by the handoff stage.", "",
           "## Totals", "",
           f"- Files: {len(media_rows)} ({_human(total_bytes)}); moments: {moments} (a Live Photo pair counts once; {pairs} pairs)",
           f"- Featured stills: {len(featured)}",
           f"- Display readiness (short side >= 1080 and long side >= 1920): {ready} of {len(media_rows)}", "",
           "## By type", "", *[f"- {k}: {v}" for k, v in sorted(types.items())], "",
           "## By year", "", *[f"- {k}: {v}" for k, v in sorted(years.items())], "",
           "## By extension and codec", "", *[f"- {k}: {v}" for k, v in sorted(exts.items())],
           *[f"- codec {k}: {v}" for k, v in sorted(codecs.items())], "",
           "## Date precision and source", "", *[f"- precision {k}: {v}" for k, v in sorted(precs.items())],
           *[f"- source {k}: {v}" for k, v in sorted(srcs.items())], "",
           "## Cut list", "", f"- Rows: {len(cuts)}", *[f"- {k}: {v}" for k, v in sorted(reasons.items())], "",
           "## Accounting", "",
           f"- {len(media_rows)} media rows + {len(cuts)} cut rows = {len(media_rows) + len(cuts)} indexed files, every file once.", ""]
    write_atomic(P.handoff / "inventory.md", "\n".join(inv))

    # ---- HANDOFF.md: only what ran, uncertainties as uncertainties
    heic = sum(1 for r in media_rows if os.path.splitext(r["filename"])[1].lower() in (".heic", ".heif"))
    hevc = sum(1 for r in media_rows if (r["video_codec"] or "").lower() in ("hevc", "h265"))
    hdr = sum(1 for r in media_rows if r["hdr"] == "yes")
    slow = [r for r in media_rows if fnum(r["fps"]) >= 100]
    pano = [r for r in media_rows if inum(r["width"]) and inum(r["height"])
            and max(inum(r["width"]), inum(r["height"])) / max(1, min(inum(r["width"]), inum(r["height"]))) > 2.4]
    tiny = [r for r in media_rows if inum(r["width"]) and min(inum(r["width"]), inum(r["height"])) < 600]
    long_v = [r for r in media_rows if fnum(r["duration_s"]) > 60]
    unprobed = [r for r in media_rows if r["type"] in ("video", "livephoto-video", "animated-gif") and not r["duration_s"]]
    open_flags = collections.Counter(f["gate"] for f in flags if f["media_id"] in sel_ids)
    h = ["# Handoff to the build", "",
         f"Written {dt.datetime.now().isoformat(timespec='seconds')} by the handoff stage of slideshow-builder.", "",
         "## What was done", "",
         f"- {len(media_rows)} files were copied from the working folder into `media/`, each verified by size and SHA-256 "
         f"against its `media_id`.",
         f"- `media.csv` carries one row per file with the columns of the index contract; `features.txt` lists the "
         f"{len(featured)} featured stills; `cut-list.csv` carries the {len(cuts)} files considered and not kept, with one-word reasons.",
         f"- The accounting invariant balances: {len(media_rows)} + {len(cuts)} = {len(items)} indexed files.",
         f"- `changes.log` is {'present and untouched' if log.stat().st_size else 'empty'}; every change from here on goes through the apply tool.", "",
         "## Special cases the build must handle", "",
         f"- HEIC stills: {heic}. Convert to JPEG during preparation (Pillow with pillow-heif on every platform).",
         f"- HEVC videos: {hevc}. Transcode clips to H.264 for the live player.",
         f"- 10-bit HDR videos: {hdr}. Tone-map to SDR BT.709.",
         f"- Slow motion (>= 100 fps): {len(slow)}. Play at 30 fps unless the per-file real-time switch says otherwise."
         + (" Files: " + ", ".join(r["filename"] for r in slow[:8]) if slow else ""),
         f"- Panoramas and extreme aspect ratios (> 2.4): {len(pano)}. Each takes a row alone."
         + (" Files: " + ", ".join(r["filename"] for r in pano[:8]) if pano else ""),
         f"- Tiny files (short side < 600 px): {len(tiny)}." + (" Files: " + ", ".join(r["filename"] for r in tiny[:8]) if tiny else ""),
         f"- Videos over 60 s: {len(long_v)}. Window renders around them."
         + (" Files: " + ", ".join(f"{r['filename']} ({fnum(r['duration_s']):.0f} s)" for r in long_v[:8]) if long_v else ""), "",
         "## Uncertainties", ""]
    if unprobed:
        h.append(f"- {len(unprobed)} moving file(s) have no duration, frame rate or codec in the index (ffprobe was not "
                 f"available when the index ran). The build must probe them before preparation.")
    if open_flags:
        h.append("- Open validation flags on files in the set: " + ", ".join(f"{k} {v}" for k, v in sorted(open_flags.items()))
                 + ". See `index/flags.csv`; none was resolved by a witness.")
    undated = sum(1 for r in media_rows if not r["precision"])
    if undated:
        h.append(f"- {undated} file(s) in the set have no settled date and will sort by year 0.")
    if not people:
        h.append("- No identify data was available; the people gate was not applied to this set.")
    if len(h) and h[-1] == "":
        h.append("- None recorded beyond the flags above.")
    h += ["", "## Verifying the transfer", "",
          f"- File count in `media/`: {len(media_rows)}; byte total: {total_bytes} ({_human(total_bytes)}).",
          "- Every row's `media_id` is the SHA-256 of the file; recompute and compare after any move.",
          "- Every `companion` names a file in `media/` and the link is symmetric; every line of `features.txt` is a still.", ""]
    write_atomic(P.handoff / "HANDOFF.md", "\n".join(h))

    say(f"handoff: media.csv {len(media_rows)} rows ({dict(sorted(types.items()))}), features.txt {len(featured)}, "
        f"cut-list.csv {len(cuts)} ({dict(sorted(reasons.items()))})")
    say(f"handoff: wrote inventory.md and HANDOFF.md; changes.log {'kept' if log.stat().st_size else 'ready (empty)'}; folder {P.handoff}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
