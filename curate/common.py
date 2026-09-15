"""Shared configuration and paths for every curation stage.

Every stage does::

    from common import project
    P = project()          # finds and loads <project folder>/config.toml, or exits with a message

and then uses ``P.work``, ``P.index``, ``P.handoff``, ``P.media``, ``P.build`` and the
config-derived helpers below. The project folder is found from ``SLIDESHOW_PROJECT`` in the
environment, from ``--project <folder>`` on the command line, or by walking up from the current
directory until a ``config.toml`` is found. Without one, nothing runs: the intake in the skill
writes it, and the stages must not guess paths, names or dates.

``P.show_settings()`` derives everything the build side needs (viewport, frame rate, row
heights, gutter, scroll speed, background, concat copies, quality, the taste knobs, the music,
the cap plan, off-limits) from ``[output]``, ``[taste]``, ``[show]``, ``[audio]``,
``[selection]`` and ``[machines]``; ``write_show_json`` writes it to ``handoff/show.json`` for
build/lib/*.js. The JavaScript only reads the numbers; the rules are here and in
references/02-index-contract.md. ``P.cap_plan()`` and ``P.year_caps()`` are the cap per year
the select stage seats under, derived from the loop length when ``[selection] cap_per_year``
is 0 (references/04).

This module imports only the standard library, so ``python curate/setup.py`` and
``python curate/common.py`` run on the system Python before the environment exists.

Nothing in here writes to the user's sources. The only writers of ``handoff/media`` are the
handoff stage and the apply tool.
"""
from __future__ import annotations

import calendar
import csv
import datetime as _dt
import hashlib
import json
import math
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "config.toml"
ENV_PROJECT = "SLIDESHOW_PROJECT"

# Zero-filled parts of a filename prefix mean unknown: 2022-00-00_ is year only.
DATE_PREFIX_LEN = len("YYYY-MM-DD_")

# The file types every stage accepts, by extension. build/lib/common.js keeps the same three
# lists; change both or the two halves disagree about what is a video.
STILL_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp"}
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".mts", ".m2ts", ".3gp", ".webm", ".wmv", ".mpg", ".mpeg"}
GIF_EXT = {".gif"}
JUNK_FILES = {".ds_store", "thumbs.db", "desktop.ini"}

