"""setup: create the environment, install the pinned dependencies, fetch the models, report versions.

    python curate/setup.py [--project <folder>] [--apply] [--venv <path>] [--skip-models]
                           [--skip-node] [--fetch-ffmpeg] [--skip-ffmpeg] [--no-install]

Plain script, no setuptools. Needs Python 3.11 or newer. What it does, in order:

1. Creates a virtual environment at <repo>/.venv (or --venv, which then has to be named in
   SLIDESHOW_VENV for run.py to find it) if there is none, and installs
   curate/requirements.txt into it with pip. Then detects what Step 0 of the intake would
   otherwise ask: the machine's IANA timezone (tzlocal in the venv, else TZ, /etc/localtime,
   /etc/timezone) and the logical resolution of its screen (GetSystemMetrics on Windows,
   system_profiler on macOS, xrandr on Linux). With --project --apply the detected values are
   written into config.toml where it is blank ([project] timezone when missing, blank or "UTC";
   [output] resolution; [machines] build_os); without --apply the lines to paste are printed.
2. On Windows, downloads the BtbN win64 GPL ffmpeg build into <repo>/tools/ffmpeg/ (gitignored)
   and extracts ffmpeg.exe and ffprobe.exe whenever either is missing; --fetch-ffmpeg downloads one
   even when there is already one on PATH, --skip-ffmpeg leaves it alone. On macOS and Linux it
   only says where to get a build. Then installs the build side in build/ with npm (Playwright and
   the Chromium the render uses) unless --skip-node.
3. Fetches the default models into curate/models/ (gitignored) unless the project's config.toml
   points [models] at user-supplied files or --skip-models is given:
     - YuNet face detector from the OpenCV Zoo (Apache-2.0).
     - YOLOv8n person detector: downloads yolov8n.pt from the Ultralytics release assets and exports
       it to ONNX with the `ultralytics` package in a throwaway environment in the system temp folder,
       which is deleted afterwards. The weights are AGPL-3.0 (see curate/models/README.md); they run
       locally and are never committed.
   Every model that identify may load is recorded in curate/models/manifest.json with its SHA-256,
   source, license and version. User-supplied models are recorded with license "user-supplied".
   This step runs last and never ends setup: a download or an export that fails is a warning, one
   model failing does not cost the other, and the rest of the toolchain is installed and reported.
4. Reports the toolchain: Python and each pinned package, Node, npm, Playwright, ffmpeg and ffprobe,
   Google Chrome, VLC, plus OS, CPU, memory and free disk. With --project it also writes
   <project>/environment.md and warns when the project sits on a synced drive.

--no-install reports only: no pip, no npm, no model download or export.
"""
from __future__ import annotations

import sys

# Above every other import on purpose: tomllib is 3.11 and later, and so is common.py through it, so on
# the very versions this message is for the import fails first and the person sees a ModuleNotFoundError
# instead of a sentence. python.org's big download button also runs ahead of what the pins and the
# ultralytics export have wheels for, which is the warning main() prints for 3.14 and newer.
if sys.version_info < (3, 11):
    print(f"setup: this needs Python 3.11 or newer; the one running it is "
          f"{'.'.join(str(n) for n in sys.version_info[:3])} ({sys.executable}). "
          f"Install 3.11 or newer and run setup with that interpreter.", flush=True)
    raise SystemExit(2)

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
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

sys.path.insert(0, str(HERE))
from common import set_config_value  # noqa: E402  (standard library only, so it runs before the venv exists)

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
            raise SystemExit(f"setup: pip install failed. It ran with Python {sys.version} ({sys.executable}); "
                             f"the pins in {REQUIREMENTS.name} need Python 3.11 or newer, so a 'No matching distribution' "
                             f"here usually means an older interpreter.\n{r.stderr[-2000:]}")
        say("  installed")
    return py


# ---------------------------------------------------------------- 1b. what Step 0 detects

# What a machine with no zone set reports; not a place, so it counts as "not detected".
UTC_NAMES = {"utc", "etc/utc", "etc/uct", "uct", "gmt", "etc/gmt", "etc/gmt0", "etc/gmt+0", "etc/gmt-0", "gmt0",
             "gmt+0", "gmt-0", "greenwich", "etc/greenwich", "universal", "etc/universal", "zulu", "etc/zulu"}
_ZONE_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+)+$")


