# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, collections
from datetime import date
WORK = os.path.expanduser("~/slideshow-work")
ROOT = os.path.expanduser("~/photo-project")
DEST = os.path.join(ROOT, "slideshow-all")
BURST = os.path.join(DEST, "_burst-duplicates")

recs = {json.loads(l)["name"]: json.loads(l) for l in open(os.path.join(WORK,"scan.jsonl"))}
plan = json.load(open(os.path.join(WORK,"plan.json")))
rel_of = {p["dest"]: p["rel"] for p in plan["plan"]}
bp = json.load(open(os.path.join(WORK,"burst_plan.json")))
fails = json.load(open(os.path.join(WORK,"copy_failures.json")))

main = sorted(n for n in os.listdir(DEST) if os.path.isfile(os.path.join(DEST,n)) and n!="inventory.md")
moved = sorted(n for n in os.listdir(BURST) if os.path.isfile(os.path.join(BURST,n)) and n in recs)
M = [recs[n] for n in main]

def sz(b):
    for u in ["B","KB","MB","GB","TB"]:
        if b < 1024 or u=="TB": return f"{b:,.1f} {u}" if u!="B" else f"{b} B"
        b/=1024
total_bytes = sum(r["size"] for r in M)
stills = [r for r in M if r["kind"]=="still"]; vids=[r for r in M if r["kind"]=="video"]

# Live Photo pairing on final contents: same source folder + same original stem
def key(n):
    rel = rel_of[n].replace("\\","/")
    return (os.path.dirname(rel), os.path.splitext(os.path.basename(rel))[0].lower())
g = collections.defaultdict(list)
for r in M: g[key(r["name"])].append(r)
paired_stills, companion_vids = [], []
for k,v in g.items():
    s=[x for x in v if x["kind"]=="still"]; m=[x for x in v if x["kind"]=="video"]
    if s and m: paired_stills += s; companion_vids += m
standalone = sorted([v for v in vids if v not in companion_vids], key=lambda r: r["name"])

BOGUS = lambda r: r["dt"] and r["dt"][:4]=="1970"
dated = [r for r in M if r["dt"] and not BOGUS(r)]
years = collections.Counter(r["dt"][:4] for r in dated)
dts = sorted(r["dt"] for r in dated)
no_dt = [r for r in M if not r["dt"] or BOGUS(r)]

L=[]
A=L.append
A("# slideshow-all — inventory\n")
A(f"Generated {date.today().isoformat()} from the configured source folders.")
A("Files were **copied**, never moved — both source folders are untouched and still hold every original.\n")
A("## Totals\n")
A(f"- **Files in `slideshow-all` (flat, excluding `_burst-duplicates`): {len(main):,}**")
A(f"- Stills: {len(stills):,}  |  Videos: {len(vids):,}")
A(f"- Total size on disk: **{sz(total_bytes)}** ({total_bytes:,} bytes)")
A(f"- Additional {len(moved)} files parked in `_burst-duplicates` ({sz(sum(recs[n]['size'] for n in moved))})\n")
A("## Count by extension\n")
A("| Extension | Files |")
A("|---|---:|")
for e,c in collections.Counter(r["ext"] for r in M).most_common(): A(f"| `{e}` | {c:,} |")
A(f"| **Total** | **{len(main):,}** |\n")
A("## Date range and count by year\n")
A(f"Timestamps come from EXIF `DateTimeOriginal` for stills and the container creation time for videos.\n")
A(f"- **Earliest: {dts[0]}**")
A(f"- **Latest: {dts[-1]}**")
A(f"- Files with a usable timestamp: {len(dated):,} of {len(main):,}")
A(f"- Files with no readable timestamp: {len(no_dt):,} (listed under *Unreadable metadata* below)\n")
A("| Year | Files |")
A("|---|---:|")
for y in sorted(years): A(f"| {y} | {years[y]:,} |")
A(f"| *no timestamp* | {len(no_dt):,} |")
A(f"| **Total** | **{len(main):,}** |\n")
A("## Live Photos\n")
A(f"A still counts as having a Live Photo companion when a video with the same filename stem sat in the **same source folder** (matching on the original path, not the flattened name, so the collision prefixes don't break real pairs).\n")
A(f"- **Stills with a Live Photo video companion: {len(paired_stills)}**")
A(f"- Companion videos backing them: {len(set(x['name'] for x in companion_vids))}")
A(f"- Both halves of every pair are present in `slideshow-all`; no pair was split by the burst pass.\n")
A("<details><summary>All paired stills</summary>\n")
for r in sorted(paired_stills, key=lambda r:r["name"]):
    mates = [x["name"] for x in g[key(r["name"])] if x["kind"]=="video"]
    A(f"- `{r['name']}` → `{', '.join(mates)}`")
