"""A synthetic photo library and project folder for the regression suite.

Everything is generated, nothing is a real photo: textured shapes with real EXIF, short H.264 clips with Apple-style
creation metadata, and a Google Takeout zip with JSON sidecars. The library holds the cases the first review found
bugs in, so the suite can show them fixed and keep them fixed:

- 70 dated stills across 2019-2023, some stored rotated (EXIF orientation 6);
- two late-October stills, for config.example.toml's example `AUTUMN-TRADITION` anchor;
- Live Photo pairs: IMG_1001 shot at home, IMG_1002 shot three time zones away (same instant, different local clocks);
- five standalone videos, an animated GIF and three undated scans;
- a Takeout zip with sidecars in both naming styles, duplicates included (`IMG_2000.jpg.supplemental-metadata(1).json`
  for `IMG_2000(1).jpg`, the older `IMG_3000.jpg(1).json` for `IMG_3000(1).jpg`), and one sidecar with no photo.

`write_config` builds the project's config.toml from curate/config.example.toml with the project's own patcher
(common.set_config_value), so the example is exercised as shipped apart from the answers an intake would give.
"""
from __future__ import annotations

import csv
import io
import json
import random
import struct
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from helpers import CURATE

from common import set_config_value  # noqa: E402  (helpers put curate/ on sys.path)

TAKEOUT_FOLDER = "Takeout/Google Photos/Photos from 2020/"


def picture(seed: int, w: int, h: int) -> Image.Image:
    """A distinct, textured image, so perceptual hashes, sharpness and the diversity rule behave as on photos."""
    r = random.Random(seed)
    im = Image.new("RGB", (w, h), tuple(r.randrange(40, 220) for _ in range(3)))
    d = ImageDraw.Draw(im)
    for _ in range(14):
        x0, y0 = r.randrange(w), r.randrange(h)
        x1, y1 = x0 + r.randrange(w // 8, w // 2), y0 + r.randrange(h // 8, h // 2)
        fill = tuple(r.randrange(256) for _ in range(3))
        (d.rectangle if r.random() < 0.5 else d.ellipse)([x0, y0, x1, y1], fill=fill)
    arr = np.asarray(im).astype(np.int16)
    arr = np.clip(arr + np.random.default_rng(seed).integers(-6, 7, arr.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def save_jpeg(path: Path, im: Image.Image, taken: str | None = None, orientation: int | None = None,
              model: str | None = None) -> None:
    """A JPEG with DateTimeOriginal ('2021:07:04 14:00:00'), an orientation tag and a camera model when given."""
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    if model:
        exif[0x010F], exif[0x0110] = "Apple", model
    if taken:
        exif.get_ifd(0x8769)[0x9003] = taken
    im.save(path, "JPEG", quality=88, exif=exif.tobytes())


def clip_from_still(still: Path, out: Path, seconds: float, creationdate: str, zoom: bool = False) -> None:
    """A short MOV made from a still, so a Live Photo's frames match its still, carrying Apple's local creationdate
    (with its offset) and creation_time in UTC, as an iPhone writes them."""
    vf = "scale=trunc(iw/4)*2:trunc(ih/4)*2" + (",zoompan=z='1+0.002*on':d=1:s=640x480" if zoom else "")
    utc = datetime.fromisoformat(creationdate).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-i", str(still), "-t", str(seconds),
                    "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "use_metadata_tags",
                    "-metadata", f"com.apple.quicktime.creationdate={creationdate}", "-metadata", f"creation_time={utc}",
                    str(out)], check=True)


def truncated_copy(src: Path, dst: Path) -> None:
    """A copy of a clip cut off just inside its media data, index first: ffprobe still reads its duration and
    creation time, but ffmpeg cannot decode a frame. What an interrupted copy or a half-synced cloud file looks like."""
    tmp = dst.with_name(dst.stem + ".faststart.mov")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c", "copy", "-map_metadata", "0",
                    "-movflags", "+faststart+use_metadata_tags", str(tmp)], check=True)
    data = tmp.read_bytes()
    tmp.unlink()
    i = 0
    while i + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[i:i + 8])
        if kind == b"mdat":
            dst.write_bytes(data[:i + 8 + 64])
            return
        i += size
    raise RuntimeError(f"{src} has no mdat atom")


def _epoch(y: int, mo: int, d: int) -> str:
    return str(int(datetime(y, mo, d, 12, 0, tzinfo=timezone.utc).timestamp()))


