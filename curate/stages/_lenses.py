"""Shared pieces for the select, sheets and handoff stages.

CSV reading and writing in the project's conventions, perceptual-hash distance, rank
percentiles, the candidate records the lenses score, the four lenses themselves and the
featured-pick chooser. The lenses follow `references/04-selection-lenses.md`; the seating
code was ported from the first run's select scripts with every constant moved to config.

A candidate is a dict with: id, name, type, date, prec, year, month, day, px, sharp, area,
n (person count), faces, bits (phash as a uint8 array or None), motion (standalone video or
GIF), lp (a Live Photo still), lat, lon, known (people data present).
"""
from __future__ import annotations

import collections
import csv
import io
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import write_atomic  # noqa: E402

# ---------------------------------------------------------------- CSV in the project's style

ITEMS_COLS = ["media_id", "filename", "original_name", "source_kind", "source_path", "location", "type",
              "companion", "width", "height", "duration_s", "fps", "hdr", "video_codec", "has_audio", "bytes",
              "date", "precision", "date_source", "date_witness", "exif_datetime_original", "container_time",
              "sidecar_time", "camera_make", "camera_model", "phash", "sharpness", "lat", "lon", "burst_group",
              "duplicate_of", "pair_stem", "pair_dt_s", "pair_frame_dist"]
PEOPLE_COLS = ["media_id", "filename", "persons", "person_area", "largest_person", "faces", "largest_face",
               "group_size", "people", "family_present"]
FLAG_COLS = ["media_id", "filename", "gate", "severity", "detail", "suggested_action", "resolved_by", "resolved_on"]
SELECTION_COLS = ["media_id", "filename", "selected", "v1_rank", "v2_rank", "v3_rank", "v4_rank", "consensus",
                  "featured", "pin", "anchor", "tag", "reason"]
CUT_COLS = ["media_id", "filename", "location", "reason", "original_source_path"]
MEDIA_COLS = ["media_id", "filename", "type", "companion", "width", "height", "duration_s", "fps", "hdr", "date",
              "precision", "date_source", "date_witness", "exif_datetime_original", "people", "tag", "featured",
              "video_codec", "has_audio", "original_source_path"]

MOTION_TYPES = {"video", "animated-gif"}
STILL_TYPES = {"still", "livephoto-still"}


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, cols) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    write_atomic(path, buf.getvalue())


