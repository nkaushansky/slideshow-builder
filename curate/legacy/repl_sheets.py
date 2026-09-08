# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, math, subprocess
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pillow_heif; pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS=None
H=os.path.expanduser("~")
D=os.path.join(H,"photo-project")
SA=os.path.join(D,"slideshow-all"); MED=os.path.join(D,"slideshow-handoff","media")
OUT=os.path.join(D,"replacements-round1","sheets")
os.makedirs(OUT,exist_ok=True)
pools=json.load(open(os.path.join(H,"slideshow-work","repl_pools.json"),encoding="utf-8"))
try:
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",15)
    fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",17)
except Exception: font=fb=ImageFont.load_default()
TB=400; CAP=46; COLS=4
def thumb(path):
    ext=os.path.splitext(path)[1].lower()
    if ext in (".mov",".mp4"):
        tmp=os.path.join(H,"slideshow-work","_fr.jpg")
        try:
            out=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format",path],capture_output=True,text=True,timeout=60).stdout
            dur=float(json.loads(out or "{}").get("format",{}).get("duration") or 1)
        except Exception: dur=1
        subprocess.run(["ffmpeg","-y","-v","quiet","-ss",str(max(0.1,dur*0.3)),"-i",path,"-frames:v","1","-vf","scale=%d:-1"%TB,tmp],timeout=60)
        if os.path.exists(tmp):
            im=Image.open(tmp).convert("RGB"); os.remove(tmp); return im
        return None
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((TB,TB)); return im.copy()
def label(f,maxlen=44):
    return f if len(f)<=maxlen else f[:22]+"…"+f[-(maxlen-23):]
for L,cands in pools.items():
    items=[("LEAVING",dict(file=L),os.path.join(MED,L))]
    for i,c in enumerate(cands):
        items.append(("C%d"%(i+1),c,os.path.join(SA,c["file"])))
    rows=math.ceil(len(items)/COLS)
    W=COLS*(TB+10)+10; Hh=44+rows*(TB+CAP+10)
    sheet=Image.new("RGB",(W,Hh),(248,248,246))
    dr=ImageDraw.Draw(sheet)
    dr.text((12,8),"Replacing: "+L+"   (pick by C-number)",fill=(20,20,20),font=fb)
    for k,(tag,c,path) in enumerate(items):
        r,cc=divmod(k,COLS); x=10+cc*(TB+10); y=44+r*(TB+CAP+10)
        try:
            im=thumb(path)
            if im is None: raise RuntimeError("no frame")
            if tag=="LEAVING":
                dr.rectangle([x-3,y-3,x+TB+3,y+TB+3],outline=(190,40,40),width=3)
            sheet.paste(im,(x+(TB-im.width)//2,y+(TB-im.height)//2))
        except Exception as e:
            dr.text((x+10,y+30),"decode fail",fill=(180,50,50),font=font)
        if tag=="LEAVING":
            dr.text((x,y+TB+4),"LEAVING  "+label(c["file"]),fill=(190,40,40),font=fb)
        else:
            bits=[tag]
            if c.get("pair"): bits.append("PAIR")
            if c.get("video"): bits.append("VIDEO")
            bits.append("±%dd"%c["dist"])
            if c.get("real"): bits.append("really "+c["real"])
            dr.text((x,y+TB+4)," ".join(bits),fill=(20,90,170) if not c.get("pair") else (140,60,160),font=fb)
            dr.text((x,y+TB+25),label(c["file"]),fill=(110,110,110),font=font)
    outp=os.path.join(OUT,L+".jpg")
    sheet.save(outp,quality=82)
    print("sheet:",os.path.basename(outp),sheet.size)
