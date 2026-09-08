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
def pv(n):
    v=P.get(n) or (P.get("9999-99-99_"+n[11:]) if len(n)>11 else None)
    return v if v and "err" not in v else None

work=[r for r in rows if r["location"]=="slideshow-all" and r["best_guess_date"]]
gkey=lambda n:(os.path.dirname(rel_of.get(o(n),"")), os.path.splitext(os.path.basename(rel_of.get(o(n),o(n))))[0].lower())
groups=collections.defaultdict(list)
for r in work: groups[gkey(r["filename"])].append(r)
px=lambda n:(recs.get(o(n),{}).get("w") or 0)*(recs.get(o(n),{}).get("h") or 0)
reps={}; rides=collections.defaultdict(list); rep_of={}
for k,v in groups.items():
    stills=[r for r in v if recs.get(o(r["filename"]),{}).get("kind")=="still"]
    rep=max(stills or v,key=lambda r:px(r["filename"]))
    reps[rep["filename"]]=rep
    for r in v:
        if r["filename"]!=rep["filename"]:
            rides[rep["filename"]].append(r["filename"]); rep_of[r["filename"]]=rep["filename"]

MOT=re.compile(r'[-_](animation|motion)',re.I)
VIDEXT=(".mov",".mp4",".m4v")
def is_motion(n):
    return os.path.splitext(n)[1].lower() in VIDEXT+(".gif",) or bool(MOT.search(n))
def has_lp(n):
    return any(os.path.splitext(c)[1].lower() in VIDEXT for c in rides.get(n,[]))
def incuts(r):
    c=0
    for col,rk in (("selected","shortlist_rank"),("selected_v2","v2_rank"),("selected_v3","v3_rank")):
        if r[col]=="yes" and (str(r[rk]).isdigit() or r[rk]=="pin"): c+=1
    return c
ANCH=json.load(open(os.path.join(W,"v3_anchors.json")))
PINS={r["filename"] for r in rows if "pin" in (r.get("v2_rank",""),r.get("v3_rank",""),r.get("shortlist_rank","")) 
      and "pinned into all three cuts" in r.get("evidence","")}
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
for n,r in reps.items(): byyear[int(r["best_guess_date"][:4])].append(r)

rank={}; tagout={}
for y,L in byyear.items():
    budget=CAP[y]
    # blended score
    area=[]; grp=[]
    for r in L:
        v=pv(r["filename"])
        area.append(v["area"] if v else 0.0); grp.append(min(v["n"],6)/6 if v else 0.3)
    sc=(0.40*pct(area)+0.10*np.array(grp)
        +0.20*pct([recs.get(o(r['filename']),{}).get('sharp') or 0 for r in L])
        +0.15*pct([px(r["filename"]) for r in L])
        +0.15*np.array([incuts(r)/3 for r in L]))
    score={r["filename"]:float(sc[i]) for i,r in enumerate(L)}
    def month_of(r):
        d=r["best_guess_date"]
        return int(d[5:7]) if len(d)>=7 and d[5:7]!="00" else 0
    def day_of(r):
        d=r["best_guess_date"]
        return d if len(d)>=10 else None
    picked=[]; pb=[]; useddays=set(); SIM=26
    def ok(n):
        b=bits(n)
        return b is None or not pb or POP[np.bitwise_xor(np.stack(pb),b)].sum(1).min()>SIM
    def take(r,tag=None):
        picked.append(r["filename"]); b=bits(r["filename"])
        if b is not None: pb.append(b)
        d=day_of(r)
        if d: useddays.add(d)
        if tag: tagout[r["filename"]]=tag
    pool={r["filename"]:r for r in L}
    def seat(name,tag):
        r=pool.get(name)
        if r and name not in picked and len(picked)<budget: take(r,tag)
    # 1. owner pins
    for n in PINS:
        if n in pool: seat(n,"PIN")
    # 2. tradition anchors
    for n,t in ANCH.items():
        if n in pool: seat(n,t)
        elif rep_of.get(n) in pool: seat(rep_of[n],t)
    # 3. one deliberate motion item per month
    months=sorted({month_of(r) for r in L if month_of(r)>0})
    for mo in months:
        if len(picked)>=budget: break
        if any(month_of(pool[n])==mo and is_motion(n) for n in picked if n in pool): continue
        cand=sorted([r for r in L if month_of(r)==mo and is_motion(r["filename"]) and r["filename"] not in picked],
                    key=lambda r:-score[r["filename"]])
        for r in cand:
            if ok(r["filename"]): take(r,"MOTION"); break
    # 3b. months with no motion at all: best Live-Photo-bearing still
    for mo in months:
        if len(picked)>=budget: break
        if any(month_of(pool[n])==mo and (is_motion(n) or has_lp(n)) for n in picked if n in pool): continue
        cand=sorted([r for r in L if month_of(r)==mo and has_lp(r["filename"]) and r["filename"] not in picked],
                    key=lambda r:-score[r["filename"]])
        for r in cand:
            if ok(r["filename"]): take(r,"MOTION-LP"); break
    # 4. month round-robin over UNUSED DAYS, blended score, dated first
    order=months+([0] if any(month_of(r)==0 for r in L) else [])
    def pick_in_month(mo,allow_used_day,allow_dayless):
        cand=[r for r in L if month_of(r)==mo and r["filename"] not in picked]
        cand.sort(key=lambda r:-score[r["filename"]])
        for r in cand:
            d=day_of(r)
            if d is None and not allow_dayless: continue
            if d is not None and (d in useddays) and not allow_used_day: continue
            if ok(r["filename"]): take(r); return True
        return False
    # pass A: new days only
    prog=True
    while len(picked)<budget and prog:
        prog=False
        for mo in order:
            if len(picked)>=budget: break
            if pick_in_month(mo,allow_used_day=False,allow_dayless=(mo==0)): prog=True
    # pass B: dayless files of real months
    prog=True
    while len(picked)<budget and prog:
        prog=False
        for mo in order:
            if len(picked)>=budget: break
            if pick_in_month(mo,allow_used_day=False,allow_dayless=True): prog=True
    # pass C: seconds from already-used days
    prog=True
    while len(picked)<budget and prog:
        prog=False
        for mo in order:
            if len(picked)>=budget: break
            if pick_in_month(mo,allow_used_day=True,allow_dayless=True): prog=True
    for i,n in enumerate(picked): rank[n]=i+1