# ---- the show settings the build reads from handoff/show.json (references/02)
SHOW_JSON_NAME = "show.json"
DEFAULT_RESOLUTION = (2560, 1440)      # the first run's display
DEFAULT_FPS = 60
DEFAULT_CONCAT_COPIES = 3
DEFAULT_BACKGROUND = "#07070F"
PEOPLE_GATES = ("none", "people", "family")
QUALITY_PRESETS = ("final", "draft")
PLAYERS = ("vlc", "tv-usb", "browser")
# Row heights as a share of the screen height (base row, feature row); each is rounded to an
# even number of pixels. medium is 520 and 820 at 1440 rows, the first run's values.
TILE_PRESETS = {"small": (0.28, 0.44), "medium": (0.3611, 0.5694), "large": (0.46, 0.72)}
# ---- the taste knobs, the music and the cap plan (references/02, references/04)
ORDERS = ("chapters", "chronological", "shuffled")
# motion_density -> (moving_cap, max_base_moving): how many tiles may move at once on screen and
# how many of those may sit in base rows. normal is the first run's 4 and 2.
MOTION_DENSITY = {"calm": (2, 1), "normal": (4, 2), "busy": (6, 3)}
LIVE_PHOTO_MODES = ("clip", "still")
SLOW_MOTION_MODES = ("slow", "realtime")
DEFAULT_SEED = 20260905
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus")   # by extension only; ffmpeg decodes at prep
DEFAULT_LOOP_MINUTES = 15
# The first run's pace: 2.2 s per item at medium tiles and 100 px/s on 1440 rows, measured on
# its 469-moment loop. Larger tiles and slower scrolling make each item take longer, so
# cap_plan() scales this by both before it turns a loop length into a cap.
FIRST_RUN_SECONDS_PER_ITEM = 2.2
# The v4 score weights and the featured-pick rules (references/04). [selection.weights] and
# [selection.featured] override them; stages/_lenses.py keeps these as its defaults.
V4_WEIGHTS = {"person_area": 0.40, "group": 0.10, "sharpness": 0.20, "resolution": 0.15, "consensus": 0.15}
FEATURED_RULES = {"max_people": 3, "min_short_side": 1000, "min_long_side": 1500, "min_sharpness_pct": 0.10}
YEAR_RANGE = (1800, 2200)   # sanity bounds for every year named in the config
_HEX_ID = re.compile(r"^[0-9a-fA-F]{64}$")
_RESOLUTION = re.compile(r"^\s*(\d+)\s*x\s*(\d+)\s*$")
_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DATE_PREFIXED = re.compile(r"^\d{4}-\d{2}-\d{2}_(.+)$")


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
        """'none' (no people check at all), 'people' (any person in frame) or 'family' (the identify
        stage says a family member is). Anything else is a config error."""
        gate = self.get("family", "gate", "people")
        if gate not in PEOPLE_GATES:
            raise ConfigError(f"[family] gate = {gate!r} is not one of {', '.join(PEOPLE_GATES)}")
        return gate

    @property
    def timezone(self) -> str:
        return self.get("project", "timezone", "UTC")

    # ---- the scope: [show] scope_start/scope_end, else first_year/last_year, else the birth year and the event
    def _scope_date(self, key: str) -> _dt.date | None:
        """[show] scope_start or scope_end as a date, None when absent. A quoted string is an error."""
        v = self.get("show", key)
        if v is None or v == "":
            return None
        if isinstance(v, _dt.datetime):
            return v.date()
        if isinstance(v, _dt.date):
            return v
        raise ConfigError(f"[show] {key} = {v!r} must be a TOML date, unquoted, like 2019-03-01")

    @property
    def scope_start(self) -> _dt.date | None:
        return self._scope_date("scope_start")

    @property
    def scope_end(self) -> _dt.date | None:
        end = self._scope_date("scope_end")
        start = self.scope_start
        if end and start and end < start:
            raise ConfigError(f"[show] scope_end = {end} is before scope_start = {start}")
        return end

    def _year(self, section: str, key: str) -> int | None:
        """A year from the config, None when absent, blank or 0; anything but a whole number is an error."""
        v = self.get(section, key)
        if v is None or v == "" or (v == 0 and not isinstance(v, bool)):
            return None
        return _int_setting(section, key, v, 0, *YEAR_RANGE)

    @property
    def first_year(self) -> int:
        """scope_start's year, else [show] first_year, else [honoree] birth_year; without any, an error."""
        s = self.scope_start
        if s:
            return s.year
        y = self._year("show", "first_year") or self._year("honoree", "birth_year")
        if y is None:
            raise ConfigError("the scope has no first year: set [show] scope_start (a date), [show] first_year or [honoree] birth_year")
        return y

    @property
    def last_year(self) -> int:
        """scope_end's year, else [show] last_year, else the event year, else this year."""
        e = self.scope_end
        if e:
            return e.year
        y = self._year("show", "last_year")
        if y:
            return y
        d = self.event_date
        return d.year if d else _dt.date.today().year

    @property
    def event_date(self) -> _dt.date | None:
        d = self.get("show", "event_date")
        return d if isinstance(d, _dt.date) else None

    def scope_years(self) -> tuple[int, int]:
        """(first_year, last_year), checked to run forwards."""
        first, last = self.first_year, self.last_year
        if first > last:
            raise ConfigError(f"the scope runs backwards: first year {first} is after last year {last} (from [show] "
                              f"scope_start/scope_end, first_year/last_year, event_date or [honoree] birth_year)")
        return first, last

    def year_shares(self) -> dict[int, float]:
        """Each scope year's share of a full year: 1.0, or months/12 for a partial first or last year.

        The first year starts at scope_start's month, else the honoree's birth month when the birth
        year opens the scope; the last year ends at scope_end's month, else the event month when the
        event year closes it. With [selection] prorate_partial_years = false every year is 1.0.
        """
        first, last = self.scope_years()
        start_m, end_m = 1, 12
        if bool(self.get("selection", "prorate_partial_years", True)):
            s, e = self.scope_start, self.scope_end
            by, ev = self._year("honoree", "birth_year"), self.event_date
            if s:
                start_m = s.month
            elif by == first:
                start_m = _int_setting("honoree", "birth_month", self.get("honoree", "birth_month"), 1, 1, 12)
            if e:
                end_m = e.month
            elif ev and ev.year == last:
                end_m = ev.month
        shares = {}
        for y in range(first, last + 1):
            lo = start_m if y == first else 1
            hi = end_m if y == last else 12
            shares[y] = max(1, hi - lo + 1) / 12
        return shares

    def cap_overrides(self) -> dict[int, int]:
        """[selection.cap_overrides]: {year: cap}; every key a year in the scope, every value a whole number."""
        raw = self.get("selection", "cap_overrides")
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ConfigError("[selection] cap_overrides must be a table of year = cap lines: [selection.cap_overrides] then 2020 = 3")
        first, last = self.scope_years()
        out: dict[int, int] = {}
        for k, v in raw.items():
            ks = str(k).strip()
            if not ks.isdigit() or not (first <= int(ks) <= last):
                raise ConfigError(f"[selection.cap_overrides] {ks} is not a year in the scope {first}-{last}")
            out[int(ks)] = _int_setting("selection.cap_overrides", ks, v, 0, 0, None)
        return out

    def cap_plan(self, show: dict[str, Any] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
        """The cap per year and where it came from (references/04).

        `[selection] cap_per_year` above 0 is used as given (source "config"). 0 or missing derives
        it from the loop length: seconds_per_item is the first run's 2.2 s scaled by the tile size
        (base row height over the medium preset's) and by the scroll speed (the first run's pace at
        this height over the configured speed); target_items = loop_minutes_target * 60 /
        seconds_per_item; the cap is that spread over the scope's year-shares (a full year 1.0, a
        partial one months/12), rounded up, at least 1. `show` is a show_settings() dict when the
        caller has one, else the display numbers are derived here (warnings go to the list given).
        Keys: cap, source, loop_minutes_target, seconds_per_item, target_items, year_shares, plus
        tile_size and scroll_speed for the printed line. Overrides are year_caps()' business.
        """
        if show is None:
            show = self._display(warnings if warnings is not None else [])
        o, t = show["output"], show["taste"]
        height, base, scroll = o["height"], t["base_row_height"], t["scroll_speed"]
        spi = FIRST_RUN_SECONDS_PER_ITEM * (base / (TILE_PRESETS["medium"][0] * height)) * ((100 * height / 1440) / scroll)
        minutes = _num_setting("show", "loop_minutes_target", self.get("show", "loop_minutes_target"), DEFAULT_LOOP_MINUTES, 0, None)
        if minutes <= 0:
            raise ConfigError(f"[show] loop_minutes_target = {minutes} must be a positive number of minutes")
        shares = round(sum(self.year_shares().values()), 4)
        target = round(minutes * 60 / spi)
        cap = _int_setting("selection", "cap_per_year", self.get("selection", "cap_per_year"), 0, 0, None)
        if cap > 0:
            source = "config"
        else:
            cap, source = max(1, math.ceil(target / shares)), "derived"
        return {"cap": cap, "source": source, "loop_minutes_target": minutes, "seconds_per_item": round(spi, 3),
                "target_items": target, "year_shares": shares, "tile_size": t["tile_size"], "scroll_speed": scroll}

    def year_caps(self, plan: dict[str, Any] | None = None) -> dict[int, int]:
        """Moments per year: the plan's cap (cap_plan(), or the one given), pro-rated by month for
        the partial first and last years, then [selection.cap_overrides] applied last.

        With a cap of 33, a scope opening in September gives 11 for that year and one closing in
        August gives 22 for its year, which is what the first run used by hand.
        """
        cap = int((plan or self.cap_plan())["cap"])
        caps = {y: (cap if share >= 1 else max(1, round(cap * share))) for y, share in self.year_shares().items()}
        caps.update(self.cap_overrides())
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
            "folder_year_rule": bool(p.get("folder_year_rule", False)),
        }

    def must_include(self) -> list[str]:
        """[show] must_include: filenames or media_ids the owner named on intake. select seats them
        exactly like [pins] files."""
        raw = self.get("show", "must_include", []) or []
        if not isinstance(raw, list):
            raise ConfigError("[show] must_include must be a list of filenames or media_ids")
        return [str(x) for x in raw]

    def off_limits(self, warnings: list[str] | None = None) -> dict[str, set[str]]:
        """[show] off_limits resolved to {"media_ids": set, "filenames": set}.

        Each entry is one of: a 64-hex media_id; a path (absolute, or relative to the project
        folder) to an existing file, hashed to its media_id, or to a folder, every file in it
        hashed recursively; otherwise a filename. Filenames go in as given, and a date-prefixed
        one (2023-08-14_IMG_0012.HEIC) also in its bare form, so a name matches a file's
        original_name and its prefixed filename either way. select compares case-insensitively.
        A filename the index already knows (index/items.csv) also contributes that file's
        media_id, so add-item refuses the same bytes under any name.
        """
        raw = self.get("show", "off_limits", []) or []
        if not isinstance(raw, list):
            raise ConfigError("[show] off_limits must be a list of strings: filenames, media_ids, or file or folder paths")
        ids: set[str] = set()
        names: set[str] = set()
        for entry in raw:
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigError(f"[show] off_limits entry {entry!r} is not a filename, a media_id or a path")
            e = entry.strip()
            if _HEX_ID.match(e):
                ids.add(e.lower())
                continue
            p = Path(e).expanduser()
            if not p.is_absolute():
                p = self.root / p
            if p.is_file():
                ids.add(media_id(p))
                continue
            if p.is_dir():
                n = 0
                for dirpath, _dirs, files in os.walk(p):
                    for f in files:
                        if f.lower() in JUNK_FILES or f.startswith("."):
                            continue
                        ids.add(media_id(os.path.join(dirpath, f)))
                        n += 1
                if n == 0 and warnings is not None:
                    warnings.append(f"[show] off_limits folder {p} holds no files")
                continue
            pathlike = "/" in e or "\\" in e
            name = os.path.basename(e.replace("\\", "/")) if pathlike else e
            if pathlike and warnings is not None:
                warnings.append(f"[show] off_limits entry {e!r} is not an existing file or folder; matched as the filename {name!r}")
            names.add(name)
            m = _DATE_PREFIXED.match(name)
            if m:
                names.add(m.group(1))
        items = self.index / "items.csv"
        if names and items.is_file():
            lower = {n.lower() for n in names}
            with open(items, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("filename", "").lower() in lower or row.get("original_name", "").lower() in lower:
                        ids.add(row["media_id"].lower())
        return {"media_ids": ids, "filenames": names}

    def _resolution(self, warnings: list[str]) -> tuple[int, int]:
        raw = self.get("output", "resolution", None)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            warnings.append(f"[output] resolution is not set in {CONFIG_NAME}; using {DEFAULT_RESOLUTION[0]}x{DEFAULT_RESOLUTION[1]} "
                            f"(run `python curate/setup.py --project <folder> --apply` to detect the display, or set it from the intake)")
            return DEFAULT_RESOLUTION
        m = _RESOLUTION.match(str(raw)) if isinstance(raw, str) else None
        if not m:
            raise ConfigError(f"[output] resolution = {raw!r} must be \"WxH\" in pixels, e.g. \"2560x1440\"")
        w, h = int(m.group(1)), int(m.group(2))
        if w % 2 or h % 2 or w < 320 or h < 320:
            raise ConfigError(f"[output] resolution = {raw!r}: both numbers must be even and at least 320")
        return w, h

    def _display(self, warn: list[str]) -> dict[str, Any]:
        """The [output] and [taste] numbers of show_settings(): {"output": {...}, "taste": {...}}.

        The part the cap derivation needs, so cap_plan() can run without the off-limits hashing
        and the music check that the full show_settings() does.
        """
        width, height = self._resolution(warn)
        fps = _int_setting("output", "fps", self.get("output", "fps"), DEFAULT_FPS, 10, 120)
        copies = _int_setting("output", "concat_copies", self.get("output", "concat_copies"), DEFAULT_CONCAT_COPIES, 1, 12)
        quality = _choice_setting("output", "quality", self.get("output", "quality"), "final", QUALITY_PRESETS)

        tile = _choice_setting("taste", "tile_size", self.get("taste", "tile_size"), "medium", tuple(TILE_PRESETS))
        base_share, feature_share = TILE_PRESETS[tile]
        base = _int_setting("taste", "base_row_height", self.get("taste", "base_row_height"), _even(height * base_share), 1, None)
        feature = _int_setting("taste", "feature_row_height", self.get("taste", "feature_row_height"), _even(height * feature_share), 1, None)
        gutter = max(4, round(8 * width / 2560))
        scroll = _int_setting("taste", "scroll_speed", self.get("taste", "scroll_speed"), 0, 0, None) or round(100 * height / 1440)
        background = self.get("taste", "background", None)
        background = DEFAULT_BACKGROUND if background is None or background == "" else str(background)
        if not _COLOUR.match(background):
            raise ConfigError(f"[taste] background = {background!r} must be a six-digit hex colour like \"#07070F\"")
        return {
            "output": {"width": width, "height": height, "fps": fps, "concat_copies": copies, "quality": quality},
            "taste": {"tile_size": tile, "base_row_height": base, "feature_row_height": feature, "max_tile_height": 2 * feature,
                      "gutter": gutter, "scroll_speed": scroll, "background": background},
        }

    def taste_knobs(self, warnings: list[str] | None = None) -> dict[str, Any]:
        """The [taste] answers that act on the selection and the build (references/02), validated.

        order, motion_density (as the word, and as moving_cap and max_base_moving), mixed_tiles,
        include_videos, include_gifs, live_photos, slow_motion and seed. Every default is 0.2's
        behaviour. The 0.2 key live_photos_full is read as live_photos with a warning.
        """
        warn = warnings if warnings is not None else []
        t = self.cfg.get("taste", {})
        order = _choice_setting("taste", "order", t.get("order"), "chapters", ORDERS)
        density = _choice_setting("taste", "motion_density", t.get("motion_density"), "normal", tuple(MOTION_DENSITY))
        moving_cap, max_base_moving = MOTION_DENSITY[density]
        live = t.get("live_photos")
        if "live_photos_full" in t:
            if live is None:
                live = "clip" if t["live_photos_full"] else "still"
                warn.append(f"[taste] live_photos_full = {str(t['live_photos_full']).lower()} is the 0.2 spelling; read as live_photos = \"{live}\"")
            else:
                warn.append("[taste] live_photos_full is the 0.2 spelling and is ignored; live_photos is what is read")
        return {
            "order": order,
            "motion_density": density,
            "moving_cap": moving_cap,
            "max_base_moving": max_base_moving,
            "mixed_tiles": _bool_setting("taste", "mixed_tiles", t.get("mixed_tiles"), True),
            "include_videos": _bool_setting("taste", "include_videos", t.get("include_videos"), True),
            "include_gifs": _bool_setting("taste", "include_gifs", t.get("include_gifs"), True),
            "live_photos": _choice_setting("taste", "live_photos", live, "clip", LIVE_PHOTO_MODES),
            "slow_motion": _choice_setting("taste", "slow_motion", t.get("slow_motion"), "slow", SLOW_MOTION_MODES),
            "seed": _int_setting("taste", "seed", t.get("seed"), DEFAULT_SEED, 0, None),
        }

    def audio_settings(self, warnings: list[str] | None = None) -> dict[str, Any]:
        """The [audio] section for show.json (references/02): enabled, files resolved to absolute
        paths (each must exist and carry a known extension), loop, crossfade_s, fade_s, volume.

        The 0.1 key [show] audio = true without an [audio] section is an error naming the section;
        audio = false is ignored.
        """
        warn = warnings if warnings is not None else []
        a = self.cfg.get("audio")
        legacy = self.get("show", "audio")
        if a is None:
            if legacy:
                raise ConfigError("[show] audio = true is the 0.1 key and nothing reads it; music goes in an [audio] section "
                                  "(enabled, files in play order, loop, crossfade_s, fade_s, volume), see curate/config.example.toml")
            a = {}
        elif legacy:
            warn.append("[show] audio is the 0.1 key and is ignored; the [audio] section is what is read")
        if not isinstance(a, dict):
            raise ConfigError("[audio] must be a section: [audio] on its own line, then enabled = true and files = [...]")
        enabled = _bool_setting("audio", "enabled", a.get("enabled"), False)
        raw_files = a.get("files", [])
        if isinstance(raw_files, str):
            raw_files = [raw_files]
        if not isinstance(raw_files, list) or not all(isinstance(x, str) for x in raw_files):
            raise ConfigError("[audio] files must be a list of file paths in play order, e.g. files = [\"music/one.mp3\", \"music/two.m4a\"]")
        files: list[str] = []
        for x in raw_files:
            if not x.strip():
                raise ConfigError("[audio] files has an empty entry")
            path = Path(x.strip()).expanduser()
            if not path.is_absolute():
                path = self.root / path
            if path.suffix.lower() not in AUDIO_EXT:
                raise ConfigError(f"[audio] files entry {x!r}: {path.suffix or 'no extension'} is not one of {' '.join(AUDIO_EXT)}")
            if not path.is_file():
                if enabled:
                    raise ConfigError(f"[audio] files entry {x!r} does not exist (looked for {path})")
                warn.append(f"[audio] files entry {x!r} does not exist (looked for {path}); audio is off, so it is only noted")
                continue
            files.append(str(path.resolve()))
        if enabled and not files:
            raise ConfigError("[audio] enabled = true but files is empty; list the music files in play order, or set enabled = false")
        return {
            "enabled": enabled,
            "files": files,
            "loop": _bool_setting("audio", "loop", a.get("loop"), True),
            "crossfade_s": _num_setting("audio", "crossfade_s", a.get("crossfade_s"), 2, 0, None),
            "fade_s": _num_setting("audio", "fade_s", a.get("fade_s"), 2, 0, None),
            "volume": float(_num_setting("audio", "volume", a.get("volume"), 1.0, 0.0, 2.0)),
        }

    def selection_weights(self, warnings: list[str] | None = None) -> dict[str, float]:
        """[selection.weights] for the v4 score: person_area, group, sharpness, resolution, consensus;
        each 0 or more, normalised to sum 1 when they do not (a warning says so)."""
        raw = self.get("selection", "weights")
        if raw is None:
            return dict(V4_WEIGHTS)
        if not isinstance(raw, dict):
            raise ConfigError(f"[selection] weights must be a table [selection.weights] with {', '.join(V4_WEIGHTS)}")
        unknown = sorted(set(raw) - set(V4_WEIGHTS))
        if unknown:
            raise ConfigError(f"[selection.weights] {unknown[0]} is not one of {', '.join(V4_WEIGHTS)}")
        w = {k: float(_num_setting("selection.weights", k, raw.get(k), V4_WEIGHTS[k], 0, None)) for k in V4_WEIGHTS}
        total = sum(w.values())
        if total <= 0:
            raise ConfigError("[selection.weights] are all 0; at least one must be above 0")
        if abs(total - 1.0) > 1e-6:
            w = {k: v / total for k, v in w.items()}
            if warnings is not None:
                warnings.append(f"[selection.weights] sum to {total:.2f}, normalised to " + ", ".join(f"{k} {v:.2f}" for k, v in w.items()))
        return w

    def featured_rules(self) -> dict[str, Any]:
        """[selection.featured]: max_people, min_short_side, min_long_side (whole numbers) and
        min_sharpness_pct (0 to 1); a still must pass all of them to take a larger tile."""
        raw = self.get("selection", "featured")
        if raw is None:
            return dict(FEATURED_RULES)
        if not isinstance(raw, dict):
            raise ConfigError(f"[selection] featured must be a table [selection.featured] with {', '.join(FEATURED_RULES)}")
        unknown = sorted(set(raw) - set(FEATURED_RULES))
        if unknown:
            raise ConfigError(f"[selection.featured] {unknown[0]} is not one of {', '.join(FEATURED_RULES)}")
        return {
            "max_people": _int_setting("selection.featured", "max_people", raw.get("max_people"), FEATURED_RULES["max_people"], 0, None),
            "min_short_side": _int_setting("selection.featured", "min_short_side", raw.get("min_short_side"), FEATURED_RULES["min_short_side"], 0, None),
            "min_long_side": _int_setting("selection.featured", "min_long_side", raw.get("min_long_side"), FEATURED_RULES["min_long_side"], 0, None),
            "min_sharpness_pct": float(_num_setting("selection.featured", "min_sharpness_pct", raw.get("min_sharpness_pct"),
                                                    FEATURED_RULES["min_sharpness_pct"], 0.0, 1.0)),
        }

    def show_settings(self, warnings: list[str] | None = None) -> dict[str, Any]:
        """The dict written to handoff/show.json; every key is always present (references/02).

        Numbers are derived here so the build only reads them. A bad value raises ConfigError
        naming the key and what it accepts. Warnings (a missing [output] resolution, a 0.1 or 0.2
        spelling) are appended to the list when one is given.
        """
        warn = warnings if warnings is not None else []
        disp = self._display(warn)
        knobs = self.taste_knobs(warn)
        chapters_raw = self.get("taste", "chapters")
        if isinstance(chapters_raw, bool):   # the 0.1 example spelled it `chapters = true`
            warn.append(f"[taste] chapters = {str(chapters_raw).lower()} is the 0.1 spelling; 0 means the build's default of ten chapters")
            chapters_raw = 0
        chapters = _int_setting("taste", "chapters", chapters_raw, 0, 0, None)
        captions = self.get("taste", "captions", "none")
        captions = "none" if captions in (None, "", False) else str(captions)

        ev = self.get("show", "event_date")
        if isinstance(ev, _dt.datetime):
            ev = ev.date()
        event_date = ev.isoformat() if isinstance(ev, _dt.date) else (str(ev) if ev else "")

        audio = self.audio_settings(warn)
        plan = self.cap_plan(disp, warn)
        # not in show.json, but checked here so the show stage catches a bad key before select does
        self.cap_overrides()
        self.selection_weights(warn)
        self.featured_rules()

        raw_player = self.get("machines", "player")
        if raw_player == "tv":                        # the 0.1 example offered vlc | browser | tv
            warn.append("[machines] player = \"tv\" is the 0.1 spelling; recorded as \"tv-usb\"")
            raw_player = "tv-usb"
        player = _choice_setting("machines", "player", raw_player, "vlc", PLAYERS)
        off = self.off_limits(warn)
        return {
            "written": _dt.datetime.now().isoformat(timespec="seconds"),
            "source": CONFIG_NAME,
            "output": disp["output"],
            "taste": {
                **disp["taste"],
                "mixed_tiles": knobs["mixed_tiles"],
                "chapters": chapters,
                "captions": captions,
                "order": knobs["order"],
                "moving_cap": knobs["moving_cap"],
                "max_base_moving": knobs["max_base_moving"],
                "include_videos": knobs["include_videos"],
                "include_gifs": knobs["include_gifs"],
                "live_photos": knobs["live_photos"],
                "slow_motion": knobs["slow_motion"],
                "seed": knobs["seed"],
            },
            "show": {
                "event": str(self.get("show", "event", "the event") or "the event"),
                "event_date": event_date,
                "playback": str(self.get("show", "playback", "loop") or "loop"),
            },
            "audio": audio,
            "selection": {
                "cap_per_year": plan["cap"],
                "cap_source": plan["source"],
                "loop_minutes_target": plan["loop_minutes_target"],
                "seconds_per_item": plan["seconds_per_item"],
                "target_items": plan["target_items"],
                "year_shares": plan["year_shares"],
            },
            "machines": {"player": player, "display_os": str(self.get("machines", "display_os", "") or "")},
            "off_limits": {"media_ids": sorted(off["media_ids"]), "filenames": sorted(off["filenames"])},
        }

    def tool(self, name: str) -> str:
        """Path to ffmpeg/ffprobe/chrome/vlc: [tools] in the config, else the repository's optional
        tools/ffmpeg/ folder (where setup.py --fetch-ffmpeg puts a static build), else the bare name
        for PATH lookup."""
        configured = self.get("tools", name, "")
        if configured:
            return str(Path(configured).expanduser())
        repo_tools = Path(__file__).resolve().parent.parent / "tools" / "ffmpeg"
        for cand in (repo_tools / name, repo_tools / f"{name}.exe"):
            if cand.is_file():
                return str(cand)
        return name


def _even(x: float) -> int:
    """The nearest even integer."""
    return int(2 * round(x / 2))


def _int_setting(section: str, key: str, value: Any, default: int, lo: int | None, hi: int | None) -> int:
    """An integer config value with bounds; None (absent) gives the default, anything else must be a whole number."""
    if value is None:
        return default
    if isinstance(value, bool):
        raise ConfigError(f"[{section}] {key} = {str(value).lower()} must be a number")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int):
        raise ConfigError(f"[{section}] {key} = {value!r} must be a whole number")
    bounds = f"{lo}..{hi}" if hi is not None else (f"at least {lo}" if lo is not None else "")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ConfigError(f"[{section}] {key} = {value} is out of range; accepted: {bounds}")
    return value


