# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, csv, collections
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
def pscore(n):
    v=pv(n)
    return (v.get("area",0)+0.05*min(v.get("n",0),6)) if v else 0.3

work=[r for r in rows if r["location"]=="slideshow-all" and r["best_guess_date"]]
gkey=lambda n:(os.path.dirname(rel_of.get(o(n),"")), os.path.splitext(os.path.basename(rel_of.get(o(n),o(n))))[0].lower())
groups=collections.defaultdict(list)
for r in work: groups[gkey(r["filename"])].append(r)
px=lambda n:(recs.get(o(n),{}).get("w") or 0)*(recs.get(o(n),{}).get("h") or 0)
reps={}; rides=collections.defaultdict(list)
for k,v in groups.items():
    stills=[r for r in v if recs.get(o(r["filename"]),{}).get("kind")=="still"]
    rep=max(stills or v,key=lambda r:px(r["filename"]))
    reps[rep["filename"]]=rep
    for r in v:
        if r["filename"]!=rep["filename"]: rides[rep["filename"]].append(r["filename"])
rep_of={}
for repn,cl in rides.items():
    for c in cl: rep_of[c]=repn

# ---------- tradition anchors ----------
# PORT: tradition anchors come from config [anchors]; the legacy code reads one JSON file in the work folder:
#   {"pinned": {"<TAG>": {"<year>": "<filename>"}}, "place": {"<TAG>": ["<filename>", ...]},
#    "date_window": {"<TAG>": {"month": 10, "day_from": 24, "day_to": 31}}}
ANCHORS=json.load(open(os.path.join(W,"anchors.json"))) if os.path.exists(os.path.join(W,"anchors.json")) else {}
PINNED_TAG=next(iter(ANCHORS.get("pinned",{})),"PINNED")
PINNED={int(y):f for y,f in ANCHORS.get("pinned",{}).get(PINNED_TAG,{}).items()}
PLACE_TAG=next(iter(ANCHORS.get("place",{})),"PLACE")
SS=ANCHORS.get("place",{}).get(PLACE_TAG,[])
DW_TAG=next(iter(ANCHORS.get("date_window",{})),"WINDOW")
DW=ANCHORS.get("date_window",{}).get(DW_TAG,{"month":0,"day_from":1,"day_to":0})
byname={r["filename"]:r for r in work}
ski=collections.defaultdict(list)
for n in SS:
    rr=byname.get(n)
    if not rr: continue
    repn=rep_of.get(n,n)
    ski[int(rr["best_guess_date"][:4])].append(repn)
SKI={y:max(set(v),key=pscore) for y,v in ski.items()}
hal=collections.defaultdict(list)
for r in work:
    d=r["best_guess_date"]
    if len(d)>=10 and int(d[5:7])==DW["month"] and DW["day_from"]<=int(d[8:10])<=DW["day_to"]:
        repn=rep_of.get(r["filename"],r["filename"])
        hal[int(d[:4])].append(repn)
def halpick(v):
    s=[n for n in set(v) if recs.get(o(n),{}).get("kind")=="still"] or list(set(v))
    grp=[n for n in s if (pv(n) or {}).get("n",0)>=2] or s
    return max(grp,key=pscore)
HAL={y:halpick(v) for y,v in hal.items()}
anchors=collections.defaultdict(dict)   # year -> name -> tags
for y,n in PINNED.items():
    n=rep_of.get(n,n)
    if n in reps: anchors[y].setdefault(n,[]).append(PINNED_TAG)
for y,n in SKI.items(): anchors[y].setdefault(n,[]).append(PLACE_TAG)
for y,n in HAL.items(): anchors[y].setdefault(n,[]).append(DW_TAG)
print("anchors per year:")
for y in sorted(anchors):
    print("  %d: %s"%(y,", ".join("%s(%s)"%(n[:38],"+".join(t)) for n,t in anchors[y].items())))

# ---------- breadth selection ----------
POP=np.unpackbits(np.arange(256,dtype=np.uint8)[:,None],axis=1).sum(1).astype(np.int16)
def bits(n):
    ph=recs.get(o(n),{}).get("phash")
    return np.packbits(imagehash.hex_to_hash(ph).hash.flatten()) if ph else None
