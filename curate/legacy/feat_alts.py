# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, math
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pillow_heif; pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS=None
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project")
MED=os.path.join(D,"slideshow-handoff","media")
fj=json.load(open(os.path.join(H,"slideshow-work","features.json"),encoding="utf-8"))
picked=set(fj["picks"])
det={p["f"]:p for p in fj["detail"]}
import csv, collections
# rebuild eligible pool from features.py logic (reuse detail? detail only has picks) -> recompute
ori={json.loads(l)["filename"]:json.loads(l) for l in open(os.path.join(H,"slideshow-work","oriented.jsonl"),encoding="utf-8")}
per={}
for l in open(os.path.join(H,"slideshow-work","persons2.jsonl"),encoding="utf-8"):
    d=json.loads(l); per[d["file"]]=d
rm=json.load(open(os.path.join(H,"slideshow-work","rename_map.json"),encoding="utf-8"))
scan={}
for l in open(os.path.join(H,"slideshow-work","scan.jsonl"),encoding="utf-8"):
    d=json.loads(l); scan[d["name"]]=d
def srec(cur): return scan.get(rm.get(cur,cur)) or scan.get(cur) or {}
VID={".mp4",".mov"}; GIF={".gif"}
names=sorted(n for n in os.listdir(MED) if not n.startswith("."))
stills=[n for n in names if os.path.splitext(n)[1].lower() not in VID|GIF]
import bisect
sharps=sorted(srec(n).get("sharp") or 0 for n in stills)
ress=sorted((ori[n]["w"]*ori[n]["h"]) for n in stills)
def pct(v,arr): return bisect.bisect_left(arr,v)/max(1,len(arr)-1)
cands=collections.defaultdict(list)
for n in stills:
    if n in picked: continue
    o=ori[n]; p=per.get(n,{}); s=srec(n)
    w,h=o["w"],o["h"]; nn=int(p.get("n") or 0); faces=int(p.get("faces") or 0); area=float(p.get("area") or 0)
    sharp=s.get("sharp") or 0
    if not ((nn>=1 or faces>=1) and nn<=3 and min(w,h)>=1000 and max(w,h)>=1500 and pct(sharp,sharps)>=0.10): continue
    score=0.45*min(area,0.8)/0.8+0.20*pct(sharp,sharps)+0.15*pct(w*h,ress)+0.10*(1.0 if nn<=2 else 0.4)+0.10*(1.0 if faces>0 else 0.0)
    cands[n[:4]].append((score,n,nn,faces,area))
YEARS=["2016","2018","2021","2022","2023","2025"]
show=[]
for y in YEARS:
    for sc,n,nn,f,a in sorted(cands[y],reverse=True)[:6]:
        show.append((y,n,nn,f,a,sc))
print("alts:",len(show))
TB=280; CAP=34; COLS=6
rows=math.ceil(len(show)/COLS)
W=COLS*(TB+8)+8; Hh=rows*(TB+CAP+8)+8
sheet=Image.new("RGB",(W,Hh),(248,248,246))
try: font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",12)
except Exception: font=ImageFont.load_default()
def th(t):
    n=t[1]
    try:
        with Image.open(os.path.join(MED,n)) as im:
            im=ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((TB,TB)); return n,im
    except Exception: return n,None
with ThreadPoolExecutor(12) as ex: thumbs=dict(ex.map(th,show))
dr=ImageDraw.Draw(sheet)
for i,(y,n,nn,f,a,sc) in enumerate(show):
    r,c=divmod(i,COLS); x=8+c*(TB+8); yy=8+r*(TB+CAP+8)
    im=thumbs.get(n)
    if im: sheet.paste(im,(x+(TB-im.width)//2,yy+(TB-im.height)//2))
    dr.text((x,yy+TB+2),"%s %s"%(chr(65+i),n[:34]),fill=(20,20,20),font=font)
    dr.text((x,yy+TB+17),"%s n=%d f=%d a=%.0f%% s=%.2f"%(y,nn,f,100*a,sc),fill=(90,90,90),font=font)
out=os.path.join(D,"slideshow-all","_contact-sheets","features-alts.jpg")
sheet.save(out,quality=80)
print("sheet:",out,sheet.size)
