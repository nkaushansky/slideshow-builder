# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, csv, json, collections, io
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project"); SA=os.path.join(D,"slideshow-all")
HO=os.path.join(D,"slideshow-handoff"); MED=os.path.join(HO,"media")

names=sorted(n for n in os.listdir(MED) if not n.startswith("."))
assert len(names)==557, len(names)
ori={json.loads(l)["filename"]:json.loads(l) for l in open(os.path.join(H,"slideshow-work","oriented.jsonl"),encoding="utf-8")}
rm=json.load(open(os.path.join(H,"slideshow-work","rename_map.json"),encoding="utf-8"))
scan={}
for l in open(os.path.join(H,"slideshow-work","scan.jsonl"),encoding="utf-8"):
    d=json.loads(l); scan[d["name"]]=d
def srec(c): return scan.get(rm.get(c,c)) or scan.get(c) or {}
rows={r["filename"]:r for r in csv.DictReader(open(os.path.join(SA,"recovered-dates.csv"),encoding="utf-8"))}
tags=json.load(open(os.path.join(H,"slideshow-work","v4_tags.json"),encoding="utf-8"))
feats=set(json.load(open(os.path.join(H,"slideshow-work","features.json"),encoding="utf-8"))["picks"])
now={json.loads(l)["filename"]:json.loads(l) for l in open(os.path.join(H,"slideshow-work","exif_now.jsonl"),encoding="utf-8")}
assert len(feats)==75

IMGE={"jpg","jpeg","heic","png"}; VIDE={"mp4","mov"}
stem=lambda n: n.rsplit(".",1)[0]
ext=lambda n: n.rsplit(".",1)[-1].lower()
bystem=collections.defaultdict(list)
for n in names: bystem[stem(n)].append(n)
comp={}
for s,ns in bystem.items():
    if len(ns)==2:
        a,b=ns
        ia,ib=ext(a) in IMGE, ext(b) in IMGE
        va,vb=ext(a) in VIDE, ext(b) in VIDE
        if ia and vb: comp[a]=b; comp[b]=a
        elif va and ib: comp[b]=a; comp[a]=b

def typ(n):
    e=ext(n)
    if e=="gif": return "animated-gif"
    if e in VIDE: return "livephoto-video" if n in comp else "video"
    return "livephoto-still" if n in comp else "still"

def ysource(r,n,t):
    c=r["confidence"]
    if c.startswith("A - EXIF"):
        if t=="livephoto-video":
            bg=(r["best_guess_date"] or "").strip()
            pref=n[:10]
            norm=bg if len(bg)==10 else (bg+"-00" if len(bg)==7 else (bg+"-00-00" if len(bg)==4 else bg))
            return "exif" if norm==pref else "exif-companion"
        return "exif"
    if c.startswith("A - inherited"): return "exif-companion" if t=="livephoto-video" else "content-match"
    if c.startswith("B - filename"): return "filename"
    if c.startswith("B - calendar"): return "folder"
    if c.startswith("C"): return "content-match"
    if c.startswith("E"): return "visual-estimate"
    if c.startswith("F"): return "owner-corrected"
    return c.lower().replace(" ","-")

PREC={"exact day":"day","month":"month","year":"year"}
out=[]
for n in names:
    r=rows[n]; o=ori[n]; s=srec(n)
    t=typ(n)
    dur=o.get("dur","")
    dt=(now.get(n,{}) or {}).get("dt") or ""
    if dt.startswith("1970"): dt=""
    rec=dict(
        filename=n, type=t, companion=comp.get(n,""),
        width=o["w"], height=o["h"],
        duration_s=(("%.2f"%dur) if isinstance(dur,(int,float)) and dur else ""),
        exif_datetime_original=dt,
        inferred_year=n[:4], year_source=ysource(r,n,t),
        date=n[:10], precision=PREC.get(r["precision"],r["precision"]),
        tag=tags.get(n,"").lower(), featured=("yes" if n in feats else ""),
        video_codec=o.get("codec",""), has_audio=("yes" if o.get("audio") else ("no" if "codec" in o else "")),
        crisp_6across_5k=r.get("crisp_6across_5k",""), fills_1080p=r.get("fills_1080p",""),
        original_source_path=r["source_path"],
    )
    out.append(rec)
flds=list(out[0].keys())
buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=flds); w.writeheader(); w.writerows(out)
open(os.path.join(HO,"media.csv"),"w",encoding="utf-8",newline="").write(buf.getvalue())
print("media.csv rows:",len(out))
print("types:",dict(collections.Counter(r["type"] for r in out)))
print("year_source:",dict(collections.Counter(r["year_source"] for r in out)))
print("precision:",dict(collections.Counter(r["precision"] for r in out)))
print("per-year:",dict(sorted(collections.Counter(r["inferred_year"] for r in out).items())))
print("featured:",sum(1 for r in out if r["featured"]),"| tagged:",dict(collections.Counter(r["tag"] for r in out if r["tag"])))
print("with exif dt:",sum(1 for r in out if r["exif_datetime_original"]))
print("companions symmetric:",all(comp.get(comp[k])==k for k in comp))

open(os.path.join(HO,"features.txt"),"w",encoding="utf-8").write("\n".join(sorted(feats))+"\n")
print("features.txt lines:",len(feats))

# cut-list
allrows=list(rows.values())
cuts=[]
for r in allrows:
    if r.get("selected_v4")=="yes": continue
    loc=r["location"]; ev=r.get("evidence","")
    if loc=="_burst-duplicates":
        reason="duplicate" if ("pHash d=0" in ev or "pixel-identical" in ev) else "burst"
    elif loc=="_no-people": reason="no-people"
    elif loc=="_undated": reason="undated"
    elif loc=="_superseded-by-originals": reason="superseded"
    else: reason="over-cap"
    cuts.append(dict(filename=r["filename"],location=loc,reason=reason,original_source_path=r["source_path"]))
cuts.sort(key=lambda r:(r["reason"],r["filename"]))
buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=["filename","location","reason","original_source_path"]); w.writeheader(); w.writerows(cuts)
open(os.path.join(HO,"cut-list.csv"),"w",encoding="utf-8",newline="").write(buf.getvalue())
print("cut-list rows:",len(cuts),"| reasons:",dict(collections.Counter(r["reason"] for r in cuts)))
print("check 526+cuts:",526+len(cuts))

# stats for docs
tot=sum(os.path.getsize(os.path.join(MED,n)) for n in names)
print("media bytes:",tot)
exts=collections.Counter(ext(n) for n in names)
print("exts:",dict(exts))
port=sum(1 for n in names if ori[n]["h"]>ori[n]["w"])
print("portrait:",port)
longv=sorted(((ori[n]["dur"],n) for n in names if ori[n].get("codec")),reverse=True)[:6]
print("longest videos:",[(round(d),n) for d,n in longv])
p=ori.get("2023-00-00_JMK23.jpeg"); print("pano/scan:",p["w"],"x",p["h"])
