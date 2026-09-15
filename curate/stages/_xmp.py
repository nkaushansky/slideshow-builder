"""XMP sidecars beside media files, for the ingest stage.

Apple Photos writes one `.xmp` per exported item when "Export IPTC as XMP" is ticked on
File > Export > Export Unmodified Originals, named after the item's stem (IMG_0001.xmp next to
IMG_0001.HEIC); Lightroom and exiftool do the same, darktable keeps the extension
(IMG_0001.HEIC.xmp). Inside is an RDF packet whose prefixes and property forms differ between
exporters (a property may be an attribute of rdf:Description or a child element), so everything
here matches by local name and reads both forms.

What is read: the capture time from photoshop:DateCreated, else xmp:CreateDate, else
exif:DateTimeOriginal (ISO 8601 with or without an offset; without one the project timezone
applies); GPS from exif:GPSLatitude and exif:GPSLongitude in the "DD,MM.mmmN" form (also
"DD,MM,SSN" and decimal, with a separate GPSLatitudeRef when there is one); the people from
Iptc4xmpExt:PersonInImage (an rdf:Bag of rdf:li), else the face region names under
mwg-rs:Regions; the description from dc:description (an rdf:Alt). The row has the Takeout
sidecar's columns (`_takeout.SIDECAR_COLUMNS`) with photo_taken_ts in epoch seconds, so the
index stage reads both kinds alike. Standard library only.

A malformed file never raises: read_sidecar returns None and ingest counts it.
"""
from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import STILL_EXT  # noqa: E402

TIME_PROPS = ("DateCreated", "CreateDate", "DateTimeOriginal")   # most trusted first
_EXIF_DATE = re.compile(r"^(\d{4}):(\d{2}):(\d{2})(.*)$")
_COORD = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)(?:\s*,\s*(\d+(?:\.\d+)?))?(?:\s*,\s*(\d+(?:\.\d+)?))?\s*([NSEWnsew])?\s*$")


def _local(name: str) -> str:
    """The local part of a Clark-form `{uri}name` or a `prefix:name`."""
    if "}" in name:
        return name.rsplit("}", 1)[1]
    return name.rsplit(":", 1)[-1]


def _text(el) -> str:
    return " ".join((el.text or "").split())


def _items(el) -> list[str]:
    """The texts of the rdf:li under an rdf:Bag, rdf:Seq or rdf:Alt, the x-default language first."""
    ranked = []
    for li in el.iter():
        if _local(li.tag) != "li":
            continue
        text = _text(li)
        if not text:
            continue                      # a structured li (a face region) has no text of its own
        lang = next((v for k, v in li.attrib.items() if _local(k) == "lang"), "")
        ranked.append((0 if lang in ("", "x-default") else 1, text))
    ranked.sort(key=lambda t: t[0])       # stable, so a Bag keeps its order
    return [t for _, t in ranked]


def _prop(root, name: str) -> str | None:
    """The first property with this local name: an attribute, or a child element (a list's first entry)."""
    for el in root.iter():
        for k, v in el.attrib.items():
            if _local(k) == name and v.strip():
                return v.strip()
        if _local(el.tag) == name:
            items = _items(el)
            if items:
                return items[0]
            text = _text(el)
            if text:
                return text
    return None


def _list(root, name: str) -> list[str]:
    """Every entry of the first list-valued property with this local name (an attribute is one entry)."""
    for el in root.iter():
        for k, v in el.attrib.items():
            if _local(k) == name and v.strip():
                return [v.strip()]
        if _local(el.tag) == name:
            return _items(el)
    return []


def _region_names(root) -> list[str]:
    """Names of the face regions under mwg-rs:Regions (Picasa, digiKam, Lightroom and some Apple exports)."""
    names: list[str] = []
    for rl in root.iter():
        if _local(rl.tag) != "RegionList":
            continue
        for li in rl.iter():
            if _local(li.tag) != "li":
                continue
            name = kind = ""
            for el in li.iter():          # attribute form on the li's Description, or child elements
                for k, v in el.attrib.items():
                    if _local(k) == "Name":
                        name = name or v.strip()
                    elif _local(k) == "Type":
                        kind = kind or v.strip()
                if _local(el.tag) == "Name":
                    name = name or _text(el)
                elif _local(el.tag) == "Type":
                    kind = kind or _text(el)
            if name and kind.lower() in ("", "face") and name not in names:
                names.append(name)
    return names


