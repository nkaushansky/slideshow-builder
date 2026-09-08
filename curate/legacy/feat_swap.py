# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, math, collections
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pillow_heif; pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS=None
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project")
MED=os.path.join(D,"slideshow-handoff","media")
fp=os.path.join(H,"slideshow-work","features.json")
fj=json.load(open(fp,encoding="utf-8"))
picks=fj["picks"]
names=sorted(os.listdir(MED))
def find(pref):
    m=[n for n in names if n.startswith(pref)]
    assert len(m)==1,(pref,m); return m[0]
# PORT: the owner's swaps come from the featured-sheet review; the legacy code reads one JSON file in the work folder:
#   {"swaps": [["<outgoing prefix>", "<incoming prefix>"], ...], "add": ["<prefix>", ...],
#    "alternate_year": "<YYYY>", "alternates": ["<filename>", ...]}
SWJ=json.load(open(os.path.join(H,"slideshow-work","feat_swaps.json"),encoding="utf-8"))
SW=[tuple(x) for x in SWJ.get("swaps",[])]
for outp,inp in SW:
    o=find(outp); i=find(inp)
    idx=picks.index(o); picks[idx]=i
    print("swap:",o,"->",i)
for pref in SWJ.get("add",[]):
    wa=find(pref)
    if wa not in picks: picks.append(wa); print("added:",wa)
fj["picks"]=picks
json.dump(fj,open(fp,"w"),indent=1)
yc=collections.Counter(p[:4] for p in picks)
print("features now:",len(picks),dict(sorted(yc.items())))

# lone alternate for one year: eligible stills of that year not picked
per={json.loads(l)["file"]:json.loads(l) for l in open(os.path.join(H,"slideshow-work","persons2.jsonl"),encoding="utf-8")}
ori={json.loads(l)["filename"]:json.loads(l) for l in open(os.path.join(H,"slideshow-work","oriented.jsonl"),encoding="utf-8")}
rm=json.load(open(os.path.join(H,"slideshow-work","rename_map.json"),encoding="utf-8"))
scan={}
for l in open(os.path.join(H,"slideshow-work","scan.jsonl"),encoding="utf-8"):
    d=json.loads(l); scan[d["name"]]=d
def srec(c): return scan.get(rm.get(c,c)) or {}
VID={".mp4",".mov",".gif"}
ALT_YEAR=SWJ.get("alternate_year",""); alt24=[]
for n in names:
    if n[:4]!=ALT_YEAR or os.path.splitext(n)[1].lower() in VID or n in picks: continue
    p=per.get(n,{}); o=ori.get(n,{})
    nn=int(p.get("n") or 0); fc=int(p.get("faces") or 0)
    if (nn>=1 or fc>=1) and nn<=3 and min(o.get("w",0),o.get("h",0))>=1000:
        alt24.append(n)
print(ALT_YEAR,"alternates:",alt24)
trio=alt24[:1]+SWJ.get("alternates",[])
TB=340
sheet=Image.new("RGB",(len(trio)*(TB+8)+8,TB+42),(248,248,246))
try: font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",13)
except Exception: font=ImageFont.load_default()
dr=ImageDraw.Draw(sheet)
for i,n in enumerate(trio):
    try:
        with Image.open(os.path.join(MED,n)) as im:
            im=ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((TB,TB))
            sheet.paste(im,(8+i*(TB+8)+(TB-im.width)//2,8+(TB-im.height)//2))
    except Exception as e: print("thumb err",n,e)
    p=per.get(n,{})
    dr.text((8+i*(TB+8),TB+12),"%d %s n=%s a=%.0f%%"%(i+1,n[:36],p.get("n","?"),100*float(p.get("area") or 0)),fill=(20,20,20),font=font)
out=os.path.join(D,"slideshow-all","_contact-sheets","features-seat62.jpg")
sheet.save(out,quality=82)
print("mini-sheet:",out)
