# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, csv, subprocess, tempfile, warnings
warnings.filterwarnings("ignore")
import numpy as np, onnxruntime as ort, cv2
from PIL import Image, ImageOps, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES=True
import pillow_heif; pillow_heif.register_heif_opener()
WORK=os.path.expanduser("~/slideshow-work"); D=os.path.expanduser("~/photo-project/slideshow-all")
OUT=os.path.join(WORK,"persons2.jsonl")
BUDGET=float(sys.argv[1]) if len(sys.argv)>1 else 145.0
start=time.time()
sess=ort.InferenceSession(os.path.join(WORK,"model/yolov8n.onnx"),providers=["CPUExecutionProvider"])
INP=sess.get_inputs()[0].name
FD=cv2.FaceDetectorYN.create(os.path.join(WORK,"model/yunet.onnx"),"",(320,320),0.5,0.3,5000)
recs={json.loads(l)["name"]:json.loads(l) for l in open(os.path.join(WORK,"scan.jsonl"))}
m=json.load(open(os.path.join(WORK,"rename_map.json")))
o=lambda n:m.get(n,n)
rows=[r for r in csv.DictReader(open(os.path.join(D,"recovered-dates.csv"),encoding="utf-8"))
      if r["location"]=="slideshow-all"]
done=set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["file"])
        except Exception: pass
todo=[r for r in rows if r["filename"] not in done]
print("total %d | done %d | todo %d"%(len(rows),len(done),len(todo)),flush=True)
def nms(b,s,thr=.5):
    if len(b)==0: return []
    x1=b[:,0]-b[:,2]/2; y1=b[:,1]-b[:,3]/2; x2=b[:,0]+b[:,2]/2; y2=b[:,1]+b[:,3]/2
    ar=(x2-x1)*(y2-y1); order=s.argsort()[::-1]; keep=[]
    while order.size>0:
        i=order[0]; keep.append(i)
        xx1=np.maximum(x1[i],x1[order[1:]]); yy1=np.maximum(y1[i],y1[order[1:]])
        xx2=np.minimum(x2[i],x2[order[1:]]); yy2=np.minimum(y2[i],y2[order[1:]])
        w=np.maximum(0,xx2-xx1); h=np.maximum(0,yy2-yy1); inter=w*h
        order=order[1:][ (inter/(ar[i]+ar[order[1:]]-inter+1e-9)) <= thr]
    return keep
TMPD=tempfile.mkdtemp()
def load(r):
    n=r["filename"]; p=os.path.join(D,n)
    if recs[o(n)]["kind"]=="video":
        f=os.path.join(TMPD,"f.png")
        for ss in ("0.5","0"):
            subprocess.run(["ffmpeg","-y","-v","quiet","-ss",ss,"-i",p,"-frames:v","1",f],timeout=60)
            if os.path.exists(f) and os.path.getsize(f)>0: break
        if not (os.path.exists(f) and os.path.getsize(f)>0): return None
        im=Image.open(f).convert("RGB"); im.load(); os.remove(f); return im
    im=Image.open(p)
    try: im.draft("RGB",(1280,1280))
    except Exception: pass
    im=ImageOps.exif_transpose(im)          # <-- the fix: honour EXIF orientation
    return im.convert("RGB")
fh=open(OUT,"a")
for r in todo:
    if time.time()-start>BUDGET: break
    n=r["filename"]
    try:
        im=load(r)
        if im is None: fh.write(json.dumps({"file":n,"err":"no frame"})+"\n"); continue
        x=np.asarray(im.resize((640,640),Image.BILINEAR),dtype=np.float32).transpose(2,0,1)[None]/255.0
        y=sess.run(None,{INP:x})[0][0].T
        cls=y[:,4:]; best=cls.argmax(1); sc=cls[np.arange(len(cls)),best]
        sel=(best==0)&(sc>=0.25)
        if sel.any():
            b=y[sel,:4]; s=sc[sel]; k=nms(b,s)
            pn=len(k); pc=float(s[k].max()); pa=float(((b[k,2]*b[k,3])/(640*640)).max())
        else: pn,pc,pa=0,0.0,0.0
        # face detector as a second opinion (catches extreme close-ups YOLO misses)
        fn,fc=0,0.0
        try:
            a=np.asarray(im.resize((640,640),Image.BILINEAR))[:,:,::-1].copy()
            FD.setInputSize((640,640)); _,faces=FD.detect(a)
            if faces is not None and len(faces): fn=len(faces); fc=float(faces[:,-1].max())
        except Exception: pass
        fh.write(json.dumps({"file":n,"n":pn,"conf":round(pc,3),"area":round(pa,4),
                             "faces":fn,"fconf":round(fc,3)})+"\n"); fh.flush()
    except Exception as e:
        fh.write(json.dumps({"file":n,"err":str(e)[:100]})+"\n"); fh.flush()
fh.close()
nd=sum(1 for _ in open(OUT))
print("ELAPSED %.0fs  %d/%d"%(time.time()-start,nd,len(rows)),flush=True)
print("COMPLETE" if nd>=len(rows) else "MORE",flush=True)