FIRST_YEAR=2000; LAST_YEAR=2014; CAP_FULL=33; CAP_FIRST=11; CAP_LAST=22  # PORT: common.year_caps() from config [selection]; the partial first/last years are pro-rated by month
CAP={**{y:CAP_FULL for y in range(FIRST_YEAR+1,LAST_YEAR)},FIRST_YEAR:CAP_FIRST,LAST_YEAR:CAP_LAST}
byyear=collections.defaultdict(list)
for n,r in reps.items(): byyear[int(r["best_guess_date"][:4])].append(r)
rank={}; tag={}
for y,L in byyear.items():
    budget=CAP[y]; picked=[]; pb=[]; SIM=26
    def take(r):
        picked.append(r["filename"]); b=bits(r["filename"])
        if b is not None: pb.append(b)
    def ok(n):
        b=bits(n)
        return b is None or not pb or POP[np.bitwise_xor(np.stack(pb),b)].sum(1).min()>SIM
    for n,tags in anchors.get(y,{}).items():
        if n in reps and len(picked)<budget and n not in picked:
            take(reps[n]); tag[n]="+".join(tags)
    # day buckets: exact day -> that day; month-only -> YYYY-MM; year-only -> YYYY
    daybu=collections.defaultdict(list)
    for r in L:
        if r["filename"] in picked: continue
        d=r["best_guess_date"]
        key=d if len(d)>=10 else (d[:7] if len(d)>=7 else d[:4])
        daybu[key].append(r)
    for k in daybu: daybu[k].sort(key=lambda r:-pscore(r["filename"]))
    exact=sorted(k for k in daybu if len(k)>=10)
    vague=sorted(k for k in daybu if len(k)<10)
    # anchors already cover some exact days - do not spend a slot re-covering them
    donedays={reps[n]["best_guess_date"] for n in picked if n in reps and len(reps[n]["best_guess_date"])>=10}
    def sweep(keys,once_per_key=True):
        prog=False
        for k in keys:
            if len(picked)>=budget: break
            if not daybu[k]: continue
            ch=None
            for idx,r in enumerate(daybu[k]):
                if ok(r["filename"]): ch=idx; break
            if ch is None: continue      # never force a near-duplicate
            take(daybu[k].pop(ch)); prog=True
        return prog
    # pass A: one per not-yet-covered exact day
    sweep([k for k in exact if k not in donedays])
    # pass B: one per month/year bucket
    if len(picked)<budget: sweep(vague)
    # pass C: seconds from exact-day buckets first
    while len(picked)<budget and any(daybu[k] for k in exact):
        if not sweep(exact): break
    # pass D: only then seconds from month/year buckets
    while len(picked)<budget and any(daybu[k] for k in vague):
        if not sweep(vague): break
    for i,n in enumerate(picked): rank[n]=i+1

sel=set(rank); ride_n=0
for r in rows:
    n=r["filename"]
    if n in rank:
        r["v3_rank"]=rank[n]; r["selected_v3"]="yes"
    elif n in rep_of and rep_of[n] in sel:
        r["v3_rank"]="rides:%d"%rank[rep_of[n]]; r["selected_v3"]="yes"; ride_n+=1
    else:
        r["v3_rank"]=""; r["selected_v3"]="no"
cols=list(rows[0].keys())
for c in ("v3_rank","selected_v3"):
    if c not in cols: cols.append(c)
with open(os.path.join(D,"recovered-dates.csv"),"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
json.dump(tag,open(os.path.join(W,"v3_anchors.json"),"w"))

v1={r["filename"] for r in rows if r["selected"]=="yes" and str(r["shortlist_rank"]).isdigit()}
v2={r["filename"] for r in rows if r["selected_v2"]=="yes" and str(r["v2_rank"]).isdigit()}
allsel=[r for r in rows if r["selected_v3"]=="yes"]
def days_of(names):
    return {r["best_guess_date"] for r in rows if r["filename"] in names
            and len(r["best_guess_date"] or "")>=10 and r["precision"]=="exact day"}
print("\nV3: %d shots + %d riding = %d files"%(len(sel),ride_n,len(allsel)))
print("distinct exact days: v1 %d | v2 %d | v3 %d (of 747 possible)"%(len(days_of(v1)),len(days_of(v2)),len(days_of(sel))))
print("overlap of v3 with v1: %d%%  with v2: %d%%"%(100*len(sel&v1)//len(sel),100*len(sel&v2)//len(sel)))
print("anchors placed:",len(tag))
byy=collections.Counter(int(r["best_guess_date"][:4]) for r in allsel)
json.dump({"shots":len(sel),"rides":ride_n,"total":len(allsel),
 "days":{"v1":len(days_of(v1)),"v2":len(days_of(v2)),"v3":len(days_of(sel)),"possible":747},
 "ov1":100*len(sel&v1)//len(sel),"ov2":100*len(sel&v2)//len(sel),
 "anchors":{n:t for n,t in tag.items()},
 "byyear":{y:byy.get(y,0) for y in range(FIRST_YEAR,LAST_YEAR+1)},
 "mix":dict(collections.Counter(r["source"] for r in allsel))},
 open(os.path.join(W,"v3_stats.json"),"w"))
