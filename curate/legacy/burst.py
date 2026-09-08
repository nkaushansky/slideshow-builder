# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, re, collections, itertools
from datetime import datetime
import imagehash

WORK = os.path.expanduser("~/slideshow-work")
DEST = os.path.expanduser("~/photo-project/slideshow-all")
BURST = os.path.join(DEST, "_burst-duplicates")
THRESH = 12          # of 256 bits; sits inside the empty 10-19 gap in the distance histogram
WINDOW = 3.0         # seconds
DRY = "--apply" not in sys.argv

recs = [json.loads(l) for l in open(os.path.join(WORK, "scan.jsonl"))]
plan = json.load(open(os.path.join(WORK, "plan.json")))["plan"]
rel_of = {p["dest"]: p["rel"] for p in plan}
by = {r["name"]: r for r in recs}

def orig_stem(dest):
    rel = rel_of[dest]
    return os.path.splitext(os.path.basename(rel))[0]
def src_dir(dest):
    return os.path.dirname(rel_of[dest].replace("\\", "/"))
NORM = re.compile(r'(?:\s*\(\d+\)|\s+Copy|[_-]Original)+$', re.I)
def norm_stem(dest):
    return NORM.sub('', orig_stem(dest)).strip().lower()

# ---- Live Photo pairing: same SOURCE FOLDER + same ORIGINAL stem, still + video ----
groups = collections.defaultdict(list)
for r in recs:
    groups[(src_dir(r["name"]), orig_stem(r["name"]).lower())].append(r)
still_has_video, video_has_still = set(), set()
for k, v in groups.items():
    s = [x for x in v if x["kind"] == "still"]
    m = [x for x in v if x["kind"] == "video"]
    if s and m:
        for x in s: still_has_video.add(x["name"])
        for x in m: video_has_still.add(x["name"])

stills = [r for r in recs if r["kind"] == "still"]
videos = [r for r in recs if r["kind"] == "video"]
print(f"stills={len(stills)} videos={len(videos)}")
print(f"Live Photo pairs: stills with a video companion = {len(still_has_video)}; "
      f"videos that are a companion = {len(video_has_still)}; "
      f"standalone videos = {len(videos)-len(video_has_still)}")

# ---- candidate pair generation ----
cand = set()
ns = collections.defaultdict(list)
for r in stills: ns[norm_stem(r["name"])].append(r)
n_stem_groups = 0
for k, v in ns.items():
    if len(v) > 1:
        n_stem_groups += 1
        for a, b in itertools.combinations(v, 2): cand.add(tuple(sorted((a["name"], b["name"]))))
n_by_stem = len(cand)

def pt(s):
    try: return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception: return None
ts = sorted([r for r in stills if r["dt"] and r["dt"][:4] != "1970" and pt(r["dt"])],
            key=lambda r: r["dt"])
for i, a in enumerate(ts):
    for b in ts[i+1:]:
        if (pt(b["dt"]) - pt(a["dt"])).total_seconds() > WINDOW: break
        cand.add(tuple(sorted((a["name"], b["name"]))))
print(f"candidates: {n_by_stem} from matching stems ({n_stem_groups} stem groups), "
      f"{len(cand)} total after adding <={WINDOW:.0f}s EXIF neighbours")

# ---- perceptual gate ----
def H(s): return imagehash.hex_to_hash(s)
linked, borderline = [], []
for a, b in cand:
    ra, rb = by[a], by[b]
    if not (ra["phash"] and rb["phash"]): continue
    d = H(ra["phash"]) - H(rb["phash"])
    if d <= THRESH: linked.append((a, b, d))
    elif d <= 30: borderline.append((a, b, d))
print(f"pairs passing pHash<={THRESH}: {len(linked)}  |  borderline {THRESH}<d<=30 kept apart: {len(borderline)}")

# ---- connected components ----
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb
for a, b, d in linked: union(a, b)
comps = collections.defaultdict(list)
for n in parent: comps[find(n)].append(n)
comps = [sorted(v) for v in comps.values() if len(v) > 1]
print(f"burst groups: {len(comps)}  files involved: {sum(len(c) for c in comps)}")

def keyfn(n):
    r = by[n]
    px = (r["w"] or 0) * (r["h"] or 0)
    return (1 if n in still_has_video else 0, px, r["sharp"] or 0, r["size"])

moves, kept_report = [], []
lp_tiebreak = 0
for c in comps:
    ranked = sorted(c, key=keyfn, reverse=True)
    keep, rest = ranked[0], ranked[1:]
    best_px = max((by[n]["w"] or 0)*(by[n]["h"] or 0) for n in c)
    if (by[keep]["w"] or 0)*(by[keep]["h"] or 0) < best_px: lp_tiebreak += 1
    moves += rest
    kept_report.append((keep, rest))
print(f"\nWOULD KEEP {len(comps)} files, WOULD MOVE {len(moves)} files to _burst-duplicates")
print(f"groups where the Live-Photo companion rule overrode a higher-resolution frame: {lp_tiebreak}")

# safety: no still moved out if it strands its video companion
stranded = []
moving = set(moves)
for k, v in groups.items():
    s = [x["name"] for x in v if x["kind"] == "still"]
    m = [x["name"] for x in v if x["kind"] == "video"]
    if s and m and all(x in moving for x in s):
        stranded.append((k, s, m))
print(f"Live Photo pairs that would be split (must be 0): {len(stranded)}", stranded[:3])

print("\n--- sample groups (keep <- moved) ---")
for keep, rest in kept_report[:14]:
    rk = by[keep]
    print(f"KEEP {keep} [{rk['w']}x{rk['h']} sharp={rk['sharp']}{' +LivePhoto' if keep in still_has_video else ''}]")
    for n in rest:
        rr = by[n]
        d = next((d for a,b,d in linked if n in (a,b) and keep in (a,b)), "-")
        print(f"   move {n} [{rr['w']}x{rr['h']} sharp={rr['sharp']}] d={d}")
print("\n--- borderline pairs NOT moved (for your eyes) ---")
for a,b,d in sorted(borderline, key=lambda x: x[2])[:10]: print(f"   d={d}  {a}  ~  {b}")

json.dump({"moves": moves, "groups": [{"keep": k, "moved": r} for k, r in kept_report],
           "borderline": [[a,b,int(d)] for a,b,d in borderline],
           "still_has_video": sorted(still_has_video),
           "video_has_still": sorted(video_has_still),
           "threshold": THRESH, "window": WINDOW},
          open(os.path.join(WORK, "burst_plan.json"), "w"), indent=1)

if DRY:
    print("\n[DRY RUN - nothing moved]")
else:
    os.makedirs(BURST, exist_ok=True)
    done = 0
    for n in moves:
        s, d = os.path.join(DEST, n), os.path.join(BURST, n)
        if os.path.exists(s) and not os.path.exists(d):
            os.rename(s, d); done += 1
    print(f"\n[APPLIED] moved {done} files into _burst-duplicates")