def _num_setting(section: str, key: str, value: Any, default: float, lo: float | None, hi: float | None) -> int | float:
    """A number, whole or decimal, with inclusive bounds; None (absent) gives the default."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"[{section}] {key} = {value!r} must be a number")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        bounds = f"{lo}..{hi}" if hi is not None else f"at least {lo}"
        raise ConfigError(f"[{section}] {key} = {value} is out of range; accepted: {bounds}")
    return value


def _bool_setting(section: str, key: str, value: Any, default: bool) -> bool:
    """true or false; None (absent) gives the default, anything else (a quoted "yes") is an error."""
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"[{section}] {key} = {value!r} must be true or false")
    return value


def _choice_setting(section: str, key: str, value: Any, default: str, choices: tuple[str, ...]) -> str:
    if value is None or value == "":
        return default
    if value not in choices:
        raise ConfigError(f"[{section}] {key} = {value!r} is not one of {' | '.join(choices)}")
    return str(value)


def fmt_num(x: float) -> str:
    """A number for a printed line: 15 -> '15', 2.2 -> '2.2', 2.20007 -> '2.2'."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def cap_line(plan: dict[str, Any]) -> str:
    """The one line about the cap that select, the show stage and `python common.py` print."""
    if plan["source"] == "config":
        return f"cap: {plan['cap']} per year from config"
    return (f"cap: derived {plan['cap']} per year from a {fmt_num(plan['loop_minutes_target'])}-minute target at "
            f"{fmt_num(plan['seconds_per_item'])} s per item ({plan['tile_size']} tiles, {plan['scroll_speed']} px/s): "
            f"{plan['target_items']} moments over {plan['year_shares']:.1f} year-shares")


