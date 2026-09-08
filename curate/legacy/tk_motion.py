# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, zipfile, subprocess, shutil
H=os.path.expanduser("~")
TD=os.path.join(H,"photo-project","takeout")
TMP=os.path.join(H,"slideshow-work","tk_tmp"); FR=os.path.join(TMP,"frames")
os.makedirs(FR,exist_ok=True)
OUT=os.path.join(H,"slideshow-work","tk_motion.jsonl")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 130.0
t0=time.time()
short=json.load(open(os.path.join(H,"slideshow-work","tk_shortlist.json"),encoding="utf-8"))
# per month: top 5 standalone MOVs (honoree first, then people count)
cands=[(c["ym"],c) for c in short.get("movs",[])]
print("MOV candidates:",len(cands))
done=set()
if os.path.exists(OUT):
    for l in open(OUT,encoding="utf-8"):
        try: done.add(json.loads(l)["stem"])
        except Exception: pass
work=[(ym,c) for ym,c in cands if c["stem"] not in done]
print("todo:",len(work),flush=True)
zh={}
def zf(z):
    if z not in zh: zh[z]=zipfile.ZipFile(os.path.join(TD,z))
    return zh[z]
n=0
with open(OUT,"a",encoding="utf-8") as f:
    for ym,c in work:
        if time.time()-t0>BUDGET: break
        e=".mov"; z=c["zips"][e]; nm=c["members"][e]
        base=c["stem"].replace("/","_")
        loc=os.path.join(TMP,base+".mov")
        rec={"stem":c["stem"],"ym":ym,"date":c["date"],"honoree":c["honoree"],"npeople":c["npeople"],
             "zip":z,"member":nm,"size":c["sizes"][e]}
        try:
            if not os.path.exists(loc) or os.path.getsize(loc)!=c["sizes"][e]:
                with zf(z).open(nm) as src, open(loc,"wb") as dst:
                    shutil.copyfileobj(src,dst,1024*1024)
            out=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",loc],
                               capture_output=True,text=True,timeout=60).stdout
            d=json.loads(out or "{}")
            vs=[s for s in d.get("streams",[]) if s.get("codec_type")=="video"]
            dur=float((d.get("format") or {}).get("duration") or 0)
            w=hh=0; codec=""
            if vs:
                w=int(vs[0].get("width") or 0); hh=int(vs[0].get("height") or 0); codec=vs[0].get("codec_name","")
                rot=0
                for sd in vs[0].get("side_data_list") or []:
                    if "rotation" in sd:
                        try: rot=int(float(sd["rotation"]))
                        except Exception: pass
                if abs(rot)%180==90: w,hh=hh,w
            rec.update(dur=round(dur,1),w=w,h=hh,codec=codec,
                       audio=any(s.get("codec_type")=="audio" for s in d.get("streams",[])))
            for tag,frac in (("a",0.25),("b",0.6)):
                fp=os.path.join(FR,base+"_"+tag+".jpg")
                if not os.path.exists(fp):
                    subprocess.run(["ffmpeg","-y","-v","quiet","-ss",str(max(0.1,dur*frac)),"-i",loc,
                                    "-frames:v","1","-vf","scale=300:-1",fp],timeout=60)
            os.remove(loc)
        except Exception as ex:
            rec["err"]=str(ex)[:100]
            try: os.path.exists(loc) and os.remove(loc)
            except Exception: pass
        f.write(json.dumps(rec)+"\n"); f.flush(); n+=1
print("probed %d | elapsed %.0fs"%(n,time.time()-t0))
rem=len(work)-n
print("REMAINING",max(rem,0))
print("COMPLETE" if rem<=0 else "RERUN")
