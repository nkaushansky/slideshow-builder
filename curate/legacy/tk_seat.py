# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, csv, collections
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project"); SA=os.path.join(D,"slideshow-all")
B=os.path.join(H,"slideshow-work")
j=lambda p: json.load(open(os.path.join(B,p),encoding="utf-8"))
idx=[json.loads(l) for l in open(os.path.join(B,"takeout_index.jsonl"),encoding="utf-8") if "err" not in l[:200]]
med=[json.loads(l) for l in open(os.path.join(B,"takeout_media.jsonl"),encoding="utf-8")]
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ET=ZoneInfo(os.environ.get("SLIDESHOW_TZ","UTC"))  # PORT: config [project] timezone
byfs={}
for r in idx:
    stem=os.path.splitext(r.get("title",""))[0]
    d=None
    if r.get("ts"): d=datetime.fromtimestamp(r["ts"],tz=timezone.utc).astimezone(ET).strftime("%Y-%m-%d")
    byfs[(r.get("folder",""),stem)]=dict(date=d,people=r.get("people",[]),lat=r.get("lat"),lon=r.get("lon"))
mbys=collections.defaultdict(dict)
for m in med:
    p=m["member"].split("/")
    if len(p)>=4 and p[2].startswith("Photos from"):
        stem,ext=os.path.splitext(p[-1]); mbys[(p[2],stem)][ext.lower()]=m
def minfo(member):
    p=member.split("/"); stem=os.path.splitext(p[-1])[0]; fol=p[2]
    return (fol,stem), byfs.get((fol,stem)), mbys.get((fol,stem),{})
scores={}
for l in open(os.path.join(B,"tk_scores.jsonl"),encoding="utf-8"):
    d=json.loads(l)
    if "phash" in d: scores[d["zip"]+"|"+d["member"]]=d
tkhash={}
for l in open(os.path.join(B,"tk_phash.jsonl"),encoding="utf-8"):
    d=json.loads(l)
    if "phash" in d: tkhash[d["zip"]+"|"+d["member"]]=d
matches=j("tk_matches.json")
short=j("tk_shortlist.json")
motion={}
for l in open(os.path.join(B,"tk_motion.jsonl"),encoding="utf-8"):
    r=json.loads(l); motion[r["stem"]]=r
tags=j("v4_tags.json")
feats=set(j("features.json")["picks"])
rm=json.load(open(os.path.join(B,"rename_map.json"),encoding="utf-8"))
scan={}
for l in open(os.path.join(B,"scan.jsonl"),encoding="utf-8"):
    d=json.loads(l); scan[d["name"]]=d
def hd(a,b): return bin(int(a,16)^int(b,16)).count("1")

MOV={
"2022":{"01":["IMG_2986","IMG_2946"],"02":["IMG_3194","IMG_3136"],"03":["IMG_3341","IMG_3234"],
 "04":["IMG_3406","IMG_3485"],"05":["IMG_3703","IMG_3768"],"06":["IMG_4391","IMG_4390"],
 "07":["IMG_4492","IMG_4609"],"08":["IMG_5187","IMG_5058"],"09":["IMG_5634","IMG_5848"],
 "10":["IMG_6384","IMG_5083"],"11":["IMG_6932"],"12":["IMG_7347","IMG_7258"]},
"2023":{"01":["IMG_7594","IMG_7444"],"02":["IMG_8127","IMG_8473"],"03":["IMG_8658","CFA7F85D-EC6E-44D0-97F4-F9600F5A5E13"],
 "04":["IMG_9408","IMG_8968"],"05":["IMG_0149","IMG_0141"],"06":["IMG_0365","IMG_0306"],
 "07":["IMG_1372","IMG_1116"],"08":["IMG_1609","IMG_1737"],"09":["IMG_2306","IMG_1993"],
 "10":["IMG_2644","IMG_2558"],"11":["IMG_3032"],"12":["IMG_3453","IMG_3618"]}}
