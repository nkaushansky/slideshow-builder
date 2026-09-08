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
picks=list(fj["picks"])
det={p["f"]:p for p in fj["detail"]}
EXTRA=[]  # PORT: owner-added featured picks from the review round
for extra in EXTRA:
    if extra not in picks: picks.append(extra)
TB=300; CAP=34; COLS=8
rows=math.ceil(len(picks)/COLS)
W=COLS*(TB+8)+8; Hh=rows*(TB+CAP+8)+8
sheet=Image.new("RGB",(W,Hh),(248,248,246))
try: font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",13)
except Exception: font=ImageFont.load_default()
def th(n):
    try:
        with Image.open(os.path.join(MED,n)) as im:
            im=ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((TB,TB))
            return n,im
    except Exception as e: return n,None
with ThreadPoolExecutor(12) as ex: thumbs=dict(ex.map(th,picks))
dr=ImageDraw.Draw(sheet)
for i,n in enumerate(picks):
    r,c=divmod(i,COLS)
    x=8+c*(TB+8); y=8+r*(TB+CAP+8)
    im=thumbs.get(n)
    if im:
        ox=x+(TB-im.width)//2; oy=y+(TB-im.height)//2
        sheet.paste(im,(ox,oy))
    d=det.get(n,{})
    lab="%d %s"%(i+1,n[:30])
    sub="%s n=%s f=%s a=%.0f%%"%(n[:4],d.get("n","?"),d.get("faces","?"),100*float(d.get("area") or 0)) if d else n[:4]+" (owner pin, no detector data)"
    dr.text((x,y+TB+2),lab,fill=(20,20,20),font=font)
    dr.text((x,y+TB+17),sub,fill=(120,40,40) if (d.get("n")==3 or not d) else (90,90,90),font=font)
out=os.path.join(D,"slideshow-all","_contact-sheets","features-candidates.jpg")
sheet.save(out,quality=80)
print("sheet:",out,sheet.size,os.path.getsize(out))