def plan_of(settings: dict[str, Any]) -> dict[str, Any]:
    """The cap plan as cap_plan() returns it, read back from a show_settings() dict."""
    sel, t = settings["selection"], settings["taste"]
    return {"cap": sel["cap_per_year"], "source": sel["cap_source"], "loop_minutes_target": sel["loop_minutes_target"],
            "seconds_per_item": sel["seconds_per_item"], "target_items": sel["target_items"], "year_shares": sel["year_shares"],
            "tile_size": t["tile_size"], "scroll_speed": t["scroll_speed"]}


def describe_show(s: dict[str, Any]) -> list[str]:
    """The derived numbers as printed lines, shared by the show stage and `python common.py`."""
    o, t, a, off = s["output"], s["taste"], s["audio"], s["off_limits"]
    density = next((k for k, v in MOTION_DENSITY.items() if v[0] == t["moving_cap"]), "?")

    def yes(b: bool) -> str:
        return "yes" if b else "no"
    if a["enabled"]:
        audio = (f"audio on: {len(a['files'])} file(s), {'looped' if a['loop'] else 'played once'}, crossfade {fmt_num(a['crossfade_s'])} s, "
                 f"fade {fmt_num(a['fade_s'])} s, volume {fmt_num(a['volume'])}: " + "; ".join(a["files"]))
    else:
        audio = "audio off" + (f" ({len(a['files'])} file(s) listed)" if a["files"] else "")
    return [
        f"resolution {o['width']}x{o['height']} at {o['fps']} fps; quality {o['quality']}; {o['concat_copies']} concat copies",
        f"tiles {t['tile_size']}: base row {t['base_row_height']} px, feature row {t['feature_row_height']} px, "
        f"max tile {t['max_tile_height']} px, gutter {t['gutter']} px",
        f"scroll {t['scroll_speed']} px/s; background {t['background']}; chapters {t['chapters'] or 'default (ten)'}",
        f"order {t['order']}; motion density {density} (moving cap {t['moving_cap']}, max base moving {t['max_base_moving']}); "
        f"mixed tiles {yes(t['mixed_tiles'])}; videos {yes(t['include_videos'])}; gifs {yes(t['include_gifs'])}; "
        f"Live Photos {t['live_photos']}; slow motion {t['slow_motion']}; seed {t['seed']}",
        audio,
        cap_line(plan_of(s)),
        f"off-limits: {len(off['media_ids'])} media id(s), {len(off['filenames'])} filename(s); player {s['machines']['player']}",
    ]