sel=set(rank); ride_n=0
for r in rows:
    n=r["filename"]
    if n in rank: r["v4_rank"]=rank[n]; r["selected_v4"]="yes"
    elif n in rep_of and rep_of[n] in sel:
        r["v4_rank"]="rides:%d"%rank[rep_of[n]]; r["selected_v4"]="yes"; ride_n+=1
    else: r["v4_rank"]=""; r["selected_v4"]="no"
cols=list(rows[0].keys())
for c in ("v4_rank","selected_v4"):
    if c not in cols: cols.append(c)
with open(os.path.join(D,"recovered-dates.csv"),"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
json.dump(tagout,open(os.path.join(W,"v4_tags.json"),"w"))
by={r["filename"]:r for r in rows}
def shots_of(col,rk):
    return {r["filename"] for r in rows if r[col]=="yes" and (str(r[rk]).isdigit() or r[rk]=="pin")}
v1=shots_of("selected","shortlist_rank"); v2=shots_of("selected_v2","v2_rank"); v3=shots_of("selected_v3","v3_rank")
allsel=[r for r in rows if r["selected_v4"]=="yes"]
days={r["best_guess_date"] for r in rows if r["filename"] in sel and len(r["best_guess_date"] or "")>=10 and r["precision"]=="exact day"}
tri=v1&v2&v3
comp=collections.Counter(incuts(by[n]) for n in sel)
mot=[n for n in {x["filename"] for x in allsel} if is_motion(n)]
motmo={by[n]["best_guess_date"][:7] for n in mot if len(by[n]["best_guess_date"])>=7 and by[n]["best_guess_date"][5:7]!="00"}
print("V4: %d shots + %d riding = %d files"%(len(sel),ride_n,len(allsel)))
print("distinct exact days: %d  (v1 341 / v2 321 / v3 397)"%len(days))
print("consensus composition of v4 shots: in-3-cuts %d, in-2 %d, in-1 %d, fresh %d"%(comp[3],comp[2],comp[1],comp[0]))
print("triple-core included: %d of %d"%(len(sel&tri),len(tri)))
print("overlap: v1 %d%%  v2 %d%%  v3 %d%%"%(100*len(sel&v1)//len(sel),100*len(sel&v2)//len(sel),100*len(sel&v3)//len(sel)))
print("motion files: %d across %d months"%(len(mot),len(motmo)))
for y in ("2024","2025"):
    mo=collections.Counter(by[n]["best_guess_date"][5:7] for n in sel if by[n]["best_guess_date"][:4]==y and len(by[n]["best_guess_date"])>=7)
    print("  %s month spread: %s"%(y,"  ".join("%s:%d"%(k,mo[k]) for k in sorted(mo))))
byy=collections.Counter(int(r["best_guess_date"][:4]) for r in allsel)
json.dump({"shots":len(sel),"rides":ride_n,"total":len(allsel),"days":len(days),
 "comp":{str(k):v for k,v in comp.items()},"tri_in":len(sel&tri),"tri":len(tri),
 "ov":[100*len(sel&v1)//len(sel),100*len(sel&v2)//len(sel),100*len(sel&v3)//len(sel)],
 "motion":[len(mot),len(motmo)],"byyear":{y:byy.get(y,0) for y in range(FIRST_YEAR,LAST_YEAR+1)},
 "mix":dict(collections.Counter(r["source"] for r in allsel)),
 "anchors":len([1 for n in tagout.values() if n not in ("PIN","MOTION","MOTION-LP")])},
 open(os.path.join(W,"v4_stats.json"),"w"))
