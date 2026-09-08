# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, csv, re, collections
import numpy as np, imagehash
W=os.path.expanduser("~/slideshow-work"); D=os.path.expanduser("~/photo-project/slideshow-all")
recs={json.loads(l)["name"]:json.loads(l) for l in open(os.path.join(W,"scan.jsonl"))}
m=json.load(open(os.path.join(W,"rename_map.json")))
rel_of={p["dest"]:p["rel"].replace("\\","/") for p in json.load(open(os.path.join(W,"plan.json")))["plan"]}
rows=list(csv.DictReader(open(os.path.join(D,"recovered-dates.csv"),encoding="utf-8")))
o=lambda n:m.get(n,n)
P={}
for l in open(os.path.join(W,"persons2.jsonl")):
    v=json.loads(l); P[v["file"]]=v
def pers(n):
    v=P.get(n)
    if v is None and len(n)>11: v=P.get("9999-99-99_"+n[11:])
    if v is None or "err" in v: return None
    return v

work=[r for r in rows if r["location"]=="slideshow-all" and r["best_guess_date"]]
gkey=lambda n:(os.path.dirname(rel_of.get(o(n),"")), os.path.splitext(os.path.basename(rel_of.get(o(n),o(n))))[0].lower())
groups=collections.defaultdict(list)
for r in work: groups[gkey(r["filename"])].append(r)
px=lambda n:(recs.get(o(n),{}).get("w") or 0)*(recs.get(o(n),{}).get("h") or 0)
reps=[]; rides=collections.defaultdict(list)
for k,v in groups.items():
    stills=[r for r in v if recs.get(o(r["filename"]),{}).get("kind")=="still"]
    rep=max(stills or v,key=lambda r:px(r["filename"])); reps.append(rep)
    for r in v:
        if r["filename"]!=rep["filename"]: rides[rep["filename"]].append(r["filename"])

MOTION_RE=re.compile(r'[-_](animation|motion)',re.I)
def is_motion(n):
    ext=os.path.splitext(n)[1].lower()
    if ext in (".mov",".mp4",".m4v",".gif"): return True
    return bool(MOTION_RE.search(n))

v1={r["filename"] for r in rows if r["selected"]=="yes" and str(r["shortlist_rank"]).isdigit()}
POP=np.unpackbits(np.arange(256,dtype=np.uint8)[:,None],axis=1).sum(1).astype(np.int16)
def bits(n):
    ph=recs.get(o(n),{}).get("phash")
    return np.packbits(imagehash.hex_to_hash(ph).hash.flatten()) if ph else None
def pct(a):
    a=np.array(a,dtype=float)
    if len(a)<2 or a.max()==a.min(): return np.ones(len(a))*.5
    return a.argsort().argsort()/(len(a)-1)
FIRST_YEAR=2000; LAST_YEAR=2014; CAP_FULL=33; CAP_FIRST=11; CAP_LAST=22  # PORT: common.year_caps() from config [selection]; the partial first/last years are pro-rated by month
CAP={**{y:CAP_FULL for y in range(FIRST_YEAR+1,LAST_YEAR)},FIRST_YEAR:CAP_FIRST,LAST_YEAR:CAP_LAST}
byyear=collections.defaultdict(list)
for r in reps: byyear[int(r["best_guess_date"][:4])].append(r)

