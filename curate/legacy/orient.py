# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pillow_heif; pillow_heif.register_heif_opener()

H=os.path.expanduser("~")
MED=os.path.join(H,"photo-project","slideshow-handoff","media")
OUT=os.path.join(H,"slideshow-work","oriented.jsonl")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
t0=time.time()

done=set()
if os.path.exists(OUT):
    for line in open(OUT,encoding="utf-8"):
        try: done.add(json.loads(line)["filename"])
        except Exception: pass
names=sorted(n for n in os.listdir(MED) if not n.startswith("."))
todo=[n for n in names if n not in done]
print("total %d done %d todo %d"%(len(names),len(done),len(todo)),flush=True)

IMGE={"jpg","jpeg","heic","png","gif"}; VIDE={"mp4","mov"}
def probe(n):
    p=os.path.join(MED,n); ext=n.rsplit(".",1)[-1].lower()
    rec={"filename":n}
    try:
        if ext in IMGE:
            with Image.open(p) as im:
                w,h=im.size; o=1
                try: o=int(im.getexif().get(274,1) or 1)
                except Exception: o=1
                if o in (5,6,7,8): w,h=h,w
                rec.update(w=w,h=h,orient=o)
                if ext=="gif" and im.format=="GIF":
                    try:
                        nf=getattr(im,"n_frames",1); dur=0.0
                        for i in range(nf):
                            im.seek(i); dur+=im.info.get("duration",100)/1000.0
                        rec.update(dur=round(dur,2),frames=nf)
                    except Exception: pass
        elif ext in VIDE:
            cmd=["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",p]
            out=subprocess.run(cmd,capture_output=True,text=True,timeout=90).stdout
            d=json.loads(out or "{}")
            vs=[s for s in d.get("streams",[]) if s.get("codec_type")=="video" and s.get("codec_name") not in ("mjpeg","png")]
            au=any(s.get("codec_type")=="audio" for s in d.get("streams",[]))
            w=h=0; rot=0; dur=0.0; codec=""
            if vs:
                s=vs[0]; w=int(s.get("width") or 0); h=int(s.get("height") or 0)
                codec=s.get("codec_name","")
                try: rot=int(float((s.get("tags") or {}).get("rotate",0)))
                except Exception: rot=0
                for sd in s.get("side_data_list") or []:
                    if "rotation" in sd:
                        try: rot=int(float(sd["rotation"]))
                        except Exception: pass
            try: dur=float((d.get("format") or {}).get("duration") or 0)
            except Exception: pass
            if abs(rot)%180==90: w,h=h,w
            rec.update(w=w,h=h,rotation=rot,dur=round(dur,2),codec=codec,audio=au)
        else:
            rec.update(w=0,h=0,note="unknown-ext")
    except Exception as e:
        rec["error"]=str(e)[:120]
    return rec

wrote=0; CH=48
with open(OUT,"a",encoding="utf-8") as f, ThreadPoolExecutor(12) as ex:
    i=0
    while i<len(todo):
        if time.time()-t0>BUDGET: break
        chunk=todo[i:i+CH]
        for rec in ex.map(probe,chunk):
            f.write(json.dumps(rec)+"\n"); wrote+=1
        f.flush(); i+=len(chunk)
        print("  %d/%d %.0fs"%(i,len(todo),time.time()-t0),flush=True)
rem=len(todo)-wrote
print("wrote %d | REMAINING %d | %.0fs"%(wrote,max(rem,0),time.time()-t0))
print("COMPLETE" if rem<=0 else "RERUN")