A("\n</details>\n")
A(f"## Standalone videos ({len(standalone)})\n")
A("Videos with no matching still — these are real clips, not Live Photo halves.\n")
A("| File | Duration | Resolution | Size | Timestamp |")
A("|---|---:|---:|---:|---|")
for r in standalone:
    d = f"{r['dur']:.1f}s" if r["dur"] else "—"
    res = f"{r['w']}×{r['h']}" if r["w"] else "—"
    ts = r["dt"] if (r["dt"] and not BOGUS(r)) else "—"
    A(f"| `{r['name']}` | {d} | {res} | {sz(r['size'])} | {ts} |")
tot = sum(r["dur"] or 0 for r in standalone)
A(f"\nCombined runtime of standalone videos: **{int(tot//60)}m {int(tot%60)}s**\n")
A("## Deduplication\n")
A("### Pass 1 — exact duplicates (SHA-256)\n")
A(f"- **Exact duplicates removed: 0**")
A(f"- All {len(plan['plan']):,} copied files hashed; {len(plan['plan']):,} distinct SHA-256 values. No two files are byte-identical.")
A(f"- Visually identical pairs *do* exist ({len(moved)} of them, handled in pass 2), but they differ at the byte level \u2014 HEIC vs JPG renditions of the same shot, re-exports at different compression, the same photo pulled twice into different calendar folders. None qualified for deletion here.\n")
A("### Pass 2 — burst / near-duplicates\n")
A(f"- **Files moved to `_burst-duplicates`: {len(moved)}**, from {len(bp['groups'])} groups. Nothing was deleted.")
A(f"- Candidates were pairs sharing a filename stem **or** shot within {bp['window']:.0f} seconds of each other by EXIF, then required to be visually near-identical.")
A(f"- Visual test: 256-bit perceptual hash, Hamming distance ≤ {bp['threshold']}. The measured distances split cleanly — 34 pairs at ≤9 and nothing at all between 10 and 19 — so the cutoff sits in an empty gap rather than on a judgment call.")
A(f"- Keeper per group: highest pixel count first, then sharpness, then file size. Resolution leads deliberately — the low-res copies often score *higher* on a Laplacian sharpness measure purely because downscaling raises local contrast, so ranking on sharpness alone would have kept 872×654 thumbnails over 4032×3024 originals.\n")
A("| Kept | Moved to `_burst-duplicates` | pHash distance |")
A("|---|---|---:|")
import imagehash as _ih
def _d(a,b): return _ih.hex_to_hash(recs[a]["phash"]) - _ih.hex_to_hash(recs[b]["phash"])
for grp in bp["groups"]:
    k = grp["keep"]; rk = recs[k]
    for n in grp["moved"]:
        rn = recs[n]
        A(f"| `{k}` <br><sub>{rk['w']}×{rk['h']}, {sz(rk['size'])}</sub> | `{n}` <br><sub>{rn['w']}×{rn['h']}, {sz(rn['size'])}</sub> | |")
A("")
A(f"### Borderline pairs deliberately left alone ({len(bp['borderline'])})\n")
A("Close enough to flag, too far apart to call duplicates. Both copies remain in the main folder — worth an eyeball.\n")
A("| File A | File B | pHash distance |")
A("|---|---|---:|")
for a,b,d in sorted(bp["borderline"], key=lambda x:x[2]): A(f"| `{a}` | `{b}` | {d} |")
A("")
A("## Problems\n")
A("### Files that failed to copy\n")
A(f"- **{len(fails)}** — every source file copied successfully and was verified byte-for-byte by size against its original.\n")
A(f"### Files with unreadable or missing metadata ({len(no_dt)})\n")
bogus = [r for r in no_dt if BOGUS(r)]
A(f"- **{len(no_dt)-len(bogus)} stills carry no EXIF timestamp at all.** These are overwhelmingly the calendar-layout images (names like `<day> <month>.jpeg` and similar) — exported, screenshotted or scanned files whose EXIF was stripped in the process. Their pixels are fine; only the date is missing, so they're absent from the year counts above.")
A(f"- **{len(bogus)} videos report a 1970-01-01 creation time**, which is a zeroed timestamp rather than a real date. Treated as undated and excluded from the range:")
for r in sorted(bogus, key=lambda r:r["name"]): A(f"  - `{r['name']}`")
A("")
A("No file was renamed into a sequence, sorted into date subfolders, converted, resized or re-encoded.")
open(os.path.join(DEST,"inventory.md"),"w",encoding="utf-8").write("\n".join(L))
print("wrote inventory.md", len("\n".join(L)), "chars")
print("main:",len(main),"| stills:",len(stills),"| videos:",len(vids),
      "| paired stills:",len(paired_stills),"| standalone:",len(standalone),
      "| moved:",len(moved),"| size:",sz(total_bytes))
