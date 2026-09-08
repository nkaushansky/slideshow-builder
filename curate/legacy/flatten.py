# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, shutil, json, time, collections
from concurrent.futures import ThreadPoolExecutor

SRC = os.path.expanduser("~/photo-project")
DEST = os.path.join(SRC, "slideshow-all")
WORK = os.path.expanduser("~/slideshow-work")
PLAN = os.path.join(WORK, "plan.json")
FAIL = os.path.join(WORK, "copy_failures.json")
BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 95.0
JUNK = {".ds_store", "thumbs.db", "desktop.ini"}
SKIP_DIRS = {"slideshow-all"}
start = time.time()

def slug(s): return "-".join(s.split())

if os.path.exists(PLAN):
    plan_data = json.load(open(PLAN))
else:
    files = []
    for root, dirs, names in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            if n.lower() in JUNK: continue
            full = os.path.join(root, n)
            files.append((full, os.path.relpath(full, SRC), n))
    by_name = collections.defaultdict(list)
    for f in files: by_name[f[2].lower()].append(f)
    assigned, plan = {}, []
    for full, rel, name in sorted(files, key=lambda x: x[1]):
        if len(by_name[name.lower()]) == 1:
            dest = name
        else:
            parts = rel.replace("\\", "/").split("/")[:-1]
            dest = "_".join([slug(p) for p in parts] + [name])
        key = dest.lower()
        if key in assigned:
            stem, ext = os.path.splitext(dest); i = 2
            while f"{stem}__{i}{ext}".lower() in assigned: i += 1
            dest = f"{stem}__{i}{ext}"; key = dest.lower()
        assigned[key] = rel
        plan.append({"src": full, "rel": rel, "dest": dest, "size": os.path.getsize(full)})
    plan_data = {"plan": plan,
                 "n_source": len(files),
                 "collision_names": sorted(k for k, v in by_name.items() if len(v) > 1)}
    json.dump(plan_data, open(PLAN, "w"), indent=1)

plan = plan_data["plan"]
os.makedirs(DEST, exist_ok=True)
have = {}
for n in os.listdir(DEST):
    fp = os.path.join(DEST, n)
    if os.path.isfile(fp): have[n] = os.path.getsize(fp)

todo = [p for p in plan if have.get(p["dest"]) != p["size"]]
failures = json.load(open(FAIL)) if os.path.exists(FAIL) else []
known_fail = {f["rel"] for f in failures}
todo = [p for p in todo if p["rel"] not in known_fail]
print(f"plan={len(plan)} present={len(plan)-len(todo)-len(known_fail)} todo={len(todo)} prior_failures={len(known_fail)}", flush=True)

stop = False
def work(p):
    global stop
    if stop or time.time() - start > BUDGET:
        stop = True; return None
    t = os.path.join(DEST, p["dest"])
    try:
        if os.path.exists(t) and os.path.getsize(t) != p["size"]:
            return {"rel": p["rel"], "dest": p["dest"],
                    "error": "different file already at target name - NOT overwritten"}
        shutil.copy2(p["src"], t)
        return None
    except Exception as e:
        return {"rel": p["rel"], "dest": p["dest"], "error": f"{type(e).__name__}: {e}"}

new_fail = []
with ThreadPoolExecutor(max_workers=12) as ex:
    for r in ex.map(work, todo):
        if r: new_fail.append(r)

if new_fail:
    failures.extend(new_fail)
    json.dump(failures, open(FAIL, "w"), indent=1)

done = sum(1 for p in plan if os.path.exists(os.path.join(DEST, p["dest"])))
print(f"ELAPSED {time.time()-start:.0f}s  in_dest={done}/{len(plan)}  new_failures={len(new_fail)}", flush=True)
print("COMPLETE" if done + len(failures) >= len(plan) else "MORE", flush=True)
