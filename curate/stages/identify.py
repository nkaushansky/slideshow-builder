"""identify: who is in frame, per file, from index/items.csv into index/people.csv.

Version 0.1 does **presence only**: a person detector (a YOLOv8-style ONNX model by default,
or any detector the config names) gives the person count and how much of the frame people fill;
a face detector (YuNet) gives the face count and the largest face. The identity gate, which
matches faces against the owner's seed photos and fills ``people`` and ``family_present``, is a
later milestone; those two columns are written blank here so the selection's family gate has
somewhere to look once it exists. Presence is not identity (references/08, lesson 2): the sheets
print these numbers so the reviewer knows what the detector saw, not who.

Every image is EXIF-transposed before detection; the first run ran a whole pass on stored
(rotated) pixels before that was fixed. Videos and GIFs are detected on their first frame
(GIF through Pillow; video through ffmpeg when it is available, else skipped and counted).

Models must be listed in curate/models/manifest.json with a matching SHA-256, which the setup
step writes; a model that is not on the manifest is refused so a stray file never runs silently.
Nothing is uploaded anywhere; everything runs on the CPU through onnxruntime and OpenCV.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import project, write_atomic, say, media_id  # noqa: E402

warnings.filterwarnings("ignore")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # OpenCV 5 warns about backend targets on every YuNet create; harmless

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:  # HEIC files will fail to open and be counted as errors, which the report shows
    pass

PEOPLE_COLUMNS = ["media_id", "filename", "persons", "person_area", "largest_person", "faces", "largest_face",
                  "group_size", "people", "family_present"]
DEFAULT_PERSON = "yolov8n.onnx"
DEFAULT_FACE = "yunet.onnx"
PERSON_CONF = 0.25
PERSON_IOU = 0.5
FACE_CONF = 0.5
FACE_NMS = 0.3
LONG_SIDE = 1280           # decode target; detectors resize from here
UNION_GRID = 512           # person_area is measured on a grid this wide (union of boxes, not a sum)
GROUP_CAP = 6
STILL_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png"}
VIDEO_EXT = {".mov", ".mp4", ".m4v"}
GIF_EXT = {".gif"}


# ---------------------------------------------------------------- models and the manifest

def manifest_path(P) -> Path:
    return P.models / "manifest.json"


def resolve_model(P, key: str, default_name: str) -> Path:
    raw = (P.get("models", key, "") or "").strip()
    if not raw:
        return P.models / default_name
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = P.root / p
    return p.resolve()


def check_manifest(P, model_file: Path, purpose: str) -> dict:
    """Return the manifest entry for this model file, or exit with a clear message."""
    mp = manifest_path(P)
    if not mp.is_file():
        raise SystemExit(f"identify: {mp} is missing. Run `python curate/setup.py` to fetch the default models "
                         f"and write the manifest, or point [models] in config.toml at your own files and run setup with --skip-models.")
    try:
        entries = json.loads(mp.read_text(encoding="utf-8")).get("models", [])
    except json.JSONDecodeError as e:
        raise SystemExit(f"identify: {mp} is not valid JSON: {e}")
    if not model_file.is_file():
        raise SystemExit(f"identify: {purpose} model {model_file} does not exist. Run `python curate/setup.py`.")
    actual = media_id(model_file)
    for e in entries:
        f = Path(e.get("file", ""))
        if not f.is_absolute():
            f = P.models / f
        try:
            same = f.resolve() == model_file.resolve()
        except OSError:
            same = False
        if same:
            if e.get("sha256", "").lower() != actual.lower():
                raise SystemExit(f"identify: {model_file} does not match the manifest's sha256 ({e.get('sha256')} vs {actual}). "
                                 f"Re-run setup, or update the manifest if you replaced the model on purpose.")
            return e
    raise SystemExit(f"identify: {model_file} is not listed in {mp}. Run `python curate/setup.py` (it records every model it fetches, "
                     f"and any user-supplied model named in config.toml).")


# ---------------------------------------------------------------- detection

def letterbox(img, size: int):
    """Resize keeping aspect, pad to size x size with grey. Returns (array HxWx3 uint8, scale, pad_x, pad_y)."""
    import numpy as np
    from PIL import Image
    w, h = img.size
    s = size / max(w, h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (px, py))
    return np.asarray(canvas), s, px, py


def nms(boxes, scores, thr: float):
    """boxes as x1,y1,x2,y2. Returns kept indices, best first."""
    import numpy as np
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    area = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest]); yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest]); yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (area[i] + area[rest] - inter + 1e-9)
        order = rest[iou <= thr]
    return keep


class Detectors:
    def __init__(self, P):
        import cv2
        import onnxruntime as ort
        self.person_file = resolve_model(P, "person_detector", DEFAULT_PERSON)
        self.face_file = resolve_model(P, "face_detector", DEFAULT_FACE)
        self.person_entry = check_manifest(P, self.person_file, "person")
        self.face_entry = check_manifest(P, self.face_file, "face")
        self.size = int(P.get("models", "person_input_size", 640) or 640)
        self.cls = int(P.get("models", "person_class_index", 0) or 0)
        self.sess = ort.InferenceSession(str(self.person_file), providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        self.fd = cv2.FaceDetectorYN.create(str(self.face_file), "", (320, 320), FACE_CONF, FACE_NMS, 5000)

    def persons(self, img):
        """Returns list of (x1, y1, x2, y2) in image pixels after NMS."""
        import numpy as np
        arr, s, px, py = letterbox(img, self.size)
        x = arr.astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        y = self.sess.run(None, {self.inp: x})[0]
        y = y[0]
        if y.shape[0] < y.shape[1]:      # (84, N) -> (N, 84); an (N, 84) export is left alone
            y = y.T
        cls = y[:, 4:]
        if cls.shape[1] == 0:
            return []
        best = cls.argmax(1)
        sc = cls[np.arange(len(cls)), best]
        sel = (best == self.cls) & (sc >= PERSON_CONF)
        if not sel.any():
            return []
        b = y[sel, :4]
        sc = sc[sel]
        xyxy = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2, b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2], 1)
        keep = nms(xyxy, sc, PERSON_IOU)
        w, h = img.size
        out = []
        for i in keep:
            x1, y1, x2, y2 = xyxy[i]
            x1 = min(max((x1 - px) / s, 0), w); x2 = min(max((x2 - px) / s, 0), w)
            y1 = min(max((y1 - py) / s, 0), h); y2 = min(max((y2 - py) / s, 0), h)
            if x2 > x1 and y2 > y1:
                out.append((float(x1), float(y1), float(x2), float(y2)))
        return out

    def faces(self, img):
        """Returns list of (x, y, w, h) in image pixels."""
        import numpy as np
        w, h = img.size
        s = min(1.0, 640 / max(w, h))
        nw, nh = max(1, round(w * s)), max(1, round(h * s))
        arr = np.asarray(img.resize((nw, nh)))[:, :, ::-1].copy()   # BGR for OpenCV
        self.fd.setInputSize((nw, nh))
        _, faces = self.fd.detect(arr)
        if faces is None or len(faces) == 0:
            return []
        return [(float(f[0]) / s, float(f[1]) / s, float(f[2]) / s, float(f[3]) / s) for f in faces]


def union_share(boxes, w: int, h: int) -> float:
    """Share of the frame covered by the union of boxes, measured on a grid (a sum would double count overlaps)."""
    import numpy as np
    if not boxes:
        return 0.0
    gw = UNION_GRID
    gh = max(1, round(gw * h / w))
    m = np.zeros((gh, gw), dtype=bool)
    for x1, y1, x2, y2 in boxes:
        a, b = int(x1 / w * gw), int(y1 / h * gh)
        c, d = int(np.ceil(x2 / w * gw)), int(np.ceil(y2 / h * gh))
        m[b:d, a:c] = True
    return float(m.mean())


# ---------------------------------------------------------------- loading frames

def load_frame(path: Path, ffmpeg: str | None, tmpdir: str):
    """PIL RGB image, EXIF-transposed, or None when no frame could be read (videos without ffmpeg)."""
    from PIL import Image, ImageOps, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        if not ffmpeg:
            return None
        out = os.path.join(tmpdir, "frame.png")
        for ss in ("0.5", "0"):
            if os.path.exists(out):
                os.remove(out)
            subprocess.run([ffmpeg, "-y", "-v", "quiet", "-ss", ss, "-i", str(path), "-frames:v", "1", out], timeout=120)
            if os.path.exists(out) and os.path.getsize(out) > 0:
                break
        if not (os.path.exists(out) and os.path.getsize(out) > 0):
            return None
        with Image.open(out) as im:
            return im.convert("RGB")
    with Image.open(path) as im:
        if ext in GIF_EXT:
            im.seek(0)
        try:
            im.draft("RGB", (LONG_SIDE, LONG_SIDE))
        except Exception:
            pass
        im = ImageOps.exif_transpose(im)
        return im.convert("RGB")


# ---------------------------------------------------------------- main

def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def ordered_rows(items: list[dict], results: dict[str, dict]) -> list[dict]:
    """One row per media_id, in items.csv order (exact duplicates share an id and get one row)."""
    seen = set()
    out = []
    for r in items:
        mid = r["media_id"]
        if mid in results and mid not in seen:
            seen.add(mid)
            out.append(results[mid])
    return out


def write_people(path, rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=PEOPLE_COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in PEOPLE_COLUMNS})
    write_atomic(path, buf.getvalue())


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="identify", description="person and face presence per file -> index/people.csv")
    ap.add_argument("--project", help="project folder (default: SLIDESHOW_PROJECT or a config.toml above the cwd)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be detected, write nothing")
    ap.add_argument("--force", action="store_true", help="re-detect files already in people.csv")
    ap.add_argument("--all", action="store_true", help="include quarantined rows (bursts, duplicates), not only location=work")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many files (for a quick check)")
    a = ap.parse_args(argv)

    P = project()
    items_path = P.index / "items.csv"
    people_path = P.index / "people.csv"
    if not items_path.is_file():
        say(f"identify: {items_path} does not exist; run the index stage first")
        return 1
    items = read_csv(items_path)
    if not a.all:
        items = [r for r in items if (r.get("location") or "work") == "work" and not r.get("duplicate_of")]
    done: dict[str, dict] = {}
    if people_path.is_file() and not a.force:
        done = {r["media_id"]: r for r in read_csv(people_path)}
    todo = [r for r in items if r["media_id"] not in done]
    if a.limit:
        todo = todo[: a.limit]

    ffmpeg = P.tool("ffmpeg")
    ffmpeg = ffmpeg if (os.path.isfile(ffmpeg) or shutil.which(ffmpeg)) else None
    n_video = sum(1 for r in todo if Path(r["filename"]).suffix.lower() in VIDEO_EXT)
    say(f"identify: {len(items)} files, {len(done)} done, {len(todo)} to do ({n_video} videos, ffmpeg {'found' if ffmpeg else 'NOT found: videos will be skipped'})")
    if a.dry_run:
        say("dry-run: nothing detected, nothing written")
        return 0
    if not todo:
        write_people(people_path, ordered_rows(items, done))
        say(f"nothing to do; {people_path} rewritten in index order")
        return 0

    det = Detectors(P)
    say(f"  person detector: {det.person_file.name} ({det.person_entry.get('license', '?')}), input {det.size}, class {det.cls}")
    say(f"  face detector:   {det.face_file.name} ({det.face_entry.get('license', '?')})")

    tmpdir = tempfile.mkdtemp(prefix="identify-")
    results = dict(done)
    n_persons = n_faces = n_skipped = n_err = 0
    try:
        for i, r in enumerate(todo, 1):
            path = P.work / r["filename"]
            loc = r.get("location") or "work"
            if loc != "work":
                path = P.root / loc / r["filename"]
            row = {"media_id": r["media_id"], "filename": r["filename"], "persons": "", "person_area": "", "largest_person": "",
                   "faces": "", "largest_face": "", "group_size": "", "people": "", "family_present": ""}
            try:
                img = load_frame(path, ffmpeg, tmpdir) if path.is_file() else None
                if img is None:
                    n_skipped += 1
                else:
                    w, h = img.size
                    pb = det.persons(img)
                    fb = det.faces(img)
                    row["persons"] = str(len(pb))
                    row["person_area"] = f"{union_share(pb, w, h):.2f}"
                    row["largest_person"] = f"{(max(((x2 - x1) * (y2 - y1)) for x1, y1, x2, y2 in pb) / (w * h)) if pb else 0:.2f}"
                    row["faces"] = str(len(fb))
                    row["largest_face"] = f"{(max((fw * fh) for _, _, fw, fh in fb) / (w * h)) if fb else 0:.3f}"
                    row["group_size"] = str(min(len(pb), GROUP_CAP))
                    n_persons += 1 if pb else 0
                    n_faces += 1 if fb else 0
            except Exception as e:  # one bad file must not stop the pass; it stays blank and is counted
                n_err += 1
                say(f"  ! {r['filename']}: {type(e).__name__}: {str(e)[:120]}")
            results[r["media_id"]] = row
            if i % 50 == 0 or i == len(todo):
                write_people(people_path, ordered_rows(items, results))
                say(f"  {i}/{len(todo)}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    say(f"identify: {len(todo)} processed | with persons {n_persons} | with faces {n_faces} | skipped (no frame) {n_skipped} | errors {n_err}")
    say(f"wrote {people_path} ({len(results)} rows)")
    if n_skipped and not ffmpeg:
        say("  videos were skipped because ffmpeg was not found; set [tools] ffmpeg in config.toml or put it on PATH and re-run")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
