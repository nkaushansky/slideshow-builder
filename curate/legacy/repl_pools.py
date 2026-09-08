# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, csv, collections
from datetime import date
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project")
HO=os.path.join(D,"slideshow-handoff"); SA=os.path.join(D,"slideshow-all")
B=os.path.join(H,"slideshow-work")
# PORT: the round's inputs come from the review flags; the legacy code reads one JSON file in the work folder:
#   {"leaving": ["<filename>", ...], "exclude": ["<filename>", ...], "takeout_years": ["<YYYY>", ...]}
RJ=json.load(open(os.path.join(B,"repl_round.json"),encoding="utf-8"))
LEAVING=RJ["leaving"]
med=list(csv.DictReader(open(os.path.join(HO,"media.csv"),encoding="utf-8")))
cut=list(csv.DictReader(open(os.path.join(HO,"cut-list.csv"),encoding="utf-8")))
rd={r["filename"]:r for r in csv.DictReader(open(os.path.join(SA,"recovered-dates.csv"),encoding="utf-8"))}
rm=json.load(open(os.path.join(B,"rename_map.json"),encoding="utf-8"))
scan={}
for l in open(os.path.join(B,"scan.jsonl"),encoding="utf-8"):
    d=json.loads(l); scan[d["name"]]=d
def srec(c): return scan.get(rm.get(c,c)) or scan.get(c) or {}
per={}
for l in open(os.path.join(B,"persons2.jsonl"),encoding="utf-8"):
    d=json.loads(l); per[d["file"]]=d
# current-show hash set
tkh={}
for l in open(os.path.join(B,"tk_phash.jsonl"),encoding="utf-8"):
    d=json.loads(l)
    if "phash" in d: tkh[d["zip"]+"|"+d["member"]]=d["phash"]
plan=json.load(open(os.path.join(B,"tk_extract_plan.json"),encoding="utf-8"))
mem2new={p["new"]:p["zip"]+"|"+p["member"] for p in plan}
show_hashes=[]
for r in med:
    f=r["filename"]
    ph=(srec(f) or {}).get("phash") or tkh.get(mem2new.get(f,""),None)
    if ph: show_hashes.append(ph)
print("show hashes:",len(show_hashes),"of",len(med))
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
    stem,ext=os.path.splitext(f)
    stems[stem][ext.lower()]=f
EXCLUDE=set(RJ.get("exclude",[]))
oc=[r for r in cut if r["reason"]=="over-cap" and r["filename"] in sa_files and r["filename"] not in EXCLUDE]
# real dates for year-only exports via pHash match against the takeout index (the years the takeout covers)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ET=ZoneInfo(os.environ.get("SLIDESHOW_TZ","UTC"))  # PORT: config [project] timezone
tk_bymem={}
idx=[json.loads(l) for l in open(os.path.join(B,"takeout_index.jsonl"),encoding="utf-8") if "err" not in l[:200]]
tkdate={}
for r0 in idx:
    stem0=os.path.splitext(r0.get("title",""))[0]
    if r0.get("ts"):
        tkdate[(r0.get("folder",""),stem0)]=datetime.fromtimestamp(r0["ts"],tz=timezone.utc).astimezone(ET).strftime("%Y-%m-%d")
tkrows=[]
for l in open(os.path.join(B,"tk_phash.jsonl"),encoding="utf-8"):
    d0=json.loads(l)
    if "phash" in d0: tkrows.append(d0)
REAL={}
for r0 in oc:
    f0=r0["filename"]
    if f0[:4] not in set(RJ.get("takeout_years",[])) or f0[5:7]!="00": continue
    ph0=(srec(f0) or {}).get("phash")
    if not ph0: continue
    best=(999,None)
    for d0 in tkrows:
        dd=hd(ph0,d0["phash"])
        if dd<best[0]: best=(dd,d0)
    if best[0]<=12 and best[1]:
        pp=best[1]["member"].split("/")
        rd0=tkdate.get((pp[2],os.path.splitext(pp[-1])[0]))
        if rd0: REAL[f0]=rd0
print("real dates recovered for year-only exports:",len(REAL))
# drop video halves of pairs from the standalone list (handled via their still)
sharps=sorted((srec(r["filename"]).get("sharp") or 0) for r in oc)
import bisect
def spct(v): return bisect.bisect_left(sharps,v)/max(1,len(sharps)-1)
pools={}
for L in LEAVING:
    Ld,_=pdate(L)
    cands=[]
    for widen,(win,allow_year) in enumerate(((45,False),(120,False),(9999,True))):
        cands=[]
        for r in oc:
            f=r["filename"]
            if f==L: continue
            ext=os.path.splitext(f)[1].lower()
            if f in REAL:
                rd=REAL[f]; fd=date(int(rd[:4]),int(rd[5:7]),int(rd[8:10])); prec="day"
            else:
                fd,prec=pdate(f)
            if prec=="year":
                if not allow_year or f[:4]!=L[:4]: continue
                dist=180
            else:
                dist=abs((fd-Ld).days)
                if allow_year:
                    if f[:4]!=L[:4] and dist>120: continue
                elif dist>win: continue
            # pair handling: videos that are the .mp4/.mov half of a pair whose still is also present -> skip (still carries the pair)
            stem=os.path.splitext(f)[0]
            sib=stems.get(stem,{})
            if ext in VIDE and any(e in sib for e in IMGE): continue
            s=srec(f); p=per.get(f,{})
            ph=s.get("phash")
            if ph and any(hd(ph,x)<=26 for x in show_hashes): continue
            sharp=s.get("sharp") or 0
            if ext not in VIDE and spct(sharp)<0.08: continue
            n=int(p.get("n") or 0); faces=int(p.get("faces") or 0); area=float(p.get("area") or 0)
            ispair=(ext in IMGE and (".mp4" in sib or ".mov" in sib) and any(sib.get(v) and os.path.splitext(sib[v])[0]==stem for v in (".mp4",".mov")))
            comp=""
            if ispair: comp=sib.get(".mp4") or sib.get(".mov")
            score=0.4*min(area,0.8)/0.8+0.2*spct(sharp)+0.1*(1 if faces>0 else 0)+0.15*max(0,(60-dist))/60+0.15*(0.5 if ext in VIDE else 1.0)
            cands.append(dict(file=f,dist=dist,pair=bool(ispair),companion=comp,video=(ext in VIDE),
                              n=n,faces=faces,area=round(area,2),score=round(score,3),prec=prec,
                              real=REAL.get(f,"")))
        if len(cands)>=8: break
    cands.sort(key=lambda c:-c["score"])
    pools[L]=cands[:10]
    print(L,"| window pass:",("±45d","±120d","year")[widen],"| pool:",len(cands),"| kept:",len(pools[L]),
          "| pairs:",sum(1 for c in pools[L] if c["pair"]),"| vids:",sum(1 for c in pools[L] if c["video"]))
json.dump(pools,open(os.path.join(B,"repl_pools.json"),"w"),indent=1)
print("saved repl_pools.json")
