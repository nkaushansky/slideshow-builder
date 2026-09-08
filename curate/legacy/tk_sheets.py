# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, math, zipfile, io, collections
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pillow_heif; pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS=None
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project")
TD=os.path.join(D,"takeout")
V4=os.path.join(D,"slideshow-all v4")
FR=os.path.join(H,"slideshow-work","tk_tmp","frames")
seat=json.load(open(os.path.join(H,"slideshow-work","tk_seating.json"),encoding="utf-8"))
try:
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",13)
    fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",14)
except Exception: font=fb=ImageFont.load_default()
zh={}
def zread(z,m):
    if z not in zh: zh[z]=zipfile.ZipFile(os.path.join(TD,z))
    return zh[z].read(m)
def thumb(e,TB):
    try:
        if e["kind"]=="mov":
            fp=os.path.join(FR,e["file"][:-4].replace("/","_")+"_a.jpg")
            im=Image.open(fp).convert("RGB")
        elif e.get("member"):
            im=Image.open(io.BytesIO(zread(e["zip"],e["member"])))
            im=ImageOps.exif_transpose(im).convert("RGB")
        else:
            im=Image.open(os.path.join(V4,e["file"]))
            im=ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((TB,TB)); return im
    except Exception as ex:
        return None
BADGE={"mov":("NEW VIDEO",(200,60,30)),"newstill":("NEW",(30,110,200)),"newlp":("NEW LP",(30,110,200))}
for Y in ("2022","2023"):
    data=seat[Y]
    items=sorted(data["seated"],key=lambda e:(e["date"],e["file"]))
    drops=sorted(data["drops"],key=lambda e:(e["date"],e["file"]))
    TB=280; CAP=40; COLS=8
    n=len(items)+len(drops)
    rows=math.ceil(len(items)/COLS)+math.ceil(len(drops)/COLS)
    W=COLS*(TB+8)+8
    Hh=40+rows*(TB+CAP+8)+70
    sheet=Image.new("RGB",(W,Hh),(248,248,246))
    dr=ImageDraw.Draw(sheet)
    st=data["stats"]
    dr.text((10,6),"%s proposed — 33 moments | %d videos, %d upgraded originals (%d now Live Photos), drops below the line"%(Y,st["movs"],st["upgrades"],st["upgrade_lp"]),fill=(20,20,20),font=fb)
    y0=34
    for i,e in enumerate(items):
        r,c=divmod(i,COLS); x=8+c*(TB+8); y=y0+r*(TB+CAP+8)
        im=thumb(e,TB)
        if im: sheet.paste(im,(x+(TB-im.width)//2,y+(TB-im.height)//2))
        else: dr.text((x+8,y+TB//2),"(decode fail)",fill=(150,60,60),font=font)
        tagl=[]
        if e["kind"] in BADGE:
            t,col=BADGE[e["kind"]]; tagl.append((t,col))
        elif e.get("upgrade"):
            tagl.append(("UPGRADED"+("→LP" if e.get("lp") else ""),(20,130,60)))
        else: tagl.append(("KEPT",(120,120,120)))
        if e.get("featured"): tagl.append(("F",(160,80,160)))
        t,col=tagl[0]
        dr.text((x,y+TB+3),"%d %s %s"%(i+1,e["date"],t+(" +F" if len(tagl)>1 else "")),fill=col,font=fb)
        nm=e["file"] if len(e["file"])<=36 else e["file"][:33]+"..."
        extra=(" %ds"%round(e["dur"])) if e.get("dur") else ""
        dr.text((x,y+TB+21),nm+extra,fill=(120,120,120),font=font)
    y0=y0+math.ceil(len(items)/COLS)*(TB+CAP+8)+8
    dr.text((10,y0),"DROPPED to make room (still archived in slideshow-all):",fill=(160,40,40),font=fb)
    y0+=26
    for i,e in enumerate(drops):
        r,c=divmod(i,COLS); x=8+c*(TB+8); y=y0+r*(TB+CAP+8)
        im=thumb(e,TB)
        if im:
            im=im.convert("L").convert("RGB")
            sheet.paste(im,(x+(TB-im.width)//2,y+(TB-im.height)//2))
        dr.text((x,y+TB+3),"D%d %s"%(i+1,e["date"]),fill=(150,60,60),font=fb)
        dr.text((x,y+TB+21),e["file"][:36],fill=(120,120,120),font=font)
    out=os.path.join(D,"slideshow-all","_contact-sheets","takeout-proposal-%s.jpg"%Y)
    sheet.save(out,quality=80)
    print("sheet:",out,sheet.size)
