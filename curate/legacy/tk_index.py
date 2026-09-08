# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, zipfile, collections, threading
H=os.path.expanduser("~")
TD=os.path.join(H,"photo-project","takeout")
OUTJ=os.path.join(H,"slideshow-work","takeout_index.jsonl")
OUTM=os.path.join(H,"slideshow-work","takeout_media.jsonl")
CK=os.path.join(H,"slideshow-work","tk_index.ck")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
t0=time.time()
zips=sorted(f for f in os.listdir(TD) if f.lower().endswith(".zip"))
done=set()
if os.path.exists(CK): done=set(json.load(open(CK)))
from concurrent.futures import ThreadPoolExecutor
tl=threading.local()
def zh(zp):
    d=getattr(tl,"h",None)
    if d is None: d={}; tl.h=d
    if zp not in d: d[zp]=zipfile.ZipFile(os.path.join(TD,zp))
    return d[zp]
MEDIA_EXT={".heic",".mp4",".mov",".jpg",".jpeg",".png",".gif",".webp"}
jout=open(OUTJ,"a",encoding="utf-8"); mout=open(OUTM,"a",encoding="utf-8")
stats=collections.Counter()
for z in zips:
    if z in done: continue
    if time.time()-t0>BUDGET: break
    zf=zipfile.ZipFile(os.path.join(TD,z))
    infos=zf.infolist()
    # media members: cheap, from central dir only
    jmembers=[]
    for i in infos:
        nm=i.filename; ext=os.path.splitext(nm)[1].lower()
        if ext in MEDIA_EXT:
            mout.write(json.dumps({"zip":z,"member":nm,"size":i.file_size})+"\n")
            stats["media"]+=1
        elif ext==".json" and "/Photos from " in nm:
            jmembers.append(nm)
    def rd(nm):
        try:
            d=json.loads(zh(z).read(nm).decode("utf-8",errors="replace"))
        except Exception as e:
            return {"zip":z,"json":nm,"err":str(e)[:60]}
        r={"zip":z,"json":nm,"title":d.get("title",""),
           "ts":int((d.get("photoTakenTime") or {}).get("timestamp") or 0),
           "folder":nm.split("/")[2] if nm.count("/")>=2 else ""}
        g=d.get("geoData") or {}
        if g.get("latitude") or g.get("longitude"):
            r["lat"]=g.get("latitude"); r["lon"]=g.get("longitude")
        ppl=[p.get("name","") for p in (d.get("people") or []) if isinstance(p,dict)]
        if ppl: r["people"]=ppl
        desc=(d.get("description") or "").strip()
        if desc: r["desc"]=desc[:140]
        return r
    with ThreadPoolExecutor(12) as ex:
        for r in ex.map(rd,jmembers):
            jout.write(json.dumps(r)+"\n")
            stats["json"]+=1
            if "people" in r: stats["with_people"]+=1
            if "lat" in r: stats["with_gps"]+=1
            if "err" in r: stats["err"]+=1
    jout.flush(); mout.flush()
    done.add(z); json.dump(sorted(done),open(CK,"w"))
    print(z,"done | cum:",dict(stats),"| %.0fs"%(time.time()-t0),flush=True)
jout.close(); mout.close()
rem=[z for z in zips if z not in done]
print("REMAINING zips:",len(rem))
print("COMPLETE" if not rem else "RERUN")