def _py_output(py: Path, code: str) -> str:
    """stdout of a one-liner run by the venv's Python, or '' when it fails (a package not installed, say)."""
    try:
        r = run([str(py), "-c", code], timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def _is_zone(name: str, known: set[str]) -> bool:
    """A real IANA key: listed by zoneinfo when this Python has a database, else at least Area/Location shaped."""
    if not name or any(ch.isspace() for ch in name):
        return False
    return name in known if known else bool(_ZONE_SHAPE.match(name))


def detect_timezone(py: Path) -> str:
    """The build machine's IANA zone, or '' when nothing more specific than UTC can be found.

    tzlocal in the venv first (it reads the Windows registry and macOS/Linux settings), then env TZ,
    then the /etc/localtime symlink under a zoneinfo folder, then /etc/timezone. A UTC answer is
    what containers and fresh servers report, not where the owner is, so it counts as not detected
    and the intake asks."""
    cands = [_py_output(py, "import tzlocal; print(tzlocal.get_localzone_name())"),
             os.environ.get("TZ", "").lstrip(":")]
    try:
        target = os.readlink("/etc/localtime").replace("\\", "/")
        if "zoneinfo/" in target:
            cands.append(target.split("zoneinfo/", 1)[1])
    except OSError:  # not a symlink, or no such file (Windows)
        pass
    try:
        cands.append(Path("/etc/timezone").read_text(encoding="utf-8", errors="replace").strip())
    except OSError:
        pass
    try:
        import zoneinfo
        known = set(zoneinfo.available_timezones())
    except Exception:
        known = set()
    for c in cands:
        c = (c or "").strip()
        if c and c.lower() not in UTC_NAMES and _is_zone(c, known):
            return c
    return ""


def detect_display() -> str:
    """The logical resolution of this machine's screen as 'WxH', or '' when it cannot be read.

    Windows: GetSystemMetrics without SetProcessDPIAware, so a scaled display reports the logical
    size the browser viewport and VLC see. macOS: system_profiler's first 'UI Looks like', which is
    the same thing, else its first 'Resolution' (the panel's pixels). Linux: the mode xrandr marks
    current with a star. A headless session gives ''."""
    try:
        if WIN:
            import ctypes
            u = ctypes.windll.user32
            w, h = int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1))
            return f"{w}x{h}" if w > 0 and h > 0 else ""
        if MAC:
            r = run(["system_profiler", "SPDisplaysDataType"], timeout=90)
            text = r.stdout or ""
            m = re.search(r"UI Looks like:\s*(\d+)\s*x\s*(\d+)", text) or re.search(r"Resolution:\s*(\d+)\s*x\s*(\d+)", text)
            return f"{m.group(1)}x{m.group(2)}" if m else ""
        xr = shutil.which("xrandr")
        if xr:
            r = run([xr, "--query"], timeout=30)
            for ln in (r.stdout or "").splitlines():
                m = re.match(r"^\s*(\d+)x(\d+)[a-z]?\s+.*\*", ln)
                if m:
                    return f"{m.group(1)}x{m.group(2)}"
    except Exception:  # no window station, no DISPLAY, a tool that is not there: not detected
        pass
    return ""


def build_os_name() -> str:
    """'Windows 11', 'macOS 15.6', 'Ubuntu 24.04.1 LTS': what [machines] build_os records."""
    if WIN:
        try:
            build = int(platform.version().split(".")[-1])
        except ValueError:
            build = 0
        return "Windows 11" if build >= 22000 else f"Windows {platform.release()}"
    if MAC:
        v = platform.mac_ver()[0]
        return f"macOS {v}" if v else "macOS"
    try:
        pretty = platform.freedesktop_os_release().get("PRETTY_NAME", "")
    except (OSError, AttributeError):
        pretty = ""
    return pretty or f"Linux {platform.release()}"


def detect_all(py: Path) -> dict[str, str]:
    return {"timezone": detect_timezone(py), "display": detect_display(), "build_os": build_os_name()}


def apply_detected(project: Path | None, detected: dict[str, str], apply: bool) -> None:
    """Record what Step 0 found in config.toml with --apply; without it, print the lines to paste.

    Only blanks are filled: a [project] timezone that is missing, blank or "UTC"; a missing or
    blank [output] resolution; a blank [machines] build_os. An answer already in the config stands.
    Comments and the order of the file are kept (common.set_config_value)."""
    if project is None:
        if apply:
            say("  --apply needs --project <folder> with a config.toml in it; nothing written")
        return
    cfg_path = project / "config.toml"
    with open(cfg_path, "rb") as f:
        cfg = tomllib.load(f)

    def current(section: str, key: str) -> str:
        return str(cfg.get(section, {}).get(key, "") or "").strip()

    wanted = []
    if detected["timezone"] and current("project", "timezone") in ("", "UTC"):
        wanted.append(("project", "timezone", detected["timezone"]))
    if detected["display"] and not current("output", "resolution"):
        wanted.append(("output", "resolution", detected["display"]))
    if detected["build_os"] and not current("machines", "build_os"):
        wanted.append(("machines", "build_os", detected["build_os"]))
    if not wanted:
        if not detected["timezone"] and not detected["display"]:
            say(f"  nothing detected to write; the intake asks for the timezone and the display resolution")
        else:
            say(f"  {cfg_path.name} already records what was detected; nothing to write")
        return
    for section, key, value in wanted:
        literal = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if apply:
            changed = set_config_value(cfg_path, section, key, literal)
            say(f"  wrote [{section}] {key} = {literal} into {cfg_path}" if changed else f"  [{section}] {key} = {literal} was already there")
        else:
            say(f"  detected [{section}] {key} = {literal}; not written. Re-run with --apply, or paste that line under [{section}] in {cfg_path}")


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


