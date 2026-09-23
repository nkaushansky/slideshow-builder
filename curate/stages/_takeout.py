"""Google Takeout helpers for the ingest stage.

A Takeout is a set of zips. Each media member (`.../Photos from 2023/IMG_0001.HEIC`) has a JSON
sidecar next to it (`IMG_0001.HEIC.json`, or the newer `IMG_0001.HEIC.supplemental-metadata.json`,
sometimes truncated) with photoTakenTime, geoData and people tags. A second file with the same title
in one folder is `IMG_0001(1).HEIC`, its sidecar `IMG_0001.HEIC(1).json` or, in newer exports,
`IMG_0001.HEIC.supplemental-metadata(1).json`. The sidecars index in seconds from the zips' central
directories and small reads; nothing is extracted to do it.

Rules from references/03 gate 5: key by member path, never by the `title` inside the sidecar. An
export keeps the original title even when it renames the member with a `(1)` suffix, so two
sidecars in one folder can share a title; both are marked `title_collision` and the index stage
leaves their dates to EXIF and the validate stage.

The same sidecars turn up beside the files when a Takeout was unzipped into a folder source;
ingest reads those with `read_sidecar_file` and runs them through `finish_rows`, the same
collision and claim rules as the zip case. Every row says where it came from in `source`:
`takeout-zip`, `takeout-json` (a file beside the media) or `xmp` (see `_xmp.py`).
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import GIF_EXT, STILL_EXT, VIDEO_EXT  # noqa: E402

MEDIA_EXT = STILL_EXT | VIDEO_EXT | GIF_EXT
SIDECAR_MAX_BYTES = 64_000
SIDECAR_COLUMNS = ["zip", "member", "title", "folder", "photo_taken_ts", "creation_ts", "lat", "lon",
                   "people", "description", "title_collision", "media_member", "source"]
SIDECAR_SOURCES = ("takeout-zip", "takeout-json", "xmp")

_SUPP_WORD = "supplemental-metadata"        # the sidecar suffix since 2024, cut short when a name passes Takeout's limit
_COUNTER = re.compile(r"^(.*)\((\d+)\)$")    # the "(1)" a second file with the same title gets, last in its sidecar's name


def list_zips(folder: str) -> list[str]:
    return sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".zip"))


def zip_members(zpath: str) -> tuple[list[zipfile.ZipInfo], list[zipfile.ZipInfo]]:
    """(media members, sidecar candidates) from the central directory only."""
    media, side = [], []
    with zipfile.ZipFile(zpath) as zf:
        for i in zf.infolist():
            if i.is_dir():
                continue
            ext = os.path.splitext(i.filename)[1].lower()
            if ext in MEDIA_EXT:
                media.append(i)
            elif ext == ".json" and i.file_size <= SIDECAR_MAX_BYTES:
                side.append(i)
    return media, side


def read_sidecar(zf: zipfile.ZipFile, member: str) -> dict | None:
    """The fields the index needs from a sidecar inside a zip, or None when the JSON is not a photo sidecar."""
    try:
        d = json.loads(zf.read(member).decode("utf-8", errors="replace"))
    except Exception:
        return None
    return sidecar_fields(d, member)


def read_sidecar_file(path: str, member: str) -> dict | None:
    """The same for a sidecar on disk (an unzipped Takeout, or a folder export that kept them);
    `member` is the file's path relative to the source. None when it is not a photo sidecar."""
    try:
        with open(path, "rb") as f:
            d = json.loads(f.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    return sidecar_fields(d, member)


def sidecar_fields(d, member: str) -> dict | None:
    """The row for one parsed sidecar, or None when the JSON is not a photo sidecar."""
    if not isinstance(d, dict) or "photoTakenTime" not in d:
        return None
    g = d.get("geoData") or {}
    lat, lon = g.get("latitude"), g.get("longitude")
    if not (lat or lon):
        lat = lon = ""
    ppl = [p.get("name", "") for p in (d.get("people") or []) if isinstance(p, dict) and p.get("name")]
    return {
        "member": member,
        "title": d.get("title", "") or "",
        "folder": os.path.dirname(member),
        "photo_taken_ts": str((d.get("photoTakenTime") or {}).get("timestamp") or ""),
        "creation_ts": str((d.get("creationTime") or {}).get("timestamp") or ""),
        "lat": lat, "lon": lon,
        "people": ";".join(ppl),
        "description": (d.get("description") or "").strip().replace("\n", " ")[:200],
    }


def index_sidecars(zpaths: list[str], workers: int = 8, progress=None) -> tuple[list[dict], dict[str, list[tuple[str, int]]]]:
    """Read every sidecar in every zip. Returns (sidecar rows, media members by member path ->
    [(zip path, size)]). Rows carry title_collision and media_member resolved by member path."""
    rows: list[dict] = []
    media_by_member: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    for zp in zpaths:
        media, side = zip_members(zp)
        for m in media:
            media_by_member[m.filename].append((zp, m.file_size))
        zname = os.path.basename(zp)
        with zipfile.ZipFile(zp) as zf:
            with ThreadPoolExecutor(workers) as ex:
                for r in ex.map(lambda i: read_sidecar(zf, i.filename), side):
                    if r:
                        r["zip"] = zname
                        r["source"] = "takeout-zip"
                        rows.append(r)
        if progress:
            progress(zname, len(rows), len(media_by_member))
    members_by_folder: dict[str, set[str]] = collections.defaultdict(set)
    for mp in media_by_member:
        members_by_folder[os.path.dirname(mp)].add(os.path.basename(mp))
    finish_rows(rows, members_by_folder)
    return rows, media_by_member


def finish_rows(rows: list[dict], members_by_folder: dict[str, set[str]]) -> int:
    """Mark title collisions (same folder, same title) and settle each row's `media_member`: a row
    that already carries one (an .xmp, resolved by its own naming) keeps it, the rest resolve by
    the Takeout names. A file claimed by two sidecars is ambiguous and left to neither; the
    number of such files is returned so the caller can say so. Every sidecar this leaves without a
    file gets `unresolved`, the reason in words, which unresolved_lines() turns into the ingest log's
    named lines (an .xmp that matched nothing is named by the folder planner, with its own reason)."""
    by_title = collections.Counter((r["folder"], r["title"]) for r in rows if r["title"])
    for r in rows:
        r["title_collision"] = "yes" if by_title[(r["folder"], r["title"])] > 1 else ""
    claims: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        if "media_member" not in r:
            r["media_member"] = resolve_media_member(r["member"], members_by_folder.get(r["folder"], set()))
            if not r["media_member"]:
                r["unresolved"] = f"names no media file in {r['folder'] or 'the top folder'}"
        if r["media_member"]:
            claims[r["media_member"]].append(r)
    ambiguous = 0
    for mm, rs in claims.items():
        if len(rs) > 1:  # two sidecars claim one file: ambiguous, no automatic decision
            for r in rs:
                others = ", ".join(o["member"] for o in rs if o is not r)
                r["unresolved"] = f"claims {os.path.basename(mm)} along with another sidecar ({others}); left to neither"
                r["media_member"] = ""
            ambiguous += 1
    return ambiguous


def unresolved_lines(rows: list[dict]) -> list[str]:
    """One line per sidecar finish_rows left without a file, with its reason, for ingest to name."""
    return [f"sidecar {r['member']}: {r['unresolved']}" for r in rows if not r.get("media_member") and r.get("unresolved")]


def _title_and_counter(name: str) -> tuple[str, str]:
    """The media title a sidecar's name (without `.json`) describes, and its duplicate counter ('' when none).

    Takeout names the sidecar of `IMG_0001.HEIC` `IMG_0001.HEIC.json`, or since 2024
    `IMG_0001.HEIC.supplemental-metadata.json`, the suffix cut short (`.supplemental-metad`, `.suppl`, ...)
    when the whole name would pass its length limit. A second file with the same title in one folder
    becomes `IMG_0001(1).HEIC`, and its sidecar carries the counter after everything else:
    `IMG_0001.HEIC(1).json`, or `IMG_0001.HEIC.supplemental-metadata(1).json`. The suffix is only taken
    off when what is left ends in a media extension, so no other name loses a part.
    """
    counter = ""
    m = _COUNTER.match(name)
    if m:
        name, counter = m.group(1), m.group(2)
    head, dot, tail = name.rpartition(".")
    if dot and tail and _SUPP_WORD.startswith(tail.lower()) and os.path.splitext(head)[1].lower() in MEDIA_EXT:
        name = head
    return name, counter


def resolve_media_member(sidecar_member: str, names_in_folder: set[str]) -> str:
    """Member path of the media file a sidecar describes, or '' when not unambiguous.

    Handles `X.HEIC.json`, `X.HEIC.supplemental-metadata.json` (also cut short), the duplicate
    counter in both namings (`X.HEIC(1).json` and `X.HEIC.supplemental-metadata(1).json` describe
    `X(1).HEIC`), and the older exports' 51-character name truncation by unique prefix match. A
    sidecar with a counter only ever reaches a file that carries that counter: falling back to the
    original `X.HEIC` is how two sidecars once claimed one photo and both were thrown away.
    """
    folder = os.path.dirname(sidecar_member)
    base = os.path.basename(sidecar_member)
    if not base.lower().endswith(".json"):
        return ""
    title, counter = _title_and_counter(base[:-5])
    join = (lambda n: f"{folder}/{n}" if folder else n)
    if counter:
        stem, ext = os.path.splitext(title)
        if f"{stem}({counter}){ext}" in names_in_folder:
            return join(f"{stem}({counter}){ext}")
        candidates = [n for n in names_in_folder if f"({counter})" in n]
    else:
        if title in names_in_folder:
            return join(title)
        candidates = list(names_in_folder)
    # a title an older export cut short: exactly one media name starts with it
    stem = os.path.splitext(title)[0] if "." in title else title
    if len(title) >= 20:
        pref = [n for n in candidates if n.startswith(title) or n.startswith(stem)]
        if len(pref) == 1:
            return join(pref[0])
    return ""


def extract_member(zpath: str, member: str, dest: str, want_size: int, chunk: int = 1 << 20) -> tuple[int, str]:
    """Stream one member to dest, returning (bytes written, sha256)."""
    import hashlib
    h = hashlib.sha256()
    n = 0
    with zipfile.ZipFile(zpath) as zf, zf.open(member) as src, open(dest, "wb") as out:
        while True:
            b = src.read(chunk)
            if not b:
                break
            h.update(b)
            out.write(b)
            n += len(b)
    if n != want_size:
        raise IOError(f"extracted {n} bytes, zip says {want_size}")
    return n, h.hexdigest()
