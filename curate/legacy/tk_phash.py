# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, zipfile, threading, io
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageOps
import pillow_heif; pillow_heif.register_heif_opener()
import imagehash
Image.MAX_IMAGE_PIXELS=60_000_000
H=os.path.expanduser("~")
TD=os.path.join(H,"photo-project","takeout")
OUT=os.path.join(H,"slideshow-work","tk_phash.jsonl")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
t0=time.time()
STILL={".heic",".jpg",".jpeg",".png",".webp"}
med=json.load(open(os.path.join(H,"slideshow-work","tk_phash_order.json"),encoding="utf-8"))
todo=[]
seenk=set()
for m in med:
    nm=m["member"]
    if os.path.splitext(nm)[1].lower() not in STILL: continue
    if "/Photos from 2022/" not in nm and "/Photos from 2023/" not in nm: continue
    k=m["zip"]+"|"+nm
    if k in seenk: continue
    seenk.add(k); todo.append(m)
done=set()
if os.path.exists(OUT):
    for l in open(OUT,encoding="utf-8"):
        try: d=json.loads(l); done.add(d["zip"]+"|"+d["member"])
        except Exception: pass
work=[m for m in todo if (m["zip"]+"|"+m["member"]) not in done]  # todo preserves priority order
print("stills total %d | done %d | todo %d"%(len(todo),len(done),len(work)),flush=True)
tl=threading.local()
def zh(zp):
    d=getattr(tl,"h",None)
    if d is None: d={}; tl.h=d
    if zp not in d: d[zp]=zipfile.ZipFile(os.path.join(TD,zp))
    return d[zp]
def ph(m):
    r={"zip":m["zip"],"member":m["member"]}
    try:
        if m.get("size",0)>80_000_000:
            r["err"]="skipped-huge"; return r
        b=zh(m["zip"]).read(m["member"])
        with Image.open(io.BytesIO(b)) as im:
            o=1
            try: o=int(im.getexif().get(274,1) or 1)
            except Exception: pass
            im=ImageOps.exif_transpose(im)
            w,h=im.size
            im=im.convert("RGB")
            r.update(phash=str(imagehash.phash(im,hash_size=16)),w=w,h=h,orient=o)
    except Exception as e:
        r["err"]=str(e)[:80]
    return r
wrote=0; CH=96
with open(OUT,"a",encoding="utf-8") as f, ThreadPoolExecutor(4) as ex:
    i=0
    while i<len(work):
        if time.time()-t0>BUDGET: break
        chunk=work[i:i+CH]
        for r in ex.map(ph,chunk):
            f.write(json.dumps(r)+"\n"); wrote+=1
        f.flush(); i+=len(chunk)
        el=time.time()-t0
        print("  %d/%d  %.0fs  (%.1f/s)"%(i,len(work),el,(wrote/el if el else 0)),flush=True)
rem=len(work)-wrote
print("wrote %d | REMAINING %d"%(wrote,max(rem,0)))
print("COMPLETE" if rem<=0 else "RERUN")
