"""Shared configuration and paths for every curation stage.

Every stage does::

    from common import project
    P = project()          # finds and loads <project folder>/config.toml, or exits with a message

and then uses ``P.work``, ``P.index``, ``P.handoff``, ``P.media``, ``P.build`` and the
config-derived helpers below. The project folder is found from ``SLIDESHOW_PROJECT`` in the
environment, from ``--project <folder>`` on the command line, or by walking up from the current
directory until a ``config.toml`` is found. Without one, nothing runs: the intake in the skill
writes it, and the stages must not guess paths, names or dates.

Nothing in here writes to the user's sources. The only writers of ``handoff/media`` are the
handoff stage and the apply tool.
"""
from __future__ import annotations

import calendar
import datetime as _dt
import hashlib
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "config.toml"
ENV_PROJECT = "SLIDESHOW_PROJECT"

# Zero-filled parts of a filename prefix mean unknown: 2022-00-00_ is year only.
DATE_PREFIX_LEN = len("YYYY-MM-DD_")

STILL_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png"}
VIDEO_EXT = {".mov", ".mp4", ".m4v"}
GIF_EXT = {".gif"}
JUNK_FILES = {".ds_store", "thumbs.db", "desktop.ini"}


class ConfigError(SystemExit):
    """Raised (and exits) when the project config is missing or unusable."""

    def __init__(self, msg: str):
        super().__init__(f"slideshow-builder: {msg}")


def find_project(start: str | os.PathLike | None = None) -> Path:
    """Locate the folder holding config.toml. See the module docstring for the search order."""
    argv = sys.argv[1:]
    if "--project" in argv:
        i = argv.index("--project")
        if i + 1 < len(argv):
            return Path(argv[i + 1]).expanduser().resolve()
    env = os.environ.get(ENV_PROJECT)
    if env:
        return Path(env).expanduser().resolve()
    here = Path(start or os.getcwd()).resolve()
    for cand in (here, *here.parents):
        if (cand / CONFIG_NAME).is_file():
            return cand
    raise ConfigError(
        f"no {CONFIG_NAME} found in {here} or above it. Run the intake first (it writes "
        f"project/{CONFIG_NAME}), or point {ENV_PROJECT} or --project at the project folder."
    )


@dataclass
class Source:
    path: Path
    kind: str  # takeout | apple-photos | icloud | folder


@dataclass
class Project:
    root: Path
    cfg: dict[str, Any]
    sources: list[Source] = field(default_factory=list)

    # ---- folders (created lazily by the stages, never here)
    @property
    def work(self) -> Path:
        return self._folder("work")

    @property
    def index(self) -> Path:
        return self._folder("index")

    @property
    def handoff(self) -> Path:
        return self._folder("handoff")

    @property
    def build(self) -> Path:
        return self._folder("build")

    @property
    def media(self) -> Path:
        return self.handoff / "media"

    @property
    def sheets(self) -> Path:
        return self.index / "sheets"

    @property
    def models(self) -> Path:
        return Path(__file__).resolve().parent / "models"

    def _folder(self, key: str) -> Path:
        raw = self.cfg.get("project", {}).get(key, key)
        return (self.root / Path(raw).expanduser()).resolve()

    # ---- config-derived values
    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.cfg.get(section, {}).get(key, default)

    @property
    def honoree(self) -> str:
        return self.get("honoree", "name", "the honoree")

    @property
    def family_names(self) -> list[str]:
        return list(self.get("family", "names", []))

    @property
    def people_gate(self) -> str:
        """'people' (any person in frame) or 'family' (identify stage says a family member is)."""
        return self.get("family", "gate", "people")

    @property
    def timezone(self) -> str:
        return self.get("project", "timezone", "UTC")

    @property
    def first_year(self) -> int:
        return int(self.get("show", "first_year") or self.get("honoree", "birth_year"))

    @property
    def last_year(self) -> int:
        y = self.get("show", "last_year")
        if y:
            return int(y)
        d = self.get("show", "event_date")
        return d.year if isinstance(d, _dt.date) else _dt.date.today().year

    @property
    def event_date(self) -> _dt.date | None:
        d = self.get("show", "event_date")
        return d if isinstance(d, _dt.date) else None

    def year_caps(self) -> dict[int, int]:
        """Moments per year, pro-rated by month for the partial first and last years.

        The first year runs from the honoree's birth month, the last year up to the event month.
        With a cap of 33, a birth in September gives 11 for that year and an event in August
        gives 22 for its year, which is what the first run used by hand.
        """
        cap = int(self.get("selection", "cap_per_year", 33))
        prorate = bool(self.get("selection", "prorate_partial_years", True))
        caps = {y: cap for y in range(self.first_year, self.last_year + 1)}
        if not prorate:
            return caps
        bm = int(self.get("honoree", "birth_month", 1) or 1)
        by = self.get("honoree", "birth_year")
        if by and int(by) == self.first_year:
            caps[self.first_year] = max(1, round(cap * (13 - bm) / 12))
        ev = self.event_date
        if ev and ev.year == self.last_year:
            caps[self.last_year] = max(1, round(cap * ev.month / 12))
        return caps

    def age_label(self, year: int) -> str:
        """'born September' for the birth year, 'age 3-4' after; blank when there is no honoree birth year."""
        by = self.get("honoree", "birth_year")
        if not by:
            return ""
        by = int(by)
        if year == by:
            bm = int(self.get("honoree", "birth_month", 1) or 1)
            return "born " + calendar.month_name[bm]
        if year < by:
            return ""
        return "age %d-%d" % (year - by - 1, year - by)

    def anchors(self) -> dict[str, list[dict[str, Any]]]:
        """Tradition anchors from [anchors]: date_window, place and pinned lists (each may be empty)."""
        a = self.cfg.get("anchors", {})
        return {k: list(a.get(k, [])) for k in ("date_window", "place", "pinned")}

    def pins(self) -> list[str]:
        return list(self.get("pins", "files", []))

    def priors(self) -> dict[str, Any]:
        """Owner-declared rules about the export. Off unless the config turns them on."""
        p = self.cfg.get("priors", {})
        return {
            "calendar_folder_year_rule": bool(p.get("calendar_folder_year_rule", False)),
            "calendar_folder_year_offset": int(p.get("calendar_folder_year_offset", -1)),
            "filename_month_rule": bool(p.get("filename_month_rule", False)),
        }

    def tool(self, name: str) -> str:
        """Path to ffmpeg/ffprobe/chrome/vlc from [tools], else the bare name for PATH lookup."""
        return self.get("tools", name, "") or name