def run(B):
    rank={}
    for y,L in byyear.items():
        area=[]; grpn=[]
        for r in L:
            v=pers(r["filename"])
            area.append(v["area"] if v else 0.0); grpn.append(min(v["n"],6)/6 if v else 0.3)
        s=(0.35*pct(area)+0.15*np.array(grpn)+0.20*pct([recs.get(o(r['filename']),{}).get('sharp') or 0 for r in L])
           +0.15*pct([px(r["filename"]) for r in L]))
        s=s+np.array([0.0 if r["filename"] in v1 else B for r in L])
        bymo=collections.defaultdict(list)
        for i,r in enumerate(L):
            d=r["best_guess_date"]; mo=int(d[5:7]) if len(d)>=7 and d[5:7]!="00" else 0
            bymo[mo].append((float(s[i]),r))
        for k in bymo: bymo[k].sort(key=lambda t:-t[0])
        months=sorted(bymo); picked=[]; pb=[]; SIM=26; budget=CAP[y]
        def take(r):
            picked.append(r); b=bits(r["filename"])
            if b is not None: pb.append(b)
        def ok(r):
            b=bits(r["filename"])
            return b is None or not pb or POP[np.bitwise_xor(np.stack(pb),b)].sum(1).min()>SIM
        # phase 1: one motion item per month, best-scoring, where one exists
        for k in months:
            if len(picked)>=budget: break
            for idx,(sc,r) in enumerate(bymo[k]):
                if is_motion(r["filename"]) and ok(r):
                    take(r); bymo[k].pop(idx); break
        # phase 1b: months with no deliberate motion get the best still WITH a video companion
        VIDEXT=(".mov",".mp4",".m4v")
        for k in months:
            if len(picked)>=budget: break
            if any((int(r2["best_guess_date"][5:7]) if len(r2["best_guess_date"])>=7 and r2["best_guess_date"][5:7]!="00" else 0)==k
                   and is_motion(r2["filename"]) for r2 in picked): continue
            for idx,(sc,r) in enumerate(bymo[k]):
                comps=rides.get(r["filename"],[])
                if any(os.path.splitext(c)[1].lower() in VIDEXT for c in comps) and ok(r):
                    take(r); bymo[k].pop(idx); break
        # phase 2: round-robin everything else; never force a near-duplicate
        stall=0
        while len(picked)<budget and any(bymo[k] for k in months) and stall<2:
            prog=False
            for k in months:
                if len(picked)>=budget: break
                if not bymo[k]: continue
                ch=None
                for idx,(sc,r) in enumerate(bymo[k]):
                    if ok(r): ch=idx; break
                if ch is None: continue
                sc,r=bymo[k].pop(ch); take(r); prog=True
            stall=0 if prog else stall+1
        for i,r in enumerate(picked): rank[r["filename"]]=i+1
    return rank

B=0.15
for _ in range(6):
    rank=run(B)
    ov=len(set(rank)&v1)/len(rank)
    print("bonus %.2f -> %d shots, overlap with v1 %.0f%%"%(B,len(rank),100*ov),flush=True)
    if ov<=0.50: break
    B+=0.10

sel=set(rank)
n_ride=sum(len(rides[n]) for n in sel)
for r in rows:
    n=r["filename"]
    if n in rank: r["v2_rank"]=rank[n]; r["selected_v2"]="yes"
    else:
        r["v2_rank"]=""; r["selected_v2"]="no"
        for repn,rl in ([(x,rides[x]) for x in sel] if False else []): pass
ride_of={}
for repn in sel:
    for c in rides[repn]: ride_of[c]=repn
for r in rows:
    n=r["filename"]
    if n in ride_of:
        r["v2_rank"]="rides:%d"%rank[ride_of[n]]; r["selected_v2"]="yes"
cols=list(rows[0].keys())
for c in ("v2_rank","selected_v2"):
    if c not in cols: cols.append(c)
with open(os.path.join(D,"recovered-dates.csv"),"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)

v2files=[r for r in rows if r["selected_v2"]=="yes"]
print("\nV2: %d shots + %d riding = %d files"%(len(sel),n_ride,len(v2files)))
print("overlap: %d of %d shots shared with v1 (%.0f%%)"%(len(sel&v1),len(sel),100*len(sel&v1)/len(sel)))
print("source mix:",dict(collections.Counter(r["source"] for r in v2files)))
# motion coverage per version
def motion_months(names):
    mm=collections.defaultdict(set); tot=0
    for r in rows:
        if r["filename"] not in names: continue
        n=r["filename"]
        if not is_motion(n): continue
        d=r["best_guess_date"]; tot+=1
        if d and len(d)>=7 and d[5:7]!="00": mm[d[:7]].add(n)
    return tot,len(mm)
v1all={r["filename"] for r in rows if r["selected"]=="yes"}
v2all={r["filename"] for r in v2files}
t1,m1=motion_months(v1all); t2,m2=motion_months(v2all)
print("motion items: v1 %d across %d months | v2 %d across %d months"%(t1,m1,t2,m2))
byy=collections.Counter(int(r["best_guess_date"][:4]) for r in v2files)
print("v2 files by year:",dict(sorted(byy.items())))
json.dump({"shots":len(sel),"rides":n_ride,"total":len(v2files),
  "overlap_shots":len(sel&v1),"overlap_pct":round(100*len(sel&v1)/len(sel)),
  "bonus":B,"motion":{"v1":[t1,m1],"v2":[t2,m2]},
  "byyear":{y:byy.get(y,0) for y in range(FIRST_YEAR,LAST_YEAR+1)},
  "mix":dict(collections.Counter(r["source"] for r in v2files))},
  open(os.path.join(W,"v2_stats.json"),"w"))
