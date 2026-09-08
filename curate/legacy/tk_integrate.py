# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, zipfile, shutil, collections
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project"); SA=os.path.join(D,"slideshow-all")
TD=os.path.join(D,"takeout")
B=os.path.join(H,"slideshow-work")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 140.0
t0=time.time()
seat=json.load(open(os.path.join(B,"tk_seating.json"),encoding="utf-8"))
med=[json.loads(l) for l in open(os.path.join(B,"takeout_media.jsonl"),encoding="utf-8")]
bymem={m["member"]:m for m in med}
mbys=collections.defaultdict(dict)
for m in med:
    p=m["member"].split("/")
    if len(p)>=4 and p[2].startswith("Photos from"):
        stem,ext=os.path.splitext(p[-1]); mbys[(p[2],stem)][ext.lower()]=m
# plan: every seated takeout-backed item -> (member, newname) + LP companion
plan=[]
seen=set()
for Y in ("2022","2023"):
    for e in seat[Y]["seated"]:
        if not e.get("member"): continue
        base=os.path.basename(e["member"])
        newname=e["date"]+"_"+base
        plan.append(dict(zip=e["zip"],member=e["member"],new=newname,entry_file=e["file"],kind=e["kind"],
                         lp=bool(e.get("lp")),date=e["date"],tag=e.get("tag",""),upgrade=bool(e.get("upgrade"))))
        seen.add(e["member"])
        if e.get("lp"):
            p=e["member"].split("/"); key=(p[2],os.path.splitext(p[-1])[0])
            mm=mbys.get(key,{})
            comp=mm.get(".mp4") if not e["member"].lower().endswith(".mp4") else mm.get(".heic")
            if comp and comp["member"] not in seen:
                cb=os.path.basename(comp["member"])
                plan.append(dict(zip=comp["zip"],member=comp["member"],new=e["date"]+"_"+cb,
                                 entry_file=e["file"],kind="companion",lp=True,date=e["date"],tag="",upgrade=False))
                seen.add(comp["member"])
json.dump(plan,open(os.path.join(B,"tk_extract_plan.json"),"w"),indent=1)
print("extract plan:",len(plan),"files | bytes: %.2f GB"%(sum(bymem[p["member"]]["size"] for p in plan)/1e9))
# collision check
existing=set(os.listdir(SA))
coll=[p for p in plan if p["new"] in existing and os.path.getsize(os.path.join(SA,p["new"]))!=bymem[p["member"]]["size"]]
print("name collisions with different size:",[(p["new"],) for p in coll])
zh={}
def zf(z):
    if z not in zh: zh[z]=zipfile.ZipFile(os.path.join(TD,z))
    return zh[z]
n=0; skipped=0
for p in plan:
    if time.time()-t0>BUDGET: print("BUDGET"); break
    dst=os.path.join(SA,p["new"])
    want=bymem[p["member"]]["size"]
    if os.path.exists(dst) and os.path.getsize(dst)==want: skipped+=1; continue
    with zf(p["zip"]).open(p["member"]) as src, open(dst,"wb") as out:
        shutil.copyfileobj(src,out,1024*1024)
    assert os.path.getsize(dst)==want
    n+=1
print("extracted %d | already had %d | of %d | %.0fs"%(n,skipped,len(plan),time.time()-t0))
print("COMPLETE" if n+skipped==len(plan) else "RERUN")
