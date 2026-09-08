# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, csv, collections, time
WORK=os.path.expanduser("~/slideshow-work"); D=os.path.expanduser("~/photo-project/slideshow-all")
BURST=os.path.join(D,"_burst-duplicates"); MAP=os.path.join(WORK,"rename_map.json")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 140.0
APPLY="--apply" in sys.argv
start=time.time()
recs={json.loads(l)["name"]:json.loads(l) for l in open(os.path.join(WORK,"scan.jsonl"))}
rel_of={p["dest"]:p["rel"].replace("\\","/") for p in json.load(open(os.path.join(WORK,"plan.json")))["plan"]}
rows={r["filename"]:r for r in csv.DictReader(open(os.path.join(D,"recovered-dates.csv"),encoding="utf-8"))}
SKIP={"inventory.md","recovered-dates.csv","rename-map.csv","gallery-manifest.json"}

def pad(d):
    if not d: return "9999-99-99"
    p=d.split("-")
    return "%s-%s-%s"%(p[0], p[1] if len(p)>1 else "00", p[2] if len(p)>2 else "00")
RANK={"exact day":0,"month":1,"year":2,"none":3}
# Live Photo groups share one date so pair prefixes stay aligned
grp=collections.defaultdict(list)
for n in rows:
    rel=rel_of[n]; grp[(os.path.dirname(rel), os.path.splitext(os.path.basename(rel))[0].lower())].append(n)
gdate={}
for k,v in grp.items():
    best=min(v, key=lambda n: RANK.get(rows[n]["precision"],3))
    for n in v: gdate[n]=pad(rows[best]["best_guess_date"])

plan=[]; taken=collections.defaultdict(set)
for folder in (D,BURST):
    for n in sorted(os.listdir(folder)):
        if n in SKIP or n.startswith("_contact-sheet") or not os.path.isfile(os.path.join(folder,n)): continue
        if n not in rows: continue
        if len(n)>11 and n[4]=="-" and n[7]=="-" and n[10]=="_" and n[:4].isdigit(): continue  # already renamed
        new="%s_%s"%(gdate.get(n,"9999-99-99"), n)
        base,ext=os.path.splitext(new); i=2
        while new.lower() in taken[folder]:
            new="%s__%d%s"%(base,i,ext); i+=1
        taken[folder].add(new.lower())
        plan.append([folder,n,new])
print("to rename:",len(plan))
if not APPLY:
    for f,o,nn in plan[:8]: print("   %s -> %s"%(o,nn))
    print("[DRY RUN]"); raise SystemExit
m=json.load(open(MAP)) if os.path.exists(MAP) else {}
done=0
for folder,o,nn in plan:
    if time.time()-start>BUDGET: break
    src,dst=os.path.join(folder,o),os.path.join(folder,nn)
    if os.path.exists(dst) or not os.path.exists(src): continue
    os.rename(src,dst); m[nn]=o; done+=1
json.dump(m,open(MAP,"w"))
left=sum(1 for f,o,nn in plan if os.path.exists(os.path.join(f,o)))
print("renamed %d this pass, %d still to go"%(done,left))
print("COMPLETE" if left==0 else "MORE")