def load(start: str | os.PathLike | None = None) -> Project:
    root = find_project(start)
    cfg_path = root / CONFIG_NAME
    if not cfg_path.is_file():
        raise ConfigError(f"{cfg_path} does not exist. Run the intake first.")
    try:
        with open(cfg_path, "rb") as f:
            cfg = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{cfg_path} is not valid TOML: {e}")
    for section in ("project", "show", "selection"):
        if section not in cfg:
            raise ConfigError(f"{cfg_path} has no [{section}] section; copy curate/config.example.toml and fill it in.")
    sources = []
    for s in cfg.get("sources", []):
        p = Path(str(s.get("path", ""))).expanduser()
        if not p.is_absolute():
            p = root / p
        sources.append(Source(path=p.resolve(), kind=str(s.get("kind", "folder"))))
    if not sources:
        raise ConfigError(f"{cfg_path} lists no [[sources]]; the intake must record where the photos are.")
    return Project(root=root, cfg=cfg, sources=sources)


_PROJECT: Project | None = None


def project() -> Project:
    """The loaded project, found once per process."""
    global _PROJECT
    if _PROJECT is None:
        _PROJECT = load()
    return _PROJECT


# ---- small helpers every stage uses

def media_id(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    """SHA-256 of the file's bytes: the stable identity across renames (see references/02)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def kind_of(name: str) -> str:
    """'still', 'video', 'gif' or '' by extension."""
    ext = os.path.splitext(name)[1].lower()
    if ext in STILL_EXT:
        return "still"
    if ext in VIDEO_EXT:
        return "video"
    if ext in GIF_EXT:
        return "gif"
    return ""


def date_prefix(date: str | None, precision: str = "day") -> str:
    """'2023-08-14_' for a day, '2023-08-00_' for a month, '2023-00-00_' for a year."""
    if not date:
        return "0000-00-00_"
    y, m, d = (date + "-00-00").split("-")[:3]
    if precision == "year":
        m, d = "00", "00"
    elif precision == "month":
        d = "00"
    return f"{y}-{m}-{d}_"


def write_atomic(path: str | os.PathLike, text: str, encoding: str = "utf-8") -> None:
    """Write under a temporary name and rename, so a killed run never leaves a half file."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding, newline="\n")
    os.replace(tmp, path)


def dry_run() -> bool:
    return "--dry-run" in sys.argv[1:]


def say(*parts: Any) -> None:
    print(*parts, flush=True)


if __name__ == "__main__":
    # `python common.py` reports what the config resolves to; useful right after the intake.
    P = project()
    say("project:", P.root)
    say("sources:", *[f"{s.kind}:{s.path}" for s in P.sources])
    say("work:", P.work, "| index:", P.index, "| handoff:", P.handoff, "| build:", P.build)
    say("honoree:", P.honoree, "| family:", ", ".join(P.family_names) or "(none)", "| gate:", P.people_gate)
    say("years:", P.first_year, "to", P.last_year, "| caps:", P.year_caps())
    say("priors:", P.priors())
    say("anchors:", {k: len(v) for k, v in P.anchors().items()}, "| pins:", len(P.pins()))
