"""validate: the gates from references/03-validation-gates.md, run over index/items.csv.

Writes index/flags.csv and never rewrites a date, a pairing or anything else in the index.
Every finding is one row: which file, which gate, how severe, the evidence, and what to do.
Severity ``block`` means a stage that depends on the value must not use it until the owner
resolves the flag; ``warn`` goes to the contact sheets.

Gates (names are the ``gate`` column):

    stem-collision            two different files share a filename stem and are not a verified pair;
                              nothing may be joined, paired or dated across them without a witness
    era-implausible           the settled date is one the file could not have (HEIC/HEVC before 2017,
                              a Live Photo before 2015-09, a phone model before its release year)
    prefix-exif-disagree      the settled date disagrees with the file's own intact EXIF or sidecar time
                              (block until a specific witness is named in date_witness)
    pair-unverified           a still and a video share a stem but the pair gate did not pass all three
                              tests (video 1-4 s long, capture times within 2 s, and the closest of the
                              frames sampled across the clip within 16 bits of a 64-bit hash of the still)
    title-collision           the Takeout sidecar this file came from shares its title with another in
                              the same folder (block when a date was taken from it)
    owner-provisional         the date came from the owner's memory and no second source agrees yet
    exif-modified             the date came from the EXIF modification stamp (DateTime, tag 306), which is
                              the edit or scan date; the file carries no usable capture time
    content-match-unrecorded  date_source says content-match but no method and distance are recorded
    undated                   no date at all
    bogus-timestamp           a 1970 or 0000 timestamp in the metadata (a zeroed clock, not a date)

Re-running is safe: flags that still apply keep their ``resolved_by``/``resolved_on``, flags that
no longer apply are dropped. ``--resolve <media_id> <gate> --by "<witness>"`` marks a flag resolved
and appends a dated line to the project's BRIEF.md changelog.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import STILL_EXT, VIDEO_EXT, project, write_atomic, say  # noqa: E402

FLAG_COLUMNS = ["media_id", "filename", "gate", "severity", "detail", "suggested_action", "resolved_by", "resolved_on"]

HEIC_EXT = {".heic", ".heif"}
HEVC_CODECS = {"hevc", "h265", "hvc1", "hev1"}
LIVE_TYPES = {"livephoto-still", "livephoto-video"}

# Public release years of phone camera models, by the model string a camera writes into EXIF.
# Used only when camera_model matches exactly (case-insensitive). A file cannot predate its camera.
CAMERA_FIRST_YEAR = {
    "iphone": 2007, "iphone 3g": 2008, "iphone 3gs": 2009, "iphone 4": 2010, "iphone 4s": 2011,
    "iphone 5": 2012, "iphone 5c": 2013, "iphone 5s": 2013, "iphone 6": 2014, "iphone 6 plus": 2014,
    "iphone 6s": 2015, "iphone 6s plus": 2015, "iphone se": 2016, "iphone 7": 2016, "iphone 7 plus": 2016,
    "iphone 8": 2017, "iphone 8 plus": 2017, "iphone x": 2017, "iphone xr": 2018, "iphone xs": 2018,
    "iphone xs max": 2018, "iphone 11": 2019, "iphone 11 pro": 2019, "iphone 11 pro max": 2019,
    "iphone se (2nd generation)": 2020, "iphone 12": 2020, "iphone 12 mini": 2020, "iphone 12 pro": 2020,
    "iphone 12 pro max": 2020, "iphone 13": 2021, "iphone 13 mini": 2021, "iphone 13 pro": 2021,
    "iphone 13 pro max": 2021, "iphone se (3rd generation)": 2022, "iphone 14": 2022, "iphone 14 plus": 2022,
    "iphone 14 pro": 2022, "iphone 14 pro max": 2022, "iphone 15": 2023, "iphone 15 plus": 2023,
    "iphone 15 pro": 2023, "iphone 15 pro max": 2023, "iphone 16": 2024, "iphone 16 plus": 2024,
    "iphone 16 pro": 2024, "iphone 16 pro max": 2024, "iphone 16e": 2025, "iphone 17": 2025,
    "iphone 17 pro": 2025, "iphone 17 pro max": 2025, "iphone air": 2025,
    "pixel": 2016, "pixel xl": 2016, "pixel 2": 2017, "pixel 2 xl": 2017, "pixel 3": 2018, "pixel 3 xl": 2018,
    "pixel 3a": 2019, "pixel 4": 2019, "pixel 4a": 2020, "pixel 5": 2020, "pixel 6": 2021, "pixel 6 pro": 2021,
    "pixel 7": 2022, "pixel 7 pro": 2022, "pixel 8": 2023, "pixel 8 pro": 2023, "pixel 9": 2024, "pixel 9 pro": 2024,
    "pixel 10": 2025, "pixel 10 pro": 2025,
}
HEIC_FIRST_YEAR = 2017
LIVE_PHOTO_FIRST = (2015, 9)


# ---------------------------------------------------------------- helpers

def ext_of(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def stem_of(name: str) -> str:
    return os.path.splitext(name)[0].strip().lower()


def year_of(date: str) -> int | None:
    if not date or len(date) < 4 or not date[:4].isdigit():
        return None
    y = int(date[:4])
    return y if y > 0 else None


def parse_stamp(raw: str) -> tuple[int, int, int] | None:
    """(y, m, d) from an EXIF 'YYYY:MM:DD HH:MM:SS', an ISO date-time, or a bare date. None if unparseable."""
    if not raw:
        return None
    m = re.match(r"\s*(\d{4})[:\-](\d{2})[:\-](\d{2})", raw)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if y == 0:
        return None
    return y, mo, d


def is_bogus(raw: str) -> bool:
    if not raw:
        return False
    s = raw.strip()
    return s.startswith("1970") or s.startswith("0000") or s.startswith("1904-01-01") or s.startswith("1904:01:01")


def disagrees(settled: str, precision: str, stamp: tuple[int, int, int]) -> bool:
    """True when the settled date (at its precision) differs from an intact metadata stamp."""
    y, mo, d = stamp
    if precision == "year":
        return settled[:4] != f"{y:04d}"
    if precision == "month":
        return settled[:7] != f"{y:04d}-{mo:02d}"
    return settled[:10] != f"{y:04d}-{mo:02d}-{d:02d}"


def has_method_and_distance(witness: str) -> bool:
    w = witness.lower()
    method = re.search(r"\b(phash|perceptual|hash|first[- ]frame|frame|pixel|sha-?256|dhash|ahash)\b", w)
    distance = re.search(r"\b(distance|bits?|hamming)\b.*?\d+|\d+\s*(bits?|/\s*256)", w)
    return bool(method and distance)


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- the gates

def run_gates(items: list[dict], sidecars: list[dict]) -> list[dict]:
    flags: list[dict] = []

    def flag(r, gate, severity, detail, action):
        flags.append({"media_id": r["media_id"], "filename": r["filename"], "gate": gate, "severity": severity,
                      "detail": detail, "suggested_action": action, "resolved_by": "", "resolved_on": ""})

    live = [r for r in items if r.get("location", "work") in ("work", "")]  # quarantined rows are already out
    by_id = {r["media_id"]: r for r in items}

    # Gate 1 / 4: stems. Group by the original stem across the live rows.
    by_stem: dict[str, list[dict]] = defaultdict(list)
    for r in live:
        if r.get("duplicate_of"):
            continue
        key = r.get("pair_stem") or stem_of(r.get("original_name") or r["filename"])
        by_stem[key].append(r)
    for stem, group in by_stem.items():
        if len(group) < 2:
            continue
        stills = [r for r in group if ext_of(r["filename"]) in STILL_EXT]
        videos = [r for r in group if ext_of(r["filename"]) in VIDEO_EXT]
        verified = {r["media_id"] for r in group if r.get("companion")}
        # a verified pair links exactly one still and one video, symmetrically
        pair_ok = (len(group) == 2 and len(stills) == 1 and len(videos) == 1 and len(verified) == 2
                   and stills[0].get("companion") == videos[0]["filename"] and videos[0].get("companion") == stills[0]["filename"])
        if pair_ok:
            continue
        if len(group) == 2 and len(stills) == 1 and len(videos) == 1:
            s, v = stills[0], videos[0]
            ev = []
            dur = v.get("duration_s") or ""
            dur_ok = bool(dur) and 1.0 <= float(dur) <= 4.0
            ev.append(f"video {dur or '?'} s" + ("" if dur_ok else " (needs 1-4 s)"))
            dt = v.get("pair_dt_s") or s.get("pair_dt_s") or ""
            dt_ok = bool(dt) and abs(float(dt)) <= 2.0
            ev.append((f"capture times {dt} s apart" if dt else "capture times unknown") + ("" if dt_ok else " (needs within 2 s)"))
            fd = v.get("pair_frame_dist") or s.get("pair_frame_dist") or ""
            # index computes the frame distance last and only when the duration and time gates have passed, so a
            # blank one is almost never about ffmpeg; the video's blank probe columns are what says the tools were missing.
            # With them filled and both gates passed there are three ways to reach a blank distance and no way to tell them
            # apart from here: a clip ffmpeg cannot decode, a still with no perceptual hash, and an index --dry-run
            unprobed = not any((v.get(c) or "").strip() for c in ("duration_s", "fps", "video_codec", "container_time"))
            no_tool = "ffmpeg was not available when index ran"
            not_run = "ffmpeg could not read the clip, or the still has no hash, or index ran as a dry run"
            if fd:
                why = ""
                ev.append(f"closest sampled frame {fd} bits of 64 from the still"
                          + ("" if int(float(fd)) <= 16 else " (needs at most 16)"))   # index.PAIR_FRAME_BITS
            else:
                why = (no_tool if unprobed else                             # no duration or codec either: no tools
                       "the duration gate failed first" if not dur_ok else
                       "the time gate failed first" if not dt_ok else not_run)
                ev.append(f"closest sampled frame not computed ({why})")
            if why == no_tool:
                action = "re-run index with ffmpeg available; the frame test is the third witness and it never ran"
            elif why == not_run:
                action = "re-run index; if the pair stays unverified, treat them as two items or declare the pair with a witness"
            elif not dur_ok:
                action = "treat them as two separate items: a Live Photo's clip runs 1 to 4 s"
            elif not dt_ok:
                action = (f"the still's capture time and the clip's container time disagree by {abs(float(dt)):.0f} s; container "
                          "times are UTC and are converted with [project] timezone in config.toml, so check that zone first, "
                          "then declare the pair with a witness if they belong together" if dt else
                          "one of the two carries no capture time, so there is nothing to compare; declare the pair with a "
                          "witness if they belong together")
            else:
                action = "treat them as two separate items: the closest sampled frame is not the still's scene"
            for r in (s, v):
                flag(r, "pair-unverified", "warn", "stem shared with " + (v if r is s else s)["filename"] + "; " + "; ".join(ev),
                     action)
            continue
        names = ", ".join(sorted(x["filename"] for x in group))
        for r in group:
            flag(r, "stem-collision", "warn", f"{len(group)} files share the stem '{stem}': {names}",
                 "never join, pair or inherit a date across these by stem; a join needs timestamps within seconds, the same camera, or pixel similarity")

    for r in live:
        name = r["filename"]
        ext = ext_of(name)
        date = (r.get("date") or "").strip()
        prec = (r.get("precision") or "").strip()
        src = (r.get("date_source") or "").strip()
        witness = (r.get("date_witness") or "").strip()
        year = year_of(date)
        exif_raw = (r.get("exif_datetime_original") or "").strip()
        cont_raw = (r.get("container_time") or "").strip()
        side_raw = (r.get("sidecar_time") or "").strip()

        # undated / bogus
        if not date or year is None:
            flag(r, "undated", "warn", f"no settled date (date_source='{src}')",
                 "find a witness: a sidecar, a matched original, or the owner's dated recollection marked provisional")
        for label, raw in (("exif", exif_raw), ("container", cont_raw), ("sidecar", side_raw)):
            if is_bogus(raw):
                sev = "block" if (date and (date.startswith("1970") or date.startswith("0000"))) else "warn"
                flag(r, "bogus-timestamp", sev, f"{label} time is '{raw}', a zeroed clock",
                     "ignore this timestamp; it is not a date" if sev == "warn" else "the settled date came from a zeroed clock; remove it and re-run index")

        # Gate 2: era plausibility
        if year is not None:
            codec = (r.get("video_codec") or "").strip().lower()
            if ext in HEIC_EXT and year < HEIC_FIRST_YEAR:
                flag(r, "era-implausible", "block", f"HEIC file dated {date}; HEIC did not exist before {HEIC_FIRST_YEAR}",
                     "the date is wrong or the file is a later re-export; find the witness before this date is used")
            if codec in HEVC_CODECS and year < HEIC_FIRST_YEAR:
                flag(r, "era-implausible", "block", f"HEVC video dated {date}; HEVC capture did not exist before {HEIC_FIRST_YEAR}",
                     "the date is wrong or the file is a later re-encode; find the witness before this date is used")
            if r.get("type") in LIVE_TYPES:
                mo = int(date[5:7]) if prec in ("day", "month") and date[5:7].isdigit() and date[5:7] != "00" else None
                before = year < LIVE_PHOTO_FIRST[0] or (year == LIVE_PHOTO_FIRST[0] and mo is not None and mo < LIVE_PHOTO_FIRST[1])
                if before:
                    flag(r, "era-implausible", "block", f"Live Photo dated {date}; Live Photos began in {LIVE_PHOTO_FIRST[0]}-{LIVE_PHOTO_FIRST[1]:02d}",
                         "the date or the pairing is wrong; check both before this date is used")
            model = (r.get("camera_model") or "").strip().lower()
            if model in CAMERA_FIRST_YEAR and year < CAMERA_FIRST_YEAR[model]:
                flag(r, "era-implausible", "block", f"camera '{r.get('camera_model')}' was released in {CAMERA_FIRST_YEAR[model]} but the file is dated {date}",
                     "the date is wrong; the camera is a hard witness against it")

        # Gate 3: prefix versus intact metadata. A file dated from the EXIF modification stamp has no capture-class
        # EXIF time that parses, so it cannot disagree here; the exif-modified gate below is its flag.
        if date and year is not None and prec:
            exif_stamp = parse_stamp(exif_raw) if not is_bogus(exif_raw) else None
            side_stamp = parse_stamp(side_raw) if not is_bogus(side_raw) else None
            if src == "sidecar" and exif_stamp and disagrees(date, prec, exif_stamp):
                flag(r, "prefix-exif-disagree", "warn", f"sidecar date {date} but EXIF DateTimeOriginal is '{exif_raw}'; two intact sources disagree",
                     "check which is right on the sheet; a sidecar can carry an upload time instead of a capture time")
            elif src in ("prior", "content-match", "owner", "visual"):
                against = []
                if exif_stamp and disagrees(date, prec, exif_stamp):
                    against.append(f"EXIF DateTimeOriginal '{exif_raw}'")
                if side_stamp and disagrees(date, prec, side_stamp):
                    against.append(f"sidecar time '{side_raw}'")
                if against:
                    sev = "block" if not witness else "warn"
                    flag(r, "prefix-exif-disagree", sev,
                         f"settled date {date} ({src}) disagrees with the file's own {' and '.join(against)}" + (f"; witness: {witness}" if witness else "; no witness named"),
                         "name the witness (the matched file, the method, the distance) or let the file's own metadata stand" if sev == "block"
                         else "review on the sheet; the witness is on record")

        # Gate 6: owner memory is provisional
        if src == "owner":
            flag(r, "owner-provisional", "warn", f"date {date} came from the owner's memory" + (f"; witness: {witness}" if witness else ""),
                 "keep provisional until a second source agrees (GPS, a sidecar, a matched file); then resolve this flag naming it")

        # The EXIF modification stamp dated this file: it is the edit or scan date until the owner says otherwise
        if src == "exif-modified":
            flag(r, "exif-modified", "warn",
                 f"dated {date} by the EXIF modification stamp (DateTime, tag 306); the file carries no usable "
                 "DateTimeOriginal or DateTimeDigitized, so this is likely the edit or scan date",
                 "confirm it on the contact sheet, or declare the date with a witness (validate --resolve)")

        # Gate 7: "content match" means a match ran
        if src == "content-match" and not has_method_and_distance(witness):
            flag(r, "content-match-unrecorded", "block", f"date_source is content-match but date_witness is '{witness or '(blank)'}'",
                 "record the method and the distance (e.g. 'phash to <file>, distance 6 bits') or change date_source to what actually happened")

    # Gate 5: Takeout title collisions
    if sidecars:
        by_member = {}
        for s in sidecars:
            if (s.get("title_collision") or "").lower() == "yes" and s.get("media_member"):
                by_member[(s.get("zip", ""), s["media_member"])] = s
        if by_member:
            for r in live:
                sp = r.get("source_path") or ""
                if "!" not in sp:
                    continue
                z, member = sp.split("!", 1)
                s = by_member.get((z, member))
                if not s:
                    continue
                took_date = (r.get("date_source") == "sidecar")
                flag(r, "title-collision", "block" if took_date else "warn",
                     f"sidecar '{s.get('title')}' in folder '{s.get('folder')}' shares its title with another sidecar there" + ("; the settled date was taken from it" if took_date else ""),
                     "quarantine this file from automatic date and pairing decisions; confirm which sidecar belongs to it by member path and timestamps")
    return flags


# ---------------------------------------------------------------- main

def merge_resolutions(new: list[dict], old: list[dict]) -> list[dict]:
    prior = {(f["media_id"], f["gate"]): f for f in old}
    for f in new:
        p = prior.get((f["media_id"], f["gate"]))
        if p and p.get("resolved_by"):
            f["resolved_by"] = p["resolved_by"]
            f["resolved_on"] = p.get("resolved_on", "")
    order = {"block": 0, "warn": 1}
    new.sort(key=lambda f: (order.get(f["severity"], 2), f["filename"], f["gate"]))
    return new


def write_flags(path, flags: list[dict]) -> None:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FLAG_COLUMNS, lineterminator="\n")
    w.writeheader()
    for f in flags:
        w.writerow({k: f.get(k, "") for k in FLAG_COLUMNS})
    write_atomic(path, buf.getvalue())


def resolve(P, flags_path, media_id: str, gate: str, by: str, dry: bool) -> int:
    if not flags_path.is_file():
        say(f"validate: {flags_path} does not exist; run validate first")
        return 1
    flags = read_csv(flags_path)
    hit = [f for f in flags if f["media_id"] == media_id and f["gate"] == gate]
    if not hit:
        say(f"validate: no flag {gate} on media_id {media_id}")
        return 1
    today = _dt.date.today().isoformat()
    for f in hit:
        f["resolved_by"] = by
        f["resolved_on"] = today
    line = f"| {today} | Flag `{gate}` on `{hit[0]['filename']}` resolved: {by} | the flag | owner |"
    brief = P.root / "BRIEF.md"
    if dry:
        say("dry-run: would mark resolved and append to BRIEF.md:", line)
        return 0
    write_flags(flags_path, flags)
    if brief.is_file():
        with open(brief, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
        say(f"resolved {gate} on {hit[0]['filename']}; changelog line appended to {brief}")
    else:
        say(f"resolved {gate} on {hit[0]['filename']}; no BRIEF.md in the project, add this line to the brief's changelog:")
        say(line)
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="validate", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", help="project folder (default: SLIDESHOW_PROJECT or a config.toml above the cwd)")
    ap.add_argument("--dry-run", action="store_true", help="print the counts, write nothing")
    ap.add_argument("--force", action="store_true", help="drop recorded resolutions and re-flag from scratch")
    ap.add_argument("--resolve", nargs=2, metavar=("MEDIA_ID", "GATE"), help="mark one flag resolved")
    ap.add_argument("--by", default="", help="the witness sentence for --resolve")
    ap.add_argument("--list", action="store_true", help="print the current flags and exit")
    a = ap.parse_args(argv)

    P = project()
    items_path = P.index / "items.csv"
    flags_path = P.index / "flags.csv"
    sidecar_path = P.index / "takeout-sidecars.csv"

    if a.resolve:
        if not a.by.strip():
            say("validate: --resolve needs --by \"<the witness sentence>\"")
            return 2
        return resolve(P, flags_path, a.resolve[0], a.resolve[1], a.by.strip(), a.dry_run)

    if a.list:
        if not flags_path.is_file():
            say("no flags.csv yet")
            return 0
        for f in read_csv(flags_path):
            mark = "resolved" if f.get("resolved_by") else f["severity"]
            say(f"{mark:8s} {f['gate']:24s} {f['filename']}  {f['detail']}")
        return 0

    if not items_path.is_file():
        say(f"validate: {items_path} does not exist; run the index stage first")
        return 1
    items = read_csv(items_path)
    sidecars = read_csv(sidecar_path) if sidecar_path.is_file() else []
    old = [] if a.force or not flags_path.is_file() else read_csv(flags_path)

    flags = merge_resolutions(run_gates(items, sidecars), old)

    by_gate = defaultdict(lambda: [0, 0, 0])  # block, warn, resolved
    for f in flags:
        b = by_gate[f["gate"]]
        if f.get("resolved_by"):
            b[2] += 1
        elif f["severity"] == "block":
            b[0] += 1
        else:
            b[1] += 1
    say(f"validate: {len(items)} items, {len(sidecars)} sidecars, {len(flags)} flags")
    for gate in sorted(by_gate):
        b = by_gate[gate]
        say(f"  {gate:26s} block {b[0]:4d}  warn {b[1]:4d}  resolved {b[2]:4d}")
    open_blocks = sum(1 for f in flags if f["severity"] == "block" and not f.get("resolved_by"))
    dropped = len({(f["media_id"], f["gate"]) for f in old} - {(f["media_id"], f["gate"]) for f in flags})
    if dropped:
        say(f"  {dropped} earlier flag(s) no longer apply and were dropped")
    if a.dry_run:
        say("dry-run: flags.csv not written")
    else:
        write_flags(flags_path, flags)
        say(f"wrote {flags_path}")
    if open_blocks:
        say(f"{open_blocks} blocking flag(s) are unresolved; the select stage excludes those files with reason 'flagged' until they are resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
