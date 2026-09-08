"""Still-image helper for the build side: dimensions and JPEG conversion without macOS `sips`.

    python curate/heic.py dims <file>
        prints JSON: {"width", "height"} after EXIF orientation, {"stored_width", "stored_height"} as stored,
        "orientation" (EXIF 1-8, 1 when absent) and "date_time_original" (raw EXIF string or "").
    python curate/heic.py convert <in> <out.jpg> [--max-height N] [--quality Q]
        opens HEIC/HEIF/JPEG/PNG (pillow-heif registers the HEIF opener), applies the EXIF orientation so the
        pixels are upright, shrinks to at most N pixels of display height (0 = keep size), and saves a JPEG.
        The EXIF block is carried across with the Orientation tag cleared (the pixels are already upright);
        when Pillow cannot re-encode the EXIF the JPEG is written without it, which the build tolerates.

Exit status is non-zero with a one-line message on stderr when the file cannot be read or written.
`build/lib/common.js` calls this through the repo's .venv when `sips` is not available.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # HEIC then fails at open time with a clear message; JPEG/PNG still work
    pillow_heif = None

Image.MAX_IMAGE_PIXELS = None
ORIENTATION_TAG = 0x0112
DATE_TIME_ORIGINAL = 0x9003
EXIF_IFD = 0x8769


def _open(path: str) -> Image.Image:
    try:
        return Image.open(path)
    except Exception as e:  # noqa: BLE001
        ext = os.path.splitext(path)[1].lower()
        hint = " (pillow-heif is not installed)" if ext in (".heic", ".heif") and pillow_heif is None else ""
        raise SystemExit(f"heic.py: cannot open {path}: {e}{hint}")


def _orientation(im: Image.Image) -> int:
    try:
        o = int(im.getexif().get(ORIENTATION_TAG, 1) or 1)
    except Exception:  # noqa: BLE001
        o = 1
    return o if 1 <= o <= 8 else 1


def _date_time_original(im: Image.Image) -> str:
    try:
        exif = im.getexif()
        ifd = exif.get_ifd(EXIF_IFD)
        v = ifd.get(DATE_TIME_ORIGINAL) or exif.get(DATE_TIME_ORIGINAL) or ""
        return str(v).strip("\x00 ")
    except Exception:  # noqa: BLE001
        return ""


def cmd_dims(args: argparse.Namespace) -> int:
    with _open(args.file) as im:
        sw, sh = im.size
        o = _orientation(im)
        w, h = (sh, sw) if o >= 5 else (sw, sh)
        print(json.dumps({"width": w, "height": h, "stored_width": sw, "stored_height": sh,
                          "orientation": o, "date_time_original": _date_time_original(im)}))
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    with _open(args.input) as im:
        exif = None
        try:
            exif = im.getexif()
        except Exception:  # noqa: BLE001
            exif = None
        upright = ImageOps.exif_transpose(im)
        if upright is None:
            upright = im
        upright = upright.convert("RGB")
        if args.max_height and upright.height > args.max_height:
            new_w = max(1, round(upright.width * args.max_height / upright.height))
            upright = upright.resize((new_w, args.max_height), Image.Resampling.LANCZOS)
        save_kwargs = {"quality": int(args.quality), "optimize": False, "subsampling": 0 if args.quality >= 95 else 2}
        if exif is not None and len(exif):
            try:
                if ORIENTATION_TAG in exif:
                    del exif[ORIENTATION_TAG]
                save_kwargs["exif"] = exif.tobytes()
            except Exception:  # noqa: BLE001
                save_kwargs.pop("exif", None)   # written without EXIF; documented above
        tmp = args.output + ".part"
        try:
            upright.save(tmp, "JPEG", **save_kwargs)
        except Exception as e:  # noqa: BLE001
            if "exif" in save_kwargs:
                save_kwargs.pop("exif")
                upright.save(tmp, "JPEG", **save_kwargs)
            else:
                raise SystemExit(f"heic.py: cannot write {args.output}: {e}")
        os.replace(tmp, args.output)
        print(json.dumps({"width": upright.width, "height": upright.height, "output": args.output}))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="heic.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dims", help="print displayed and stored dimensions, orientation and DateTimeOriginal as JSON")
    d.add_argument("file")
    d.set_defaults(fn=cmd_dims)
    c = sub.add_parser("convert", help="write an upright JPEG, optionally capped at a display height")
    c.add_argument("input")
    c.add_argument("output")
    c.add_argument("--max-height", type=int, default=0, help="cap on the display height in pixels; 0 keeps the size")
    c.add_argument("--quality", type=int, default=90)
    c.set_defaults(fn=cmd_convert)
    args = ap.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