def _sidecar(title: str, taken: str, people=(), description: str = "") -> str:
    return json.dumps({"title": title, "description": description,
                       "photoTakenTime": {"timestamp": taken, "formatted": ""},
                       "creationTime": {"timestamp": taken, "formatted": ""},
                       "geoData": {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
                       "people": [{"name": p} for p in people]})


def make_library(project: Path) -> None:
    """Write sources/phone (a folder source) and sources/takeout/<one zip> under the project folder."""
    phone = project / "sources" / "phone"
    takeout = project / "sources" / "takeout"
    phone.mkdir(parents=True)
    takeout.mkdir(parents=True)
    rng = random.Random(1234)

    n = 0
    for year in range(2019, 2024):
        for k in range(14):
            n += 1
            month, day = rng.randrange(1, 13), rng.randrange(1, 28)
            if month == 10 and day >= 24:          # late October is kept for the anchor case below
                day = 10
            w, h = rng.choice([(1600, 1200), (1200, 1600), (1920, 1080), (1600, 1200), (1200, 1600)])
            orient = 6 if k % 7 == 3 else None
            if orient:
                w, h = h, w                         # stored landscape, displayed portrait
            save_jpeg(phone / f"IMG_{5000 + n:04d}.JPG", picture(n, w, h),
                      f"{year}:{month:02d}:{day:02d} 12:{k:02d}:00", orient, "iPhone X")

    for i, year in enumerate((2020, 2022)):
        save_jpeg(phone / f"IMG_HALLOWEEN_{year}.JPG", picture(900 + i, 1600, 1200), f"{year}:10:28 18:00:00", None, "iPhone 12")

    # Live Photo pairs. The project's zone is America/New_York.
    home = phone / "IMG_1001.JPG"
    save_jpeg(home, picture(1001, 1600, 1200), "2021:07:04 14:00:00", None, "iPhone 12")
    clip_from_still(home, phone / "IMG_1001.MOV", 2.0, "2021-07-04T14:00:00-0400")
    away = phone / "IMG_1002.JPG"                    # California: 10:00 on the camera's clock, 13:00 in New York
    save_jpeg(away, picture(1002, 1600, 1200), "2022:08:10 10:00:00", None, "iPhone 12")
    clip_from_still(away, phone / "IMG_1002.MOV", 2.0, "2022-08-10T10:00:00-0700")

    for i, (year, month) in enumerate(((2019, 5), (2020, 9), (2021, 3), (2022, 11), (2023, 6))):
        still = project / f"_video-source-{i}.jpg"
        picture(3000 + i, 1280, 720).save(still, quality=90)
        clip_from_still(still, phone / f"VID_{year}{month:02d}.MOV", 8.0, f"{year}-{month:02d}-15T12:00:00-0400", zoom=True)
        still.unlink()
    frames = [picture(4000 + i, 400, 300) for i in range(6)]
    frames[0].save(phone / "fun.gif", save_all=True, append_images=frames[1:], duration=150, loop=0)
    for i in range(3):
        picture(6000 + i, 1500, 1000).save(phone / f"scan_{i:02d}.jpg", quality=90)

    with zipfile.ZipFile(takeout / "takeout-20260901T000000Z-001.zip", "w", zipfile.ZIP_DEFLATED) as z:
        def photo(name: str, seed: int) -> None:
            buf = io.BytesIO()
            picture(seed, 1600, 1200).save(buf, "JPEG", quality=88)   # no EXIF: the sidecar is the only date
            z.writestr(TAKEOUT_FOLDER + name, buf.getvalue())
        photo("PXL_20200505_120000000.jpg", 7001)
        z.writestr(TAKEOUT_FOLDER + "PXL_20200505_120000000.jpg.supplemental-metadata.json",
                   _sidecar("PXL_20200505_120000000.jpg", _epoch(2020, 5, 5), ["Sam Jones"], "Sam at the lake"))
        photo("IMG_2000.jpg", 7002)                 # a duplicate title, newer naming
        photo("IMG_2000(1).jpg", 7003)
        z.writestr(TAKEOUT_FOLDER + "IMG_2000.jpg.supplemental-metadata.json", _sidecar("IMG_2000.jpg", _epoch(2020, 6, 1), ["Sam Jones"]))
        z.writestr(TAKEOUT_FOLDER + "IMG_2000.jpg.supplemental-metadata(1).json", _sidecar("IMG_2000.jpg", _epoch(2020, 6, 2), ["Alex Jones"]))
        photo("IMG_3000.jpg", 7004)                 # a duplicate title, older naming
        photo("IMG_3000(1).jpg", 7005)
        z.writestr(TAKEOUT_FOLDER + "IMG_3000.jpg.json", _sidecar("IMG_3000.jpg", _epoch(2020, 7, 1), ["Sam Jones"]))
        z.writestr(TAKEOUT_FOLDER + "IMG_3000.jpg(1).json", _sidecar("IMG_3000.jpg", _epoch(2020, 7, 2), ["Sam Jones"]))
        photo("IMG_4000.jpg", 7006)
        z.writestr(TAKEOUT_FOLDER + "IMG_4000.jpg.supplemental-metadata.json", _sidecar("IMG_4000.jpg", _epoch(2020, 8, 8)))
        # a sidecar whose photo is not in the export: ingest must name it, not only count it
        z.writestr(TAKEOUT_FOLDER + "IMG_9999.jpg.supplemental-metadata.json", _sidecar("IMG_9999.jpg", _epoch(2020, 9, 9)))


# The answers an intake would give for this library, as TOML literals keyed by (section, key).
DEFAULT_SETTINGS = {
    ("project", "timezone"): '"America/New_York"',
    ("honoree", "birth_year"): "2019",
    ("family", "names"): '["Sam"]',
    ("family", "gate"): '"none"',
    ("show", "event_date"): "2024-03-01",
    ("show", "hard_stop"): "2024-02-27",
    ("show", "scope_start"): "2019-01-01",
    ("show", "scope_end"): "2023-12-31",
    ("show", "loop_minutes_target"): "1",
    ("output", "resolution"): '"640x360"',
    ("output", "fps"): "30",
    ("output", "quality"): '"draft"',
}


def write_config(project: Path, settings: dict | None = None, sources: bool = True) -> Path:
    """<project>/config.toml from curate/config.example.toml with the intake's answers filled in."""
    text = (CURATE / "config.example.toml").read_text(encoding="utf-8")
    shipped = 'path = "sources/phone-export"'
    if shipped not in text:
        raise AssertionError(f"config.example.toml no longer has {shipped!r}; update tests/fixture.py")
    text = text.replace(shipped, 'path = "sources/phone"')
    if not sources:   # a folder source alone
        text = text.replace('[[sources]]\npath = "sources/takeout"\nkind = "takeout"\n\n', "", 1)
    cfg = project / "config.toml"
    project.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding="utf-8")
    for (section, key), literal in {**DEFAULT_SETTINGS, **(settings or {})}.items():
        set_config_value(cfg, section, key, literal)
    return cfg


