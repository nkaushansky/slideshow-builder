# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, csv, time, shutil
from concurrent.futures import ThreadPoolExecutor
D=os.path.expanduser("~/photo-project/slideshow-all")
V=os.path.expanduser("~/photo-project/slideshow-all v4")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
start=time.time(); os.makedirs(V,exist_ok=True)
rows=[r for r in csv.DictReader(open(os.path.join(D,"recovered-dates.csv"),encoding="utf-8"))
      if r.get("selected_v4")=="yes"]
have={n:os.path.getsize(os.path.join(V,n)) for n in os.listdir(V) if os.path.isfile(os.path.join(V,n))}
todo=[r for r in rows if have.get(r["filename"]) != os.path.getsize(os.path.join(D,r["filename"]))]
print("v2 selected %d | copied %d | todo %d"%(len(rows),len(rows)-len(todo),len(todo)),flush=True)
stop=False
def cp(r):
    global stop
    if stop or time.time()-start>BUDGET: stop=True; return
    try: shutil.copy2(os.path.join(D,r["filename"]),os.path.join(V,r["filename"]))
    except Exception as e: return str(e)[:60]
with ThreadPoolExecutor(max_workers=12) as ex: errs=[x for x in ex.map(cp,todo) if x]
n=len([1 for x in os.listdir(V) if os.path.isfile(os.path.join(V,x))])
print("ELAPSED %.0fs  in v2 folder: %d/%d  errors %d"%(time.time()-start,n,len(rows),len(errs)),flush=True)
print("COMPLETE" if n>=len(rows) else "MORE",flush=True)
