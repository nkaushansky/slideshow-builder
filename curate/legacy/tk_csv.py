# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, csv, io, collections, math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ET=ZoneInfo(os.environ.get("SLIDESHOW_TZ","UTC"))  # PORT: config [project] timezone
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project"); SA=os.path.join(D,"slideshow-all")
B=os.path.join(H,"slideshow-work")
PLACES=[]  # PORT: config [[anchors.place]] entries as (tag, lat, lon, radius_km)
SUP=os.path.join(SA,"_superseded-by-originals"); os.makedirs(SUP,exist_ok=True)
seat=json.load(open(os.path.join(B,"tk_seating.json"),encoding="utf-8"))
plan=json.load(open(os.path.join(B,"tk_extract_plan.json"),encoding="utf-8"))
idx=[json.loads(l) for l in open(os.path.join(B,"takeout_index.jsonl"),encoding="utf-8") if "err" not in l[:200]]
byfs={}
for r in idx:
    stem=os.path.splitext(r.get("title",""))[0]
    byfs[(r.get("folder",""),stem)]=r
hashes={}
for fn in ("tk_phash.jsonl","tk_scores.jsonl"):
    for l in open(os.path.join(B,fn),encoding="utf-8"):
        d=json.loads(l)
        if "phash" in d: hashes[d["zip"]+"|"+d["member"]]=d
motion={}
for l in open(os.path.join(B,"tk_motion.jsonl"),encoding="utf-8"):
    r=json.loads(l); motion[r["stem"]]=r
cp=os.path.join(SA,"recovered-dates.csv")
rows=list(csv.DictReader(open(cp,encoding="utf-8"))); flds=list(rows[0].keys())
byname={r["filename"]:r for r in rows}
sup_moves=0; drop_marks=0; new_rows=0
# 1) upgraded incumbents -> supersede old
for Y in ("2022","2023"):
    for e in seat[Y]["seated"]:
        if e.get("upgrade") and e.get("member"):
            old=e["file"]; r=byname.get(old)
            newname=e["date"]+"_"+os.path.basename(e["member"])
            if r and r.get("location")!="_superseded-by-originals":
                r["location"]="_superseded-by-originals"; r["selected_v4"]="no"
                r["evidence"]=(r.get("evidence","")+"; superseded 2026-08-30 by takeout original "+newname)[:400]
                drop_marks+=0
            src=os.path.join(SA,old)
            if os.path.exists(src):
                os.rename(src,os.path.join(SUP,old)); sup_moves+=1
    for e in seat[Y]["drops"]:
        if e["kind"]!="incumbent": continue
        r=byname.get(e["file"])
        if r and r.get("selected_v4")=="yes":
            r["selected_v4"]="no"
            r["evidence"]=(r.get("evidence","")+"; unseated in 2026-08-30 takeout re-seat")[:400]
            drop_marks+=1
# 2) new rows for extracted files
def km(a,b,c,d):
    p=math.pi/180
    x=0.5-math.cos((c-a)*p)/2+math.cos(a*p)*math.cos(c*p)*(1-math.cos((d-b)*p))/2
    return 12742*math.asin(math.sqrt(x))
for p in plan:
    if p["new"] in byname: continue
    key=p["zip"]+"|"+p["member"]
    hs=hashes.get(key,{})
    pp=p["member"].split("/"); k2=(pp[2],os.path.splitext(pp[-1])[0])
    info=byfs.get(k2,{})
    w=hs.get("w") or (motion.get(k2[1],{}) or {}).get("w") or ""
    h=hs.get("h") or (motion.get(k2[1],{}) or {}).get("h") or ""
    short=min(int(w),int(h)) if w and h else ""
    ppl=info.get("people",[])
    lat=info.get("lat"); lon=info.get("lon")
    ev="Takeout sidecar photoTakenTime (Google Photos original)"
    for tag,plat,plon,pkm in PLACES:
        if lat and km(lat,lon,plat,plon)<pkm: ev+="; GPS "+tag
    if p.get("tag"): ev+="; tag "+p["tag"]
    r={k:"" for k in flds}
    r.update(filename=p["new"],location="slideshow-all",source="google-takeout",
             source_path="takeout/"+p["zip"]+"!"+p["member"],
             best_guess_date=p["date"],precision="exact day",confidence="A - EXIF",
             width=str(w),height=str(h),short_side_px=str(short),
             fills_1080p=("yes" if short and int(short)>=1080 and max(int(w),int(h))>=1920 else "no"),
             crisp_6across_5k=("yes" if short and int(short)>=815 else "no"),
             evidence=ev,has_person=("yes" if ppl else ""),faces=str(len(ppl)) if ppl else "",
             selected_v4="yes",v4_rank="tk")
    rows.append(r); byname[p["new"]]=r; new_rows+=1
buf=io.StringIO(); wtr=csv.DictWriter(buf,fieldnames=flds); wtr.writeheader(); wtr.writerows(rows)
open(cp,"w",encoding="utf-8",newline="").write(buf.getvalue())
print("csv: rows now %d | new %d | unseated marks %d | superseded moves %d"%(len(rows),new_rows,drop_marks,sup_moves))
sel=[r for r in rows if r.get("selected_v4")=="yes"]
print("selected_v4 total:",len(sel))
yc=collections.Counter(r["filename"][:4] for r in sel)
print("by prefix year:",dict(sorted(yc.items())))
