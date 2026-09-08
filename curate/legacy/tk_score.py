# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, zipfile, threading, io
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2
from PIL import Image, ImageOps
import pillow_heif; pillow_heif.register_heif_opener()
import imagehash
Image.MAX_IMAGE_PIXELS=None
H=os.path.expanduser("~")
TD=os.path.join(H,"photo-project","takeout")
OUT=os.path.join(H,"slideshow-work","tk_scores.jsonl")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
t0=time.time()
short=json.load(open(os.path.join(H,"slideshow-work","tk_shortlist.json"),encoding="utf-8"))
IMGE=(".heic",".jpg",".jpeg",".png")
work={}
def add(c):
    for e in IMGE:
        if e in c["members"]:
            k=c["zips"][e]+"|"+c["members"][e]
            work[k]=(c["zips"][e],c["members"][e]); return
for ym,arr in short["stills"].items():
    for c in arr: add(c)
for ym,arr in short["motion"].items():
    for c in arr: add(c)
done=set()
if os.path.exists(OUT):
    for l in open(OUT,encoding="utf-8"):
        try: d=json.loads(l); done.add(d["zip"]+"|"+d["member"])
        except Exception: pass
items=[v for k,v in sorted(work.items()) if k not in done]
print("scoring targets %d | done %d | todo %d"%(len(work),len(done),len(items)),flush=True)
tl=threading.local()
def zh(zp):
    d=getattr(tl,"h",None) or {}; tl.h=d
    if zp not in d: d[zp]=zipfile.ZipFile(os.path.join(TD,zp))
    return d[zp]
def sc(t):
    zp,nm=t; r={"zip":zp,"member":nm}
    try:
        b=zh(zp).read(nm)
        with Image.open(io.BytesIO(b)) as im:
            im=ImageOps.exif_transpose(im)
            w,h=im.size
            im=im.convert("RGB")
            r.update(w=w,h=h,phash=str(imagehash.phash(im,hash_size=16)))
            im.thumbnail((1024,1024))
            g=cv2.cvtColor(np.array(im),cv2.COLOR_RGB2GRAY)
            r["sharp"]=float(cv2.Laplacian(g,cv2.CV_64F).var())
    except Exception as e:
        r["err"]=str(e)[:80]
    return r
wrote=0; CH=96
with open(OUT,"a",encoding="utf-8") as f, ThreadPoolExecutor(8) as ex:
    i=0
    while i<len(items):
        if time.time()-t0>BUDGET: break
        for r in ex.map(sc,items[i:i+CH]):
            f.write(json.dumps(r)+"\n"); wrote+=1
        f.flush(); i+=CH
        el=time.time()-t0
        print("  %d/%d %.0fs (%.1f/s)"%(min(i,len(items)),len(items),el,wrote/el),flush=True)
rem=len(items)-wrote
print("wrote %d | REMAINING %d"%(wrote,max(rem,0)))
print("COMPLETE" if rem<=0 else "RERUN")
