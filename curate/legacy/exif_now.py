# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, json, time, subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pillow_heif; pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS=None
H=os.path.expanduser("~")
MED=os.path.join(H,"photo-project","slideshow-handoff","media")
OUT=os.path.join(H,"slideshow-work","exif_now.jsonl")
names=sorted(n for n in os.listdir(MED) if not n.startswith("."))
VID={".mp4",".mov"}
def rd(n):
    p=os.path.join(MED,n); e=os.path.splitext(n)[1].lower()
    rec={"filename":n,"dt":""}
    try:
        if e in VID:
            out=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",p],capture_output=True,text=True,timeout=60).stdout
            d=json.loads(out or "{}")
            ct=((d.get("format") or {}).get("tags") or {}).get("creation_time","")
            if not ct:
                for s in d.get("streams",[]):
                    ct=(s.get("tags") or {}).get("creation_time","")
                    if ct: break
            rec["dt"]=(ct or "").replace("T"," ").replace("Z","")[:19]
        else:
            with Image.open(p) as im:
                ex=im.getexif()
                v=""
                try: v=ex.get_ifd(34665).get(36867) or ""
                except Exception: pass
                if not v: v=ex.get(306) or ""
                rec["dt"]=str(v).replace(":", "-",2)[:19] if v else ""
    except Exception as ex2:
        rec["err"]=str(ex2)[:80]
    return rec
t0=time.time()
with open(OUT,"w",encoding="utf-8") as f, ThreadPoolExecutor(12) as ex:
    for rec in ex.map(rd,names):
        f.write(json.dumps(rec)+"\n")
print("exif_now:",len(names),"in %.0fs"%(time.time()-t0))