def write_show_json(P: Project, settings: dict[str, Any] | None = None) -> Path:
    """Write handoff/show.json (atomically, creating handoff/ if needed) and return its path."""
    settings = settings if settings is not None else P.show_settings()
    P.handoff.mkdir(parents=True, exist_ok=True)
    path = P.handoff / SHOW_JSON_NAME
    write_atomic(path, json.dumps(settings, indent=2) + "\n")
    return path


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


def _trailing_comment(line: str) -> tuple[int, str]:
    """(column, text) of a `# comment` after the value on a key line, outside any string; (0, '') when none."""
    quote = None
    i = line.index("=") + 1
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 1
            elif ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == "#":
            return i, line[i:].rstrip()
        i += 1
    return 0, ""


def set_config_value(cfg_path: str | os.PathLike, section: str, key: str, literal: str) -> bool:
    """Set one key in a TOML file by lines, keeping every comment and the order of everything else.

    `literal` is the TOML text to write (the caller quotes strings). Within `[section]` the first
    `key = ...` line is replaced, its trailing `# comment` kept in its column; a missing key is
    inserted right after the header; a missing section is appended with a blank line before it.
    Returns True when the file changed. Step 0 uses this to record what it detected.
    """
    path = Path(cfg_path)
    with open(path, encoding="utf-8", newline="") as f:   # newline="" keeps a CRLF file's endings as they are
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    header = re.compile(r"^\s*\[\s*" + re.escape(section) + r"\s*\]\s*(#.*)?$")
    any_header = re.compile(r"^\s*\[")
    key_line = re.compile(r"^(\s*)" + re.escape(key) + r"\s*=")

    def body(ln: str) -> str:
        return ln.rstrip("\r\n")

    new_line = f"{key} = {literal}"
    start = next((i for i, ln in enumerate(lines) if header.match(body(ln))), None)
    if start is None:
        lead = "" if not text or text.endswith(("\n", "\r")) else nl
        new_text = text + lead + nl + f"[{section}]" + nl + new_line + nl
    else:
        end = next((i for i in range(start + 1, len(lines)) if any_header.match(body(lines[i]))), len(lines))
        hit = next((i for i in range(start + 1, end) if key_line.match(body(lines[i]))), None)
        if hit is None:
            lines.insert(start + 1, new_line + nl)
        else:
            old = body(lines[hit])
            ending = lines[hit][len(old):]
            indent = key_line.match(old).group(1)
            col, comment = _trailing_comment(old)
            replaced = f"{indent}{new_line}"
            if comment:
                replaced += " " * max(1, col - len(replaced)) + comment
            lines[hit] = replaced + ending
        new_text = "".join(lines)
    if new_text == text:
        return False
    write_atomic(path, new_text)
    return True


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
    plan = P.cap_plan()
    say("years:", P.first_year, "to", P.last_year, "| caps:", P.year_caps(plan))
    say("cap plan:", cap_line(plan))
    overrides = P.cap_overrides()
    if overrides:
        say("cap overrides:", ", ".join(f"{y} = {c}" for y, c in sorted(overrides.items())))
    say("priors:", P.priors())
    say("anchors:", {k: len(v) for k, v in P.anchors().items()}, "| pins:", len(P.pins()), "| must_include:", len(P.must_include()))
    warnings: list[str] = []
    settings = P.show_settings(warnings)
    for w in warnings:
        say("  !", w)
    for line in describe_show(settings):
        say("show:", line)
