"""sheets: numbered contact sheets of the proposed cut, for owner checkpoint 1 and the review rounds.

    python curate/run.py sheets [--project P] [--dry-run] [--force] [--with-drops]
                                [--featured] [--alternates YEAR ...] [--replacements FILE]
                                [--thumb 400] [--cols 5] [--pdf]

Default: one sheet per year of the proposed cut, thumbnails numbered so the owner can answer by
number ("drop 7", "swap 12 for D3"). Drops for the year (cut as over-cap) are grayed below a
line only with --with-drops, so a whole-life show stays at about fifteen sheets.
--featured writes one sheet of the featured picks. --alternates YEAR writes the best unseated
candidates for that year. --replacements FILE reads the live player's flags list (the player writes
one tab-separated `filename<TAB>note<TAB>time` per line; a hand-written line with just a filename
and an optional note after it is read too) and writes one sheet per flagged file with up to ten
candidates from the cut list, plus index/sheets/replacements-pools.json.
--pdf bundles every sheet in index/sheets/ into contact-sheets.pdf, one page per sheet (years
ascending, then featured, alternates, replacements), for an owner who is not at the machine. It
runs after whatever else the command wrote; --pdf alone re-bundles the sheets on disk, since the
default year pass skips sheets that are unchanged.

Every sheet gets lines in index/sheets/index.md mapping numbers to filenames and media_ids.
Each tile's third line says what the identify stage saw: the detector's numbers (`p2 f2 a41%`,
or `people ?` when it did not run) and, after a middle dot, the family names the export's tags
name (`· Sam; Alex`). Spec: references/05-review-loop.md. Age-and-era outlier highlighting
(gate 8) is not in 0.1; month- and year-precision dates are marked so the reviewer can watch those.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import project, say, write_atomic  # noqa: E402
from stages._lenses import (STILL_TYPES, fnum, hamming, inum, load_fonts, pct_of, phash_bits, read_csv,  # noqa: E402
                            thumbnail)

PAD, LAB = 10, 46


def _ffmpeg(P) -> str | None:
    t = P.tool("ffmpeg")
    if os.path.isfile(t):
        return t
    return shutil.which(t)


def _path_of(P, item: dict):
    loc = (item.get("location") or "work").replace("\\", "/")
    rel = loc[len("work"):].strip("/") if loc.startswith("work") else loc
    p = P.work / rel / item["filename"] if rel else P.work / item["filename"]
    if p.is_file():
        return p
    q = P.media / item["filename"]
    return q if q.is_file() else p


def _label(name: str, maxlen: int = 44) -> str:
    return name if len(name) <= maxlen else name[:22] + "…" + name[-(maxlen - 23):]


class SheetWriter:
    def __init__(self, P, thumb: int, cols: int, ffmpeg: str | None, force: bool, dry: bool):
        self.P, self.TH, self.COLS, self.ffmpeg, self.force, self.dry = P, thumb, cols, ffmpeg, force, dry
        self.fonts = load_fonts((12, 13, 20))
        self.state_path = P.sheets / ".state.json"
        self.state = {}
        if self.state_path.is_file():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.state = {}
        self.written = self.skipped = 0
        self.placeholders = 0
        self.names: list[str] = []  # every sheet this run wrote, would write or skipped, for --pdf

    def write(self, name: str, title: str, subtitle: str, entries: list[dict], drops: list[dict] | None = None,
              index_lines: list[str] | None = None) -> None:
        """entries/drops: dicts with num, item, text1, text2, color, gray. Skips when unchanged."""
        self.names.append(name)
        # the presence line is part of the key, so a sheet made before identify ran is written again with the names
        key = hashlib.sha256(json.dumps([[e["num"], e["item"]["media_id"], e["text1"], e.get("text3", "")] for e in (entries + (drops or []))]
                                        + [title, subtitle, self.TH, self.COLS]).encode()).hexdigest()
        out = self.P.sheets / f"{name}.jpg"
        prev = self.state.get(name, {})
        if not self.force and out.is_file() and prev.get("hash") == key:
            self.skipped += 1
            return
        if self.dry:
            say(f"  would write {out.name} ({len(entries)} entries{', %d drops' % len(drops) if drops else ''})")
            self.written += 1
            return
        from PIL import Image, ImageDraw, ImageOps
        f1, fb, fh = self.fonts
        TH, COLS = self.TH, self.COLS

        def grid(rows):
            out_rows = []
            for i in range(0, len(rows), COLS):
                chunk = rows[i:i + COLS]
                ims = []
                for e in chunk:
                    im, kind = thumbnail(str(_path_of(self.P, e["item"])), TH, self.ffmpeg)
                    if kind == "placeholder":
                        self.placeholders += 1
                    if e.get("gray"):
                        im = ImageOps.grayscale(im).convert("RGB")
                        im = Image.blend(im, Image.new("RGB", im.size, (245, 245, 245)), 0.45)
                    ims.append((e, im, kind))
                out_rows.append(ims)
            return out_rows
        top = grid(entries)
        bottom = grid(drops or [])
        Wd = COLS * (TH + PAD) + PAD
        h_rows = sum(max(t[1].height for t in rr) + LAB + PAD for rr in top)
        h_drops = (sum(max(t[1].height for t in rr) + LAB + PAD for rr in bottom) + 40) if bottom else 0
        Ht = 64 + PAD + h_rows + h_drops + PAD
        sh = Image.new("RGB", (Wd, Ht), (250, 250, 250))
        d = ImageDraw.Draw(sh)
        d.text((PAD, 12), title, font=fh, fill=(15, 15, 15))
        d.text((PAD, 40), subtitle, font=fb, fill=(110, 110, 110))
        yy = 64 + PAD

        def paint(rows):
            nonlocal yy
            for rr in rows:
                rh = max(t[1].height for t in rr)
                x = PAD
                for e, im, kind in rr:
                    sh.paste(im, (x, yy))
                    col = e.get("color", (55, 80, 160))
                    d.rectangle([x - 2, yy - 2, x + im.width + 1, yy + im.height + 1], outline=col, width=2)
                    if kind == "placeholder":
                        d.text((x + 8, yy + 8), "no frame (ffmpeg missing)", font=f1, fill=(120, 120, 120))
                    d.text((x, yy + im.height + 3), e["text1"], font=fb, fill=col)
                    d.text((x, yy + im.height + 18), e["text2"], font=f1, fill=(105, 105, 105))
                    d.text((x, yy + im.height + 31), e.get("text3", ""), font=f1, fill=(105, 105, 105))
                    x += TH + PAD
                yy += rh + LAB + PAD
        paint(top)
        if bottom:
            d.line([PAD, yy + 8, Wd - PAD, yy + 8], fill=(150, 150, 150), width=2)
            d.text((PAD, yy + 14), "below the line: dropped for the cap (D numbers); ask for any by number", font=fb, fill=(120, 120, 120))
            yy += 40
            paint(bottom)
        self.P.sheets.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp.jpg")
        sh.save(tmp, "JPEG", quality=86)
        os.replace(tmp, out)
        self.state[name] = {"hash": key, "lines": index_lines or []}
        self.written += 1
        say(f"  wrote {out.name} ({len(entries)} entries{', %d drops' % len(drops) if drops else ''})")

    def finish(self) -> None:
        if self.dry:
            return
        self.P.sheets.mkdir(parents=True, exist_ok=True)
        # index.md is regenerated from the state of every sheet that still exists
        live = {k: v for k, v in self.state.items() if (self.P.sheets / f"{k}.jpg").is_file()}
        self.state = live
        write_atomic(self.state_path, json.dumps(live, indent=0))
        lines = ["# Contact sheets", "", f"Generated {dt.date.today().isoformat()}; people gate `{self.P.people_gate}`. Answer by sheet and number.", ""]
        for k in sorted(live):
            lines.append(f"## {k}.jpg")
            lines.append("")
            lines.extend(live[k].get("lines", []))
            lines.append("")
        write_atomic(self.P.sheets / "index.md", "\n".join(lines) + "\n")


def _sheet_rank(stem: str) -> tuple[int, str]:
    """Page order of the PDF: year sheets ascending, featured, alternates, replacements, then the rest by name."""
    if len(stem) == 4 and stem.isascii() and stem.isdigit():
        return (0, stem)
    if stem == "featured":
        return (1, stem)
    if stem.startswith("alternates-"):
        return (2, stem)
    if stem.startswith("replace-"):
        return (3, stem)
    return (4, stem)


def bundle_pdf(folder, dry: bool = False, planned: list[str] | None = None) -> int:
    """Bundle every sheet (*.jpg) in folder into folder/contact-sheets.pdf, one page per sheet; returns the page count.

    dry: print what would be written and write nothing. planned: the sheet names a dry run would have written,
    so the count matches what a real run leaves on disk. The writer's own half-written *.tmp.jpg is never a page.
    """
    folder = Path(folder)
    stems = set()
    if folder.is_dir():
        stems = {p.stem for p in folder.glob("*.jpg") if not p.name.endswith(".tmp.jpg")}
    if dry:
        stems |= set(planned or [])
    order = sorted(stems, key=_sheet_rank)
    out = folder / "contact-sheets.pdf"
    if not order:
        say(f"  ! no sheets in {folder}; {out.name} not written")
        return 0
    if dry:
        say(f"  would write {out.name} ({len(order)} pages)")
        return len(order)
    from PIL import Image
    pages = []
    try:
        for stem in order:
            with Image.open(folder / f"{stem}.jpg") as im:
                pages.append(im.convert("RGB"))  # a loaded copy, so the file closes here
        tmp = out.with_name(out.name + ".tmp")  # format given explicitly: the temp name has no .pdf suffix
        pages[0].save(tmp, "PDF", save_all=True, append_images=pages[1:], resolution=100.0, quality=86)
        os.replace(tmp, out)
    finally:
        for im in pages:
            im.close()
    say(f"  wrote {out.name} ({len(order)} pages): {out}")
    return len(order)


def _presence(pp: dict | None) -> str:
    """`p2 f2 a41%` from the detector (`people ?` when it did not run), then `· Sam; Alex` when the
    export's tags name family members (people.csv `people`)."""
    if not pp:
        return "people ?"
    if str(pp.get("persons", "")).strip() == "":
        base = "people ?"
    else:
        base = f"p{inum(pp.get('persons'))} f{inum(pp.get('faces'))} a{100 * fnum(pp.get('person_area')):.0f}%"
    names = [n.strip() for n in (pp.get("people") or "").split(";") if n.strip()]
    return f"{base} · {'; '.join(names)}" if names else base