PRIORITY2={"2022":["10","09","07","12","08","05","03","01"],
           "2023":["10","09","07","12","06","04","01","02"]}

rows=[r for r in csv.DictReader(open(os.path.join(SA,"recovered-dates.csv"),encoding="utf-8"))
      if r.get("selected_v4")=="yes" and r["filename"][:4] in ("2022","2023")]
incs={"2022":[],"2023":[]}
for r in rows:
    cur=r["filename"]; m=matches.get(cur,{})
    e=dict(file=cur,kind="incumbent",date=cur[:10],prec=r["precision"],
           featured=cur in feats,tag=tags.get(cur,""),rank=r.get("v4_rank",""),
           phash=(scan.get(rm.get(cur,cur)) or {}).get("phash"))
    if m.get("best_d",999)<=12 and m.get("match"):
        key=m["match"]; z,member=key.split("|",1)
        ks,info,mm=minfo(member)
        if info and info.get("date"):
            e.update(upgrade=True,member=member,zip=z,date=info["date"],prec="exact day",
                     lp=(".mp4" in mm),phash=tkhash.get(key,{}).get("phash") or e["phash"])
    ty=e["date"][:4]
    if ty in incs: incs[ty].append(e)
    else: print("OUT-OF-SCOPE year:",ty,cur)
