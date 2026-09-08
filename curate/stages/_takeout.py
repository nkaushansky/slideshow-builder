"""Google Takeout helpers for the ingest stage.

A Takeout is a set of zips. Each media member (`.../Photos from 2023/IMG_0001.HEIC`) has a JSON
sidecar next to it (`IMG_0001.HEIC.json`, or the newer `IMG_0001.HEIC.supplemental-metadata.json`,
sometimes truncated) with photoTakenTime, geoData and people tags. The sidecars index in seconds
from the zips' central directories and small reads; nothing is extracted to do it.

Rules from references/03 gate 5: key by member path, never by the `title` inside the sidecar. An
export keeps the original title even when it renames the member with a `(1)` suffix, so two
sidecars in one folder can share a title; both are marked `title_collision` and the index stage
leaves their dates to EXIF and the validate stage.
"""
from __future__ import annotations

import collections
import json
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor

MEDIA_EXT = {".heic", ".heif", ".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
SIDECAR_MAX_BYTES = 64_000
SIDECAR_COLUMNS = ["zip", "member", "title", "folder", "photo_taken_ts", "creation_ts", "lat", "lon",
                   "people", "description", "title_collision", "media_member"]

_SUPP = re.compile(r"\.supplemental-metad[a-z]*$", re.I)
_DUP = re.compile(r"^(.*)\.([A-Za-z0-9]+)\((\d+)\)$")


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
    """The fields the index needs, or None when the JSON is not a photo sidecar."""
    try:
        d = json.loads(zf.read(member).decode("utf-8", errors="replace"))
    except Exception:
        return None
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
                        rows.append(r)
        if progress:
            progress(zname, len(rows), len(media_by_member))
    # title collisions: same folder (across zips), same title
    by_title = collections.Counter((r["folder"], r["title"]) for r in rows if r["title"])
    for r in rows:
        r["title_collision"] = "yes" if by_title[(r["folder"], r["title"])] > 1 else ""
    # media_member by member path
    members_by_folder: dict[str, set[str]] = collections.defaultdict(set)
    for mp in media_by_member:
        members_by_folder[os.path.dirname(mp)].add(os.path.basename(mp))
    claims: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        mm = resolve_media_member(r["member"], members_by_folder.get(r["folder"], set()))
        r["media_member"] = mm
        if mm:
            claims[mm].append(r)
    for mm, rs in claims.items():
        if len(rs) > 1:  # two sidecars claim one file: ambiguous, no automatic decision
            for r in rs:
                r["media_member"] = ""
    return rows, media_by_member


def resolve_media_member(sidecar_member: str, names_in_folder: set[str]) -> str:
    """Member path of the media file a sidecar describes, or '' when not unambiguous.

    Handles `X.HEIC.json`, `X.HEIC.supplemental-metadata.json` (also truncated), `X.HEIC(1).json`
    for `X(1).HEIC`, and Takeout's 51-character name truncation by unique prefix match.
    """
    folder = os.path.dirname(sidecar_member)
    base = os.path.basename(sidecar_member)
    if not base.lower().endswith(".json"):
        return ""
    base = base[:-5]
    base = _SUPP.sub("", base)
    join = (lambda n: f"{folder}/{n}" if folder else n)
    if base in names_in_folder:
        return join(base)
    m = _DUP.match(base)
    if m:
        cand = f"{m.group(1)}({m.group(3)}).{m.group(2)}"
        if cand in names_in_folder:
            return join(cand)
    # truncated sidecar name: exactly one media name starts with it
    stem = os.path.splitext(base)[0] if "." in base else base
    if len(base) >= 20:
        pref = [n for n in names_in_folder if n.startswith(base) or n.startswith(stem)]
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