def fnum(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def inum(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- hashes and percentiles

POP = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(1).astype(np.int16)


def phash_bits(hexstr: str):
    """A 256-bit (or any even-length) hex phash as a uint8 array, or None when blank or malformed."""
    h = (hexstr or "").strip()
    if not h or len(h) % 2:
        return None
    try:
        return np.frombuffer(bytes.fromhex(h), dtype=np.uint8)
    except ValueError:
        return None


def hamming(a, b) -> int:
    if a is None or b is None or a.shape != b.shape:
        return 999
    return int(POP[np.bitwise_xor(a, b)].sum())


def pct(vals) -> np.ndarray:
    """Rank percentile in [0, 1]; a flat array gets 0.5 everywhere."""
    a = np.array(list(vals), dtype=float)
    if len(a) < 2 or a.max() == a.min():
        return np.ones(len(a)) * 0.5
    return a.argsort().argsort() / (len(a) - 1)


def pct_of(v, sorted_vals) -> float:
    import bisect
    return bisect.bisect_left(sorted_vals, v) / max(1, len(sorted_vals) - 1)


# ---------------------------------------------------------------- dates

def month_of(date: str) -> int:
    return int(date[5:7]) if len(date) >= 7 and date[5:7] != "00" else 0


def day_of(date: str):
    return date if len(date) >= 10 and date[8:10] != "00" and date[5:7] != "00" else None


def date_key(date: str, prec: str) -> str:
    """Ordering key: day precision the date, month the 15th, year July 1 (references/06)."""
    y = date[:4]
    if prec == "day":
        return date
    if prec == "month":
        return f"{y}-{date[5:7]}-15"
    return f"{y}-07-01"


def km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- candidates

def make_candidate(item: dict, person: dict | None) -> dict:
    d = item.get("date", "") or ""
    w, h = inum(item.get("width")), inum(item.get("height"))
    t = item.get("type", "")
    return {
        "id": item["media_id"], "name": item["filename"], "type": t, "date": d,
        "prec": item.get("precision", "") or "", "year": inum(d[:4]) if d[:4].isdigit() else 0,
        "month": month_of(d), "day": day_of(d), "px": w * h, "w": w, "h": h,
        "sharp": fnum(item.get("sharpness")), "bits": phash_bits(item.get("phash", "")),
        "area": fnum((person or {}).get("person_area")), "n": inum((person or {}).get("persons")),
        "faces": inum((person or {}).get("faces")),
        "known": bool(person) and (str(person.get("persons", "")).strip() != ""),
        "motion": t in MOTION_TYPES, "lp": t == "livephoto-still" and bool(item.get("companion")),
        "lat": fnum(item.get("lat"), None) if item.get("lat") else None,
        "lon": fnum(item.get("lon"), None) if item.get("lon") else None,
        "companion": item.get("companion", "") or "",
    }


def pscore(c: dict) -> float:
    """People score used by v3 and the anchor choosers: person-area plus a small group bonus."""
    return (c["area"] + 0.05 * min(c["n"], 6)) if c["known"] else 0.3


class Seater:
    """Seats candidates for one period under a cap and the diversity rule."""

    def __init__(self, budget: int, sim: int):
        self.budget, self.sim = budget, sim
        self.picked: list[dict] = []
        self.ids: set[str] = set()
        self.pb: list = []
        self.tags: dict[str, list[str]] = {}
        self.used_days: set[str] = set()

    def full(self) -> bool:
        return len(self.picked) >= self.budget

    def ok(self, c: dict) -> bool:
        b = c["bits"]
        if b is None or not self.pb:
            return True
        pb = [x for x in self.pb if x.shape == b.shape]
        if not pb:
            return True
        return int(POP[np.bitwise_xor(np.stack(pb), b)].sum(1).min()) > self.sim

    def take(self, c: dict, tag: str | None = None) -> None:
        self.picked.append(c)
        self.ids.add(c["id"])
        if c["bits"] is not None:
            self.pb.append(c["bits"])
        if c["day"]:
            self.used_days.add(c["day"])
        if tag:
            self.tags.setdefault(c["id"], []).append(tag)

    def seat(self, c: dict, tag: str | None = None) -> bool:
        if c["id"] in self.ids or self.full():
            return False
        self.take(c, tag)
        return True

    def ranks(self) -> dict[str, int]:
        return {c["id"]: i + 1 for i, c in enumerate(self.picked)}


def _round_robin(seater: Seater, buckets: dict, order: list, chooser):
    """Sweep the buckets in order, taking one candidate per bucket per round, until nothing moves."""
    prog = True
    while not seater.full() and prog:
        prog = False
        for k in order:
            if seater.full():
                break
            c = chooser(buckets.get(k, []))
            if c is not None:
                seater.take(c)
                prog = True


# ---------------------------------------------------------------- the lenses

def lens_v1(L: list[dict], budget: int, sim: int) -> Seater:
    """Quality: 0.6 pixel-count percentile + 0.4 sharpness percentile; month round-robin, best first."""
    s = 0.6 * pct(c["px"] for c in L) + 0.4 * pct(c["sharp"] for c in L)
    score = {c["id"]: float(s[i]) for i, c in enumerate(L)}
    bymo = collections.defaultdict(list)
    for c in L:
        bymo[c["month"]].append(c)
    for k in bymo:
        bymo[k].sort(key=lambda c: -score[c["id"]])
    S = Seater(budget, sim)

    def choose(cands):
        for c in cands:
            if c["id"] not in S.ids and S.ok(c):
                return c
        return None
    _round_robin(S, bymo, sorted(bymo), choose)
    return S


def _v2_once(L, budget, sim, v1ids, bonus) -> Seater:
    area = pct(c["area"] if c["known"] else 0.0 for c in L)
    grp = np.array([min(c["n"], 6) / 6 if c["known"] else 0.3 for c in L])
    s = (0.35 * area + 0.15 * grp + 0.20 * pct(c["sharp"] for c in L) + 0.15 * pct(c["px"] for c in L)
         + np.array([0.0 if c["id"] in v1ids else bonus for c in L]))
    score = {c["id"]: float(s[i]) for i, c in enumerate(L)}
    bymo = collections.defaultdict(list)
    for c in L:
        bymo[c["month"]].append(c)
    for k in bymo:
        bymo[k].sort(key=lambda c: -score[c["id"]])
    months = sorted(bymo)
    S = Seater(budget, sim)
    # phase 1: one deliberate motion item per month
    for k in months:
        if S.full():
            break
        for c in bymo[k]:
            if c["motion"] and c["id"] not in S.ids and S.ok(c):
                S.take(c, "MOTION")
                break
    # phase 1b: months without motion get the best Live Photo still
    for k in months:
        if S.full():
            break
        if any(c["month"] == k and c["motion"] for c in S.picked):
            continue
        for c in bymo[k]:
            if c["lp"] and c["id"] not in S.ids and S.ok(c):
                S.take(c, "MOTION-LP")
                break

    def choose(cands):
        for c in cands:
            if c["id"] not in S.ids and S.ok(c):
                return c
        return None
    _round_robin(S, bymo, months, choose)
    return S


def lens_v2(L: list[dict], budget: int, sim: int, v1ids: set[str]) -> Seater:
    """People and motion, with a novelty bonus raised until at most half the picks overlap v1."""
    bonus, S = 0.15, None
    for _ in range(6):
        S = _v2_once(L, budget, sim, v1ids, bonus)
        if not S.picked or len(S.ids & v1ids) / len(S.ids) <= 0.50:
            break
        bonus += 0.10
    return S


def _day_passes(S: Seater, L: list[dict], score) -> None:
    """Month round-robin over unused days: new days first, then dayless files, then seconds."""
    months = sorted({c["month"] for c in L if c["month"] > 0})
    order = months + ([0] if any(c["month"] == 0 for c in L) else [])

    def pick_in_month(mo, allow_used_day, allow_dayless):
        cand = sorted((c for c in L if c["month"] == mo and c["id"] not in S.ids), key=lambda c: -score(c))
        for c in cand:
            d = c["day"]
            if d is None and not allow_dayless:
                continue
            if d is not None and d in S.used_days and not allow_used_day:
                continue
            if S.ok(c):
                S.take(c)
                return True
        return False
    for allow_used, allow_dayless_real in ((False, False), (False, True), (True, True)):
        prog = True
        while not S.full() and prog:
            prog = False
            for mo in order:
                if S.full():
                    break
                if pick_in_month(mo, allow_used, allow_dayless_real or mo == 0):
                    prog = True


def lens_v3(L: list[dict], budget: int, sim: int, anchors: dict[str, list[str]]) -> Seater:
    """Breadth and traditions: anchors first, then one photo per distinct day, month round-robin."""
    S = Seater(budget, sim)
    byid = {c["id"]: c for c in L}
    for cid, tags in anchors.items():
        if cid in byid:
            for t in tags:
                S.seat(byid[cid], t)
    _day_passes(S, L, pscore)
    return S


def lens_v4(L: list[dict], budget: int, sim: int, pins: set[str], anchors: dict[str, list[str]],
            consensus: dict[str, int], motion_per_month: int = 1) -> tuple[Seater, dict[str, float]]:
    """Synthesis: pins, anchors, one motion item per month, then month round-robin over unused days."""
    area = pct(c["area"] if c["known"] else 0.0 for c in L)
    grp = np.array([min(c["n"], 6) / 6 if c["known"] else 0.3 for c in L])
    s = (0.40 * area + 0.10 * grp + 0.20 * pct(c["sharp"] for c in L) + 0.15 * pct(c["px"] for c in L)
         + 0.15 * np.array([consensus.get(c["id"], 0) / 3 for c in L]))
    score = {c["id"]: float(s[i]) for i, c in enumerate(L)}
    S = Seater(budget, sim)
    byid = {c["id"]: c for c in L}
    for cid in pins:
        if cid in byid:
            S.seat(byid[cid], "PIN")
    for cid, tags in anchors.items():
        if cid in byid:
            for t in tags:
                S.seat(byid[cid], t)
    months = sorted({c["month"] for c in L if c["month"] > 0})
    for mo in months:
        if S.full():
            break
        have = sum(1 for c in S.picked if c["month"] == mo and c["motion"])
        for c in sorted((c for c in L if c["month"] == mo and c["motion"] and c["id"] not in S.ids),
                        key=lambda c: -score[c["id"]]):
            if have >= motion_per_month or S.full():
                break
            if S.ok(c):
                S.take(c, "MOTION")
                have += 1
    for mo in months:
        if S.full():
            break
        if any(c["month"] == mo and (c["motion"] or c["lp"]) for c in S.picked):
            continue
        for c in sorted((c for c in L if c["month"] == mo and c["lp"] and c["id"] not in S.ids),
                        key=lambda c: -score[c["id"]]):
            if S.ok(c):
                S.take(c, "MOTION-LP")
                break
    _day_passes(S, L, lambda c: score[c["id"]])
    return S, score


# ---------------------------------------------------------------- featured picks

def choose_featured(stills: list[dict], fraction: float, min_per_year: int, sim: int) -> tuple[list[dict], dict]:
    """About `fraction` of the selected stills, spread by year, day-diverse, both orientations."""
    if not stills:
        return [], {}
    sharps = sorted(c["sharp"] for c in stills)
    ress = sorted(c["px"] for c in stills)
    cand = []
    for c in stills:
        n, faces = c["n"], c["faces"]
        people_ok = (not c["known"]) or n >= 1 or faces >= 1
        ok = people_ok and n <= 3 and min(c["w"], c["h"]) >= 1000 and max(c["w"], c["h"]) >= 1500 \
            and pct_of(c["sharp"], sharps) >= 0.10
        score = (0.45 * min(c["area"], 0.8) / 0.8 + 0.20 * pct_of(c["sharp"], sharps) + 0.15 * pct_of(c["px"], ress)
                 + 0.10 * (1.0 if n <= 2 else 0.4) + 0.10 * (1.0 if faces > 0 else 0.0))
        cand.append(dict(c, ok=ok, fscore=score))
    el = [c for c in cand if c["ok"]]
    target = max(1, round(fraction * len(stills)))
    ycount = collections.Counter(c["year"] for c in cand)
    yel = collections.Counter(c["year"] for c in el)
    years = sorted(ycount)
    raw = {y: target * ycount[y] / len(stills) for y in years}
    q = {y: int(raw[y]) for y in years}
    for y in years:
        if yel.get(y, 0) > 0:
            q[y] = max(q[y], min(min_per_year, yel[y]))
    rem = target - sum(q.values())
    for y in sorted(years, key=lambda y: raw[y] - int(raw[y]), reverse=True):
        if rem <= 0:
            break
        if yel.get(y, 0) > q[y]:
            q[y] += 1
            rem -= 1
    q = {y: min(q[y], yel.get(y, 0)) for y in years}
    picks = []
    for y in years:
        pool = sorted((c for c in el if c["year"] == y), key=lambda c: -c["fscore"])
        got, used = [], set()
        for c in pool:
            if len(got) >= q[y]:
                break
            if c["day"] and c["day"] in used:
                continue
            if any(hamming(c["bits"], g["bits"]) <= sim for g in got):
                continue
            got.append(c)
            if c["day"]:
                used.add(c["day"])
        for c in pool:
            if len(got) >= q[y]:
                break
            if c in got or any(hamming(c["bits"], g["bits"]) <= sim for g in got):
                continue
            got.append(c)
        if got and not any(g["h"] > g["w"] for g in got):
            ports = [c for c in pool if c["h"] > c["w"] and c not in got
                     and not any(hamming(c["bits"], g["bits"]) <= sim for g in got[:-1])]
            if ports and ports[0]["fscore"] >= 0.85 * got[-1]["fscore"]:
                got[-1] = ports[0]
        picks += got
    return picks, q


# ---------------------------------------------------------------- fonts and thumbnails (sheets)

def load_fonts(sizes=(11, 12, 19)):
    """Best available truetype fonts per platform, else Pillow's default. Returns (small, bold, header)."""
    from PIL import ImageFont
    if sys.platform.startswith("win"):
        regular, bold = ["segoeui.ttf", "arial.ttf"], ["segoeuib.ttf", "arialbd.ttf"]
    elif sys.platform == "darwin":
        regular, bold = ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"], \
            ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial Bold.ttf"]
    else:
        regular = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]
        bold = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]

    def first(names, size):
        for n in names:
            try:
                return ImageFont.truetype(n, size)
            except OSError:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()
    return first(regular, sizes[0]), first(bold, sizes[1]), first(bold, sizes[2])


