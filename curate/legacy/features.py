# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, csv, collections, math
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project"); SA=os.path.join(D,"slideshow-all")
MED=os.path.join(D,"slideshow-handoff","media")
GIF={".gif"}; VID={".mp4",".mov"}
names=sorted(n for n in os.listdir(MED) if not n.startswith("."))
stills=[n for n in names if os.path.splitext(n)[1].lower() not in VID|GIF]

ori={json.loads(l)["filename"]:json.loads(l) for l in open(os.path.join(H,"slideshow-work","oriented.jsonl"),encoding="utf-8")}
per={}
for l in open(os.path.join(H,"slideshow-work","persons2.jsonl"),encoding="utf-8"):
    d=json.loads(l); per[d["file"]]=d
rm=json.load(open(os.path.join(H,"slideshow-work","rename_map.json"),encoding="utf-8"))
scan={}
for l in open(os.path.join(H,"slideshow-work","scan.jsonl"),encoding="utf-8"):
    d=json.loads(l); scan[d["name"]]=d
def srec(cur): return scan.get(rm.get(cur,cur)) or scan.get(cur) or {}

miss_p=[n for n in stills if n not in per]
print("stills:",len(stills),"| persons2 misses:",len(miss_p),miss_p[:5])

# assemble candidates
cand=[]
sharps=sorted(srec(n).get("sharp") or 0 for n in stills)
def pct(v,arr):
    import bisect; return bisect.bisect_left(arr,v)/max(1,len(arr)-1)
ress=sorted((ori[n]["w"]*ori[n]["h"]) for n in stills)
for n in stills:
    o=ori[n]; p=per.get(n,{}); s=srec(n)
    w,h=o["w"],o["h"]
    nn=int(p.get("n") or 0); faces=int(p.get("faces") or 0); area=float(p.get("area") or 0)
    sharp=s.get("sharp") or 0
    year=n[:4]
    ok = (nn>=1 or faces>=1) and nn<=3 and min(w,h)>=1000 and max(w,h)>=1500 and pct(sharp,sharps)>=0.10
    score = 0.45*min(area,0.8)/0.8 + 0.20*pct(sharp,sharps) + 0.15*pct(w*h,ress) + 0.10*(1.0 if nn<=2 else 0.4) + 0.10*(1.0 if faces>0 else 0.0)
    cand.append(dict(f=n,year=year,w=w,h=h,n=nn,faces=faces,area=area,sharp=sharp,ok=ok,score=score,phash=s.get("phash",""),day=n[:10]))
el=[c for c in cand if c["ok"]]
print("eligible:",len(el))
ycount=collections.Counter(c["year"] for c in cand)
yel=collections.Counter(c["year"] for c in el)
print("per-year stills:",dict(sorted(ycount.items())))
print("per-year eligible:",dict(sorted(yel.items())))

# quotas: proportional to per-year still counts, total 74, min 1 where eligible
TARGET=74
years=sorted(ycount)
raw={y:TARGET*ycount[y]/len(stills) for y in years}
q={y:int(raw[y]) for y in years}
for y in years:
    if yel.get(y,0)>0 and q[y]==0: q[y]=1
rem=TARGET-sum(q.values())
for y in sorted(years,key=lambda y:raw[y]-int(raw[y]),reverse=True):
    if rem<=0: break
    if yel.get(y,0)>q[y]: q[y]+=1; rem-=1
q={y:min(q[y],yel.get(y,0)) for y in years}
print("quotas:",dict(sorted(q.items())),"sum",sum(q.values()))

def hd(a,b):
    try: return bin(int(a,16)^int(b,16)).count("1")
    except Exception: return 999
picks=[]
for y in years:
    pool=sorted([c for c in el if c["year"]==y],key=lambda c:-c["score"])
    got=[]; used_days=collections.Counter()
    # pass1: day-diverse
    for c in pool:
        if len(got)>=q[y]: break
        if used_days[c["day"]]>=1: continue
        if any(hd(c["phash"],g["phash"])<=26 for g in got): continue
        got.append(c); used_days[c["day"]]+=1
    # pass2: fill remaining ignoring day rule
    for c in pool:
        if len(got)>=q[y]: break
        if c in got: continue
        if any(hd(c["phash"],g["phash"])<=26 for g in got): continue
        got.append(c)
    # gentle portrait swap: if no portrait among got but portrait candidate close
    if got and not any(g["h"]>g["w"] for g in got):
        ports=[c for c in pool if c["h"]>c["w"] and c not in got and not any(hd(c["phash"],g["phash"])<=26 for g in got[:-1])]
        if ports and got and ports[0]["score"]>=0.85*got[-1]["score"]:
            got[-1]=ports[0]
    picks+=got
print("picked:",len(picks))
pc=collections.Counter(p["year"] for p in picks)
print("per-year picks:",dict(sorted(pc.items())))
port=sum(1 for p in picks if p["h"]>p["w"])
print("portrait picks:",port,"| n==3 picks:",sum(1 for p in picks if p["n"]==3))
lp=sum(1 for p in picks if os.path.splitext(p["f"])[0]+".MP4" in names or os.path.splitext(p["f"])[0]+".mp4" in names or os.path.splitext(p["f"])[0]+".MOV" in names)
print("LP-still picks:",lp)
json.dump({"picks":[p["f"] for p in picks],"detail":picks,"quotas":q},open(os.path.join(H,"slideshow-work","features.json"),"w"),indent=1)
print("saved features.json")
