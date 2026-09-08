"""index: one row per file in work/ with the settled date, displayed dimensions, hashes, sharpness,
Live Photo pairs, bursts, exact duplicates and GPS -> index/items.csv.

    python curate/run.py index [--dry-run] [--force] [--workers N]

Date ladder (references/01 §2), most trusted first: Takeout photoTakenTime from the sidecar index
(unless the sidecar is title-collided) > EXIF DateTimeOriginal > video container creation time in the
project's timezone > owner priors only when config [priors] turns them on > nothing. File
modification time is never used, and no date is ever inherited by filename stem alone.

Joins need a second witness (references/03 gate 1, 4): a Live Photo pair is written only when the
video is 1-4 s long, its capture time is within 2 s of the still's, and its first frame is within 20
bits of the still's perceptual hash. Otherwise both halves stay separate items with pair_stem set,
and the validate stage flags them.

Quarantine, never delete: exact duplicates go to work/_duplicates/, burst extras to
work/_burst-duplicates/. Working copies are renamed to YYYY-MM-DD_<original name> (zero-filled
unknown parts); items.csv, not the name, is the record. Probe results are cached per media_id in
index/_probe-cache.jsonl so reruns only look at new files.
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import itertools
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import project, media_id as sha256_of, write_atomic, say, date_prefix, STILL_EXT, VIDEO_EXT, GIF_EXT, JUNK_FILES  # noqa: E402
from stages import _probe  # noqa: E402

ITEM_COLUMNS = ["media_id", "filename", "original_name", "source_kind", "source_path", "location", "type",
                "companion", "width", "height", "duration_s", "fps", "hdr", "video_codec", "has_audio", "bytes",
                "date", "precision", "date_source", "date_witness", "exif_datetime_original", "container_time",
                "sidecar_time", "camera_make", "camera_model", "phash", "sharpness", "lat", "lon", "burst_group",
                "duplicate_of", "pair_stem", "pair_dt_s", "pair_frame_dist"]

LOCATIONS = ["work", "work/_burst-duplicates", "work/_duplicates", "work/_quarantine"]
PAIR_DUR = (1.0, 4.0)
PAIR_DT_S = 2.0
PAIR_FRAME_BITS = 20
BURST_WINDOW_S = 3.0
BURST_BITS = 12
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_")
NORM_STEM = re.compile(r"(?:\s*\(\d+\)|\s+copy|[_-]original)+$", re.I)
CAL_FOLDER = re.compile(r"(?<!\d)(\d{4})\s*[- _]?\s*calendar", re.I)
YEAR_TOKEN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
MONTHS = {m.lower(): i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTH_TOKEN = re.compile(r"(?<![a-z])(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")(?![a-z])", re.I)


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, buf.getvalue())


def kind_of_name(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in STILL_EXT:
        return "still"
    if ext in VIDEO_EXT:
        return "video"
    if ext in GIF_EXT:
        return "gif"
    return "other"


def parse_dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ---------------------------------------------------------------- probe cache

def load_cache(path: Path) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if path.is_file():
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    cache[d["media_id"]] = d
                except Exception:
                    continue
    return cache


def probe_one(mid: str, path: str, kind: str, ffprobe: str | None, tz: str) -> dict:
    d: dict = {"media_id": mid, "kind": kind}
    try:
        if kind in ("still", "gif"):
            d.update(_probe.probe_still(path))
        elif kind == "video":
            if ffprobe:
                d.update(_probe.probe_video(path, ffprobe, tz))
            else:
                d["error"] = "ffprobe unavailable"
                d["unprobed"] = True
        else:
            d["kind"] = "other"
    except Exception as e:
        d["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return d


# ---------------------------------------------------------------- dates

def settle_date(row: dict, pr: dict, sidecar: dict | None, priors: dict, tz: ZoneInfo) -> None:
    """Fill date, precision, date_source, date_witness and the informational time columns."""
    row["exif_datetime_original"] = pr.get("exif_raw") or ""
    row["container_time"] = pr.get("container_raw") or ""
    if sidecar and sidecar.get("photo_taken_ts"):
        try:
            ts = int(sidecar["photo_taken_ts"])
            row["sidecar_time"] = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            row["sidecar_time"] = ""
    if row.get("sidecar_time") and sidecar.get("title_collision") != "yes":
        row.update(date=row["sidecar_time"][:10], precision="day", date_source="sidecar", date_witness="")
        return
    if pr.get("exif_dt"):
        row.update(date=pr["exif_dt"][:10], precision="day", date_source="exif", date_witness="")
        return
    if pr.get("container_dt"):
        row.update(date=pr["container_dt"][:10], precision="day", date_source="container",
                   date_witness=f"video container creation time {row['container_time']} read in {tz.key}")
        return
    # owner priors, only when the config turns them on
    year = month = None
    why = []
    src_path = (row.get("source_path") or "").replace("\\", "/")
    folders = src_path.split("!")[-1].split("/")[:-1]
    if priors.get("calendar_folder_year_rule"):
        for f in folders:
            m = CAL_FOLDER.search(f)
            if m:
                year = int(m.group(1)) + int(priors.get("calendar_folder_year_offset", -1))
                why.append(f"owner prior: folder '{f}' is a calendar printed for {m.group(1)}, photos are from {year}")
                break
    if priors.get("filename_month_rule"):
        name = os.path.splitext(row["original_name"])[0]
        m = MONTH_TOKEN.search(name)
        if m:
            month = MONTHS[m.group(1).lower()]
            if year is None:
                y = YEAR_TOKEN.search(name) or next((YEAR_TOKEN.search(f) for f in folders if YEAR_TOKEN.search(f)), None)
                if y:
                    year = int(y.group(1))
                    why.append(f"owner prior: year {year} named in the path")
            why.append(f"owner prior: month '{m.group(1)}' named in the filename")
    if year is not None:
        if month is not None:
            row.update(date=f"{year:04d}-{month:02d}-00", precision="month")
        else:
            row.update(date=f"{year:04d}-00-00", precision="year")
        row.update(date_source="prior", date_witness="; ".join(why))
        return
    row.update(date="", precision="", date_source="", date_witness="")


def capture_dt(row: dict, pr: dict):
    """The most trusted full timestamp for pairing and bursts (sidecar > exif > container)."""
    if row.get("sidecar_time") and row.get("date_source") == "sidecar":
        return parse_dt(row["sidecar_time"])
    return parse_dt(pr.get("exif_dt")) or parse_dt(pr.get("container_dt")) or parse_dt(row.get("sidecar_time"))


# ---------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="index", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="probe every file again, ignoring the cache")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    P = project()
    dry = a.dry_run
    t0 = time.time()
    try:
        tz = ZoneInfo(P.timezone)
    except Exception:
        raise SystemExit(f"index: config [project] timezone {P.timezone!r} is not a known IANA zone "
                         f"(on Windows the zone database comes from the tzdata package; it is in requirements.txt)")
    ffprobe = _probe.find_tool(P.tool("ffprobe"))
    ffmpeg = _probe.find_tool(P.tool("ffmpeg"))
    items_csv = P.index / "items.csv"
    cache_path = P.index / "_probe-cache.jsonl"
    if not P.work.is_dir():
        raise SystemExit(f"index: {P.work} does not exist; run ingest first")

    ingest_rows = read_csv(P.index / "ingest.csv")
    ingest_by_name = {r["filename"]: r for r in ingest_rows}
    sidecars_by_member = {r["media_member"]: r for r in read_csv(P.index / "takeout-sidecars.csv") if r.get("media_member")}
    prev_by_name = {r["filename"]: r for r in read_csv(items_csv)}
    cache = {} if a.force else load_cache(cache_path)

    # ---- files on disk, identity
    files: list[dict] = []
    for loc in LOCATIONS:
        folder = P.work / loc[len("work"):].lstrip("/")
        if not folder.is_dir():
            continue
        for n in sorted(os.listdir(folder)):
            p = folder / n
            if not p.is_file() or n.lower() in JUNK_FILES or n.startswith("."):
                continue
            files.append({"filename": n, "location": loc, "path": str(p), "bytes": p.stat().st_size})
    hashed = 0
    for f in files:
        prev = prev_by_name.get(f["filename"])
        ing = ingest_by_name.get(f["filename"])
        if prev and prev.get("media_id"):
            f["media_id"] = prev["media_id"]
            f["original_name"] = prev.get("original_name") or f["filename"]
            f["source_kind"], f["source_path"] = prev.get("source_kind", ""), prev.get("source_path", "")
        elif ing and ing.get("media_id"):
            f["media_id"] = ing["media_id"]
            f["original_name"] = f["filename"]
            f["source_kind"], f["source_path"] = ing.get("source_kind", ""), ing.get("source_path", "")
        else:
            f["media_id"] = sha256_of(f["path"])
            hashed += 1
            f["original_name"] = DATE_PREFIX_RE.sub("", f["filename"]) if DATE_PREFIX_RE.match(f["filename"]) else f["filename"]
            f["source_kind"], f["source_path"] = "", ""
        if not f["source_path"]:
            ing = ingest_by_name.get(f["original_name"])
            if ing:
                f["source_kind"], f["source_path"] = ing.get("source_kind", ""), ing.get("source_path", "")
        f["kind"] = kind_of_name(f["original_name"])
    say(f"index: {len(files)} files in work/ ({hashed} hashed afresh), {len(cache)} probe results cached")

    # ---- probe
    todo = [f for f in files if f["media_id"] not in cache and f["kind"] != "other"]
    if todo:
        if dry:
            say(f"[dry run] would probe {len(todo)} files; dates and pairs below are unknown until that runs")
        else:
            say(f"probing {len(todo)} files with {a.workers} workers")
            with open(cache_path, "a" if not a.force else "w", encoding="utf-8") as cf, ThreadPoolExecutor(a.workers) as ex:
                for i, d in enumerate(ex.map(lambda f: probe_one(f["media_id"], f["path"], f["kind"], ffprobe, P.timezone), todo), 1):
                    cache[d["media_id"]] = d
                    if not d.get("unprobed"):
                        cf.write(json.dumps(d) + "\n")
                    if i % 100 == 0:
                        cf.flush()
                        say(f"  {i}/{len(todo)} probed, {time.time() - t0:.0f}s")
    unprobed_videos = [f for f in files if f["kind"] == "video" and (f["media_id"] not in cache or cache[f["media_id"]].get("unprobed"))]
    errors = [(f["filename"], cache[f["media_id"]]["error"]) for f in files if f["media_id"] in cache and cache[f["media_id"]].get("error") and not cache[f["media_id"]].get("unprobed")]

    # ---- rows
    rows: list[dict] = []
    priors = P.priors()
    for f in files:
        pr = cache.get(f["media_id"], {})
        kind = f["kind"]
        r = {k: "" for k in ITEM_COLUMNS}
        r.update(media_id=f["media_id"], filename=f["filename"], original_name=f["original_name"],
                 source_kind=f["source_kind"], source_path=f["source_path"], location=f["location"], bytes=f["bytes"])
        r["type"] = {"still": "still", "video": "video", "gif": "animated-gif", "other": "other"}[kind]
        if pr.get("w"):
            r["width"], r["height"] = pr["w"], pr["h"]
        if kind == "video" and pr.get("dur") is not None and not pr.get("unprobed"):
            r["duration_s"] = pr.get("dur", "")
            r["fps"] = pr.get("fps") if pr.get("fps") is not None else ""
            r["hdr"] = "yes" if pr.get("hdr") else "no"
            r["video_codec"] = pr.get("codec", "")
            r["has_audio"] = "yes" if pr.get("audio") else "no"
        elif kind == "gif":
            r["duration_s"] = pr.get("dur", "")
        r["camera_make"], r["camera_model"] = pr.get("make", ""), pr.get("model", "")
        r["phash"], r["sharpness"] = pr.get("phash", "") or "", pr.get("sharp", "") if pr.get("sharp") is not None else ""
        member = f["source_path"].split("!", 1)[1] if f["source_kind"] == "takeout" and "!" in f["source_path"] else None
        sc = sidecars_by_member.get(member) if member else None
        if sc and sc.get("lat"):
            r["lat"], r["lon"] = sc["lat"], sc["lon"]
        elif pr.get("lat") is not None:
            r["lat"], r["lon"] = pr["lat"], pr["lon"]
        settle_date(r, pr, sc, priors, tz)
        r["_dt"] = capture_dt(r, pr)
        r["_pr"] = pr
        r["_path"] = f["path"]
        rows.append(r)

    # ---- exact duplicates (same bytes): the first copy in work/ keeps its place
    by_id = collections.defaultdict(list)
    for r in rows:
        by_id[r["media_id"]].append(r)
    moves: list[tuple[dict, str]] = []  # (row, new location)
    n_dups = 0
    for mid, rs in by_id.items():
        if len(rs) < 2:
            continue
        # the copy ingested first keeps its place (ingest noted the later ones as duplicate-of)
        rs.sort(key=lambda r: (LOCATIONS.index(r["location"]),
                               1 if (ingest_by_name.get(r["original_name"], {}).get("note") or "").startswith("duplicate-of") else 0,
                               r["filename"]))
        keeper = rs[0]
        for r in rs[1:]:
            r["duplicate_of"] = keeper["media_id"]
            if r["location"] == "work":
                moves.append((r, "work/_duplicates"))
            n_dups += 1

    def active(r):
        return r["location"] == "work" and not r["duplicate_of"] and all(m[0] is not r for m in moves)

    # ---- Live Photo pairs: same stem, one still + one video, then the three-part gate
    by_stem = collections.defaultdict(list)
    for r in rows:
        if active(r) and r["type"] in ("still", "video"):
            by_stem[os.path.splitext(r["original_name"])[0].lower()].append(r)
    n_pair_cand = n_pairs = n_frame_skipped = 0
    for stem, rs in by_stem.items():
        stills = [r for r in rs if r["type"] == "still"]
        vids = [r for r in rs if r["type"] == "video"]
        if not (stills and vids):
            continue
        for r in rs:
            r["pair_stem"] = stem
        if len(stills) != 1 or len(vids) != 1:
            continue  # ambiguous by stem alone; validate flags stem-collision
        s, v = stills[0], vids[0]
        n_pair_cand += 1
        vp = v["_pr"]
        if vp.get("unprobed") or vp.get("dur") is None:
            continue
        dur_ok = PAIR_DUR[0] <= float(vp["dur"]) <= PAIR_DUR[1]
        if s["_dt"] and v["_dt"]:
            dt_s = abs((v["_dt"] - s["_dt"]).total_seconds())
            s["pair_dt_s"] = v["pair_dt_s"] = round(dt_s, 1)
        else:
            dt_s = None
        frame_ok = None
        if dur_ok and dt_s is not None and dt_s <= PAIR_DT_S and s["phash"]:
            ff = vp.get("first_frame_phash")
            if ff is None and ffmpeg and not dry:
                ff = _probe.first_frame_phash(v["_path"], ffmpeg) or ""
                vp["first_frame_phash"] = ff
                with open(cache_path, "a", encoding="utf-8") as cf:
                    cf.write(json.dumps(vp) + "\n")
            if ff:
                dist = _probe.hash_distance(s["phash"], ff)
                s["pair_frame_dist"] = v["pair_frame_dist"] = dist
                frame_ok = dist <= PAIR_FRAME_BITS
            elif not ffmpeg:
                n_frame_skipped += 1
        if dur_ok and dt_s is not None and dt_s <= PAIR_DT_S and frame_ok:
            s["companion"], v["companion"] = v["filename"], s["filename"]
            s["type"], v["type"] = "livephoto-still", "livephoto-video"
            v.update(date=s["date"], precision=s["precision"], date_source=s["date_source"],
                     date_witness=f"Live Photo pair with {s['original_name']}: video {vp['dur']:.1f} s, capture times "
                                  f"{dt_s:.1f} s apart, first frame {s['pair_frame_dist']} bits from the still")
            n_pairs += 1

    # ---- bursts among stills: time neighbours or shared normalized stem, phash within 12 bits
    stills = [r for r in rows if active(r) and r["type"] in ("still", "livephoto-still") and r["phash"]]
    cand: set[tuple[int, int]] = set()
    idx = {id(r): i for i, r in enumerate(stills)}
    norm = collections.defaultdict(list)
    for r in stills:
        norm[NORM_STEM.sub("", os.path.splitext(r["original_name"])[0]).strip().lower()].append(r)
    for rs in norm.values():
        for x, y in itertools.combinations(rs, 2):
            cand.add(tuple(sorted((idx[id(x)], idx[id(y)]))))
    timed = sorted((r for r in stills if r["_dt"]), key=lambda r: r["_dt"])
    for i, x in enumerate(timed):
        for y in timed[i + 1:]:
            if (y["_dt"] - x["_dt"]).total_seconds() > BURST_WINDOW_S:
                break
            cand.add(tuple(sorted((idx[id(x)], idx[id(y)]))))
    parent = list(range(len(stills)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    n_linked = 0
    for i, j in cand:
        if _probe.hash_distance(stills[i]["phash"], stills[j]["phash"]) <= BURST_BITS:
            parent[find(i)] = find(j)
            n_linked += 1
    groups = collections.defaultdict(list)
    for i in range(len(stills)):
        groups[find(i)].append(stills[i])
    by_name = {r["filename"]: r for r in rows}
    n_burst_groups = n_burst_moved = 0
    for g in groups.values():
        if len(g) < 2:
            continue
        n_burst_groups += 1
        g.sort(key=lambda r: (1 if r["companion"] else 0, int(r["width"] or 0) * int(r["height"] or 0),
                              float(r["sharpness"] or 0), int(r["bytes"])), reverse=True)
        keeper = g[0]
        for r in g[1:]:
            r["burst_group"] = keeper["media_id"]
            moves.append((r, "work/_burst-duplicates"))
            n_burst_moved += 1
            if r["companion"] and r["companion"] in by_name:
                c = by_name[r["companion"]]
                c["burst_group"] = keeper["media_id"]
                moves.append((c, "work/_burst-duplicates"))

    # ---- renames: the date travels with the file
    renames: list[tuple[dict, str]] = []
    planned_names: dict[tuple[str, str], dict] = {}
    conflicts = 0
    for r in rows:
        r["_new_location"] = next((loc for rr, loc in moves if rr is r), r["location"])
        new = date_prefix(r["date"] or None, r["precision"] or "day") + r["original_name"]
        key = (r["_new_location"], new.lower())
        if key in planned_names:
            conflicts += 1
            say(f"  ! rename conflict in {r['_new_location']}: {r['filename']} and {planned_names[key]['filename']} both want {new}; leaving {r['filename']} as is")
            new = r["filename"]
        planned_names[key] = r
        r["_new_name"] = new
        if new != r["filename"]:
            renames.append((r, new))
    for r in rows:
        if r["companion"]:
            r["companion"] = by_name[r["companion"]]["_new_name"] if r["companion"] in by_name else r["companion"]

    # ---- apply
    say(f"plan: {n_dups} exact duplicates, {n_pair_cand} Live Photo candidates ({n_pairs} verified pairs"
        f"{f', {n_frame_skipped} need ffmpeg for the frame check' if n_frame_skipped else ''}), "
        f"{n_burst_groups} burst groups ({n_burst_moved} extras, {n_linked} links), {len(moves)} moves, {len(renames)} renames")
    if dry:
        for r, loc in moves[:6]:
            say(f"   move {r['filename']} -> {loc}/")
        for r, new in renames[:6]:
            say(f"   rename {r['filename']} -> {new}")
        say("[dry run] nothing written")
        return 0
    moved = renamed = 0
    for r, loc in moves:
        dest_dir = P.work / loc[len("work"):].lstrip("/")
        dest_dir.mkdir(parents=True, exist_ok=True)
        src, dst = Path(r["_path"]), dest_dir / r["filename"]
        if dst.exists():
            say(f"  ! {dst} exists; not moving {r['filename']}")
            r["_new_location"] = r["location"]
            continue
        os.replace(src, dst)
        r["_path"] = str(dst)
        r["location"] = loc
        moved += 1
    for r, new in renames:
        src = Path(r["_path"])
        dst = src.with_name(new)
        if dst.exists():
            say(f"  ! {dst} exists; not renaming {r['filename']}")
            continue
        os.replace(src, dst)
        r["_path"] = str(dst)
        r["filename"] = new
        renamed += 1

    rows.sort(key=lambda r: (LOCATIONS.index(r["location"]), r["date"] or "9999", r["filename"]))
    write_csv(items_csv, rows, ITEM_COLUMNS)

    # ---- counts
    types = collections.Counter(r["type"] for r in rows)
    locs = collections.Counter(r["location"] for r in rows)
    srcs = collections.Counter(r["date_source"] or "undated" for r in rows)
    say(f"index: {len(rows)} rows -> {items_csv} in {time.time() - t0:.0f}s")
    say("  types: " + ", ".join(f"{v} {k}" for k, v in sorted(types.items())))
    say("  locations: " + ", ".join(f"{v} {k}" for k, v in sorted(locs.items())))
    say("  dates by source: " + ", ".join(f"{v} {k}" for k, v in sorted(srcs.items())))
    say(f"  moved {moved}, renamed {renamed}, rename conflicts {conflicts}")
    say(f"accounting: {len(files)} files on disk = {len(rows)} rows, every file once")
    if errors:
        say(f"  ! {len(errors)} files could not be probed (rows kept, columns blank):")
        for n, e in errors[:10]:
            say(f"     {n}: {e}")
    if unprobed_videos:
        say(f"  ! ffprobe not found ({P.tool('ffprobe')!r}): {len(unprobed_videos)} videos have blank duration, fps, codec and "
            f"container time, and no Live Photo pair could be verified. Set [tools] ffprobe in config.toml and rerun index.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