def _try_model(failures: list[str], label: str, step) -> None:
    """Run one model step, so that the one that fails costs neither the other one nor the manifest.

    The export is the long, fragile half of this script; a torch wheel that will not install must
    not take a YuNet that downloaded fine with it. The reason is kept for the caller to report."""
    try:
        step()
    except KeyboardInterrupt:
        raise
    except (SystemExit, Exception) as e:
        failures.append(f"{label}: {str(e) or e.__class__.__name__}")


def setup_models(project: Path | None, skip: bool) -> None:
    say("models")
    m = load_manifest()
    supplied = project_models(project)
    failures: list[str] = []
    if supplied["person_detector"]:
        _try_model(failures, "person detector",
                   lambda: record_user_model(m, "user-person-detector", "person detection", supplied["person_detector"]))
    elif skip:
        say("  --skip-models: YOLOv8n not fetched (identify will refuse to run until it is listed in the manifest)")
    else:
        _try_model(failures, "person detector", lambda: export_yolo(m))
    if supplied["face_detector"]:
        _try_model(failures, "face detector",
                   lambda: record_user_model(m, "user-face-detector", "face detection", supplied["face_detector"]))
    elif skip:
        say("  --skip-models: YuNet not fetched")
    else:
        _try_model(failures, "face detector", lambda: fetch_yunet(m))
    save_manifest(m)                    # written for whatever did succeed, even when one model did not
    say(f"  manifest: {MANIFEST} ({len(m['models'])} model(s))")
    if failures:
        raise SystemExit("; ".join(failures))


def setup_models_reported(project: Path | None, skip: bool, no_install: bool) -> None:
    """The model step as main() runs it: last, and never able to end setup.

    Before this, a torch failure in the export raised SystemExit before ffmpeg and Playwright were
    installed and before the table printed, so one missing wheel left the machine with nothing."""
    if no_install:
        say("models")
        say("  --no-install: nothing downloaded or exported (report only)")
        return
    try:
        setup_models(project, skip)
    except KeyboardInterrupt:
        raise
    except (SystemExit, Exception) as e:
        say(f"  ! models not installed: {str(e) or e.__class__.__name__}")
        say("    The pipeline still runs without them: identify --tags-only needs no model, and [family] gate =")
        say("    \"family\" or gate = \"none\" work with it. Re-run `python curate/setup.py` later to try the")
        say("    download again, or pass --skip-models to leave the models out.")


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


def report(py: Path, project: Path | None, detected: dict[str, str] | None = None) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    rows.append(("OS", f"{platform.system()} {platform.release()} ({platform.version()})", ""))
    d = detected or {}
    rows.append(("timezone", d.get("timezone") or "not detected", "config.toml [project] timezone"))
    rows.append(("display", d.get("display") or "not detected", "logical resolution of the build machine's screen; [output] resolution"))
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
    rows.append(("node", first_line([node, "--version"]) if node else "MISSING", node or "install Node.js 20 or newer; the current LTS is the easy choice"))
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    rows.append(("npm", first_line([npm, "--version"]) if npm else "MISSING", npm or ""))
    pw = REPO / "build" / "node_modules" / "playwright" / "package.json"
    if pw.is_file():
        rows.append(("playwright", json.loads(pw.read_text(encoding="utf-8")).get("version", "?"), str(pw.parent)))
    else:
        # build/lib/common.js requires the package, so without it the render cannot start: MISSING,
        # not a note, or setup would say "everything found" about a machine that cannot render.
        rows.append(("playwright", "MISSING", "run `npm install` in build/"))
    for t in ("ffmpeg", "ffprobe"):
        p = find_tool(t, project)
        ver = first_line([p, "-version"]) if p else ""
        rows.append((t, (ver.split(" version ")[1].split(" ")[0] if " version " in ver else (ver or "MISSING")), p or ("see below" if WIN else "install ffmpeg 7+ (static build is fine)")))
    cv, cp = chrome_info()
    configured = find_tool("chrome", project)     # [tools] chrome is the browser the render tries first
    if configured and configured != cp and Path(configured).is_file():
        cv, cp = (first_line([configured, "--version"]) or "configured"), configured + " ([tools] chrome)"
    rows.append(("google chrome", cv or "MISSING", cp or "needed by the render (Playwright channel 'chrome')"))
    vv, vp = vlc_info()
    # Not MISSING: VLC is only needed where the show plays, which may be another machine entirely.
    rows.append(("vlc", vv or "not found", vp or "needed on the display machine"))
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

