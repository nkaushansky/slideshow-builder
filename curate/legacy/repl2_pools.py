# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, csv, collections, bisect
from datetime import date
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project")
HO=os.path.join(D,"slideshow-handoff"); SA=os.path.join(D,"slideshow-all")
B=os.path.join(H,"slideshow-work")
# PORT: the round's inputs come from the review flags; the legacy code reads one JSON file in the work folder:
#   {"slots": ["<filename>", ...], "round1_adds": ["<filename>", ...], "removed": ["<filename>", ...]}
RJ=json.load(open(os.path.join(B,"repl_round2.json"),encoding="utf-8"))
SLOTS=RJ["slots"]; ROUND1_ADDS_SA=set(RJ.get("round1_adds",[])); REMOVED=set(RJ.get("removed",[]))
med=list(csv.DictReader(open(os.path.join(HO,"media.csv"),encoding="utf-8")))
cut=list(csv.DictReader(open(os.path.join(HO,"cut-list.csv"),encoding="utf-8")))
rm=json.load(open(os.path.join(B,"rename_map.json"),encoding="utf-8"))
scan={}
for l in open(os.path.join(B,"scan.jsonl"),encoding="utf-8"):
    d=json.loads(l); scan[d["name"]]=d
def srec(c): return scan.get(rm.get(c,c)) or scan.get(c) or {}
per={}
for l in open(os.path.join(B,"persons2.jsonl"),encoding="utf-8"):
    d=json.loads(l); per[d["file"]]=d
tkh={}
for l in open(os.path.join(B,"tk_phash.jsonl"),encoding="utf-8"):
    d=json.loads(l)
    if "phash" in d: tkh[d["zip"]+"|"+d["member"]]=d["phash"]
plan=json.load(open(os.path.join(B,"tk_extract_plan.json"),encoding="utf-8"))
mem2new={p["new"]:p["zip"]+"|"+p["member"] for p in plan}
# show set = media.csv - REMOVED + round1 adds
show=[r["filename"] for r in med if r["filename"] not in REMOVED]+list(ROUND1_ADDS_SA)
show_hashes=[]
for f in show:
    ph=(srec(f) or {}).get("phash") or tkh.get(mem2new.get(f,""))
    if ph: show_hashes.append(ph)
print("show files:",len(show),"| hashes:",len(show_hashes))
def hd(a,b): return bin(int(a,16)^int(b,16)).count("1")
def pdate(f):
    y,m,dd=f[:4],f[5:7],f[8:10]
    if m=="00": return None,"year"
    if dd=="00": return date(int(y),int(m),15),"month"
    return date(int(y),int(m),int(dd)),"day"
VIDE={".mp4",".mov"}; IMGE={".heic",".jpg",".jpeg",".png"}
sa_files=set(os.listdir(SA))
stems=collections.defaultdict(dict)
for f in sa_files:
    stem,ext=os.path.splitext(f); stems[stem][ext.lower()]=f
oc=[r for r in cut if r["reason"]=="over-cap" and r["filename"] in sa_files
    and r["filename"] not in ROUND1_ADDS_SA and r["filename"] not in REMOVED]
sharps=sorted((srec(r["filename"]).get("sharp") or 0) for r in oc)
def spct(v): return bisect.bisect_left(sharps,v)/max(1,len(sharps)-1)
pools={}
for L in SLOTS:
    Ld,_=pdate(L)
    for widen,(win,allow_year) in enumerate(((45,False),(120,False),(9999,True))):
        cands=[]
        for r in oc:
            f=r["filename"]
            ext=os.path.splitext(f)[1].lower()
            fd,prec=pdate(f)
            if prec=="year":
                if not allow_year or f[:4]!=L[:4]: continue
                dist=180
            else:
                dist=abs((fd-Ld).days)
                if allow_year:
                    if f[:4]!=L[:4] and dist>120: continue
                elif dist>win: continue
            stem=os.path.splitext(f)[0]
            sib=stems.get(stem,{})
            if ext in VIDE and any(e in sib for e in IMGE): continue
            s=srec(f); p=per.get(f,{})
            ph=s.get("phash")
            if ph and any(hd(ph,x)<=26 for x in show_hashes): continue
            sharp=s.get("sharp") or 0
            if ext not in VIDE and spct(sharp)<0.08: continue
            n=int(p.get("n") or 0); faces=int(p.get("faces") or 0); area=float(p.get("area") or 0)
            if ext in VIDE: continue  # both slots want stills (LP pairs count via still half)
            ispair=(ext in IMGE and any(v in sib for v in (".mp4",".mov")))
            comp=(sib.get(".mp4") or sib.get(".mov")) if ispair else ""
            score=0.45*min(area,0.8)/0.8+0.2*spct(sharp)+0.1*(1 if faces>0 else 0)+0.15*max(0,(60-dist))/60+0.1*(1 if n>=1 else 0)
            cands.append(dict(file=f,dist=dist,pair=bool(ispair),companion=comp,video=False,
                              n=n,faces=faces,area=round(area,2),score=round(score,3),prec=prec))
        if len(cands)>=8: break
    cands.sort(key=lambda c:-c["score"])
    pools[L]=cands[:10]
    print(L,"| pass:",("±45d","±120d","year")[widen],"| pool:",len(cands),"| kept:",len(pools[L]),
          "| pairs:",sum(1 for c in pools[L] if c["pair"]))
    for c in pools[L]:
        print("   %-52s d=%3d %sn=%d f=%d a=%.2f s=%.2f"%(c["file"][:52],c["dist"],("PAIR " if c["pair"] else ""),c["n"],c["faces"],c["area"],c["score"]))
json.dump(pools,open(os.path.join(B,"repl2_pools.json"),"w"),indent=1)
print("saved repl2_pools.json")