# ---------------------------------------------------------------- layout-only projects

MEDIA_COLUMNS = ["media_id", "filename", "type", "companion", "width", "height", "duration_s", "fps", "hdr", "date",
                 "precision", "date_source", "date_witness", "exif_datetime_original", "people", "tag", "featured",
                 "video_codec", "has_audio", "original_source_path", "caption"]


def write_layout_project(project: Path, items: int, video_share: float, featured_share: float, mixed_tiles: bool,
                         years: int = 13, seed: int = 1, live_share: float = 0.08) -> None:
    """A handoff with a synthetic media.csv and no media, enough for `bin/build --dry-run`, which lays the show out
    from media.csv's dimensions when prep has not run. The mix is a phone library's: landscape and portrait stills, some
    16:9, a few panoramas, a share of videos and Live Photos, a share of featured stills."""
    write_config(project, {("output", "resolution"): '"2560x1440"', ("output", "fps"): "60",
                           ("taste", "mixed_tiles"): "true" if mixed_tiles else "false"})
    handoff = project / "handoff"
    (handoff / "media").mkdir(parents=True)
    r = random.Random(seed)
    rows, n_video, n_live = [], round(items * video_share), round(items * live_share)
    for i in range(items):
        date = f"{2010 + r.randrange(years)}-{r.randrange(1, 13):02d}-{r.randrange(1, 28):02d}"
        stem = f"{date}_IMG_{i:04d}"
        if i < n_video:
            w, h = r.choice([(1920, 1080), (1920, 1080), (1080, 1920)])
            rows.append(dict(filename=stem + ".MOV", type="video", width=w, height=h, duration_s=f"{r.uniform(5, 60):.1f}", fps="30", date=date, precision="day"))
        elif i < n_video + n_live:
            w, h = r.choice([(1440, 1080), (1080, 1440)])
            rows.append(dict(filename=stem + ".HEIC", type="livephoto-still", companion=stem + ".MOV", width=w, height=h, date=date, precision="day"))
            rows.append(dict(filename=stem + ".MOV", type="livephoto-video", companion=stem + ".HEIC", width=w, height=h, duration_s="2.8", fps="30", date=date, precision="day"))
        else:
            p = r.random()
            w, h = (4032, 3024) if p < 0.52 else (3024, 4032) if p < 0.90 else (1920, 1080) if p < 0.98 else (8000, 2400)
            rows.append(dict(filename=stem + ".JPG", type="still", width=w, height=h, date=date, precision="day"))
    featured = []
    if mixed_tiles and featured_share > 0:
        stills = [x for x in rows if x["type"] == "still"]
        for x in r.sample(stills, round(featured_share * items)):
            x["featured"] = "yes"
            featured.append(x["filename"])
    for x in rows:
        x["media_id"] = "%064x" % r.getrandbits(256)
    with open(handoff / "media.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MEDIA_COLUMNS, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for x in sorted(rows, key=lambda x: x["filename"]):
            w.writerow({k: x.get(k, "") for k in MEDIA_COLUMNS})
    (handoff / "features.txt").write_text("".join(n + "\n" for n in sorted(featured)), encoding="utf-8")
    (handoff / "cut-list.csv").write_text("media_id,filename,location,reason,original_source_path\n", encoding="utf-8")