def setup_build(skip: str) -> None:
    """Install the build side: Playwright (pinned in build/package.json) and its bundled Chromium.

    skip is the flag that turned this step off, or "" to run it; the message names the flag the person actually passed.
    """
    say("build side")
    if skip:
        say(f"  skipped ({skip})")
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
    # the refusal of anything older than 3.11 is at the top of the file, where it can still be read.
    if sys.version_info >= (3, 14):
        say(f"setup: Python {platform.python_version()} is newer than the versions this port was tested with "
            f"(3.11 to 3.13).")
        say("  pip may report \"No matching distribution\" for a pinned package, or the model export may fail.")
        say("  If either happens, install 3.13 from https://www.python.org/downloads/ (the release list below the")
        say("  button) and run setup with that; it is the safe choice. Continuing.")

    ap = argparse.ArgumentParser(prog="setup", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", help="project folder with config.toml; enables user-supplied model paths and writes environment.md")
    ap.add_argument("--apply", action="store_true",
                    help="write the detected timezone, display resolution and build OS into <project>/config.toml where they are blank (needs --project)")
    ap.add_argument("--venv", default=str(REPO / ".venv"),
                    help="virtual environment path (default <repo>/.venv; elsewhere, set SLIDESHOW_VENV to it for run.py)")
    ap.add_argument("--skip-models", action="store_true", help="do not fetch the default models")
    ap.add_argument("--fetch-ffmpeg", action="store_true", help="Windows: download a static ffmpeg build into <repo>/tools/ffmpeg/ even if one is on PATH")
    ap.add_argument("--skip-ffmpeg", action="store_true", help="Windows: do not download ffmpeg when it is missing")
    ap.add_argument("--skip-node", action="store_true", help="do not run npm install / playwright install in build/")
    ap.add_argument("--no-install", action="store_true", help="do not run pip, npm or downloads (report only)")
    a = ap.parse_args(argv)
    if a.apply and not a.project:
        say("setup: --apply needs --project <folder>")
        return 2

    project = Path(a.project).expanduser().resolve() if a.project else None
    if project and not (project / "config.toml").is_file():
        say(f"setup: {project / 'config.toml'} does not exist; the intake writes it. Continuing without a project.")
        project = None

    say("environment")
    venv = Path(a.venv).expanduser().resolve()
    py = ensure_venv(venv, install=not a.no_install)
    if venv != (REPO / ".venv").resolve():
        # run.py looks in <repo>/.venv and nowhere else unless it is told; without this line the stages
        # would quietly run on the interpreter that started them and fail on the first import of Pillow.
        say(f"  this is not <repo>/.venv, so set SLIDESHOW_VENV={venv} in the environment for run.py to find it")
    detected = detect_all(py)
    say(f"  timezone {detected['timezone'] or 'not detected'}; display {detected['display'] or 'not detected'}; build OS {detected['build_os']}")
    if WIN and not a.no_install and not a.skip_ffmpeg:
        have = find_tool("ffmpeg", project) and find_tool("ffprobe", project)
        if a.fetch_ffmpeg or not have:
            say("ffmpeg")
            fetch_ffmpeg_windows()
    setup_build(skip="--skip-node" if a.skip_node else "--no-install" if a.no_install else "")
    # Last, because it is the step most likely to fail and the one the pipeline can do without.
    setup_models_reported(project, a.skip_models, a.no_install)

    say("toolchain")
    rows = report(py, project, detected)
    print_table(rows)
    say("step 0")
    apply_detected(project, detected, a.apply)
    missing = [r[0] for r in rows if r[1] == "MISSING"]
    if WIN and any(t in missing for t in ("ffmpeg", "ffprobe")):
        say("  ffmpeg is not installed. Re-run setup without --skip-ffmpeg to download a static build into tools/ffmpeg/, or install one from")
        say("  https://www.gyan.dev/ffmpeg/builds/ or https://github.com/BtbN/FFmpeg-Builds/releases and put it on PATH or in config.toml [tools].")
    elif any(t in missing for t in ("ffmpeg", "ffprobe")):
        say("  ffmpeg is not installed. macOS: `brew install ffmpeg`, or a static build from https://evermeet.cx/ffmpeg/ ; Linux: your package manager.")
        say("  Then put it on PATH or set [tools] ffmpeg and ffprobe in config.toml.")
    if any(r[0] == "vlc" and r[1] == "not found" for r in rows):
        say("  VLC was not found on this machine; it is needed only where the show plays (this one, if the same); "
            "https://www.videolan.org/")
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