def _entry(num: str, item: dict, sel: dict | None, pp: dict | None, color=(55, 80, 160), gray=False) -> dict:
    t = item.get("type", "")
    marks = []
    if sel:
        if sel.get("pin") == "yes":
            marks.append("PIN")
        if sel.get("anchor"):
            marks.append("[" + sel["anchor"] + "]")
        if sel.get("featured") == "yes":
            marks.append("*F*")
    if t == "livephoto-still":
        marks.append("LP")
    elif t == "video":
        marks.append("VIDEO")
    elif t == "animated-gif":
        marks.append("GIF")
    date = item.get("date", "")
    prec = item.get("precision", "")
    if prec == "month":
        date += " (mo)"
    elif prec == "year":
        date += " (yr)"
    elif not prec:
        date = "undated"
    col = (170, 70, 30) if t in ("video", "animated-gif") else color
    return dict(num=num, item=item, text1=f"{num}  {' '.join(marks)}  {date}".replace("   ", "  "),
                text2=_label(item["filename"][11:] if len(item["filename"]) > 11 else item["filename"], 40),
                text3=_presence(pp), color=(150, 150, 150) if gray else col, gray=gray)


def _index_line(num: str, item: dict) -> str:
    return f"- {num}: `{item['filename']}` {item['media_id'][:12]}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="sheets", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--with-drops", action="store_true", help="gray the year's over-cap drops below a line")
    ap.add_argument("--featured", action="store_true", help="one sheet of the featured picks")
    ap.add_argument("--alternates", action="append", type=int, default=[], metavar="YEAR")
    ap.add_argument("--replacements", metavar="FILE", help="flags list from the live player; one sheet per flagged file")
    ap.add_argument("--thumb", type=int, default=400)
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--alternates-count", type=int, default=12)
    ap.add_argument("--pdf", action="store_true", help="bundle every sheet in the folder into contact-sheets.pdf, one page per sheet")
    a = ap.parse_args(argv)
    P = project()

    sel_path = P.index / "selection.csv"
    if not sel_path.is_file():
        say(f"sheets: {sel_path} missing; run select first")
        return 2
    selection = read_csv(sel_path)
    items = {}
    for r in read_csv(P.index / "items.csv"):  # a parked exact duplicate shares its keeper's media_id; keep the work/ row
        if r["media_id"] not in items or (r.get("location") or "work") == "work":
            items[r["media_id"]] = r
    people_path = P.index / "people.csv"
    people = {r["media_id"]: r for r in read_csv(people_path)} if people_path.is_file() else {}
    has_identity = any((r.get("family_present") or "").strip() for r in people.values())   # identify matched the export's tags
    flags_path = P.index / "flags.csv"
    flags = read_csv(flags_path) if flags_path.is_file() else []
    scores_path = P.index / "_select-scores.json"
    scores = json.loads(scores_path.read_text(encoding="utf-8")).get("scores", {}) if scores_path.is_file() else {}
    ffmpeg = _ffmpeg(P)
    if not ffmpeg:
        say("sheets: ffmpeg not found; video tiles get a gray placeholder")
    # the sheets stay one per year, which is what an owner reviews in one sitting; with [selection] period
    # smaller than a year, a year's cap is the sum of the caps of the periods inside it
    period_caps = P.period_caps()
    caps: dict[int, int] = {}
    for key, cap in period_caps.items():
        if key[:4].isdigit():
            caps[int(key[:4])] = caps.get(int(key[:4]), 0) + cap
    W = SheetWriter(P, a.thumb, a.cols, ffmpeg, a.force, a.dry_run)
    selected = [r for r in selection if r["selected"] == "yes" and r.get("tag") != "companion" and r["media_id"] in items]
    sel_by_id = {r["media_id"]: r for r in selection}

    def year_of(mid):
        return inum((items[mid].get("date") or "")[:4])

    def sort_key(mid):
        return (items[mid].get("date", ""), items[mid]["filename"])

    only_special = a.featured or a.alternates or a.replacements
    if not only_special:
        byy = collections.defaultdict(list)
        for r in selected:
            byy[year_of(r["media_id"])].append(r["media_id"])
        drops_by_year = collections.defaultdict(list)
        if a.with_drops:
            for r in selection:
                if r["selected"] != "yes" and r.get("reason") == "over-cap" and r["media_id"] in items \
                        and items[r["media_id"]].get("type") != "livephoto-video":
                    drops_by_year[year_of(r["media_id"])].append(r["media_id"])
        flags_by_year = collections.defaultdict(collections.Counter)
        for f in flags:
            if f["media_id"] in items and not (f.get("resolved_by") or "").strip():
                flags_by_year[year_of(f["media_id"])][f["gate"]] += 1
        for y in sorted(byy):
            ids = sorted(byy[y], key=sort_key)
            entries, lines = [], []
            for i, mid in enumerate(ids, 1):
                entries.append(_entry(str(i), items[mid], sel_by_id.get(mid), people.get(mid)))
                lines.append(_index_line(str(i), items[mid]))
            drops = []
            for i, mid in enumerate(sorted(drops_by_year.get(y, []), key=sort_key), 1):
                drops.append(_entry(f"D{i}", items[mid], sel_by_id.get(mid), people.get(mid), gray=True))
                lines.append(_index_line(f"D{i}", items[mid]))
            seen = sum(1 for mid in ids if inum(people.get(mid, {}).get("persons")) >= 1 or inum(people.get(mid, {}).get("faces")) >= 1)
            family = sum(1 for mid in ids if people.get(mid, {}).get("family_present") == "yes")
            fam_txt = f", family named in {family}" if has_identity else ""
            fl = flags_by_year.get(y)
            fl_txt = ("flags: " + ", ".join(f"{k} {v}" for k, v in sorted(fl.items()))) if fl else "no open flags"
            title = f"{y}   {P.honoree} {P.age_label(y)}".rstrip()
            sub = (f"gate {P.people_gate}  |  {len(ids)} of cap {caps.get(y, 0)}  |  people detected in {seen} of {len(ids)}{fam_txt}  |  {fl_txt}  |  "
                   f"*F* featured, LP Live Photo, (mo)/(yr) month- or year-precision date")
            W.write(f"{y}", title, sub, entries, drops, lines)

    if a.featured:
        ids = sorted((r["media_id"] for r in selected if r.get("featured") == "yes"), key=sort_key)
        entries = [_entry(str(i), items[m], sel_by_id.get(m), people.get(m)) for i, m in enumerate(ids, 1)]
        lines = [_index_line(str(i), items[m]) for i, m in enumerate(ids, 1)]
        W.write("featured", f"Featured picks ({len(ids)})", "larger tiles; swap by number, criteria in references/04",
                entries, None, lines)

    for y in a.alternates:
        pool = [r for r in selection if r["selected"] != "yes" and r.get("reason") == "over-cap" and r["media_id"] in items
                and items[r["media_id"]].get("type") != "livephoto-video" and year_of(r["media_id"]) == y]
        pool.sort(key=lambda r: -fnum(scores.get(r["media_id"], {}).get("v4")))
        ids = [r["media_id"] for r in pool[:a.alternates_count]]
        entries = [_entry(f"A{i}", items[m], sel_by_id.get(m), people.get(m), color=(20, 120, 90)) for i, m in enumerate(ids, 1)]
        lines = [_index_line(f"A{i}", items[m]) for i, m in enumerate(ids, 1)]
        W.write(f"alternates-{y}", f"Alternates for {y} ({len(ids)} of {len(pool)} unseated)",
                "best unseated candidates by the synthesis score; ask for more with --alternates-count",
                entries, None, lines)

    if a.replacements:
        pools = _replacement_pools(P, a.replacements, selection, items, people, scores, say)
        for n, (leaving, cands) in enumerate(pools.items(), 1):
            lv = items.get(leaving)
            if lv is None:
                continue
            entries = [_entry("LEAVING", lv, sel_by_id.get(leaving), people.get(leaving), color=(190, 40, 40))]
            lines = [_index_line("LEAVING", lv)]
            for i, c in enumerate(cands, 1):
                it = items[c["media_id"]]
                e = _entry(f"C{i}", it, None, people.get(c["media_id"]), color=(20, 90, 170) if not c["pair"] else (140, 60, 160))
                e["text1"] = f"C{i}  {'PAIR ' if c['pair'] else ''}{'VIDEO ' if c['video'] else ''}±{c['dist']}d  {it.get('date', '')}"
                entries.append(e)
                lines.append(_index_line(f"C{i}", it))
            stem = os.path.splitext(lv["filename"])[0][:40]
            W.write(f"replace-{n:02d}-{stem}", f"Replacing {lv['filename']}", "pick a C number or say drop; PAIR = Live Photo still",
                    entries, None, lines)
        if not a.dry_run:
            write_atomic(P.sheets / "replacements-pools.json", json.dumps(pools, indent=1))
            say(f"  wrote replacements-pools.json ({len(pools)} pools)")

    W.finish()
    pdf_pages = bundle_pdf(P.sheets, a.dry_run, W.names) if a.pdf else None
    say(f"sheets: {W.written} {'would be written (dry run)' if a.dry_run else 'written'}, {W.skipped} unchanged, "
        f"{W.placeholders} placeholder tile(s); folder {P.sheets}")
    return 2 if pdf_pages == 0 else 0


