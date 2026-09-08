# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, csv, time, subprocess, warnings
warnings.filterwarnings("ignore")
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES=True
import pillow_heif; pillow_heif.register_heif_opener()
W=os.path.expanduser("~/slideshow-work"); D=os.path.expanduser("~/photo-project/slideshow-all")
OUT=os.path.join(W,"gps.jsonl")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
start=time.time()
done=set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["file"])
        except Exception: pass
rows=[r for r in csv.DictReader(open(os.path.join(D,"recovered-dates.csv"),encoding="utf-8"))
      if r["location"]=="slideshow-all"]
todo=[r for r in rows if r["filename"] not in done]
print("total %d done %d todo %d"%(len(rows),len(done),len(todo)),flush=True)
def dms(v,ref):
    try:
        d=float(v[0]); m=float(v[1]); s=float(v[2])
        x=d+m/60+s/3600
        return -x if ref in ("S","W") else x
    except Exception: return None
def still_gps(p):
    with Image.open(p) as im:
        ex=im.getexif()
        try: g=ex.get_ifd(34853)
        except Exception: return None
        if not g: return None
        lat=dms(g.get(2),g.get(1,"N")); lon=dms(g.get(4),g.get(3,"E"))
        if lat is None or lon is None or (lat==0 and lon==0): return None
        return round(lat,5),round(lon,5)
def vid_gps(p):
    try:
        r=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format",p],
                         capture_output=True,text=True,timeout=60)
        tags=json.loads(r.stdout).get("format",{}).get("tags",{})
        for k in ("com.apple.quicktime.location.ISO6709","location","location-eng"):
            v=tags.get(k)
            if v:
                import re
                mm=re.match(r'^([+-]\d+\.\d+)([+-]\d+\.\d+)',v)
                if mm: return round(float(mm.group(1)),5),round(float(mm.group(2)),5)
    except Exception: pass
    return None
fh=open(OUT,"a")
for r in todo:
    if time.time()-start>BUDGET: break
    n=r["filename"]; p=os.path.join(D,n)
    ext=os.path.splitext(n)[1].lower()
    g=None
    try:
        g=vid_gps(p) if ext in (".mov",".mp4",".m4v") else still_gps(p)
    except Exception: pass
    fh.write(json.dumps({"file":n,"gps":g})+"\n")
fh.close()
nd=sum(1 for _ in open(OUT))
print("ELAPSED %.0fs %d/%d"%(time.time()-start,nd,len(rows)),flush=True)
print("COMPLETE" if nd>=len(rows) else "MORE",flush=True)
