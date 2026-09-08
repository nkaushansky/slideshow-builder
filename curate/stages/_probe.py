"""Per-file probing shared by the index stage: EXIF, orientation, perceptual hash, sharpness,
ffprobe for videos, first-frame hashing, GPS.

Methods, so the numbers in items.csv are reproducible:
- phash: imagehash.phash(hash_size=16) on the RGB image after EXIF orientation, 256 bits, hex.
- sharpness: variance of the Laplacian (cv2.CV_64F) of a grayscale copy downscaled so the long side
  is at most 1024 px. Bigger source images therefore compare on equal footing.
- width/height: displayed dimensions, i.e. stored size swapped when EXIF orientation is 5-8, and
  video stored size swapped when the rotation (display matrix or rotate tag) is +-90 or 270.
- hdr: color_transfer smpte2084 or arib-std-b67, or a 10-bit pix_fmt (contains "10").
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import warnings
from datetime import datetime, timezone
from fractions import Fraction
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")
import numpy as np
import cv2
from PIL import Image, ImageFile, ImageOps

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:  # the requirements pin it; without it HEIC files fail loudly per file
    pillow_heif = None
import imagehash

EXIF_DT_ORIGINAL = 36867
EXIF_DT_DIGITIZED = 36868
EXIF_DT = 306
EXIF_IFD = 0x8769
GPS_IFD = 34853
ORIENTATION = 274
MAKE, MODEL = 271, 272

SHARPNESS_LONG_SIDE = 1024
BOGUS_YEARS = ("1970", "0000", "1904")


def find_tool(spec: str) -> str | None:
    """Resolve an ffprobe/ffmpeg spec (path or bare name) to an executable, or None."""
    if not spec:
        return None
    if os.path.isfile(spec):
        return spec
    return shutil.which(spec)


# ---------------------------------------------------------------- EXIF

def _exif_value(ex, tag):
    v = ex.get(tag)
    if not v:
        try:
            v = ex.get_ifd(EXIF_IFD).get(tag)
        except Exception:
            v = None
    return v


def parse_exif_datetime(s: str) -> str | None:
    """'2023:08:14 18:23:11' (or with '-' or '/') -> '2023-08-14 18:23:11'; None if unusable."""
    if not s:
        return None
    s = str(s).strip().replace("/", ":")
    try:
        d, t = s.split(" ")[0], (s.split(" ") + ["00:00:00"])[1]
        d = d.replace("-", ":")
        y, mo, dy = d.split(":")[:3]
        y, mo, dy = int(y), int(mo), int(dy)
        if not (1900 < y < 2100) or not (1 <= mo <= 12) or not (1 <= dy <= 31):
            return None
        t = t[:8]
        datetime.strptime(f"{y:04d}-{mo:02d}-{dy:02d} {t}", "%Y-%m-%d %H:%M:%S")
        return f"{y:04d}-{mo:02d}-{dy:02d} {t}"
    except Exception:
        return None


def _dms(v, ref):
    try:
        d, m, s = (float(Fraction(x)) if not isinstance(x, float) else x for x in v[:3])
        x = d + m / 60 + s / 3600
        return -x if ref in ("S", "W") else x
    except Exception:
        return None


def probe_still(path: str) -> dict:
    """Everything the index needs from a still or an animated GIF, from one decode."""
    r: dict = {"kind": "still"}
    with Image.open(path) as im:
        r["format"] = im.format or ""
        w, h = im.size
        orient = 1
        make = model = ""
        raw_dt = ""
        lat = lon = None
        try:
            ex = im.getexif()
        except Exception:
            ex = None
        if ex:
            try:
                orient = int(ex.get(ORIENTATION, 1) or 1)
            except Exception:
                orient = 1
            make = str(ex.get(MAKE) or "").strip("\x00 ")
            model = str(ex.get(MODEL) or "").strip("\x00 ")
            for tag in (EXIF_DT_ORIGINAL, EXIF_DT_DIGITIZED, EXIF_DT):
                v = _exif_value(ex, tag)
                if v:
                    raw_dt = str(v)
                    if parse_exif_datetime(raw_dt):
                        break
            try:
                g = ex.get_ifd(GPS_IFD)
            except Exception:
                g = None
            if g:
                lat = _dms(g.get(2), g.get(1, "N"))
                lon = _dms(g.get(4), g.get(3, "E"))
                if lat is None or lon is None or (lat == 0 and lon == 0):
                    lat = lon = None
        if orient in (5, 6, 7, 8):
            w, h = h, w
        r.update(stored_w=im.size[0], stored_h=im.size[1], w=w, h=h, orient=orient,
                 make=make, model=model, exif_raw=raw_dt, exif_dt=parse_exif_datetime(raw_dt),
                 lat=round(lat, 5) if lat is not None else None,
                 lon=round(lon, 5) if lon is not None else None)
        if im.format == "GIF":
            r["kind"] = "gif"
            try:
                nf = getattr(im, "n_frames", 1)
                dur = 0.0
                for i in range(nf):
                    im.seek(i)
                    dur += im.info.get("duration", 100) / 1000.0
                im.seek(0)
                r.update(dur=round(dur, 2), frames=nf)
            except Exception:
                pass
        # hash and sharpness on the displayed (oriented) image
        oriented = ImageOps.exif_transpose(im) if orient != 1 else im
        try:
            rgb = oriented.convert("RGB")
            r["phash"] = str(imagehash.phash(rgb, hash_size=16))
            r["sharp"] = sharpness(rgb)
        finally:
            if oriented is not im:
                oriented.close()
    return r


def sharpness(img: Image.Image) -> float:
    g = img.convert("L")
    ls = max(g.size)
    if ls > SHARPNESS_LONG_SIDE:
        s = SHARPNESS_LONG_SIDE / ls
        g = g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))))
    return round(float(cv2.Laplacian(np.asarray(g, dtype=np.float64), cv2.CV_64F).var()), 2)


def phash_bytes(data: bytes) -> str | None:
    """phash of an image held in memory (a first frame, a zip member)."""
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        return str(imagehash.phash(im.convert("RGB"), hash_size=16))


def hash_distance(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


# ---------------------------------------------------------------- video

ISO6709 = re.compile(r"^([+-]\d+\.?\d*)([+-]\d+\.?\d*)")


def _parse_container_time(s: str):
    """ffprobe creation_time -> (aware datetime, raw string) or (None, raw)."""
    raw = str(s or "").strip()
    if not raw or raw[:4] in BOGUS_YEARS:
        return None, raw
    t = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except Exception:
        try:
            dt = datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            try:
                dt = datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None, raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.year < 1990:
        return None, raw
    return dt, raw


def probe_video(path: str, ffprobe: str, tz: str) -> dict:
    """ffprobe -> displayed dimensions, duration, fps, codec, audio, hdr, container time, GPS."""
    r: dict = {"kind": "video"}
    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if out.returncode != 0 or not out.stdout.strip():
        r["error"] = "ffprobe failed: " + (out.stderr.strip()[:120] or f"exit {out.returncode}")
        return r
    d = json.loads(out.stdout)
    streams = d.get("streams", [])
    vs = [s for s in streams if s.get("codec_type") == "video" and s.get("codec_name") not in ("mjpeg", "png", "gif")]
    fmt = d.get("format") or {}
    w = h = 0
    rot = 0
    fps = None
    codec = ""
    hdr = False
    if vs:
        s = vs[0]
        w, h = int(s.get("width") or 0), int(s.get("height") or 0)
        codec = s.get("codec_name", "")
        try:
            rot = int(float((s.get("tags") or {}).get("rotate", 0)))
        except Exception:
            rot = 0
        for sd in s.get("side_data_list") or []:
            if "rotation" in sd:
                try:
                    rot = int(float(sd["rotation"]))
                except Exception:
                    pass
        for key in ("avg_frame_rate", "r_frame_rate"):
            v = s.get(key)
            if v and v not in ("0/0", "0"):
                try:
                    fps = round(float(Fraction(v)), 3)
                    break
                except Exception:
                    continue
        ct = (s.get("color_transfer") or "").lower()
        pf = (s.get("pix_fmt") or "").lower()
        hdr = ct in ("smpte2084", "arib-std-b67") or "10" in pf
    if abs(rot) % 180 == 90:
        w, h = h, w
    try:
        dur = round(float(fmt.get("duration") or 0), 3)
    except Exception:
        dur = 0.0
    tags = {**(fmt.get("tags") or {})}
    for s in streams:
        for k, v in (s.get("tags") or {}).items():
            tags.setdefault(k, v)
    # Apple's creationdate carries the local offset; creation_time is UTC.
    local_dt = None
    raw = ""
    for k in ("com.apple.quicktime.creationdate", "creation_time", "date", "DateTimeOriginal"):
        if tags.get(k):
            dt, raw = _parse_container_time(tags[k])
            if dt:
                local_dt = dt
                break
    if local_dt is not None:
        try:
            local_dt = local_dt.astimezone(ZoneInfo(tz))
        except Exception:
            local_dt = local_dt.astimezone(timezone.utc)
    lat = lon = None
    for k in ("com.apple.quicktime.location.ISO6709", "location", "location-eng"):
        v = tags.get(k)
        if v:
            m = ISO6709.match(str(v))
            if m:
                lat, lon = round(float(m.group(1)), 5), round(float(m.group(2)), 5)
                break
    r.update(w=w, h=h, rotation=rot, dur=dur, fps=fps, codec=codec,
             audio=any(s.get("codec_type") == "audio" for s in streams),
             hdr=hdr, container_raw=raw,
             container_dt=local_dt.strftime("%Y-%m-%d %H:%M:%S") if local_dt else None,
             lat=lat, lon=lon)
    return r


def first_frame_phash(path: str, ffmpeg: str) -> str | None:
    """phash of a video's first frame (for the Live Photo pair gate); None when it cannot be read."""
    cmd = [ffmpeg, "-v", "error", "-y", "-i", path, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=120)
        if out.returncode != 0 or not out.stdout:
            return None
        return phash_bytes(out.stdout)
    except Exception:
        return None