out={}
for Y in ("2022","2023"):
    inc=incs[Y]
    seated=list(inc)
    CAP=33
    def month(e): return e["date"][5:7] if e["date"][5:7]!="00" else None
    drops=[]
    prot=lambda e:(e["featured"] or e["tag"] or e.get("rank")=="pin")
    # near-dup flags among incumbents (same year)
    for i,a in enumerate(inc):
        for b in inc[i+1:]:
            if a.get("phash") and b.get("phash") and hd(a["phash"],b["phash"])<=26:
                (b if not prot(b) else a)["neardup"]=True
    def do_drop():
        mc=collections.Counter(month(e) for e in seated if month(e))
        cands=[e for e in seated if e["kind"]=="incumbent" and not prot(e)]
        def dk(e):
            m=month(e); r=e.get("rank"); rn=int(r) if str(r).isdigit() else 0
            return (0 if e.get("neardup") else 1, -mc.get(m,0), -rn)
        cands.sort(key=dk)
        for e in cands:
            m=month(e)
            if m and mc[m]<=1: continue
            seated.remove(e); drops.append(e); return True
        return False
    def enforce():
        while len(seated)>CAP:
            if not do_drop(): return False
        return True
    def seat(e):
        seated.append(e)
        if not enforce():
            if e in seated: seated.remove(e)
            enforce(); return False
        return True
    for mm_ in sorted(MOV[Y]):
        r=motion.get(MOV[Y][mm_][0])
        if r: seat(dict(file=MOV[Y][mm_][0]+".MOV",kind="mov",member=r["member"],zip=r["zip"],
                        date=r["date"],dur=r.get("dur"),why="motion-1 "+mm_,featured=False,tag="",motion=True))
    def motion_count(): return sum(1 for e in seated if e.get("motion") or e.get("lp"))
    for mm_ in PRIORITY2[Y]:
        if motion_count()>=17: break
        lst=MOV[Y].get(mm_,[])
        if len(lst)>1:
            r=motion.get(lst[1])
            if r: seat(dict(file=lst[1]+".MOV",kind="mov",member=r["member"],zip=r["zip"],
                            date=r["date"],dur=r.get("dur"),why="motion-2 "+mm_,featured=False,tag="",motion=True))
    # month balance: months with <2 moments get best takeout still, while cap allows a swap
    for _ in range(10):
        mc=collections.Counter(month(e) for e in seated if month(e))
        thin=[m for m in sorted(MOV[Y]) if mc.get(m,0)<2]
        if not thin: break
        mm_=thin[0]
        pool=[c for c in short["stills"].get(Y+"-"+mm_,[]) if c["honoree"]] or short["stills"].get(Y+"-"+mm_,[])
        best=None;bs=-1
        for c in pool:
            e0=".heic" if ".heic" in c["members"] else sorted(c["members"])[0]
            key=c["zips"].get(e0,"")+"|"+c["members"].get(e0,"")
            sc0=scores.get(key)
            if not sc0: continue
            ph=sc0.get("phash")
            if ph and any(x.get("phash") and hd(ph,x["phash"])<=26 for x in seated if x.get("phash")): continue
            v=(sc0.get("sharp",0)/3000)+(sc0.get("w",0)*sc0.get("h",0))/12e6+(2 if c["honoree"] else 0)
            if v>bs: bs=v; best=(c,sc0,key,e0)
        if not best: break
        c,sc0,key,e0=best
        okd=seat(dict(file=c["stem"]+e0.upper(),kind="newstill",member=c["members"][e0],zip=c["zips"][e0],
                      date=c["date"],lp=(c["lp"] and ".mp4" in c["members"]),phash=sc0.get("phash"),
                      why="fill "+mm_,featured=False,tag=""))
        if not okd: break
    # if still under cap (year had few incumbents), top up with best remaining takeout stills
    allmonths=sorted(MOV[Y])
    ptr=0
    while len(seated)<CAP and ptr<400:
        ptr+=1
        mc=collections.Counter(month(e) for e in seated if month(e))
        mm_=min(allmonths,key=lambda m:mc.get(m,0))
        pool=[c for c in short["stills"].get(Y+"-"+mm_,[]) if c["honoree"]] or short["stills"].get(Y+"-"+mm_,[])
        best=None;bs=-1
        for c in pool:
            e0=".heic" if ".heic" in c["members"] else sorted(c["members"])[0]
            key=c["zips"].get(e0,"")+"|"+c["members"].get(e0,"")
            sc0=scores.get(key)
            if not sc0: continue
            ph=sc0.get("phash")
            if ph and any(x.get("phash") and hd(ph,x["phash"])<=26 for x in seated if x.get("phash")): continue
            v=(sc0.get("sharp",0)/3000)+(sc0.get("w",0)*sc0.get("h",0))/12e6+(2 if c["honoree"] else 0)
            if v>bs: bs=v; best=(c,sc0,key,e0)
        if not best:
            allmonths=[m for m in allmonths if m!=mm_]
            if not allmonths: break
            continue
        c,sc0,key,e0=best
        seated.append(dict(file=c["stem"]+e0.upper(),kind="newstill",member=c["members"][e0],zip=c["zips"][e0],
                           date=c["date"],lp=(c["lp"] and ".mp4" in c["members"]),phash=sc0.get("phash"),
                           why="topup "+mm_,featured=False,tag=""))
    ups=sum(1 for e in seated if e.get("upgrade"))
    uplp=sum(1 for e in seated if e.get("lp") and e.get("upgrade"))
    out[Y]=dict(seated=[{k:v for k,v in e.items() if k!="phash"} for e in seated],
                drops=[{k:v for k,v in e.items() if k!="phash"} for e in drops],
                stats=dict(total=len(seated),drops=len(drops),movs=sum(1 for e in seated if e["kind"]=="mov"),
                           newstill=sum(1 for e in seated if e["kind"]=="newstill"),
                           upgrades=ups,upgrade_lp=uplp,motion=sum(1 for e in seated if e.get("motion") or e.get("lp"))))
    print(Y,out[Y]["stats"])
    print("  months:",dict(sorted(collections.Counter(e["date"][5:7] for e in seated if e["date"][5:7]!="00").items())),
          "| dateless:",sum(1 for e in seated if e["date"][5:7]=="00"))
json.dump(out,open(os.path.join(B,"tk_seating.json"),"w"),indent=1)
print("saved tk_seating.json")
