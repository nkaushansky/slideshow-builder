# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, csv, time, shutil
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project"); SA=os.path.join(D,"slideshow-all")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 140.0
t0=time.time()
rows=list(csv.DictReader(open(os.path.join(SA,"recovered-dates.csv"),encoding="utf-8")))
target={r["filename"] for r in rows if r.get("selected_v4")=="yes"}
sizes={}
for f in target:
    p=os.path.join(SA,f)
    sizes[f]=os.path.getsize(p)
print("target set:",len(target),"| bytes:",sum(sizes.values()))
for root in (os.path.join(D,"slideshow-handoff","media"), os.path.join(D,"slideshow-all v4")):
    have={f:os.path.getsize(os.path.join(root,f)) for f in os.listdir(root) if os.path.isfile(os.path.join(root,f))}
    extra=[f for f in have if f not in target]
    missing=[f for f in target if have.get(f)!=sizes[f]]
    print(os.path.basename(root),"| extra:",len(extra),"| to copy:",len(missing))
    for f in extra:
        os.remove(os.path.join(root,f))
    n=0
    for f in missing:
        if time.time()-t0>BUDGET: print("  BUDGET, rerun"); break
        shutil.copy2(os.path.join(SA,f),os.path.join(root,f)); n+=1
    have2={f:os.path.getsize(os.path.join(root,f)) for f in os.listdir(root) if os.path.isfile(os.path.join(root,f))}
    ok=(have2=={f:sizes[f] for f in target})
    print("  synced %d | now %d files | MATCH: %s"%(n,len(have2),ok))
