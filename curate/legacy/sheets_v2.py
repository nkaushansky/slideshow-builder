# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, csv, time, subprocess, tempfile, collections, warnings
warnings.filterwarnings("ignore")
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES=True
import pillow_heif; pillow_heif.register_heif_opener()
D=os.path.expanduser("~/photo-project/slideshow-all")
V=os.path.expanduser("~/photo-project/slideshow-all v2")
CS=os.path.join(V,"_contact-sheets"); os.makedirs(CS,exist_ok=True)
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
start=time.time()
rows=[r for r in csv.DictReader(open(os.path.join(D,"recovered-dates.csv"),encoding="utf-8"))
      if r.get("selected_v2")=="yes"]
byy=collections.defaultdict(list)
for r in rows: byy[r["best_guess_date"][:4]].append(r)
TH=250; PAD=9; LAB=28; COLS=7
try:
    f1=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",11)
    fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",12)
    fh=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",19)
except Exception: f1=fb=fh=ImageFont.load_default()
T=tempfile.mkdtemp()

def robust_video_frame(p,TH):
    import numpy as _np
    best=None; bestb=-1
    for ss in ("0.5","1.5","3.0","6.0"):
        f=os.path.join(T,"f.png")
        subprocess.run(["ffmpeg","-y","-v","quiet","-ss",ss,"-i",p,"-frames:v","1",f],timeout=60)
        if not (os.path.exists(f) and os.path.getsize(f)>0): continue
        im=Image.open(f).convert("RGB"); im.load(); os.remove(f)
        b=float(_np.asarray(im.convert("L").resize((32,32)),dtype=float).mean())
        if b>bestb: best,bestb=im,b
        if b>=20: break
    if best is None: return None
    best.thumbnail((TH,TH),Image.LANCZOS); return best
def robust_gif_mid(im):
    try:
        n=getattr(im,"n_frames",1)
        if n>1 and im.format=="GIF":
            im.seek(n//2)
            fr=im.convert("RGBA")
            bg=Image.new("RGBA",fr.size,(255,255,255,255))
            return Image.alpha_composite(bg,fr).convert("RGB")
    except Exception: pass
    return im.convert("RGB")

def th(n):
    p=os.path.join(V,n)
    try:
        im=Image.open(p)
        try: im.draft("RGB",(TH*3,TH*3))
        except Exception: pass
        im=robust_gif_mid(im)
        im=ImageOps.exif_transpose(im); im.thumbnail((TH,TH),Image.LANCZOS); return im,False
    except Exception:
        im=robust_video_frame(p,TH)
        if im is not None: return im,True
        return Image.new("RGB",(TH,int(TH*.7)),(235,235,235)),True
FIRST_YEAR=2000; LAST_YEAR=2014; BIRTH_MONTH="January"; HONOREE="honoree"  # PORT: config [honoree] and [show]
AGE={FIRST_YEAR:"born "+BIRTH_MONTH,**{y:"age %d-%d"%(y-FIRST_YEAR-1,y-FIRST_YEAR) for y in range(FIRST_YEAR+1,LAST_YEAR+1)}}
for y in sorted(byy):
    out=os.path.join(CS,"%s.jpg"%y)
    if os.path.exists(out): continue
    if time.time()-start>BUDGET: break
    L=sorted(byy[y],key=lambda r:(r["best_guess_date"],r["filename"]))
    ims=[(r,)+th(r["filename"]) for r in L]
    R=[ims[i:i+COLS] for i in range(0,len(ims),COLS)]
    Wd=COLS*(TH+PAD)+PAD; Ht=sum(max(t[1].height for t in rr)+LAB+PAD for rr in R)+PAD+52
    sh=Image.new("RGB",(Wd,Ht),(250,250,250)); d=ImageDraw.Draw(sh)
    shared=sum(1 for r in L if r["selected"]=="yes")
    d.text((PAD,12),"%s  (v2)  -  %s %s"%(y,HONOREE,AGE.get(int(y),"")),font=fh,fill=(15,15,15))
    d.text((PAD,34),"%d files - %d also in v1, %d new  -  * marks a pick shared with v1"%(len(L),shared,len(L)-shared),font=fb,fill=(110,110,110))
    yy=52+PAD
    for rr in R:
        rh=max(t[1].height for t in rr); x=PAD
        for r,im,isv in rr:
            sh.paste(im,(x,yy))
            col=(170,70,30) if isv else (55,80,160)
            d.rectangle([x-2,yy-2,x+im.width+1,yy+im.height+1],outline=col,width=2)
            tag="* " if r["selected"]=="yes" else ""
            lab=r["best_guess_date"]
            if r["precision"]=="month": lab+=" (mo)"
            elif r["precision"]=="year": lab+=" (yr)"
            d.text((x,yy+im.height+3),tag+("VIDEO " if isv else "")+lab,font=fb,fill=col)
            d.text((x,yy+im.height+15),r["filename"][11:][:34],font=f1,fill=(105,105,105))
            x+=TH+PAD
        yy+=rh+LAB+PAD
    sh.save(out,"JPEG",quality=86)
    print("wrote %s (%d files)"%(os.path.basename(out),len(L)),flush=True)
done=len([f for f in os.listdir(CS) if f.endswith(".jpg")])
print("sheets %d/%d"%(done,len(byy)),flush=True)
print("COMPLETE" if done>=len(byy) else "MORE",flush=True)