def _replacement_pools(P, path: str, selection, items, people, scores, say) -> dict:
    """Per flagged file, up to ten cut candidates from the same weeks (references/05)."""
    from datetime import date as _date
    sim = int(P.get("selection", "diversity_distance", 26))
    byname = {r["filename"]: r for r in items.values()}

    def parse_flag_line(line: str) -> tuple[str, str]:
        """(filename, note) from one line of the flags list.

        The player writes `filename<TAB>note<TAB>time`, and a filename can hold spaces
        ("2020-03-03_Screenshot 2020-03-03.png"), so the first whitespace token is only the last
        resort: on its own it turned that name into a file the index had never heard of."""
        if "\t" in line:
            parts = line.split("\t")
            return parts[0].strip(), " ".join(p.strip() for p in parts[1:] if p.strip())
        if line in byname:
            return line, ""
        hits = [n for n in byname if line.startswith(n)]
        if hits:
            name = max(hits, key=len)        # the longest name that fits, so a note cannot eat part of it
            return name, line[len(name):].strip()
        name = line.split()[0].strip(",;")
        return name, line[len(name):].strip()

    flagged = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            flagged.append(parse_flag_line(line))
    set_bits = [phash_bits(items[r["media_id"]].get("phash", "")) for r in selection
                if r["selected"] == "yes" and r["media_id"] in items]
    set_bits = [b for b in set_bits if b is not None]
    cut = [r for r in selection if r["selected"] != "yes" and r.get("reason") == "over-cap" and r["media_id"] in items
           and items[r["media_id"]].get("type") != "livephoto-video"]
    sharps = sorted(fnum(items[r["media_id"]].get("sharpness")) for r in cut)

    def pdate(d):
        if len(d) < 7 or d[5:7] == "00":
            return None, "year"
        if len(d) < 10 or d[8:10] == "00":
            return _date(int(d[:4]), int(d[5:7]), 15), "month"
        return _date(int(d[:4]), int(d[5:7]), int(d[8:10])), "day"
    pools = {}
    for name, note in flagged:
        lv = byname.get(name)
        if lv is None:
            say(f"  ! flagged file not in the index: {name}")
            continue
        Ld, _ = pdate(lv.get("date", ""))
        cands = []
        for win, allow_year in ((45, False), (120, False), (9999, True)):
            cands = []
            for r in cut:
                it = items[r["media_id"]]
                fd, prec = pdate(it.get("date", ""))
                if prec == "year" or Ld is None:
                    if not allow_year or it.get("date", "")[:4] != lv.get("date", "")[:4]:
                        continue
                    dist = 180
                else:
                    dist = abs((fd - Ld).days)
                    if allow_year:
                        if it.get("date", "")[:4] != lv.get("date", "")[:4] and dist > 120:
                            continue
                    elif dist > win:
                        continue
                b = phash_bits(it.get("phash", ""))
                if b is not None and any(hamming(b, x) <= sim for x in set_bits):
                    continue
                video = it.get("type") in ("video", "animated-gif")
                sharp = fnum(it.get("sharpness"))
                sp = pct_of(sharp, sharps)
                if not video and sp < 0.08:
                    continue
                pp = people.get(r["media_id"], {})
                n, faces, area = inum(pp.get("persons")), inum(pp.get("faces")), fnum(pp.get("person_area"))
                pair = it.get("type") == "livephoto-still" and bool(it.get("companion"))
                score = (0.4 * min(area, 0.8) / 0.8 + 0.2 * sp + 0.1 * (1 if faces > 0 else 0)
                         + 0.15 * max(0, 60 - dist) / 60 + 0.15 * (0.5 if video else 1.0))
                cands.append(dict(media_id=r["media_id"], file=it["filename"], dist=dist, pair=pair,
                                  companion=it.get("companion", ""), video=video, n=n, faces=faces,
                                  area=round(area, 2), score=round(score, 3), prec=prec,
                                  v4=fnum(scores.get(r["media_id"], {}).get("v4"))))
            if len(cands) >= 8:
                break
        cands.sort(key=lambda c: -c["score"])
        pools[lv["media_id"]] = cands[:10]
        say(f"  {name}: pool {len(cands)}, kept {len(pools[lv['media_id']])}, note: {note or '-'}")
    return pools


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
