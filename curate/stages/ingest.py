"""ingest: copy every source file into one flat work/ folder, hash it, verify it, and index the
Takeout sidecars inside the zips before extracting anything.

    python curate/run.py ingest [--dry-run] [--force] [--workers N]

Outputs: work/<flat files>, index/ingest.csv, index/takeout-sidecars.csv (Takeout sources only).
Sources are never modified. The copy is a stream that hashes as it goes; the destination is hashed
again afterwards and a row is `verified = yes` only when size and hash agree. Reruns skip verified
rows, so a killed run is safe to restart. Basename collisions get the source path chain as a
prefix, never a sequence number, so origin stays readable in the name.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import project, write_atomic, say, JUNK_FILES  # noqa: E402
from stages import _takeout  # noqa: E402

INGEST_COLUMNS = ["media_id", "filename", "source_kind", "source_path", "bytes", "mtime", "verified", "note"]
CHUNK = 1 << 20
FLUSH_EVERY = 50


def slug(s: str) -> str:
    return "-".join(str(s).split())


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, buf.getvalue())


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(CHUNK), b""):
            h.update(c)
    return h.hexdigest()


def copy_hashing(src: str, dst: str) -> tuple[int, str]:
    h = hashlib.sha256()
    n = 0
    with open(src, "rb") as f, open(dst, "wb") as out:
        for c in iter(lambda: f.read(CHUNK), b""):
            h.update(c)
            out.write(c)
            n += len(c)
    try:
        shutil.copystat(src, dst)
    except Exception:
        pass
    return n, h.hexdigest()


# ---------------------------------------------------------------- planning

def plan_folder(src_root: Path, kind: str, source_label: str) -> list[dict]:
    items = []
    for root, dirs, names in os.walk(src_root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for n in sorted(names):
            if n.lower() in JUNK_FILES or n.startswith("."):
                continue
            full = os.path.join(root, n)
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, src_root).replace("\\", "/")
            chain = [source_label] + rel.split("/")[:-1]
            items.append(dict(kind=kind, src=full, zip=None, member=None, rel=rel, name=n,
                              chain=chain, size=os.path.getsize(full), mtime=os.path.getmtime(full)))
    return items


def plan_takeout(src_root: Path, source_label: str, sidecar_out: Path, dry: bool) -> tuple[list[dict], list[dict]]:
    zips = [str(src_root)] if src_root.is_file() and src_root.suffix.lower() == ".zip" else _takeout.list_zips(str(src_root))
    if not zips:
        raise SystemExit(f"ingest: Takeout source {src_root} holds no .zip files")
    t0 = time.time()
    rows, media_by_member = _takeout.index_sidecars(
        zips, progress=lambda z, ns, nm: say(f"  sidecars: {z}: {ns} sidecars, {nm} media members so far"))
    say(f"  {len(rows)} sidecars in {len(zips)} zips, {sum(1 for r in rows if r['title_collision'])} title collisions, "
        f"{sum(1 for r in rows if r['media_member'])} resolved to a member, {time.time() - t0:.1f}s")
    items = []
    for member in sorted(media_by_member):
        copies = media_by_member[member]
        zpath, size = copies[0]
        if len({s for _, s in copies}) > 1:
            say(f"  ! {member} appears in {len(copies)} zips with different sizes; using {os.path.basename(zpath)}")
        zname = os.path.basename(zpath)
        parts = member.split("/")
        items.append(dict(kind="takeout", src=None, zip=zpath, member=member, rel=f"{zname}!{member}",
                          name=parts[-1], chain=[source_label] + parts[:-1], size=size, mtime=None))
    return items, rows


def assign_names(items: list[dict]) -> None:
    by_name = collections.Counter(i["name"].lower() for i in items)
    taken: dict[str, dict] = {}
    clashes = []
    for i in items:
        dest = i["name"] if by_name[i["name"].lower()] == 1 else "_".join(slug(p) for p in i["chain"] if p) + "_" + i["name"]
        key = dest.lower()
        if key in taken:
            clashes.append((dest, taken[key]["rel"], i["rel"]))
        taken[key] = i
        i["dest"] = dest
    if clashes:
        for d, a, b in clashes[:10]:
            say(f"  ! name clash: {d} <- {a} and {b}")
        raise SystemExit(f"ingest: {len(clashes)} destination names collide even with the source path chain; "
                         f"give the sources distinct folder names and rerun")


# ---------------------------------------------------------------- copying

def do_copy(item: dict, work: Path) -> dict:
    dst = work / item["dest"]
    row = {"media_id": "", "filename": item["dest"], "source_kind": item["kind"], "source_path": item["rel"],
           "bytes": item["size"], "mtime": f"{item['mtime']:.0f}" if item["mtime"] else "", "verified": "", "note": ""}
    try:
        if dst.exists() and dst.stat().st_size != item["size"]:
            row["note"] = "error: a different file already sits at the target name; not overwritten"
            return row
        if item["kind"] == "takeout":
            n, h1 = _takeout.extract_member(item["zip"], item["member"], str(dst), item["size"])
        else:
            n, h1 = copy_hashing(item["src"], str(dst))
        h2 = sha256_file(str(dst))
        row["media_id"] = h1
        if n == item["size"] and h1 == h2:
            row["verified"] = "yes"
        else:
            row["note"] = f"error: verify failed (copied {n} of {item['size']} bytes, hash {'ok' if h1 == h2 else 'differs'})"
    except Exception as e:
        row["note"] = f"error: {type(e).__name__}: {str(e)[:120]}"
    return row


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="copy again even when a verified row exists")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    P = project()
    dry = a.dry_run
    work, index = P.work, P.index
    ingest_csv = index / "ingest.csv"
    sidecar_csv = index / "takeout-sidecars.csv"

    say(f"ingest: project {P.root}")
    for s in P.sources:
        if not s.path.exists():
            raise SystemExit(f"ingest: source does not exist: {s.path}")
        say(f"  source [{s.kind}] {s.path}")

    # ---- plan
    items: list[dict] = []
    sidecar_rows: list[dict] = []
    labels = collections.Counter(s.path.name for s in P.sources)
    for s in P.sources:
        label = s.path.name if labels[s.path.name] == 1 else f"{s.path.parent.name}-{s.path.name}"
        if s.kind == "takeout":
            its, rows = plan_takeout(s.path, label, sidecar_csv, dry)
            sidecar_rows.extend(rows)
        else:
            its = plan_folder(s.path, s.kind, label)
        say(f"  {len(its)} files, {sum(i['size'] for i in its) / 1e9:.2f} GB in {s.path.name}")
        items.extend(its)
    assign_names(items)
    prefixed = sum(1 for i in items if i["dest"] != i["name"])

    # ---- resume
    existing = {r["source_path"]: r for r in read_csv(ingest_csv)}
    todo, skipped = [], 0
    for i in items:
        r = existing.get(i["rel"])
        if r and r.get("verified") == "yes" and not a.force:
            skipped += 1
        else:
            todo.append(i)
    say(f"plan: {len(items)} files ({prefixed} with a path prefix), {skipped} already verified, {len(todo)} to copy, "
        f"{sum(i['size'] for i in todo) / 1e9:.2f} GB")
    if dry:
        for i in todo[:8]:
            say(f"   {i['rel']} -> work/{i['dest']}")
        if sidecar_rows:
            say(f"   would write {sidecar_csv.name} with {len(sidecar_rows)} rows")
        say("[dry run] nothing written")
        return 0

    index.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    if sidecar_rows:
        write_csv(sidecar_csv, sidecar_rows, _takeout.SIDECAR_COLUMNS)
        say(f"wrote {sidecar_csv} ({len(sidecar_rows)} rows)")

    # ---- copy
    t0 = time.time()
    rows_by_src = dict(existing)
    seen_ids: dict[str, str] = {r["media_id"]: r["filename"] for r in existing.values() if r.get("media_id") and r.get("verified") == "yes"}
    done = failed = dups = 0
    copied_bytes = 0

    def flush():
        ordered = [rows_by_src[i["rel"]] for i in items if i["rel"] in rows_by_src]
        extra = [r for k, r in rows_by_src.items() if k not in {i["rel"] for i in items}]
        write_csv(ingest_csv, ordered + extra, INGEST_COLUMNS)

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for n, row in enumerate(ex.map(lambda it: do_copy(it, work), todo), 1):
            if row["verified"] == "yes":
                done += 1
                copied_bytes += int(row["bytes"])
                first = seen_ids.get(row["media_id"])
                if first and first != row["filename"]:
                    row["note"] = f"duplicate-of:{row['media_id']}"
                    dups += 1
                else:
                    seen_ids[row["media_id"]] = row["filename"]
            else:
                failed += 1
                say(f"  ! {row['source_path']}: {row['note']}")
            rows_by_src[row["source_path"]] = row
            if n % FLUSH_EVERY == 0:
                flush()
                say(f"  {n}/{len(todo)} copied, {time.time() - t0:.0f}s")
    flush()
    verified = sum(1 for r in rows_by_src.values() if r.get("verified") == "yes")
    say(f"ingest: copied {done} ({copied_bytes / 1e9:.2f} GB) in {time.time() - t0:.0f}s, {failed} failed, "
        f"{dups} exact duplicates of an earlier file (kept, noted), {skipped} skipped as already verified")
    say(f"accounting: {len(items)} planned = {verified} verified + {failed} failed + "
        f"{len(items) - verified - failed} not attempted")
    say(f"wrote {ingest_csv}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