def thumbnail(path: str, size: int, ffmpeg: str | None):
    """(image, kind) where kind is 'image', 'video' or 'placeholder'. Never raises."""
    import subprocess
    import tempfile
    from PIL import Image, ImageFile, ImageOps
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".mov", ".mp4", ".m4v"):
        try:
            with Image.open(path) as im:
                try:
                    im.draft("RGB", (size * 3, size * 3))
                except Exception:
                    pass
                n = getattr(im, "n_frames", 1)
                if n > 1 and im.format == "GIF":
                    im.seek(n // 2)
                    fr = im.convert("RGBA")
                    bg = Image.new("RGBA", fr.size, (255, 255, 255, 255))
                    im2 = Image.alpha_composite(bg, fr).convert("RGB")
                else:
                    im2 = ImageOps.exif_transpose(im).convert("RGB")
                im2.thumbnail((size, size), Image.LANCZOS)
                return im2.copy(), "image"
        except Exception:
            pass
    if ffmpeg:
        tmp = tempfile.mkdtemp()
        try:
            best, bestb = None, -1.0
            for ss in ("0.5", "1.5", "3.0"):
                f = os.path.join(tmp, "f.png")
                try:
                    subprocess.run([ffmpeg, "-y", "-v", "quiet", "-ss", ss, "-i", path, "-frames:v", "1", f],
                                   timeout=60, check=False)
                except Exception:
                    break
                if not (os.path.exists(f) and os.path.getsize(f) > 0):
                    continue
                with Image.open(f) as fr:
                    im = fr.convert("RGB")
                    im.load()
                os.remove(f)
                b = float(np.asarray(im.convert("L").resize((32, 32)), dtype=float).mean())
                if b > bestb:
                    best, bestb = im, b
                if b >= 20:
                    break
            if best is not None:
                best.thumbnail((size, size), Image.LANCZOS)
                return best, "video"
        finally:
            try:
                for n in os.listdir(tmp):
                    os.remove(os.path.join(tmp, n))
                os.rmdir(tmp)
            except OSError:
                pass
    ph = Image.new("RGB", (size, int(size * 0.7)), (225, 225, 225))
    return ph, "placeholder"