def parse_time(raw: str | None, tz) -> int | None:
    """Epoch seconds of an XMP date-time; a value without an offset is read in tz. None when unusable."""
    if not raw:
        return None
    s = raw.strip()
    m = _EXIF_DATE.match(s)
    if m:                                 # some writers keep EXIF's own 2020:05:05 10:00:00 form
        s = f"{m.group(1)}-{m.group(2)}-{m.group(3)}{m.group(4)}"
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if not (1900 < dt.year < 2100):       # the same bounds as the EXIF reader in _probe
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return int(dt.timestamp())            # aware, so this is arithmetic and works before 1970 on Windows too


def parse_coord(raw: str | None, ref: str | None = None) -> float | None:
    """Degrees from "40,26.7N", "40,26,42N", "-79.97", or "79.97" with ref "W"; None when unreadable."""
    m = _COORD.match(raw or "")
    if not m:
        return None
    deg, mins, secs = float(m.group(1)), float(m.group(2) or 0), float(m.group(3) or 0)
    value = abs(deg) + mins / 60 + secs / 3600
    hemi = (m.group(4) or ref or "").strip().upper()[:1]
    if m.group(1).startswith("-") or hemi in ("S", "W"):
        value = -value
    return round(value, 5)


def read_sidecar(path: str, member: str, tz) -> dict | None:
    """The fields the index needs from one .xmp, in the Takeout sidecar's columns; None when the
    file is not an XMP packet (unparseable, or no rdf:Description inside)."""
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    if not any(_local(el.tag) == "Description" for el in root.iter()):
        return None
    ts = None
    for prop in TIME_PROPS:
        ts = parse_time(_prop(root, prop), tz)
        if ts is not None:
            break
    lat = parse_coord(_prop(root, "GPSLatitude"), _prop(root, "GPSLatitudeRef"))
    lon = parse_coord(_prop(root, "GPSLongitude"), _prop(root, "GPSLongitudeRef"))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        lat = lon = ""
    people = _list(root, "PersonInImage") or _region_names(root)
    return {
        "member": member,
        # a Takeout title is the original filename and two alike in one folder mean trouble (gate 5);
        # dc:title is a caption and says nothing about which file is which, so it stays out of this column
        "title": "",
        "folder": os.path.dirname(member),
        "photo_taken_ts": str(ts) if ts is not None else "",
        "creation_ts": "",
        "lat": lat, "lon": lon,
        "people": ";".join(p.replace(";", ",") for p in people if p),
        "description": (_prop(root, "description") or "").replace("\n", " ")[:200],
    }


def resolve_media_member(sidecar_member: str, names_in_folder: set[str]) -> str:
    """Member path of the media file an .xmp describes, or '' when there is none or it is ambiguous.

    An exact name wins (IMG_0001.HEIC.xmp for IMG_0001.HEIC), then the one media file with the
    same stem (IMG_0001.xmp). A Live Photo exported as IMG_0001.HEIC + IMG_0001.MOV shares the
    stem and the sidecar describes the photo: the lone still takes it and the pair gate carries
    the date to the video. Two stills with one stem stay unresolved; nothing is guessed.
    """
    folder = os.path.dirname(sidecar_member)
    base = os.path.basename(sidecar_member)
    if not base.lower().endswith(".xmp"):
        return ""
    base = base[:-4]
    join = (lambda n: f"{folder}/{n}" if folder else n)
    exact = [n for n in names_in_folder if n.casefold() == base.casefold()]
    if len(exact) == 1:
        return join(exact[0])
    same = [n for n in names_in_folder if os.path.splitext(n)[0].casefold() == base.casefold()]
    if len(same) == 1:
        return join(same[0])
    stills = [n for n in same if os.path.splitext(n)[1].lower() in STILL_EXT]
    if len(same) > 1 and len(stills) == 1:
        return join(stills[0])
    return ""
