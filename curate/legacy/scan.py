# Legacy script from the first run, copied for the port (Day 1). Paths are placeholders
# (~/photo-project for the sources, ~/slideshow-work for caches) until this script is wired
# to curate/common.py and moved under curate/stages/ (Day 2). Not runnable as-is.
import os, sys, json, time, hashlib, subprocess, threading, warnings
warnings.filterwarnings("ignore")
import numpy as np, cv2
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import pillow_heif, imagehash
pillow_heif.register_heif_opener()
from concurrent.futures import ThreadPoolExecutor

DEST = os.path.expanduser("~/photo-project/slideshow-all")
OUT = os.path.expanduser("~/slideshow-work/scan.jsonl")
BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
start = time.time()
VIDEO_EXT = {".mp4",".mov",".m4v",".avi",".3gp",".mkv",".wmv",".mpg",".mpeg",".webm"}

done = set()
if os.path.exists(OUT):
    for line in open(OUT):
        try: done.add(json.loads(line)["name"])
        except Exception: pass

names = sorted(n for n in os.listdir(DEST)
               if os.path.isfile(os.path.join(DEST, n)) and n != "inventory.md")
todo = [n for n in names if n not in done]
print(f"total={len(names)} done={len(done)} todo={len(todo)}", flush=True)

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()

def exif_dt(img):
    try: ex = img.getexif()
    except Exception: return None
    cands = []
    for tag in (36867, 36868, 306):
        v = ex.get(tag)
        if not v:
            try: v = ex.get_ifd(0x8769).get(tag)
            except Exception: v = None
        if v: cands.append(str(v))
    for s in cands:
        s = s.strip().replace("/", ":")
        try:
            d, t = s.split(" ")[0], (s.split(" ") + ["00:00:00"])[1]
            y, mo, dy = d.split(":")[:3]
            if 1900 < int(y) < 2100:
                return f"{int(y):04d}-{int(mo):02d}-{int(dy):02d} {t[:8]}"
        except Exception: continue
    return None

def probe(p):
    try:
        r = subprocess.run(["ffprobe","-v","quiet","-print_format","json",
                            "-show_format","-show_streams",p],
                           capture_output=True, text=True, timeout=90)
        return json.loads(r.stdout)
    except Exception: return None

lock = threading.Lock()
fh = open(OUT, "a")
stop = threading.Event()

def work(n):
    if stop.is_set() or time.time() - start > BUDGET:
        stop.set(); return
    p = os.path.join(DEST, n)
    ext = os.path.splitext(n)[1].lower()
    rec = {"name":n,"ext":ext,"size":os.path.getsize(p),
           "kind":"video" if ext in VIDEO_EXT else "still",
           "sha":None,"dt":None,"w":None,"h":None,
           "phash":None,"sharp":None,"dur":None,"meta_err":None}
    try:
        rec["sha"] = sha256(p)
    except Exception as e:
        rec["meta_err"] = f"read failed: {type(e).__name__}"
    if rec["sha"]:
        if rec["kind"] == "video":
            info = probe(p)
            if not info: rec["meta_err"] = "ffprobe failed"
            else:
                try: rec["dur"] = round(float(info["format"]["duration"]), 2)
                except Exception: pass
                vs = next((s for s in info.get("streams",[]) if s.get("codec_type")=="video"), None)
                if vs: rec["w"], rec["h"] = vs.get("width"), vs.get("height")
                tags = {**info.get("format",{}).get("tags",{}), **((vs or {}).get("tags",{}))}
                for k in ("creation_time","com.apple.quicktime.creationdate","date","DateTimeOriginal"):
                    if tags.get(k):
                        rec["dt"] = str(tags[k]).replace("T"," ")[:19]; break
                if not rec["dt"]: rec["meta_err"] = "no creation timestamp"
        else:
            try:
                with Image.open(p) as img:
                    rec["w"], rec["h"] = img.size
                    rec["dt"] = exif_dt(img)
                    im = img.convert("L")
                    rec["phash"] = str(imagehash.phash(im, hash_size=16))
                    ls = max(im.size)
                    if ls > 512:
                        s = 512/ls
                        im = im.resize((max(1,int(im.width*s)), max(1,int(im.height*s))))
                    rec["sharp"] = round(float(cv2.Laplacian(np.asarray(im, dtype=np.float64), cv2.CV_64F).var()), 2)
                if not rec["dt"]: rec["meta_err"] = "no EXIF timestamp"
            except Exception as e:
                rec["meta_err"] = f"{type(e).__name__}: {str(e)[:120]}"
    with lock:
        fh.write(json.dumps(rec) + "\n"); fh.flush()

with ThreadPoolExecutor(max_workers=8) as ex:
    list(ex.map(work, todo))
fh.close()

n_done = sum(1 for _ in open(OUT))
print(f"ELAPSED {time.time()-start:.0f}s  scanned={n_done}/{len(names)}", flush=True)
print("COMPLETE" if n_done >= len(names) else "MORE", flush=True)
