"""select: build the candidate pool, run the four lenses, seat the cut, choose featured picks.

    python curate/run.py select [--project P] [--dry-run] [--force] [--lens v1|v2|v3|v4]
                                [--include-undated] [--allow-presence-gate]

Reads index/items.csv, index/people.csv and index/flags.csv; writes index/selection.csv,
index/cut-list.csv and index/_select-scores.json (the v4 scores the sheets use for alternates
and replacement pools). Spec: references/04-selection-lenses.md and references/01-stages.md §5.

The cap per year is `[selection] cap_per_year`, or derived from `[show] loop_minutes_target`
and the tile size when that is 0 (`P.cap_plan()`, references/04); it is pro-rated by month for
the partial first and last years of the scope and `[selection.cap_overrides]` replaces single
years last. The stage prints the cap and its arithmetic on one line. A Live Photo pair costs one
slot and is represented by its still; no pick lands within the configured perceptual distance
of one already seated; a bucket with no dissimilar candidate stays short. All four lenses are
computed and written; `[selection] lens` (default v4) decides which one fills `selected`;
`[selection.weights]` and `[selection.featured]` tune the v4 score and the featured gate.

The taste knobs that act here: `[taste] include_videos = false` cuts every video and
`include_gifs = false` every animated GIF with reason `excluded-type`; `live_photos = "still"`
cuts every Live Photo clip the same way and lets its still compete as a plain still;
`mixed_tiles = false` means no featured picks.

The owner's `[show] off_limits` (filenames, media_ids, or a file or folder path) is applied
before any other test and cuts with reason `off-limits`; a Live Photo pair goes together.
`[show] must_include` entries are seated like `[pins] files`, matched by media_id, by the
date-prefixed filename or by the original name; a miss is a printed warning, never silent.
`[family] gate = "none"` skips the people check and says so.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import DATE_PREFIX_LEN, cap_line, fmt_num, project, say  # noqa: E402
from stages._lenses import (CUT_COLS, SELECTION_COLS, STILL_TYPES, choose_featured, inum, km, lens_v1,  # noqa: E402
                            lens_v2, lens_v3, lens_v4, make_candidate, pscore, read_csv, write_csv)

CUT_REASONS = ("off-limits", "over-cap", "no-family", "no-people", "undated", "unsupported", "excluded-type", "superseded",
               "burst", "duplicate", "flagged")
_DATE_PREFIXED = re.compile(r"^\d{4}-\d{2}-\d{2}_")


def _location_reason(loc: str) -> str | None:
    if loc == "work":
        return None
    if loc.endswith("_burst-duplicates"):
        return "burst"
    if loc.endswith("_duplicates"):
        return "duplicate"
    if "superseded" in loc:
        return "superseded"
    return "flagged"  # quarantine and anything else parked by validate


def _name_forms(r: dict) -> set[str]:
    """The lowercased names a config entry may use for a file: its date-prefixed filename, that
    name without the prefix, and the original name it came in with."""
    fname = r["filename"]
    forms = {fname.lower(), (r.get("original_name") or "").lower()}
    if _DATE_PREFIXED.match(fname):
        forms.add(fname[DATE_PREFIX_LEN:].lower())
    forms.discard("")
    return forms


def _excluded_type(t: str, knobs: dict, paired_clip: bool) -> str:
    """What [taste] turned off for a row of this type: 'video', 'animated-gif' or 'livephoto-video', else ''."""
    if t == "video" and not knobs["include_videos"]:
        return "video"
    if t == "animated-gif" and not knobs["include_gifs"]:
        return "animated-gif"
    if paired_clip and knobs["live_photos"] == "still":
        return "livephoto-video"
    return ""


def _anchor_pick(matches: list[dict]) -> dict | None:
    """The first run's rule: prefer stills, then groups of two or more, then the people score."""
    if not matches:
        return None
    s = [c for c in matches if c["type"] in STILL_TYPES] or matches
    grp = [c for c in s if c["known"] and c["n"] >= 2] or s
    return max(grp, key=pscore)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="select", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="rewrite outputs even if they exist (select always recomputes)")
    ap.add_argument("--lens", choices=("v1", "v2", "v3", "v4"), help="override [selection] lens")
    ap.add_argument("--include-undated", action="store_true", help="let undated files compete (they bucket as year 0)")
    ap.add_argument("--allow-presence-gate", action="store_true",
                    help="when the config asks for the family gate but identify has no identities yet, fall back to presence")
    a = ap.parse_args(argv)
    P = project()

    items_path = P.index / "items.csv"
    if not items_path.is_file():
        say(f"select: {items_path} missing; run the index stage first")
        return 2
    items = read_csv(items_path)
    if not items:
        say("select: items.csv is empty")
        return 2
    gate = P.people_gate
    people_path = P.index / "people.csv"
    people = {r["media_id"]: r for r in read_csv(people_path)} if people_path.is_file() else None
    if people is None and gate != "none":
        say("select: WARNING no index/people.csv; the people gate is skipped and every file passes it. Run identify first for a real cut.")
    flags_path = P.index / "flags.csv"
    blocked = set()
    if flags_path.is_file():
        for r in read_csv(flags_path):
            if r.get("severity") == "block" and not (r.get("resolved_by") or "").strip():
                blocked.add(r["media_id"])

    lens = a.lens or str(P.get("selection", "lens", "v4"))
    sim = int(P.get("selection", "diversity_distance", 26))
    frac = float(P.get("selection", "featured_fraction", 1 / 6))
    min_per_year = int(P.get("selection", "featured_min_per_year", 2))
    motion_per_month = int(P.get("selection", "motion_per_month", 1))
    config_warnings: list[str] = []
    knobs = P.taste_knobs(config_warnings)
    plan = P.cap_plan(warnings=config_warnings)
    weights = P.selection_weights(config_warnings)
    rules = P.featured_rules()
    for w in config_warnings:
        say("  !", w)
    caps = P.year_caps(plan)
    overrides = P.cap_overrides()
    lp_still = knobs["live_photos"] == "still"
    no_featured = ""
    if not knobs["mixed_tiles"]:
        frac, no_featured = 0.0, "[taste] mixed_tiles = false"
    elif frac <= 0:
        no_featured = "[selection] featured_fraction = 0"
    if gate == "family":
        have_identity = people is not None and any((r.get("family_present") or "") == "yes" for r in people.values())
        if not have_identity:
            if not a.allow_presence_gate:
                say("select: the config asks for the family gate ([family] gate = \"family\") but people.csv carries no "
                    "family_present values (the identity gate is a later milestone). Re-run with --allow-presence-gate "
                    "to use presence (any person in frame) instead, or set gate = \"people\" in config.toml.")
                return 2
            say("select: family gate requested but no identities available; using the presence gate (--allow-presence-gate)")
            gate = "people"

    byname = {r["filename"]: r for r in items}

    # ---- the owner's off-limits list: cut before any other test; a Live Photo pair goes together
    off_warnings: list[str] = []
    off = P.off_limits(off_warnings)
    for w in off_warnings:
        say("  !", w)
    off_names = {n.lower() for n in off["filenames"]}
    off_ids = {r["media_id"] for r in items if r["media_id"].lower() in off["media_ids"] or _name_forms(r) & off_names}
    for r in items:
        comp = byname.get(r.get("companion") or "")
        if comp is not None and comp["media_id"] in off_ids:
            off_ids.add(r["media_id"])

    reason: dict[str, str] = {}
    candidates: list[dict] = []
    unknown_people = 0
    out_of_scope = 0
    excluded: collections.Counter = collections.Counter()   # excluded-type cuts, by the type the taste turned off
    for r in items:
        mid, t, loc = r["media_id"], r.get("type", ""), r.get("location", "work")
        paired_clip = t == "livephoto-video" and r.get("companion") in byname
        if paired_clip and not lp_still:
            continue  # rides with its still
        if mid in off_ids:
            reason[mid] = "off-limits"
            continue
        lr = _location_reason(loc)
        if lr:
            reason[r["filename"]] = lr  # parked copies may share a media_id with their keeper
            continue
        if t == "other":
            reason[mid] = "unsupported"   # an extension outside common.STILL_EXT / VIDEO_EXT / GIF_EXT
            continue
        off_type = _excluded_type(t, knobs, paired_clip)
        if off_type:
            reason[mid] = "excluded-type"   # [taste] include_videos, include_gifs or live_photos = "still"
            excluded[off_type] += 1
            continue
        if mid in blocked:
            reason[mid] = "flagged"
            continue
        if not (r.get("precision") or "").strip() and not a.include_undated:
            reason[mid] = "undated"
            continue
        year = inum((r.get("date") or "")[:4])
        if year and year not in caps:
            reason[mid] = "over-cap"
            out_of_scope += 1
            continue
        p = people.get(mid) if people is not None else None
        known = bool(p) and str(p.get("persons", "")).strip() != ""
        if gate == "none":
            pass  # no people requirement for this show; every dated candidate competes
        elif people is None or not known:
            unknown_people += 1
        elif gate == "people":
            if inum(p.get("persons")) < 1 and inum(p.get("faces")) < 1:
                reason[mid] = "no-people"
                continue
        else:
            if (p.get("family_present") or "") != "yes":
                reason[mid] = "no-family"
                continue
        candidates.append(make_candidate(r, p, live_as_still=lp_still))

    byyear: dict[int, list[dict]] = collections.defaultdict(list)
    for c in candidates:
        byyear[c["year"]].append(c)

    # ---- anchors and pins from the config
    anchors: dict[str, list[str]] = collections.defaultdict(list)
    A = P.anchors()
    for y, L in byyear.items():
        for dw in A["date_window"]:
            mo, d0, d1 = inum(dw.get("month")), inum(dw.get("day_from"), 1), inum(dw.get("day_to"), 31)
            m = [c for c in L if c["day"] and c["month"] == mo and d0 <= inum(c["day"][8:10]) <= d1]
            pick = _anchor_pick(m)
            if pick:
                anchors[pick["id"]].append(str(dw.get("tag", "WINDOW")))
        for pl in A["place"]:
            lat, lon, rad = pl.get("lat"), pl.get("lon"), float(pl.get("radius_km", 15))
            if lat is None or lon is None or (float(lat) == 0.0 and float(lon) == 0.0):
                continue
            m = [c for c in L if c["lat"] is not None and c["lon"] is not None
                 and km(c["lat"], c["lon"], float(lat), float(lon)) <= rad]
            pick = _anchor_pick(m)
            if pick:
                anchors[pick["id"]].append(str(pl.get("tag", "PLACE")))
    byid = {c["id"]: c for c in candidates}
    cand_by_name = {c["name"]: c for c in candidates}
    for pn in A["pinned"]:
        for _y, fname in (pn.get("files") or {}).items():
            c = cand_by_name.get(str(fname)) or byid.get(str(fname))
            if c:
                anchors[c["id"]].append(str(pn.get("tag", "PINNED")))
    ids_by_name: dict[str, set[str]] = collections.defaultdict(set)   # over every indexed row, so a miss can say why
    for r in items:
        for form in _name_forms(r):
            ids_by_name[form].add(r["media_id"])
    pins = set()
    n_pinned = {"[pins] files": 0, "[show] must_include": 0}
    missing_pins = []
    for label, entries in (("[pins] files", P.pins()), ("[show] must_include", P.must_include())):
        for f in entries:
            f = str(f).strip()
            c = cand_by_name.get(f) or byid.get(f.lower())
            if c is None:
                hits = ids_by_name.get(f.lower(), set())
                if len(hits) > 1:
                    missing_pins.append(f"{f} ({label}: {len(hits)} files carry that name; use the media_id or the dated filename)")
                    continue
                mid = next(iter(hits), None)
                row = next((r for r in items if r["media_id"] == mid), None) if mid else None
                if row is not None and row.get("type") == "livephoto-video" and row.get("companion") in byname:
                    mid = byname[row["companion"]]["media_id"]   # a Live Photo pair is seated through its still
                c = byid.get(mid) if mid else None
                if c is None:
                    if not mid:
                        why = "not in the index"
                    elif mid in off_ids:
                        why = "off-limits"
                    elif mid in reason:
                        why = f"cut: {reason[mid]}"
                    else:
                        parked = [reason[r["filename"]] for r in items if r["media_id"] == mid and r["filename"] in reason]
                        why = f"cut: {parked[0]}" if parked else "not a candidate"
                    missing_pins.append(f"{f} ({label}: {why})")
                    continue
            if c["id"] not in pins:
                n_pinned[label] += 1
            pins.add(c["id"])
    if missing_pins:
        say(f"select: WARNING {len(missing_pins)} pin(s) not among the candidates: {'; '.join(missing_pins[:5])}")

    # ---- the lenses, per year
    ranks = {k: {} for k in ("v1", "v2", "v3", "v4")}
    tags4: dict[str, list[str]] = {}
    scores4: dict[str, float] = {}
    consensus_all: dict[str, int] = {}
    for y in sorted(byyear):
        L = byyear[y]
        budget = caps.get(y, 0)
        if budget <= 0:
            continue
        S1 = lens_v1(L, budget, sim)
        S2 = lens_v2(L, budget, sim, S1.ids)
        anch_y = {c["id"]: anchors[c["id"]] for c in L if c["id"] in anchors}
        S3 = lens_v3(L, budget, sim, anch_y)
        cons = {c["id"]: (c["id"] in S1.ids) + (c["id"] in S2.ids) + (c["id"] in S3.ids) for c in L}
        S4, sc = lens_v4(L, budget, sim, pins, anch_y, cons, motion_per_month, weights)
        for k, S in (("v1", S1), ("v2", S2), ("v3", S3), ("v4", S4)):
            ranks[k].update(S.ranks())
        tags4.update(S4.tags)
        scores4.update(sc)
        consensus_all.update(cons)
    chosen = set(ranks[lens])

    # ---- featured picks among the selected stills
    stills = [c for c in candidates if c["id"] in chosen and c["type"] in STILL_TYPES]
    feats, quotas = choose_featured(stills, frac, min_per_year, sim, rules)   # nothing when frac is 0
    featured = {c["id"] for c in feats}

    # ---- rows
    sel_rows, cut_rows = [], []
    for r in items:
        mid, t = r["media_id"], r.get("type", "")
        # a Live Photo clip rides with its still, except when the show plays stills only: then it is a cut row
        rides_with = byname.get(r.get("companion", "")) if t == "livephoto-video" and not lp_still else None
        if rides_with is not None:
            sid = rides_with["media_id"]
            selected = sid in chosen
            rsn = "" if selected else reason.get(sid, "over-cap")
            row = dict(media_id=mid, filename=r["filename"], selected="yes" if selected else "no",
                       v1_rank="", v2_rank="", v3_rank="", v4_rank="", consensus="", featured="",
                       pin="", anchor="", tag="companion", reason=rsn)
        else:
            parked = _location_reason(r.get("location", "work"))
            selected = mid in chosen and not parked
            rsn = "" if selected else ("off-limits" if mid in off_ids else (parked or reason.get(mid, "over-cap")))
            tg = tags4.get(mid, [])
            anchor_tags = [x for x in tg if x not in ("PIN", "MOTION", "MOTION-LP")]
            row = dict(media_id=mid, filename=r["filename"], selected="yes" if selected else "no",
                       v1_rank=ranks["v1"].get(mid, ""), v2_rank=ranks["v2"].get(mid, ""),
                       v3_rank=ranks["v3"].get(mid, ""), v4_rank=ranks["v4"].get(mid, ""),
                       consensus=consensus_all.get(mid, "") if mid in byid else "",
                       featured="yes" if mid in featured else "", pin="yes" if "PIN" in tg else "",
                       anchor="+".join(anchor_tags), tag=";".join(anchor_tags), reason=rsn)
        sel_rows.append(row)
        if not selected:
            cut_rows.append(dict(media_id=mid, filename=r["filename"], location=r.get("location", "work"),
                                 reason=rsn, original_source_path=r.get("source_path", "")))
    cut_rows.sort(key=lambda r: (r["reason"], r["filename"]))

    # ---- counts and the accounting
    n_sel_items = len(chosen)
    n_companions = sum(1 for r in sel_rows if r["tag"] == "companion" and r["selected"] == "yes")
    n_cut = len(cut_rows)
    balance = n_sel_items + n_companions + n_cut == len(items)
    say(f"select: lens {lens}, gate {gate}, diversity distance {sim}, {len(candidates)} candidates of {len(items)} rows")
    say("  " + cap_line(plan))
    if overrides:
        say("  cap overrides ([selection.cap_overrides]): " + ", ".join(f"{y} = {c}" for y, c in sorted(overrides.items())))
    say(f"  taste: order {knobs['order']}; motion density {knobs['motion_density']}; mixed tiles {'yes' if knobs['mixed_tiles'] else 'no'}; "
        f"videos {'yes' if knobs['include_videos'] else 'no'}; gifs {'yes' if knobs['include_gifs'] else 'no'}; Live Photos {knobs['live_photos']}")
    if gate == "none":
        say("  gate none: no people check ran; every dated candidate competed")
    if unknown_people:
        say(f"  ! {unknown_people} candidate(s) have no people data and passed the gate unchecked")
    if out_of_scope:
        say(f"  {out_of_scope} dated file(s) outside {P.first_year}-{P.last_year} cut as over-cap")
    say("  year   cap  cand   sel  motion  feat")
    for y in sorted(byyear):
        L = byyear[y]
        sel_y = [c for c in L if c["id"] in chosen]
        say("  %4d  %4d  %4d  %4d  %6d  %4d" % (y, caps.get(y, 0), len(L), len(sel_y),
                                               sum(1 for c in sel_y if c["motion"]), sum(1 for c in sel_y if c["id"] in featured)))
    reasons = collections.Counter(r["reason"] for r in cut_rows)
    say("  cut reasons:", ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
    say(f"  off-limits {reasons.get('off-limits', 0)} ([show] off_limits resolves to {len(off['media_ids'])} media id(s) and "
        f"{len(off['filenames'])} filename(s)); pins {len(pins)} seated "
        f"({n_pinned['[pins] files']} from [pins] files, {n_pinned['[show] must_include']} from [show] must_include)")
    n_excluded = reasons.get("excluded-type", 0)
    if n_excluded:
        what = {"video": "[taste] include_videos = false: {n} video(s)", "animated-gif": "include_gifs = false: {n} GIF(s)",
                "livephoto-video": "live_photos = \"still\": {n} Live Photo clip(s), their stills compete as plain stills"}
        say(f"  excluded-type {n_excluded}: " + "; ".join(what[k].format(n=v) for k, v in excluded.items() if v))
    say(f"  accounting: {n_sel_items} selected + {n_companions} pair videos + {n_cut} cut = "
        f"{n_sel_items + n_companions + n_cut} of {len(items)} rows {'OK' if balance else 'MISMATCH'}")
    n_videos = sum(1 for c in candidates if c["id"] in chosen and c["type"] == "video")
    if no_featured:
        say(f"  {no_featured}: no featured picks; every still takes a base tile"
            + (", and standalone videos ride in the grid" if not knobs["mixed_tiles"] else ""))
    if knobs["mixed_tiles"]:
        n_anchors = len(featured) + n_videos
        say(f"  featured {len(featured)} + standalone videos {n_videos} = {n_anchors} layout anchors "
            f"({(100 * n_anchors / n_sel_items) if n_sel_items else 0:.0f}% of items)")
    else:
        say(f"  layout anchors: none (mixed tiles off); standalone videos {n_videos}")
    spi = plan["seconds_per_item"]
    est = round(n_sel_items * spi)
    say(f"  rough loop estimate: about {est // 60} min {est % 60:02d} s at {fmt_num(spi)} s per item "
        f"({plan['tile_size']} tiles, {plan['scroll_speed']} px/s, references/04); the build prints the real number")
    if not balance:
        say("select: the accounting does not balance; nothing written")
        return 1
    if a.dry_run:
        say(f"select: dry run; would write {P.index / 'selection.csv'} ({len(sel_rows)} rows), "
            f"{P.index / 'cut-list.csv'} ({len(cut_rows)} rows)")
        return 0
    P.index.mkdir(parents=True, exist_ok=True)
    write_csv(P.index / "selection.csv", sel_rows, SELECTION_COLS)
    write_csv(P.index / "cut-list.csv", cut_rows, CUT_COLS)
    scores = {c["id"]: {"v4": round(scores4.get(c["id"], 0.0), 4), "consensus": consensus_all.get(c["id"], 0),
                        "featured_quota_year": c["year"]} for c in candidates}
    from common import write_atomic
    write_atomic(P.index / "_select-scores.json", json.dumps({"lens": lens, "quotas": {str(k): v for k, v in quotas.items()},
                                                             "scores": scores}, indent=0))
    say(f"select: wrote selection.csv ({len(sel_rows)} rows) and cut-list.csv ({len(cut_rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
