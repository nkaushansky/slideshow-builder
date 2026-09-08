"""setup: create the environment, install the pinned dependencies, fetch the models, report versions.

    python curate/setup.py [--project <folder>] [--venv <path>] [--skip-models] [--fetch-ffmpeg] [--no-install]

Plain script, no setuptools. What it does, in order:

1. Creates a virtual environment at <repo>/.venv (or --venv) if there is none, and installs
   curate/requirements.txt into it with pip.
2. Fetches the default models into curate/models/ (gitignored) unless the project's config.toml
   points [models] at user-supplied files or --skip-models is given:
     - YuNet face detector from the OpenCV Zoo (Apache-2.0).
     - YOLOv8n person detector: downloads yolov8n.pt from the Ultralytics release assets and exports
       it to ONNX with the `ultralytics` package in a throwaway environment in the system temp folder,
       which is deleted afterwards. The weights are AGPL-3.0 (see curate/models/README.md); they run
       locally and are never committed.
   Every model that identify may load is recorded in curate/models/manifest.json with its SHA-256,
   source, license and version. User-supplied models are recorded with license "user-supplied".
3. Reports the toolchain: Python and each pinned package, Node, npm, Playwright, ffmpeg and ffprobe,
   Google Chrome, VLC, plus OS, CPU, memory and free disk. With --project it also writes
   <project>/environment.md and warns when the project sits on a synced drive.

On Windows without ffmpeg it says where to get a static build; --fetch-ffmpeg downloads the BtbN
win64 GPL build into <repo>/tools/ffmpeg/ (gitignored) and extracts ffmpeg.exe and ffprobe.exe.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent          # curate/
REPO = HERE.parent
MODELS = HERE / "models"
MANIFEST = MODELS / "manifest.json"
REQUIREMENTS = HERE / "requirements.txt"
TOOLS_FFMPEG = REPO / "tools" / "ffmpeg"

YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_FILE = "yunet.onnx"
YOLO_PT_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"
YOLO_FILE = "yolov8n.onnx"
YOLO_IMGSZ = 640
YOLO_OPSET = 12
FFMPEG_WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
SYNCED_MARKERS = ("google drive", "googledrive", "my drive", "onedrive", "dropbox", "icloud", "mobile documents")

WIN = sys.platform.startswith("win")
MAC = sys.platform == "darwin"


def say(*a):
    print(*a, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def first_line(cmd) -> str:
    try:
        r = run(cmd, timeout=30)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0].strip() if out else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def download(url: str, dest: Path, label: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    say(f"  fetching {label} from {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "slideshow-builder-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if total:
                print(f"\r    {got / 1e6:.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        if total:
            print()
    if tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"setup: {label} downloaded as an empty file; check the network and try again")
    os.replace(tmp, dest)


# ---------------------------------------------------------------- 1. the environment

def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if WIN else "bin/python")


def ensure_venv(venv: Path, install: bool) -> Path:
    py = venv_python(venv)
    if not py.exists():
        say(f"creating virtual environment at {venv}")
        r = run([sys.executable, "-m", "venv", str(venv)])
        if r.returncode != 0:
            raise SystemExit(f"setup: venv creation failed:\n{r.stderr}")
    else:
        say(f"virtual environment: {venv}")
    if install:
        say(f"installing {REQUIREMENTS.name} (pinned)")
        r = run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
        r = run([str(py), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)])
        if r.returncode != 0:
            raise SystemExit(f"setup: pip install failed:\n{r.stderr[-2000:]}")
        say("  installed")
    return py


# ---------------------------------------------------------------- 2. the models

def load_manifest() -> dict:
    if MANIFEST.is_file():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            say(f"  ! {MANIFEST} was not valid JSON; rewriting it")
    return {"models": []}


def save_manifest(m: dict) -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    m["written"] = _dt.datetime.now().isoformat(timespec="seconds")
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")


def record(m: dict, entry: dict) -> None:
    m["models"] = [e for e in m.get("models", []) if e.get("name") != entry["name"]] + [entry]


def project_models(project: Path | None) -> dict[str, str]:
    """[models] person_detector / face_detector from the project config, absolute where set."""
    out = {"person_detector": "", "face_detector": ""}
    if not project:
        return out
    cfg = project / "config.toml"
    if not cfg.is_file():
        return out
    with open(cfg, "rb") as f:
        models = tomllib.load(f).get("models", {})
    for k in out:
        raw = (models.get(k) or "").strip()
        if raw:
            p = Path(raw).expanduser()
            out[k] = str((project / p).resolve() if not p.is_absolute() else p.resolve())
    return out


def fetch_yunet(m: dict) -> None:
    dest = MODELS / YUNET_FILE
    if not dest.is_file():
        download(YUNET_URL, dest, "YuNet face detector")
    else:
        say(f"  {YUNET_FILE} already present")
    record(m, {"name": "YuNet", "purpose": "face detection", "file": YUNET_FILE, "sha256": sha256(dest), "source": YUNET_URL,
               "license": "Apache-2.0", "version": "2023mar", "fetched": _dt.date.today().isoformat()})


def export_yolo(m: dict) -> None:
    dest = MODELS / YOLO_FILE
    if dest.is_file():
        say(f"  {YOLO_FILE} already present (delete it to re-export)")
        entry = next((e for e in m.get("models", []) if e.get("name") == "YOLOv8n"), None)
        version = (entry or {}).get("version", "unknown")
    else:
        tmp = Path(tempfile.mkdtemp(prefix="slideshow-yolo-export-"))
        try:
            pt = tmp / "yolov8n.pt"
            download(YOLO_PT_URL, pt, "YOLOv8n weights")
            tvenv = tmp / "venv"
            say("  creating a throwaway environment for the ultralytics export (this pulls torch; several hundred MB, a few minutes)")
            r = run([sys.executable, "-m", "venv", str(tvenv)])
            if r.returncode != 0:
                raise SystemExit(f"setup: throwaway venv failed:\n{r.stderr}")
            tpy = venv_python(tvenv)
            r = run([str(tpy), "-m", "pip", "install", "--quiet", "ultralytics", "onnx"], timeout=1800)
            if r.returncode != 0:
                raise SystemExit(f"setup: pip install ultralytics failed:\n{r.stderr[-2000:]}")
            code = ("from ultralytics import YOLO; import ultralytics, sys; "
                    f"YOLO(r'{pt}').export(format='onnx', imgsz={YOLO_IMGSZ}, opset={YOLO_OPSET}, simplify=False, dynamic=False); "
                    "print('ULTRALYTICS', ultralytics.__version__)")
            say("  exporting to ONNX")
            r = run([str(tpy), "-c", code], timeout=1800, cwd=str(tmp))
            if r.returncode != 0:
                raise SystemExit(f"setup: ONNX export failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
            mver = re.search(r"ULTRALYTICS (\S+)", r.stdout)
            version = mver.group(1) if mver else "unknown"
            out = tmp / "yolov8n.onnx"
            if not out.is_file():
                raise SystemExit(f"setup: export reported success but {out} is missing:\n{r.stdout[-1500:]}")
            MODELS.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out, dest)
            say(f"  exported with ultralytics {version} -> {dest}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    record(m, {"name": "YOLOv8n", "purpose": "person detection", "file": YOLO_FILE, "sha256": sha256(dest),
               "source": YOLO_PT_URL + " exported to ONNX with the ultralytics package",
               "license": "AGPL-3.0", "version": f"ultralytics {version}, imgsz {YOLO_IMGSZ}, opset {YOLO_OPSET}",
               "fetched": _dt.date.today().isoformat(),
               "input_size": YOLO_IMGSZ, "class_index": 0})


def record_user_model(m: dict, name: str, purpose: str, path: str) -> None:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"setup: config.toml names {purpose} model {p}, which does not exist")
    record(m, {"name": name, "purpose": purpose, "file": str(p), "sha256": sha256(p), "source": "config.toml [models]",
               "license": "user-supplied", "version": "", "fetched": _dt.date.today().isoformat()})
    say(f"  recorded user-supplied {purpose} model {p}")


def setup_models(project: Path | None, skip: bool) -> None:
    say("models")
    m = load_manifest()
    supplied = project_models(project)
    if supplied["person_detector"]:
        record_user_model(m, "user-person-detector", "person detection", supplied["person_detector"])
    elif skip:
        say("  --skip-models: YOLOv8n not fetched (identify will refuse to run until it is listed in the manifest)")
    else:
        export_yolo(m)
    if supplied["face_detector"]:
        record_user_model(m, "user-face-detector", "face detection", supplied["face_detector"])
    elif skip:
        say("  --skip-models: YuNet not fetched")
    else:
        fetch_yunet(m)
    save_manifest(m)
    say(f"  manifest: {MANIFEST} ({len(m['models'])} model(s))")


# ---------------------------------------------------------------- 3. the report

def find_tool(name: str, project: Path | None) -> str:
    """config [tools] > PATH > <repo>/tools/ffmpeg/. Empty when nothing is found."""
    if project and (project / "config.toml").is_file():
        with open(project / "config.toml", "rb") as f:
            raw = (tomllib.load(f).get("tools", {}).get(name) or "").strip()
        if raw:
            p = Path(raw).expanduser()
            p = p if p.is_absolute() else (project / p)
            if p.is_file():
                return str(p)
    w = shutil.which(name)
    if w:
        return w
    for cand in (TOOLS_FFMPEG / (name + (".exe" if WIN else "")), TOOLS_FFMPEG / "bin" / (name + (".exe" if WIN else ""))):
        if cand.is_file():
            return str(cand)
    return ""


def chrome_info() -> tuple[str, str]:
    if WIN:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "")):
            exe = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if exe.is_file():
                vers = sorted((d.name for d in exe.parent.iterdir() if d.is_dir() and re.match(r"\d+\.\d+", d.name)), key=lambda s: [int(x) for x in s.split(".")])
                return (vers[-1] if vers else "installed"), str(exe)
    elif MAC:
        app = Path("/Applications/Google Chrome.app")
        if app.is_dir():
            try:
                import plistlib
                with open(app / "Contents" / "Info.plist", "rb") as f:
                    return plistlib.load(f).get("CFBundleShortVersionString", "installed"), str(app / "Contents/MacOS/Google Chrome")
            except Exception:
                return "installed", str(app)
    else:
        for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            w = shutil.which(n)
            if w:
                return first_line([w, "--version"]), w
    return "", ""


def vlc_info() -> tuple[str, str]:
    if WIN:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            exe = Path(base) / "VideoLAN" / "VLC" / "vlc.exe"
            if exe.is_file():
                return "installed", str(exe)
    elif MAC:
        for app in (Path("/Applications/VLC.app"), Path.home() / "Applications" / "VLC.app"):
            if app.is_dir():
                try:
                    import plistlib
                    with open(app / "Contents" / "Info.plist", "rb") as f:
                        return plistlib.load(f).get("CFBundleShortVersionString", "installed"), str(app / "Contents/MacOS/VLC")
                except Exception:
                    return "installed", str(app)
    else:
        w = shutil.which("vlc")
        if w:
            return first_line([w, "--version"]), w
    return "", ""


def memory_gb() -> str:
    try:
        if WIN:
            import ctypes
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS(); ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return f"{ms.ullTotalPhys / 2**30:.1f} GB"
        if MAC:
            return f"{int(first_line(['sysctl', '-n', 'hw.memsize'])) / 2**30:.1f} GB"
        return f"{os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30:.1f} GB"
    except Exception:
        return "unknown"


def pip_versions(py: Path) -> dict[str, str]:
    r = run([str(py), "-m", "pip", "list", "--format=json"])
    try:
        return {p["name"].lower().replace("_", "-"): p["version"] for p in json.loads(r.stdout)}
    except Exception:
        return {}


def pinned() -> list[tuple[str, str]]:
    out = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "==" in line:
            n, v = line.split("==", 1)
            out.append((n.strip(), v.strip()))
    return out


def report(py: Path, project: Path | None) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    rows.append(("OS", f"{platform.system()} {platform.release()} ({platform.version()})", ""))
    rows.append(("CPU", f"{platform.machine()}, {os.cpu_count()} logical cores", platform.processor() or ""))
    rows.append(("memory", memory_gb(), ""))
    disk_at = project if project else REPO
    try:
        du = shutil.disk_usage(disk_at)
        rows.append(("free disk", f"{du.free / 2**30:.0f} GB of {du.total / 2**30:.0f} GB", str(disk_at)))
    except OSError:
        pass
    rows.append(("python (venv)", first_line([str(py), "--version"]).replace("Python ", ""), str(py)))
    have = pip_versions(py)
    for name, want in pinned():
        got = have.get(name.lower().replace("_", "-"), "")
        rows.append((name, got or "MISSING", "" if got == want else f"pinned {want}"))
    node = shutil.which("node")
    rows.append(("node", first_line([node, "--version"]) if node else "MISSING", node or "install Node 24 LTS"))
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    rows.append(("npm", first_line([npm, "--version"]) if npm else "MISSING", npm or ""))
    pw = REPO / "build" / "node_modules" / "playwright" / "package.json"
    if pw.is_file():
        rows.append(("playwright", json.loads(pw.read_text(encoding="utf-8")).get("version", "?"), str(pw.parent)))
    else:
        rows.append(("playwright", "not installed", "run `npm install` in build/"))
    for t in ("ffmpeg", "ffprobe"):
        p = find_tool(t, project)
        ver = first_line([p, "-version"]) if p else ""
        rows.append((t, (ver.split(" version ")[1].split(" ")[0] if " version " in ver else (ver or "MISSING")), p or ("see below" if WIN else "install ffmpeg 7+ (static build is fine)")))
    cv, cp = chrome_info()
    rows.append(("google chrome", cv or "MISSING", cp or "needed by the render (Playwright channel 'chrome')"))
    vv, vp = vlc_info()
    rows.append(("vlc", vv or "MISSING", vp or "needed on the display machine"))
    return rows


def print_table(rows) -> None:
    w1 = max(len(r[0]) for r in rows)
    w2 = max(len(r[1]) for r in rows)
    for a, b, c in rows:
        say(f"  {a:{w1}s}  {b:{w2}s}  {c}")


def write_environment(project: Path, rows) -> None:
    lines = [f"# Environment, {_dt.datetime.now().isoformat(timespec='minutes')}", "",
             "Detected by `python curate/setup.py`. Pin these in BRIEF.md; a version that changes later is a changelog line.", "",
             "| Tool | Version | Where / note |", "|---|---|---|"]
    for a, b, c in rows:
        lines.append(f"| {a} | {b} | {c} |")
    marks = [m for m in SYNCED_MARKERS if m in str(project).lower()]
    if marks:
        lines += ["", f"**Warning:** the project folder looks like it is on a synced drive ({', '.join(marks)}). Synced folders fought both git and file deletion on the first run; prefer a plain local folder."]
    (project / "environment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(f"  wrote {project / 'environment.md'}")


def fetch_ffmpeg_windows() -> None:
    if not WIN:
        say("--fetch-ffmpeg only knows the Windows build; on macOS use a static build from ffmpeg.org or Homebrew, on Linux the distribution package or a static build")
        return
    TOOLS_FFMPEG.mkdir(parents=True, exist_ok=True)
    z = TOOLS_FFMPEG / "ffmpeg-win64-gpl.zip"
    download(FFMPEG_WIN_URL, z, "ffmpeg (BtbN win64 gpl)")
    with zipfile.ZipFile(z) as zf:
        for member in zf.namelist():
            base = member.rsplit("/", 1)[-1]
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                with zf.open(member) as src, open(TOOLS_FFMPEG / base, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                say(f"  extracted {base} -> {TOOLS_FFMPEG / base}")
    z.unlink(missing_ok=True)


# ---------------------------------------------------------------- main

def setup_build(skip: bool) -> None:
    """Install the build side: Playwright (pinned in build/package.json) and its bundled Chromium."""
    say("build side")
    if skip:
        say("  skipped (--skip-node)")
        return
    npm = shutil.which("npm")
    npx = shutil.which("npx")
    if not npm or not npx:
        say("  npm not found; install Node 20 or newer from https://nodejs.org/ and re-run setup")
        return
    build = REPO / "build"
    if (build / "node_modules" / "playwright" / "package.json").is_file():
        say("  playwright already installed in build/node_modules")
    else:
        say("  npm install in build/ (Playwright, pinned)")
        r = run([npm, "install", "--no-audit", "--no-fund"], cwd=str(build))
        if r.returncode != 0:
            say("  ! npm install failed:", (r.stderr or r.stdout or "").strip()[-400:])
            return
    say("  playwright install chromium (the browser the render uses; a few hundred MB, cached per user)")
    r = run([npx, "playwright", "install", "chromium"], cwd=str(build))
    if r.returncode != 0:
        say("  ! playwright install chromium failed:", (r.stderr or r.stdout or "").strip()[-400:])
        say("    the render can still use an installed Google Chrome; see build/README.md")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="setup", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", help="project folder with config.toml; enables user-supplied model paths and writes environment.md")
    ap.add_argument("--venv", default=str(REPO / ".venv"), help="virtual environment path (default <repo>/.venv)")
    ap.add_argument("--skip-models", action="store_true", help="do not fetch the default models")
    ap.add_argument("--fetch-ffmpeg", action="store_true", help="Windows: download a static ffmpeg build into <repo>/tools/ffmpeg/ even if one is on PATH")
    ap.add_argument("--skip-ffmpeg", action="store_true", help="Windows: do not download ffmpeg when it is missing")
    ap.add_argument("--skip-node", action="store_true", help="do not run npm install / playwright install in build/")
    ap.add_argument("--no-install", action="store_true", help="do not run pip, npm or downloads (report only)")
    a = ap.parse_args(argv)

    project = Path(a.project).expanduser().resolve() if a.project else None
    if project and not (project / "config.toml").is_file():
        say(f"setup: {project / 'config.toml'} does not exist; the intake writes it. Continuing without a project.")
        project = None

    say("environment")
    py = ensure_venv(Path(a.venv).expanduser().resolve(), install=not a.no_install)
    setup_models(project, a.skip_models)
    if WIN and not a.no_install and not a.skip_ffmpeg:
        have = find_tool("ffmpeg", project) and find_tool("ffprobe", project)
        if a.fetch_ffmpeg or not have:
            say("ffmpeg")
            fetch_ffmpeg_windows()
    setup_build(skip=a.skip_node or a.no_install)

    say("toolchain")
    rows = report(py, project)
    print_table(rows)
    missing = [r[0] for r in rows if r[1] == "MISSING"]
    if WIN and any(t in missing for t in ("ffmpeg", "ffprobe")):
        say("  ffmpeg is not installed. Re-run setup without --skip-ffmpeg to download a static build into tools/ffmpeg/, or install one from")
        say("  https://www.gyan.dev/ffmpeg/builds/ or https://github.com/BtbN/FFmpeg-Builds/releases and put it on PATH or in config.toml [tools].")
    elif any(t in missing for t in ("ffmpeg", "ffprobe")):
        say("  ffmpeg is not installed. macOS: `brew install ffmpeg`, or a static build from https://evermeet.cx/ffmpeg/ ; Linux: your package manager.")
        say("  Then put it on PATH or set [tools] ffmpeg and ffprobe in config.toml.")
    if project:
        write_environment(project, rows)
        marks = [m for m in SYNCED_MARKERS if m in str(project).lower()]
        if marks:
            say(f"  ! the project folder looks like it is on a synced drive ({', '.join(marks)}); prefer a plain local folder")
    if missing:
        say(f"missing: {', '.join(missing)}")
    else:
        say("everything found. Next: open Claude Code in this folder and say \"Let's build a slideshow from my photos\".")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
