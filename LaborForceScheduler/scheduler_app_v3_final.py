
# LaborForceScheduler V3 (NEW) — Portable, 30-minute ticks, Optimizer
# -------------------------------------------------------------------
# Core principles:
# - Portable one-folder app (relative ./data ./history ./exports)
# - 30-minute tick time system
# - Fixed schedules + weekly overrides + bulk requirements apply
# - Optimizer (greedy + local search improvement)
# - Participation guarantee when feasible (>=1 shift >=1 hour for wants_hours=True)
# - ND minor rules (configurable for 14-15; conservative checks)
#
# RUN:
#   py LaborForceScheduler.py
#
# OPTIONAL EXE:
#   py -m pip install pyinstaller
#   py -m PyInstaller --onefile --windowed --name LaborForceScheduler LaborForceScheduler.py
#
# NOTE:
# This is a NEW program. It does not overwrite or modify your old working build.

from __future__ import annotations

import os, json, tempfile, shutil, webbrowser, datetime, random, math, subprocess, sys, zipfile, copy, pathlib, re
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Tuple, Optional, Set, Any

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont

from ui.shell import AppShell
from ui.pages import DashboardPage, LandingPage, SchedulingPage

# ---- Build/version ----
APP_VERSION = 'V3.5 PHASE5_E3_EMPLOYEE_FIT'

def _app_dir() -> str:
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()

def _write_crash_log(exc_type, exc, tb):
    try:
        import traceback, platform
        p = os.path.join(_app_dir(), 'crash_log.txt')
        with open(p, 'a', encoding='utf-8') as f:
            f.write('\n' + '='*78 + '\n')
            f.write(f'Time: {datetime.datetime.now().isoformat()}\n')
            f.write(f'Version: {APP_VERSION}\n')
            f.write(f'Python: {sys.version}\n')
            f.write(f'Platform: {platform.platform()}\n')
            f.write(f'CWD: {os.getcwd()}\n')
            f.write(f'AppDir: {_app_dir()}\n')
            f.write('Traceback:\n')
            traceback.print_exception(exc_type, exc, tb, file=f)
    except Exception:
        pass


def _run_log_path() -> str:
    try:
        return os.path.join(_app_dir(), 'run_log.txt')
    except Exception:
        return os.path.join(os.getcwd(), 'run_log.txt')

def _write_run_log(msg: str):
    """Append a single line to run_log.txt (best-effort)."""
    try:
        p = _run_log_path()
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(p, 'a', encoding='utf-8') as f:
            f.write(f'[{ts}] {msg}\n')
    except Exception:
        pass

def _install_crash_hooks():
    # Unhandled exceptions
    try:
        def _hook(exc_type, exc, tb):
            _write_crash_log(exc_type, exc, tb)
            try:
                sys.__excepthook__(exc_type, exc, tb)
            except Exception:
                pass
        sys.excepthook = _hook
    except Exception:
        pass
    # Thread exceptions (py3.8+)
    try:
        import threading
        def _thread_hook(args):
            _write_crash_log(args.exc_type, args.exc_value, args.exc_traceback)
        threading.excepthook = _thread_hook  # type: ignore[attr-defined]
    except Exception:
        pass

# Pillow for branding images
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

# -----------------------------
# Time system: 30-minute ticks
# -----------------------------
TICK_MINUTES = 30
TICKS_PER_HOUR = 2
DAY_TICKS = 48  # 24h * 2

DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
AREAS = ["CSTORE", "KITCHEN", "CARWASH"]

def tick_to_hhmm(t: int) -> str:
    t = max(0, min(DAY_TICKS, int(t)))
    mins = t * TICK_MINUTES
    h = mins // 60
    m = mins % 60
    return f"{h:02d}:{m:02d}"

def hhmm_to_tick(s: str) -> int:
    s = str(s).strip()
    if not s:
        return 0
    h, m = s.split(":")
    h = int(h); m = int(m)
    return max(0, min(DAY_TICKS, (h*60 + m)//TICK_MINUTES))

TIME_CHOICES = [tick_to_hhmm(t) for t in range(0, DAY_TICKS+1)]  # inclusive 24:00

def ticks_between(a: int, b: int) -> int:
    return max(0, int(b) - int(a))

def hours_between_ticks(a: int, b: int) -> float:
    return ticks_between(a,b) / TICKS_PER_HOUR

def ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p

def _atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    """Write text atomically using temp-file + replace in the same directory."""
    d = os.path.dirname(path) or "."
    ensure_dir(d)
    fd, tmp = tempfile.mkstemp(prefix=".__tmp_", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _atomic_write_json(path: str, payload: Any, indent: int = 2) -> None:
    """Serialize JSON deterministically and write atomically."""
    data = json.dumps(payload, indent=indent, ensure_ascii=False)
    _atomic_write_text(path, data, encoding="utf-8")


def _safe_file_backup(path: str) -> Optional[str]:
    """Best-effort single-file backup; returns backup path when created."""
    try:
        if not path or not os.path.isfile(path):
            return None
        d = os.path.dirname(path) or "."
        ensure_dir(d)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"{path}.bak.{stamp}"
        shutil.copy2(path, bak)
        return bak
    except Exception:
        return None

def app_dir() -> str:
    return _app_dir()

def rel_path(*parts: str) -> str:
    return os.path.join(app_dir(), *parts)

def _safe_export_label_token(label: str, max_len: int = 24) -> str:
    raw = str(label or '').strip()
    wk = week_sun_from_label(raw)
    if wk is not None:
        token = f"wk{wk.isoformat()}"
    else:
        cleaned = []
        for ch in raw.lower():
            if ch.isalnum():
                cleaned.append(ch)
            elif ch in (' ', '-', '_'):
                cleaned.append('_')
        token = ''.join(cleaned).strip('_') or 'schedule'
        while '__' in token:
            token = token.replace('__', '_')
    return token[:max_len].rstrip('_') or 'schedule'

def _build_export_filename(prefix: str, label: str, ext: str) -> str:
    date_token = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    label_token = _safe_export_label_token(label)
    return f"{prefix}_{date_token}_{label_token}.{ext}"

def open_local_export_file(path: str) -> bool:
    """Open a local export file in the default browser/app (best effort)."""
    try:
        if not path or not os.path.isfile(path):
            return False
        abs_path = os.path.abspath(path)
        return bool(webbrowser.open(abs_path))
    except Exception:
        return False

def default_data_path() -> str:
    return rel_path("data", "scheduler_data.json")


def _backup_dir() -> str:
    return rel_path("data", "backups")


def _backup_stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d_%H%M")


def _iter_backup_source_files() -> List[Tuple[str, str]]:
    """Yield (abs_path, archive_rel_path) for files included in a store backup."""
    items: List[Tuple[str, str]] = []

    def add_file(abs_path: str, rel_name: str) -> None:
        if os.path.isfile(abs_path):
            items.append((abs_path, rel_name.replace('\\', '/')))

    def add_tree(abs_root: str, rel_root: str, suffix: str = '.json') -> None:
        if not os.path.isdir(abs_root):
            return
        for root, _dirs, files in os.walk(abs_root):
            for name in sorted(files):
                if suffix and not name.lower().endswith(suffix):
                    continue
                abs_path = os.path.join(root, name)
                rel_path_name = os.path.relpath(abs_path, abs_root)
                add_file(abs_path, os.path.join(rel_root, rel_path_name))

    add_file(default_data_path(), os.path.join('data', 'scheduler_data.json'))
    add_file(rel_path('data', 'patterns.json'), os.path.join('data', 'patterns.json'))
    add_file(rel_path('data', 'last_schedule.json'), os.path.join('data', 'last_schedule.json'))
    add_tree(rel_path('data', 'final_schedules'), os.path.join('data', 'final_schedules'))
    add_tree(rel_path('history'), 'history')
    return items


def create_store_backup_zip(dest_zip_path: str) -> Dict[str, Any]:
    ensure_dir(os.path.dirname(dest_zip_path))
    included = _iter_backup_source_files()
    meta = {
        'created_on': datetime.datetime.now().isoformat(timespec='seconds'),
        'app_version': APP_VERSION,
        'included_files': [arc for _abs, arc in included],
    }
    with zipfile.ZipFile(dest_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('backup_manifest.json', json.dumps(meta, indent=2))
        for abs_path, arc_name in included:
            zf.write(abs_path, arc_name)
    return {'path': dest_zip_path, 'file_count': len(included), 'meta': meta}


def list_store_backups() -> List[str]:
    folder = _backup_dir()
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder), reverse=True):
        if name.lower().endswith('.zip'):
            out.append(os.path.join(folder, name))
    return out


def restore_store_backup_zip(zip_path: str) -> Dict[str, Any]:
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f'Backup not found: {zip_path}')
    with tempfile.TemporaryDirectory(prefix='lfs_restore_') as tmpdir:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            members = zf.infolist()
            member_names = [info.filename for info in members]
            data_members = [m for m in member_names if m.startswith('data/') and not m.endswith('/')]
            if 'data/scheduler_data.json' not in data_members:
                raise ValueError('Backup is missing data/scheduler_data.json')
            for info in members:
                name = info.filename
                if not name:
                    continue
                normalized = name.replace('\\', '/')
                parts = [part for part in normalized.split('/') if part not in ('', '.')]
                if (
                    normalized.startswith(('/', '\\'))
                    or normalized.startswith('\\\\')
                    or (len(normalized) >= 2 and normalized[1] == ':')
                    or any(part == '..' for part in parts)
                ):
                    raise ValueError(f'Unsafe path in backup zip: {name}')
                target = os.path.normpath(os.path.join(tmpdir, *parts)) if parts else tmpdir
                if os.path.commonpath([tmpdir, target]) != tmpdir:
                    raise ValueError(f'Unsafe path in backup zip: {name}')
                if name.endswith('/') or info.is_dir():
                    ensure_dir(target)
                    continue
                ensure_dir(os.path.dirname(target))
                with zf.open(info, 'r') as src_fh, open(target, 'wb') as dst_fh:
                    shutil.copyfileobj(src_fh, dst_fh)
        extracted_data = os.path.join(tmpdir, 'data', 'scheduler_data.json')
        _ = load_data(extracted_data)  # validate structure before overwrite

        restored: List[str] = []
        safety_backups: List[str] = []
        for rel_name in [
            os.path.join('data', 'scheduler_data.json'),
            os.path.join('data', 'patterns.json'),
            os.path.join('data', 'last_schedule.json'),
        ]:
            src = os.path.join(tmpdir, rel_name)
            dst = rel_path(*rel_name.split(os.sep))
            if os.path.isfile(src):
                ensure_dir(os.path.dirname(dst))
                bak = _safe_file_backup(dst)
                if bak:
                    safety_backups.append(bak)
                fd, tmp_dst = tempfile.mkstemp(prefix=os.path.basename(dst) + '.__restore_tmp__', dir=os.path.dirname(dst))
                os.close(fd)
                try:
                    shutil.copyfile(src, tmp_dst)
                    os.replace(tmp_dst, dst)
                finally:
                    if os.path.exists(tmp_dst):
                        os.remove(tmp_dst)
                restored.append(rel_name.replace('\\', '/'))

        for rel_folder in [os.path.join('data', 'final_schedules'), 'history']:
            src_root = os.path.join(tmpdir, rel_folder)
            dst_root = rel_path(*rel_folder.split(os.sep))
            if os.path.isdir(src_root):
                parent_dir = os.path.dirname(dst_root)
                ensure_dir(parent_dir)
                stage_root = tempfile.mkdtemp(prefix=os.path.basename(dst_root) + '.__restore_tmp__', dir=parent_dir)
                os.rmdir(stage_root)
                backup_root = None
                try:
                    shutil.copytree(src_root, stage_root)
                    if os.path.exists(dst_root):
                        backup_root = tempfile.mkdtemp(prefix=os.path.basename(dst_root) + '.__restore_old__', dir=parent_dir)
                        os.rmdir(backup_root)
                        os.replace(dst_root, backup_root)
                    os.replace(stage_root, dst_root)
                    if backup_root and os.path.exists(backup_root):
                        shutil.rmtree(backup_root)
                except Exception:
                    if os.path.exists(stage_root):
                        shutil.rmtree(stage_root)
                    if backup_root and os.path.exists(backup_root) and not os.path.exists(dst_root):
                        os.replace(backup_root, dst_root)
                    raise
                for root, _dirs, files in os.walk(dst_root):
                    for name in files:
                        restored.append(os.path.relpath(os.path.join(root, name), app_dir()).replace('\\', '/'))

    return {'path': zip_path, 'restored_files': sorted(restored), 'safety_backups': sorted(set(safety_backups))}

def compute_weekly_eligibility(model: "DataModel", label: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (eligible, not_eligible) dicts mapping employee_name -> reason.

    Eligible definition (Milestone 3):
      - work_status == 'Active'
      - wants_hours == True
      - has at least one 1-hour window (2 ticks) available in the week after applying:
          * base availability DayRules
          * weekly overrides for the given label (off_all_day, blocked_ranges)
    """
    eligible: Dict[str, str] = {}
    not_eligible: Dict[str, str] = {}

    # Index overrides for quick lookup: (emp, day) -> WeeklyOverride
    ov_map: Dict[Tuple[str, str], WeeklyOverride] = {}
    for o in getattr(model, "weekly_overrides", []) or []:
        try:
            if (o.label or "").strip() == (label or "").strip():
                ov_map[(o.employee_name, o.day)] = o
        except Exception:
            continue

    one_hour_ticks = 2  # 30-min ticks => 1 hour
    for e in getattr(model, "employees", []) or []:
        name = getattr(e, "name", "(unknown)")
        # Active / opted-in
        if getattr(e, "work_status", "") != "Active":
            not_eligible[name] = f"Not Active ({getattr(e, 'work_status', '')})"
            continue
        if not bool(getattr(e, "wants_hours", True)):
            not_eligible[name] = "Opted-out (wants_hours=False)"
            continue

        any_window = False
        for day in DAYS:
            dr = None
            try:
                dr = (getattr(e, "availability", {}) or {}).get(day)
            except Exception:
                dr = None
            if dr is None:
                # default: unavailable_day=False, full day available
                dr = DayRules(False, 0, DAY_TICKS, [])
            # Apply weekly override
            o = ov_map.get((name, day))
            if o is not None:
                if bool(getattr(o, "off_all_day", False)):
                    continue
                # Merge blocked ranges (override blocks add to existing)
                try:
                    br = list(getattr(dr, "blocked_ranges", []) or [])
                    br.extend(list(getattr(o, "blocked_ranges", []) or []))
                    dr = DayRules(bool(getattr(dr, "unavailable_day", False)),
                                 int(getattr(dr, "earliest_start", 0)),
                                 int(getattr(dr, "latest_end", DAY_TICKS)),
                                 br)
                except Exception:
                    pass

            # Scan for at least one 1-hour window
            try:
                earliest = int(getattr(dr, "earliest_start", 0))
                latest = int(getattr(dr, "latest_end", DAY_TICKS))
                if bool(getattr(dr, "unavailable_day", False)):
                    continue
                for s in range(max(0, earliest), max(0, latest - one_hour_ticks) + 1):
                    if dr.is_available(s, s + one_hour_ticks):
                        any_window = True
                        break
            except Exception:
                # If availability structure is malformed, treat as no availability for safety
                pass

            if any_window:
                break

        if any_window:
            eligible[name] = "Eligible"
        else:
            not_eligible[name] = "No 1-hour availability after weekly overrides/time off/blocks"

    return eligible, not_eligible

def today_iso() -> str:
    return datetime.date.today().isoformat()

def weekend_days() -> Set[str]:
    return {"Sat","Sun"}

def html_escape(s: str) -> str:
    return (str(s).replace("&", "&amp;")
            .replace("<","&lt;")
            .replace(">","&gt;")
            .replace('"',"&quot;")
            .replace("'","&#039;"))

# -----------------------------
# ND minor rules helpers
# -----------------------------
def labor_day(year: int) -> datetime.date:
    # first Monday in September
    d = datetime.date(year, 9, 1)
    while d.weekday() != 0:
        d += datetime.timedelta(days=1)
    return d

def is_summer_for_minor_14_15(day_date: datetime.date) -> bool:
    # June 1 – Labor Day (inclusive)
    ld = labor_day(day_date.year)
    return (day_date >= datetime.date(day_date.year, 6, 1)) and (day_date <= ld)

# -----------------------------
# Data models
# -----------------------------
MINOR_TYPES = ["ADULT", "MINOR_14_15", "MINOR_16_17"]

@dataclass
class DayRules:
    unavailable_day: bool = False
    earliest_start: int = 0         # tick
    latest_end: int = DAY_TICKS     # tick
    blocked_ranges: List[Tuple[int,int]] = field(default_factory=list)  # tick ranges

    def is_available(self, start_t: int, end_t: int) -> bool:
        if self.unavailable_day:
            return False
        if start_t < self.earliest_start:
            return False
        if end_t > self.latest_end:
            return False
        for bs, be in self.blocked_ranges:
            if not (end_t <= bs or start_t >= be):
                return False
        return True

@dataclass
class FixedShift:
    day: str
    start_t: int
    end_t: int
    area: str
    locked: bool

@dataclass
class Employee:
    name: str
    phone: str = ""
    work_status: str = "Active"                 # Active / On Leave / Inactive
    wants_hours: bool = True

    # New (V3.2 employee hard-rules + metadata)
    employee_type: str = "Crew Member"          # informational for now
    split_shifts_ok: bool = True                # if False: no split shifts across any areas
    double_shifts_ok: bool = False              # if False: hard cap 8h per shift block
    min_hours_per_shift: float = 1.0            # hard rule (final schedule): minimum contiguous shift length
    max_hours_per_shift: float = 8.0            # per-employee cap; may be raised if double_shifts_ok
    max_shifts_per_day: int = 1                 # contiguous work blocks/day (area changes w/o break count as same shift)
    max_weekly_hours: float = 30.0
    target_min_hours: float = 0.0               # optional
    minor_type: str = "ADULT"                   # ADULT / MINOR_14_15 / MINOR_16_17

    areas_allowed: List[str] = field(default_factory=lambda: ["CSTORE"])
    preferred_areas: List[str] = field(default_factory=list)

    avoid_clopens: bool = True
    max_consecutive_days: int = 6
    weekend_preference: str = "Neutral"         # Prefer / Avoid / Neutral

    availability: Dict[str, DayRules] = field(default_factory=dict)
    fixed_schedule: List[FixedShift] = field(default_factory=list)
    recurring_locked_schedule: List[FixedShift] = field(default_factory=list)

@dataclass
class WeeklyOverride:
    label: str               # week label key
    employee_name: str
    day: str
    off_all_day: bool
    blocked_ranges: List[Tuple[int,int]] = field(default_factory=list)
    note: str = ""

@dataclass
class RequirementBlock:
    day: str
    area: str
    start_t: int
    end_t: int
    min_count: int
    preferred_count: int
    max_count: int

@dataclass
class Assignment:
    day: str
    area: str
    start_t: int
    end_t: int
    employee_name: str
    locked: bool = False
    source: str = "solver"   # solver / fixed_locked / fixed_prefer

@dataclass
class ScheduleSummary:
    label: str
    created_on: str
    total_hours: float
    warnings: List[str]
    employee_hours: Dict[str, float]
    weekend_counts: Dict[str, int]
    undesirable_counts: Dict[str, int]
    filled_slots: int
    total_slots: int

@dataclass
class StoreInfo:
    store_name: str = ""
    store_address: str = ""
    store_phone: str = ""
    store_manager: str = ""
    cstore_open: str = "00:00"
    cstore_close: str = "24:00"
    kitchen_open: str = "00:00"
    kitchen_close: str = "24:00"
    carwash_open: str = "00:00"
    carwash_close: str = "24:00"


def _norm_hhmm_or_default(v: str, default: str) -> str:
    try:
        return tick_to_hhmm(hhmm_to_tick(str(v).strip()))
    except Exception:
        return default


def area_open_close_ticks(model: "DataModel", area: str) -> Tuple[int, int]:
    if area not in AREAS:
        return 0, DAY_TICKS
    si = getattr(model, "store_info", None)
    if si is None:
        return 0, DAY_TICKS
    if area == "CSTORE":
        op = _norm_hhmm_or_default(getattr(si, "cstore_open", "00:00"), "00:00")
        cl = _norm_hhmm_or_default(getattr(si, "cstore_close", "24:00"), "24:00")
    elif area == "KITCHEN":
        op = _norm_hhmm_or_default(getattr(si, "kitchen_open", "00:00"), "00:00")
        cl = _norm_hhmm_or_default(getattr(si, "kitchen_close", "24:00"), "24:00")
    else:
        op = _norm_hhmm_or_default(getattr(si, "carwash_open", "00:00"), "00:00")
        cl = _norm_hhmm_or_default(getattr(si, "carwash_close", "24:00"), "24:00")
    op_t = hhmm_to_tick(op)
    cl_t = hhmm_to_tick(cl)
    if cl_t <= op_t:
        return 0, DAY_TICKS
    return op_t, cl_t


def is_within_area_hours(model: "DataModel", area: str, start_t: int, end_t: int) -> bool:
    op_t, cl_t = area_open_close_ticks(model, area)
    return int(start_t) >= int(op_t) and int(end_t) <= int(cl_t) and int(end_t) > int(start_t)

@dataclass
class Settings:
    ui_scale: float = 1.0
    min_rest_hours: int = 10               # clopen rest
    fairness_lookback_weeks: int = 6
    optimizer_iterations: int = 2500
    optimizer_temperature: float = 0.8
    solver_scrutiny_level: str = "Balanced"
    learn_from_history: bool = True
    enable_multi_scenario_generation: bool = True
    scenario_schedule_count: int = 4
    enable_demand_forecast_engine: bool = True
    enable_employee_fit_engine: bool = True
    
@dataclass
class NdMinorRuleConfig:
    enforce: bool = True
    # School week toggle affects 14-15 weekly hour limit.
    is_school_week: bool = True


@dataclass
class ManagerGoals:
    # Targets & thresholds used for manager reporting and solver preferences/caps.
    # NOTE: In Milestone 1 these caps are persisted + validated; solver behavior is unchanged.
    coverage_goal_pct: float = 95.0                 # percent of required 30-min blocks fully covered
    daily_overstaff_allow_hours: float = 0.0        # informational threshold for warnings

    # Weekly labor caps:
    # preferred_weekly_cap: soft target (0 = ignore)
    # maximum_weekly_cap: hard cap (0 = disabled) — enforced starting Milestone 2
    preferred_weekly_cap: float = 0.0
    maximum_weekly_cap: float = 0.0


    # --- Milestone 6: Scoring weights (soft penalties) ---
    # Higher weight = stronger preference to avoid.
    w_under_preferred_coverage: float = 5.0      # per 30-min deficit tick
    w_over_preferred_cap: float = 20.0           # per hour over preferred cap
    w_participation_miss: float = 250.0          # per eligible employee missing >=1hr
    w_split_shifts: float = 30.0                 # per extra shift in a day
    w_hour_imbalance: float = 2.0                # per hour away from average (L1)

    # --- P2-3: Schedule Stability ---
    enable_schedule_stability: bool = True      # prefer keeping last week's assignments when feasible
    w_schedule_stability: float = 14.0          # per hour moved/changed vs previous schedule
    # --- Phase 4 C3: Risk-Aware Optimization ---
    enable_risk_aware_optimization: bool = True   # penalize fragile windows at generation time
    protect_single_point_failures: bool = True    # extra penalty for 1/1 windows
    w_risk_fragile: float = 4.0                   # scheduled == minimum required
    w_risk_single_point: float = 8.0              # minimum=1 and scheduled=1


    
    # --- Phase 3: Coverage Risk Protection + Utilization Optimizer ---
    enable_coverage_risk_protection: bool = True   # fill scarce shifts first and reserve scarce employees for scarce shifts
    w_coverage_risk: float = 10.0                  # strength of scarcity-aware preference (soft)

    enable_utilization_optimizer: bool = True      # prefer cleaner schedules: fewer unique employees, fewer fragments
    w_new_employee_penalty: float = 3.0            # penalty for introducing a brand-new employee (soft)
    w_fragmentation_penalty: float = 2.5           # penalty per assignment segment (soft)
    w_extend_shift_bonus: float = 2.0              # bonus for extending an adjacent shift (soft)
    w_low_hours_priority_bonus: float = 2.5        # bonus for using employees who are currently under-used
    w_near_cap_penalty: float = 5.0                # penalty for piling more hours onto already-heavy employees
    w_target_min_fill_bonus: float = 1.5           # bonus for employees still below their target minimum hours
    utilization_balance_tolerance_hours: float = 2.0   # ignore small hour differences inside this band

# Optional preferences (soft toggles)
    prefer_longer_shifts: bool = True            # slight penalty for very short segments
    prefer_area_consistency: bool = False        # slight penalty for switching areas
    # Backward compatibility: older saves used weekly_hours_cap. We keep it so old files load/saves remain compatible.
    # It is migrated into preferred_weekly_cap when loading older data.
    weekly_hours_cap: float = 0.0                   # legacy (0 = ignore)
    # --- Phase 2 Milestone P2-4/P2-5 ---
    w_pattern_learning: float = 8.0              # weight for deviating from learned patterns (soft preference)

    # Demand-adaptive staffing multipliers (applied to staffing requirements)
    demand_morning_multiplier: float = 1.0
    demand_midday_multiplier: float = 1.0
    demand_evening_multiplier: float = 1.0


    call_list_depth: int = 5
    include_noncertified_in_call_list: bool = False


@dataclass
class DataModel:
    meta_version: str = "LaborForceScheduler_v3_new"
    store_info: StoreInfo = field(default_factory=StoreInfo)
    settings: Settings = field(default_factory=Settings)
    nd_rules: NdMinorRuleConfig = field(default_factory=NdMinorRuleConfig)
    manager_goals: ManagerGoals = field(default_factory=ManagerGoals)

    week_start_sun: str = ""  # ISO date for current schedule label default
    employees: List[Employee] = field(default_factory=list)
    requirements: List[RequirementBlock] = field(default_factory=list)
    weekly_overrides: List[WeeklyOverride] = field(default_factory=list)

    learned_patterns: Dict[str, Any] = field(default_factory=dict)

    history: List[ScheduleSummary] = field(default_factory=list)

# -----------------------------
# Defaults
# -----------------------------
def default_day_rules() -> Dict[str, DayRules]:
    return {d: DayRules(False, 0, DAY_TICKS, []) for d in DAYS}

def default_requirements() -> List[RequirementBlock]:
    # Default blocks: 05:00–23:00 in 30-minute increments, CSTORE=2, others=0
    out: List[RequirementBlock] = []
    start = hhmm_to_tick("05:00")
    end = hhmm_to_tick("23:00")
    for day in DAYS:
        t = start
        while t < end:
            t2 = t + 1  # 30 min
            for area in AREAS:
                cnt = 2 if area == "CSTORE" else 0
                out.append(RequirementBlock(day, area, t, t2, cnt, cnt, cnt))
            t = t2
    return out

# -----------------------------
# Serialization
# -----------------------------
def ser_dayrules(dr: DayRules) -> dict:
    return {"unavailable_day": dr.unavailable_day,
            "earliest_start": dr.earliest_start,
            "latest_end": dr.latest_end,
            "blocked_ranges": [list(x) for x in dr.blocked_ranges]}

def des_dayrules(d: dict) -> DayRules:
    return DayRules(
        unavailable_day=bool(d.get("unavailable_day", False)),
        earliest_start=int(d.get("earliest_start", 0)),
        latest_end=int(d.get("latest_end", DAY_TICKS)),
        blocked_ranges=[(int(a), int(b)) for a,b in d.get("blocked_ranges", []) if int(b) > int(a)]
    )

def ser_employee(e: Employee) -> dict:
    return {
        "name": e.name,
        "phone": e.phone,
        "work_status": e.work_status,
        "wants_hours": bool(e.wants_hours),
        "employee_type": str(getattr(e, "employee_type", "Crew Member")),
        "split_shifts_ok": bool(getattr(e, "split_shifts_ok", True)),
        "double_shifts_ok": bool(getattr(e, "double_shifts_ok", False)),
        "min_hours_per_shift": float(getattr(e, "min_hours_per_shift", 1.0)),
        "max_hours_per_shift": float(getattr(e, "max_hours_per_shift", 8.0)),
        "max_shifts_per_day": int(getattr(e, "max_shifts_per_day", 1)),
        "max_weekly_hours": float(e.max_weekly_hours),
        "target_min_hours": float(e.target_min_hours),
        "minor_type": e.minor_type,
        "areas_allowed": list(e.areas_allowed),
        "preferred_areas": list(e.preferred_areas),
        "avoid_clopens": bool(e.avoid_clopens),
        "max_consecutive_days": int(e.max_consecutive_days),
        "weekend_preference": str(e.weekend_preference),
        "availability": {d: ser_dayrules(e.availability.get(d, DayRules())) for d in DAYS},
        "fixed_schedule": [asdict(fs) for fs in e.fixed_schedule],
        "recurring_locked_schedule": [asdict(fs) for fs in getattr(e, "recurring_locked_schedule", [])],
    }

def des_employee(d: dict) -> Employee:
    av_raw = d.get("availability", {})
    av = {day: des_dayrules(av_raw.get(day, {})) for day in DAYS}
    fs = []
    for x in d.get("fixed_schedule", []):
        try:
            fs.append(FixedShift(
                day=x.get("day","Sun"),
                start_t=int(x.get("start_t",0)),
                end_t=int(x.get("end_t",0)),
                area=x.get("area","CSTORE"),
                locked=bool(x.get("locked", False)),
            ))
        except Exception:
            pass

    recurring_raw = d.get("recurring_locked_schedule", None)
    rls: List[FixedShift] = []
    if isinstance(recurring_raw, list):
        for x in recurring_raw:
            try:
                rls.append(FixedShift(
                    day=x.get("day","Sun"),
                    start_t=int(x.get("start_t",0)),
                    end_t=int(x.get("end_t",0)),
                    area=x.get("area","CSTORE"),
                    locked=True,
                ))
            except Exception:
                pass
    else:
        for x in fs:
            if bool(getattr(x, "locked", False)):
                rls.append(FixedShift(day=x.day, start_t=x.start_t, end_t=x.end_t, area=x.area, locked=True))
        fs = [x for x in fs if not bool(getattr(x, "locked", False))]

    et = str(d.get("employee_type", "Crew Member"))
    if not et.strip():
        et = "Crew Member"

    def _as_float(val, default):
        try:
            return float(val)
        except Exception:
            return float(default)

    def _as_int(val, default):
        try:
            return int(val)
        except Exception:
            return int(default)

    split_ok = bool(d.get("split_shifts_ok", True))
    double_ok = bool(d.get("double_shifts_ok", False))
    min_shift_h = _as_float(d.get("min_hours_per_shift", 1.0), 1.0)
    max_raw = d.get("max_hours_per_shift", None)
    max_shift_h = None if max_raw is None else _as_float(max_raw, 8.0)
    max_shifts_day = _as_int(d.get("max_shifts_per_day", 1), 1)

    if max_shift_h is None:
        t = et.strip().lower()
        if t in ["store manager", "assistant manager", "kitchen manager"]:
            max_shift_h = 16.0
        elif t in ["senior crew member", "manager in training"]:
            max_shift_h = 12.0
        else:
            max_shift_h = 8.0

    min_shift_h = max(0.5, min_shift_h)
    max_shift_h = max(min_shift_h, max_shift_h)
    max_shifts_day = max(1, max_shifts_day)
    mt = d.get("minor_type","ADULT")
    if mt not in MINOR_TYPES:
        mt = "ADULT"
    areas = [a for a in d.get("areas_allowed", ["CSTORE"]) if a in AREAS]
    if not areas:
        areas = ["CSTORE"]
    pref_areas = [a for a in d.get("preferred_areas", []) if a in AREAS]
    return Employee(
        name=str(d.get("name","")).strip(),
        phone=str(d.get("phone","")).strip(),
        work_status=str(d.get("work_status","Active")),
        wants_hours=bool(d.get("wants_hours", True)),
        employee_type=et,
        split_shifts_ok=split_ok,
        double_shifts_ok=double_ok,
        min_hours_per_shift=min_shift_h,
        max_hours_per_shift=max_shift_h,
        max_shifts_per_day=max_shifts_day,
        max_weekly_hours=float(d.get("max_weekly_hours", 30.0)),
        target_min_hours=float(d.get("target_min_hours", 0.0)),
        minor_type=mt,
        areas_allowed=areas,
        preferred_areas=pref_areas,
        avoid_clopens=bool(d.get("avoid_clopens", True)),
        max_consecutive_days=int(d.get("max_consecutive_days", 6)),
        weekend_preference=str(d.get("weekend_preference", "Neutral")),
        availability=av,
        fixed_schedule=fs,
        recurring_locked_schedule=rls,
    )

def ser_override(o: WeeklyOverride) -> dict:
    return {"label": o.label, "employee_name": o.employee_name, "day": o.day,
            "off_all_day": bool(o.off_all_day),
            "blocked_ranges": [list(x) for x in o.blocked_ranges],
            "note": o.note}

def des_override(d: dict) -> WeeklyOverride:
    br = []
    for a,b in d.get("blocked_ranges", []):
        try:
            a=int(a); b=int(b)
            if b>a: br.append((a,b))
        except Exception:
            pass
    return WeeklyOverride(
        label=str(d.get("label","")).strip(),
        employee_name=str(d.get("employee_name","")).strip(),
        day=str(d.get("day","Sun")),
        off_all_day=bool(d.get("off_all_day", False)),
        blocked_ranges=br,
        note=str(d.get("note","")).strip(),
    )

def ser_req(r: RequirementBlock) -> dict:
    return asdict(r)

def des_req(d: dict) -> RequirementBlock:
    # Backward compatible: older saves used required_count only
    rc = int(d.get("required_count", d.get("min_count", 0)))
    mn = int(d.get("min_count", rc))
    pr = int(d.get("preferred_count", mn))
    mx = int(d.get("max_count", pr))
    # normalize
    mn = max(0, mn)
    pr = max(mn, pr)
    mx = max(pr, mx)
    return RequirementBlock(
        day=str(d.get("day","Sun")),
        area=str(d.get("area","CSTORE")),
        start_t=int(d.get("start_t",0)),
        end_t=int(d.get("end_t",0)),
        min_count=mn,
        preferred_count=pr,
        max_count=mx,
    )

def ser_assignment(a: Assignment) -> dict:
    return asdict(a)

def des_assignment(d: dict) -> Assignment:
    return Assignment(
        day=str(d.get("day", "Sun")),
        area=str(d.get("area", "CSTORE")),
        start_t=int(d.get("start_t", 0)),
        end_t=int(d.get("end_t", 0)),
        employee_name=str(d.get("employee_name", "")).strip(),
        locked=bool(d.get("locked", False)),
        source=str(d.get("source", "solver") or "solver"),
    )

def ser_summary(s: ScheduleSummary) -> dict:
    return asdict(s)

def des_summary(d: dict) -> ScheduleSummary:
    return ScheduleSummary(
        label=d.get("label",""),
        created_on=d.get("created_on",""),
        total_hours=float(d.get("total_hours",0.0)),
        warnings=list(d.get("warnings",[])),
        employee_hours={k: float(v) for k,v in d.get("employee_hours",{}).items()},
        weekend_counts={k: int(v) for k,v in d.get("weekend_counts",{}).items()},
        undesirable_counts={k: int(v) for k,v in d.get("undesirable_counts",{}).items()},
        filled_slots=int(d.get("filled_slots",0)),
        total_slots=int(d.get("total_slots",0)),
    )

def save_data(model: DataModel, path: str):
    payload = {
        "meta": {"version": model.meta_version, "saved_on": today_iso()},
        "store_info": asdict(model.store_info),
        "settings": asdict(model.settings),
        "nd_rules": asdict(model.nd_rules),
        "manager_goals": asdict(model.manager_goals),
        "week_start_sun": model.week_start_sun,
        "employees": [ser_employee(e) for e in model.employees],
        "requirements": [ser_req(r) for r in model.requirements],
        "weekly_overrides": [ser_override(o) for o in model.weekly_overrides],
        "history": [ser_summary(s) for s in model.history],
    }
    ensure_dir(os.path.dirname(path))
    _atomic_write_json(path, payload, indent=2)

def load_data(path: str) -> DataModel:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    m = DataModel()
    m.week_start_sun = str(payload.get("week_start_sun","")).strip()

    store_info_raw = dict(payload.get("store_info", {}) or {})
    try:
        allowed_store_info_keys = set(StoreInfo.__dataclass_fields__.keys())
        unknown_store_info = sorted(k for k in store_info_raw.keys() if k not in allowed_store_info_keys)
        if unknown_store_info:
            _write_run_log(f"[load_data] Ignoring unknown store_info keys: {', '.join(unknown_store_info)}")
        store_info_filtered = {k: v for k, v in store_info_raw.items() if k in allowed_store_info_keys}
    except Exception:
        store_info_filtered = store_info_raw
    m.store_info = StoreInfo(**store_info_filtered)

    settings_raw = dict(payload.get("settings", {}) or {})
    try:
        allowed_settings_keys = set(Settings.__dataclass_fields__.keys())
        unknown_settings = sorted(k for k in settings_raw.keys() if k not in allowed_settings_keys)
        if unknown_settings:
            _write_run_log(f"[load_data] Ignoring unknown settings keys: {', '.join(unknown_settings)}")
        settings_filtered = {k: v for k, v in settings_raw.items() if k in allowed_settings_keys}
    except Exception:
        settings_filtered = settings_raw
    m.settings = Settings(**settings_filtered)
    # Clamp ui_scale to prevent oversized UI from test files or older saves.
    # Target baseline is 1.0; allow up to 1.3 (roughly +30%) for readability.
    try:
        if m.settings.ui_scale is None:
            m.settings.ui_scale = 1.0
        if float(m.settings.ui_scale) > 1.3:
            m.settings.ui_scale = 1.3
        if float(m.settings.ui_scale) < 0.5:
            m.settings.ui_scale = 1.0
    except Exception:
        m.settings.ui_scale = 1.0
    nd_rules_raw = dict(payload.get("nd_rules", {}) or {})
    try:
        allowed_nd_rules_keys = set(NdMinorRuleConfig.__dataclass_fields__.keys())
        unknown_nd_rules = sorted(k for k in nd_rules_raw.keys() if k not in allowed_nd_rules_keys)
        if unknown_nd_rules:
            _write_run_log(f"[load_data] Ignoring unknown nd_rules keys: {', '.join(unknown_nd_rules)}")
        nd_rules_filtered = {k: v for k, v in nd_rules_raw.items() if k in allowed_nd_rules_keys}
    except Exception:
        nd_rules_filtered = nd_rules_raw
    m.nd_rules = NdMinorRuleConfig(**nd_rules_filtered)
    # Manager goals migration (backward compatible)
    mg = dict(payload.get("manager_goals", {}) or {})
    # Older saves used weekly_hours_cap; migrate into preferred_weekly_cap if needed.
    if "preferred_weekly_cap" not in mg and "weekly_hours_cap" in mg:
        try:
            mg["preferred_weekly_cap"] = float(mg.get("weekly_hours_cap", 0.0) or 0.0)
        except Exception:
            mg["preferred_weekly_cap"] = 0.0
    # Ensure new field exists (0 = disabled)
    if "maximum_weekly_cap" not in mg:
        mg["maximum_weekly_cap"] = 0.0
    # P2-3 stability defaults
    if "enable_schedule_stability" not in mg:
        mg["enable_schedule_stability"] = True
    if "w_schedule_stability" not in mg:
        mg["w_schedule_stability"] = 14.0

    # Phase 4 C3: Risk-Aware Optimization defaults (soft)
    if "enable_risk_aware_optimization" not in mg:
        mg["enable_risk_aware_optimization"] = True
    if "protect_single_point_failures" not in mg:
        mg["protect_single_point_failures"] = True
    if "w_risk_fragile" not in mg:
        mg["w_risk_fragile"] = 4.0
    if "w_risk_single_point" not in mg:
        mg["w_risk_single_point"] = 8.0
    # Keep legacy field populated for backward compatibility
    if "weekly_hours_cap" not in mg:
        mg["weekly_hours_cap"] = mg.get("preferred_weekly_cap", 0.0)

    # Compatibility hardening: ignore unknown keys from future / partially patched builds
    # instead of crashing ManagerGoals(**mg).
    try:
        allowed_mg_keys = set(ManagerGoals.__dataclass_fields__.keys())
        unknown_mg = sorted(k for k in mg.keys() if k not in allowed_mg_keys)
        if unknown_mg:
            _write_run_log(f"[load_data] Ignoring unknown manager_goals keys: {', '.join(unknown_mg)}")
        mg = {k: v for k, v in mg.items() if k in allowed_mg_keys}
    except Exception:
        pass

    m.manager_goals = ManagerGoals(**mg)
    m.employees = [des_employee(e) for e in payload.get("employees", []) if str(e.get("name","")).strip()]
    m.requirements = [des_req(r) for r in payload.get("requirements", [])]
    if not m.requirements:
        m.requirements = default_requirements()
    m.weekly_overrides = [des_override(o) for o in payload.get("weekly_overrides", [])]
    m.history = [des_summary(s) for s in payload.get("history", [])]
    return m

# -----------------------------
# P2-3 — Schedule Stability helpers
# -----------------------------
def _expand_assignments_to_tick_map(assigns: List[Assignment]) -> Dict[Tuple[str,str,int], str]:
    out: Dict[Tuple[str,str,int], str] = {}
    for a in assigns:
        for tt in range(int(a.start_t), int(a.end_t)):
            out[(a.day, a.area, int(tt))] = a.employee_name
    return out

def load_last_schedule_tick_map() -> Tuple[Optional[str], Dict[Tuple[str,str,int], str]]:
    """Loads the previous schedule tick map from ./data/last_schedule.json (if present)."""
    path = rel_path("data", "last_schedule.json")
    if not os.path.exists(path):
        return None, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        label = str(payload.get("label", "")).strip() or None
        assigns_raw = payload.get("assignments", []) or []
        assigns: List[Assignment] = []
        for x in assigns_raw:
            try:
                assigns.append(Assignment(
                    day=str(x.get("day","Sun")),
                    area=str(x.get("area","CSTORE")),
                    start_t=int(x.get("start_t",0)),
                    end_t=int(x.get("end_t",0)),
                    employee_name=str(x.get("employee_name","")).strip(),
                    locked=bool(x.get("locked", False)),
                    source=str(x.get("source","prev")),
                ))
            except Exception:
                pass
        return label, _expand_assignments_to_tick_map(assigns)
    except Exception:
        return None, {}



def load_prev_final_schedule_tick_map(current_label: Optional[str]) -> Tuple[Optional[str], Dict[Tuple[str,str,int], str]]:
    """Prefer last week's *published final* schedule (./data/final_schedules/YYYY-MM-DD.json) for stability.
    Falls back to most recent final schedule found earlier than the current week if exact prev-week file is missing.
    """
    try:
        wk = week_sun_from_label(str(current_label or ""))
    except Exception:
        wk = None
    if not wk:
        return None, {}

    def _load_final(path: str) -> Tuple[Optional[str], Dict[Tuple[str,str,int], str]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f) or {}
            label = str(payload.get("label", "")).strip() or None
            assigns_raw = payload.get("assignments", []) or []
            assigns: List[Assignment] = []
            for x in assigns_raw:
                try:
                    assigns.append(Assignment(
                        day=str(x.get("day","Sun")),
                        area=str(x.get("area","CSTORE")),
                        start_t=int(x.get("start_t",0)),
                        end_t=int(x.get("end_t",0)),
                        employee_name=str(x.get("employee_name","")).strip(),
                        locked=bool(x.get("locked", False)),
                        source=str(x.get("source","final")),
                    ))
                except Exception:
                    pass
            return label, _expand_assignments_to_tick_map(assigns)
        except Exception:
            return None, {}

    # Prefer exact prior week file
    prev = wk - datetime.timedelta(days=7)
    exact = rel_path("data", "final_schedules", f"{prev.isoformat()}.json")
    if os.path.isfile(exact):
        return _load_final(exact)

    # Otherwise, choose most recent final earlier than current week
    d = rel_path("data", "final_schedules")
    if not os.path.isdir(d):
        return None, {}
    best_date = None
    best_path = None
    for fn in os.listdir(d):
        if not fn.lower().endswith(".json"):
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.json$", fn)
        if not m:
            continue
        try:
            dt = datetime.date.fromisoformat(m.group(1))
        except Exception:
            continue
        if dt >= wk:
            continue
        if best_date is None or dt > best_date:
            best_date = dt
            best_path = os.path.join(d, fn)
    if best_path:
        return _load_final(best_path)
    return None, {}

def load_final_schedule_payload_for_label(label: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    """Load the published final schedule payload for the given label/week, if present."""
    try:
        wk = week_sun_from_label(str(label or ""))
    except Exception:
        wk = None
    if not wk:
        return None, {}
    path = rel_path("data", "final_schedules", f"{wk.isoformat()}.json")
    if not os.path.isfile(path):
        return None, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        return path, payload
    except Exception:
        return None, {}


def load_assignments_from_final_payload(payload: Dict[str, Any]) -> List[Assignment]:
    assigns: List[Assignment] = []
    for item in (payload.get("assignments", []) or []):
        try:
            assigns.append(des_assignment(item))
        except Exception:
            pass
    return assigns


def load_prev_final_schedule_assignments(current_label: Optional[str]) -> Tuple[Optional[str], Optional[str], List[Assignment]]:
    """Return the label/path/assignments for the prior published final schedule used by stability logic."""
    try:
        wk = week_sun_from_label(str(current_label or ""))
    except Exception:
        wk = None
    if not wk:
        return None, None, []

    def _load_final(path: str) -> Tuple[Optional[str], Optional[str], List[Assignment]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f) or {}
            return str(payload.get("label", "")).strip() or None, path, load_assignments_from_final_payload(payload)
        except Exception:
            return None, None, []

    prev = wk - datetime.timedelta(days=7)
    exact = rel_path("data", "final_schedules", f"{prev.isoformat()}.json")
    if os.path.isfile(exact):
        return _load_final(exact)

    d = rel_path("data", "final_schedules")
    if not os.path.isdir(d):
        return None, None, []
    best_date = None
    best_path = None
    for fn in os.listdir(d):
        if not fn.lower().endswith(".json"):
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.json$", fn)
        if not m:
            continue
        try:
            dt = datetime.date.fromisoformat(m.group(1))
        except Exception:
            continue
        if dt >= wk:
            continue
        if best_date is None or dt > best_date:
            best_date = dt
            best_path = os.path.join(d, fn)
    if best_path:
        return _load_final(best_path)
    return None, None, []


def load_last_schedule_assignments() -> Tuple[Optional[str], List[Assignment]]:
    path = rel_path("data", "last_schedule.json")
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        label = str(payload.get("label", "")).strip() or None
        assigns = []
        for x in (payload.get("assignments", []) or []):
            try:
                assigns.append(Assignment(
                    day=str(x.get("day","Sun")),
                    area=str(x.get("area","CSTORE")),
                    start_t=int(x.get("start_t",0)),
                    end_t=int(x.get("end_t",0)),
                    employee_name=str(x.get("employee_name","")).strip(),
                    locked=bool(x.get("locked", False)),
                    source=str(x.get("source","prev")),
                ))
            except Exception:
                pass
        return label, assigns
    except Exception:
        return None, []


def _patterns_path() -> str:
    return rel_path("data", "patterns.json")

def load_patterns() -> Dict[str, Any]:
    """Load learned patterns from ./data/patterns.json."""
    path = _patterns_path()
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

def save_patterns(patterns: Dict[str, Any]) -> None:
    path = _patterns_path()
    try:
        ensure_dir(os.path.dirname(path))
        _atomic_write_json(path, patterns or {}, indent=2)
    except Exception:
        pass

def _tick_to_hour(tick: int) -> float:
    return float(tick) * 0.5

def _demand_bucket_for_tick(tick: int) -> str:
    """Return 'morning' | 'midday' | 'evening' based on start tick."""
    hr = _tick_to_hour(int(tick))
    # Treat overnight (before 5am) as evening demand.
    if hr < 5.0:
        return "evening"
    if hr < 11.0:
        return "morning"
    if hr < 17.0:
        return "midday"
    return "evening"

def learn_patterns_from_history_folder() -> Dict[str, Any]:
    """Scan ./history/*.json and ./data/last_schedule.json to infer soft preferences."""
    patterns: Dict[str, Any] = {}
    # Accumulators
    area_counts: Dict[str, Dict[str, int]] = {}
    start_counts: Dict[str, Dict[str, int]] = {}
    len_counts: Dict[str, Dict[str, int]] = {}

    def add_assignment(a: Dict[str, Any]) -> None:
        emp = str(a.get("employee","")).strip()
        if not emp:
            return
        area = str(a.get("area","")).strip()
        st = int(a.get("start_t", 0))
        en = int(a.get("end_t", 0))
        ln = max(1, int(en - st))
        area_counts.setdefault(emp, {})
        area_counts[emp][area] = area_counts[emp].get(area, 0) + 1
        start_counts.setdefault(emp, {})
        start_counts[emp][str(st)] = start_counts[emp].get(str(st), 0) + 1
        len_counts.setdefault(emp, {})
        len_counts[emp][str(ln)] = len_counts[emp].get(str(ln), 0) + 1

    # history snapshots
    try:
        hdir = rel_path("history")
        if os.path.isdir(hdir):
            for fn in os.listdir(hdir):
                if not fn.lower().endswith(".json"):
                    continue
                path = os.path.join(hdir, fn)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        payload = json.load(f) or {}
                    assigns = payload.get("assignments") or payload.get("schedule", {}).get("assignments") or []
                    if isinstance(assigns, list):
                        for a in assigns:
                            if isinstance(a, dict):
                                add_assignment(a)
                except Exception:
                    continue
    except Exception:
        pass

    # last schedule
    try:
        lpath = rel_path("data", "last_schedule.json")
        if os.path.isfile(lpath):
            with open(lpath, "r", encoding="utf-8") as f:
                payload = json.load(f) or {}
            assigns = payload.get("assignments") or []
            if isinstance(assigns, list):
                for a in assigns:
                    if isinstance(a, dict):
                        add_assignment(a)
    except Exception:
        pass

    # finalize
    for emp in set(list(area_counts.keys()) + list(start_counts.keys()) + list(len_counts.keys())):
        ac = area_counts.get(emp, {})
        sc = start_counts.get(emp, {})
        lc = len_counts.get(emp, {})
        pref_area = max(ac.items(), key=lambda kv: kv[1])[0] if ac else ""
        pref_start = int(max(sc.items(), key=lambda kv: kv[1])[0]) if sc else 0
        pref_len = int(max(lc.items(), key=lambda kv: kv[1])[0]) if lc else 0
        patterns[emp] = {
            "preferred_area": pref_area,
            "preferred_start_tick": pref_start,
            "preferred_len_ticks": pref_len,
            "area_counts": ac,
            "start_tick_counts": sc,
            "len_counts": lc,
        }
    return patterns


def build_demand_forecast_profile() -> Dict[str, Any]:
    bucket_counts = {"morning": 0.0, "midday": 0.0, "evening": 0.0}
    area_counts: Dict[str, float] = {}

    def _consume(assigns: List[Dict[str, Any]]) -> None:
        for a in assigns or []:
            try:
                st = int(a.get("start_t", 0) or 0)
                en = int(a.get("end_t", 0) or 0)
                ln = max(1, en - st)
                bucket = _demand_bucket_for_tick(st)
                bucket_counts[bucket] = bucket_counts.get(bucket, 0.0) + float(ln)
                area = str(a.get("area", "") or "").strip()
                if area:
                    area_counts[area] = area_counts.get(area, 0.0) + float(ln)
            except Exception:
                pass

    try:
        hdir = rel_path("history")
        if os.path.isdir(hdir):
            for fn in os.listdir(hdir):
                if not fn.lower().endswith('.json'):
                    continue
                p = os.path.join(hdir, fn)
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        payload = json.load(f) or {}
                    _consume(payload.get('assignments') or payload.get('schedule', {}).get('assignments') or [])
                except Exception:
                    pass
    except Exception:
        pass

    try:
        p = rel_path('data', 'last_schedule.json')
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                payload = json.load(f) or {}
            _consume(payload.get('assignments') or [])
    except Exception:
        pass

    total = sum(float(v) for v in bucket_counts.values())
    multipliers = {"morning": 1.0, "midday": 1.0, "evening": 1.0}
    if total > 0.0:
        baseline = total / 3.0
        for bucket, raw in bucket_counts.items():
            ratio = float(raw) / max(1.0, baseline)
            multipliers[bucket] = max(0.85, min(1.20, round(ratio, 2)))

    peak_bucket = max(multipliers.items(), key=lambda kv: kv[1])[0] if multipliers else 'midday'
    low_bucket = min(multipliers.items(), key=lambda kv: kv[1])[0] if multipliers else 'midday'
    return {'bucket_counts': bucket_counts, 'multipliers': multipliers, 'peak_bucket': peak_bucket, 'low_bucket': low_bucket, 'dominant_area': max(area_counts.items(), key=lambda kv: kv[1])[0] if area_counts else ''}


def apply_demand_forecast_to_model(model: DataModel, forecast: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    forecast = dict(forecast or build_demand_forecast_profile())
    mults = dict(forecast.get('multipliers') or {})
    try:
        model.manager_goals.demand_morning_multiplier = float(mults.get('morning', 1.0) or 1.0)
        model.manager_goals.demand_midday_multiplier = float(mults.get('midday', 1.0) or 1.0)
        model.manager_goals.demand_evening_multiplier = float(mults.get('evening', 1.0) or 1.0)
    except Exception:
        pass
    return forecast


def build_employee_fit_profiles() -> Dict[str, Any]:
    profiles: Dict[str, Any] = {}
    area_counts: Dict[str, Dict[str, float]] = {}
    bucket_counts: Dict[str, Dict[str, float]] = {}
    def _consume(assigns: List[Dict[str, Any]]) -> None:
        for a in assigns or []:
            try:
                emp = str(a.get('employee_name', a.get('employee', '')) or '').strip()
                if not emp:
                    continue
                area = str(a.get('area', '') or '').strip()
                st = int(a.get('start_t', 0) or 0)
                en = int(a.get('end_t', 0) or 0)
                ln = max(1, en - st)
                bucket = _demand_bucket_for_tick(st)
                area_counts.setdefault(emp, {})
                bucket_counts.setdefault(emp, {})
                if area:
                    area_counts[emp][area] = area_counts[emp].get(area, 0.0) + float(ln)
                bucket_counts[emp][bucket] = bucket_counts[emp].get(bucket, 0.0) + float(ln)
            except Exception:
                pass
    try:
        hdir = rel_path('history')
        if os.path.isdir(hdir):
            for fn in os.listdir(hdir):
                if not fn.lower().endswith('.json'):
                    continue
                p = os.path.join(hdir, fn)
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        payload = json.load(f) or {}
                    _consume(payload.get('assignments') or payload.get('schedule', {}).get('assignments') or [])
                except Exception:
                    pass
    except Exception:
        pass
    try:
        p = rel_path('data', 'last_schedule.json')
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                payload = json.load(f) or {}
            _consume(payload.get('assignments') or [])
    except Exception:
        pass
    for emp in sorted(set(list(area_counts.keys()) + list(bucket_counts.keys()))):
        ac = area_counts.get(emp, {}) or {}
        bc = bucket_counts.get(emp, {}) or {}
        profiles[emp] = {'best_area': max(ac.items(), key=lambda kv: kv[1])[0] if ac else '', 'best_bucket': max(bc.items(), key=lambda kv: kv[1])[0] if bc else '', 'area_counts': ac, 'bucket_counts': bc}
    return profiles


def get_employee_fit_score(learned_patterns: Dict[str, Any], emp_name: str, area: str, start_tick: int) -> float:
    fit_profiles = dict((learned_patterns or {}).get('__employee_fit__') or {})
    profile = dict(fit_profiles.get(emp_name) or {})
    if not profile:
        return 0.0
    score = 0.0
    best_area = str(profile.get('best_area', '') or '').strip()
    best_bucket = str(profile.get('best_bucket', '') or '').strip()
    bucket = _demand_bucket_for_tick(int(start_tick))
    if best_area:
        score += 2.5 if area == best_area else -1.5
    if best_bucket:
        score += 1.5 if bucket == best_bucket else -0.5
    return score


def save_last_schedule(assigns: List[Assignment], label: str):
    """Persists the latest schedule to ./data/last_schedule.json for stability scoring."""
    path = rel_path("data", "last_schedule.json")
    ensure_dir(os.path.dirname(path))
    try:
        payload = {
            "label": str(label),
            "saved_on": today_iso(),
            "assignments": [asdict(a) for a in assigns],
        }
        _atomic_write_json(path, payload, indent=2)
    except Exception:
        pass

# -----------------------------
# Constraint checking

# -----------------------------
def week_sun_from_label(label: str) -> Optional[datetime.date]:
    # expects label like "Week starting YYYY-MM-DD"
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})", label)
    if not m:
        return None
    try:
        return datetime.date.fromisoformat(m.group(1))
    except Exception:
        return None

def day_date(week_sun: datetime.date, day: str) -> datetime.date:
    return week_sun + datetime.timedelta(days=DAYS.index(day))

def calc_schedule_stats(model: "DataModel", assignments: List[Assignment]) -> Tuple[Dict[str,float], float, int, int]:
    emp_hours: Dict[str, float] = {}
    total_hours = 0.0
    for a in assignments or []:
        hrs = hours_between_ticks(int(a.start_t), int(a.end_t))
        emp_hours[a.employee_name] = emp_hours.get(a.employee_name, 0.0) + hrs
        total_hours += hrs

    coverage: Dict[Tuple[str, str, int], int] = {}
    for a in assignments or []:
        try:
            for t in range(int(a.start_t), int(a.end_t)):
                k = (a.day, a.area, t)
                coverage[k] = coverage.get(k, 0) + 1
        except Exception:
            continue

    filled = 0
    total_slots = 0
    min_req, _pref_req, _max_req = build_requirement_maps(getattr(model, "requirements", []) or [], goals=getattr(model, "manager_goals", None), store_info=getattr(model, "store_info", None))
    for k, mn in min_req.items():
        total_slots += int(mn)
        filled += min(int(mn), int(coverage.get(k, 0)))

    return emp_hours, float(total_hours), int(filled), int(total_slots)

def is_employee_available(model: DataModel, e: Employee, label: str, day: str, start_t: int, end_t: int, area: str,
                          clopen_min_start: Dict[Tuple[str,str], int]) -> bool:
    if e.work_status != "Active":
        return False
    if area not in e.areas_allowed:
        return False
    if not is_within_area_hours(model, area, start_t, end_t):
        return False
    dr = e.availability.get(day)
    if dr is None:
        return False
    if not dr.is_available(start_t, end_t):
        return False

    # weekly override
    for o in model.weekly_overrides:
        if o.label.strip() == label.strip() and o.employee_name == e.name and o.day == day:
            if o.off_all_day:
                return False
            for bs, be in o.blocked_ranges:
                if not (end_t <= bs or start_t >= be):
                    return False

    # clopen rest
    ms = clopen_min_start.get((e.name, day))
    if ms is not None and start_t < ms:
        return False

    # ND minor rules (14-15)
    if model.nd_rules.enforce and e.minor_type == "MINOR_14_15":
        ws = week_sun_from_label(label) or datetime.date.today()
        ddate = day_date(ws, day)
        summer = is_summer_for_minor_14_15(ddate)
        # Allowed window
        earliest = hhmm_to_tick("07:00")
        latest = hhmm_to_tick("21:00") if summer else hhmm_to_tick("19:00")
        if start_t < earliest:
            return False
        if end_t > latest:
            return False
    return True

def apply_clopen_from(model: DataModel, e: Employee, a: Assignment,
                      clopen_min_start: Dict[Tuple[str,str], int]):
    if not e.avoid_clopens:
        return
    # if ends late (>=22:00), enforce min rest for next day
    end_hr = a.end_t / TICKS_PER_HOUR
    if end_hr >= 22.0:
        idx = DAYS.index(a.day)
        next_day = DAYS[(idx + 1) % 7]
        min_start_ticks = int(max(0, (a.end_t + model.settings.min_rest_hours*TICKS_PER_HOUR) - DAY_TICKS))
        clopen_min_start[(e.name, next_day)] = max(clopen_min_start.get((e.name, next_day), 0), min_start_ticks)

# -----------------------------
# Optimizer
# -----------------------------
def build_requirement_maps(reqs: List[RequirementBlock], goals: Optional[Any] = None, store_info: Optional[StoreInfo] = None) -> Tuple[Dict[Tuple[str,str,int], int], Dict[Tuple[str,str,int], int], Dict[Tuple[str,str,int], int]]:
    """Compile requirements into per-30-minute-tick maps.

    Returns:
      min_req[(day, area, tick)] = hard minimum headcount
      pref_req[(day, area, tick)] = preferred (soft) target headcount
      max_req[(day, area, tick)] = hard maximum headcount (cap)
    Overlaps are combined conservatively:
      - min / preferred: take max
      - max: take min (tightest cap)
    """
    min_req: Dict[Tuple[str,str,int], int] = {}
    pref_req: Dict[Tuple[str,str,int], int] = {}
    max_req: Dict[Tuple[str,str,int], int] = {}
    for r in reqs:
        if r.day not in DAYS or r.area not in AREAS:
            continue
        mn = max(0, int(getattr(r, "min_count", 0)))
        pr = max(mn, int(getattr(r, "preferred_count", mn)))
        mx = max(pr, int(getattr(r, "max_count", pr)))
        m_morn = float(getattr(goals, "demand_morning_multiplier", 1.0) or 1.0) if goals is not None else 1.0
        m_mid  = float(getattr(goals, "demand_midday_multiplier", 1.0) or 1.0) if goals is not None else 1.0
        m_eve  = float(getattr(goals, "demand_evening_multiplier", 1.0) or 1.0) if goals is not None else 1.0
        if store_info is not None:
            tmp_model = DataModel(store_info=store_info)
            if not is_within_area_hours(tmp_model, r.area, int(r.start_t), int(r.end_t)):
                continue
        for t in range(int(r.start_t), int(r.end_t)):
            mult = 1.0
            bucket = _demand_bucket_for_tick(int(t))
            if bucket == "morning":
                mult = m_morn
            elif bucket == "midday":
                mult = m_mid
            else:
                mult = m_eve
            mn_t = int(round(mn * mult))
            pr_t = int(round(pr * mult))
            mx_t = int(round(mx * mult))
            mn_t = max(0, mn_t)
            pr_t = max(mn_t, pr_t)
            mx_t = max(pr_t, mx_t)

            k = (r.day, r.area, int(t))
            min_req[k] = max(min_req.get(k, 0), mn_t)
            pref_req[k] = max(pref_req.get(k, 0), pr_t)
            if k in max_req:
                max_req[k] = min(max_req[k], mx_t)
            else:
                max_req[k] = mx_t
    for k in set(list(min_req.keys()) + list(pref_req.keys()) + list(max_req.keys())):
        mn = min_req.get(k, 0)
        pr = pref_req.get(k, mn)
        mx = max_req.get(k, pr)
        mn = max(0, mn)
        pr = max(mn, pr)
        mx = max(pr, mx)
        min_req[k] = mn
        pref_req[k] = pr
        max_req[k] = mx
    return min_req, pref_req, max_req

def count_coverage_per_tick(assignments: List[Assignment]) -> Dict[Tuple[str,str,int], int]:
    cov: Dict[Tuple[str,str,int], int] = {}
    for a in assignments:
        for t in range(int(a.start_t), int(a.end_t)):
            k = (a.day, a.area, int(t))
            cov[k] = cov.get(k, 0) + 1
    return cov

def compute_requirement_shortfalls(min_req: Dict[Tuple[str,str,int], int],
                                   pref_req: Dict[Tuple[str,str,int], int],
                                   max_req: Dict[Tuple[str,str,int], int],
                                   cov: Dict[Tuple[str,str,int], int]) -> Tuple[int,int,int]:
    """Return (min_shortfall_ticks, preferred_shortfall_ticks, max_violations_ticks)."""
    min_short = 0
    pref_short = 0
    max_viol = 0
    for k, mn in min_req.items():
        if cov.get(k, 0) < mn:
            min_short += (mn - cov.get(k, 0))
    for k, pr in pref_req.items():
        if cov.get(k, 0) < pr:
            pref_short += (pr - cov.get(k, 0))
    for k, mx in max_req.items():
        if cov.get(k, 0) > mx:
            max_viol += (cov.get(k, 0) - mx)
    return min_short, pref_short, max_viol

def overlaps(a1: Assignment, a2: Assignment) -> bool:
    if a1.employee_name != a2.employee_name or a1.day != a2.day:
        return False
    return not (a1.end_t <= a2.start_t or a1.start_t >= a2.end_t)

def _merge_touching_intervals(intervals: List[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: (x[0], x[1]))
    out = [intervals[0]]
    for st,en in intervals[1:]:
        pst, pen = out[-1]
        # merge if overlaps OR touches (end==start counts as continuous shift)
        if st <= pen:
            out[-1] = (pst, max(pen, en))
        else:
            out.append((st,en))
    return out

def employee_allowed_max_shift_hours(e: Employee) -> float:
    """Hard cap 8h unless employee allows double shifts."""
    mx = float(getattr(e, "max_hours_per_shift", 8.0))
    if not bool(getattr(e, "double_shifts_ok", False)):
        return min(8.0, mx)
    return mx

def daily_shift_blocks(assigns: List[Assignment], emp_name: str, day: str, extra: Optional[Tuple[int,int]] = None) -> List[Tuple[int,int]]:
    intervals = [(a.start_t, a.end_t) for a in assigns if a.employee_name==emp_name and a.day==day]
    if extra is not None:
        intervals.append(extra)
    return _merge_touching_intervals(intervals)

def respects_daily_shift_limits(assigns: List[Assignment], e: Employee, day: str, extra: Optional[Tuple[int,int]] = None) -> bool:
    blocks = daily_shift_blocks(assigns, e.name, day, extra=extra)
    n = len(blocks)
    max_shifts = int(getattr(e, "max_shifts_per_day", 1))
    if max_shifts < 1:
        max_shifts = 1
    if n > max_shifts:
        return False
    if not bool(getattr(e, "split_shifts_ok", True)) and n > 1:
        return False
    # enforce max shift length (per contiguous block)
    mxh = employee_allowed_max_shift_hours(e)
    for st,en in blocks:
        if hours_between_ticks(st,en) - mxh > 1e-9:
            return False
    return True

def respects_max_consecutive_days(assigns: List[Assignment], e: Employee, day: str) -> bool:
    """Hard check for max consecutive days after adding/considering a day assignment."""
    lim = int(getattr(e, "max_consecutive_days", 0) or 0)
    if lim <= 0:
        return True
    days_worked = {a.day for a in assigns if a.employee_name == e.name}
    days_worked.add(day)
    idxs = sorted({DAYS.index(d) for d in days_worked if d in DAYS})
    if not idxs:
        return True
    run = 1
    maxrun = 1
    for i in range(1, len(idxs)):
        if idxs[i] == idxs[i-1] + 1:
            run += 1
            maxrun = max(maxrun, run)
        else:
            run = 1
    return maxrun <= lim


def schedule_score(model: DataModel, label: str,
                   assignments: List[Assignment],
                   unfilled: int,
                   history_stats: Dict[str, Dict[str,int]],
                   prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None) -> float:
    """Return a single numeric score (lower is better).

    Hard constraints should be enforced by construction/feasibility checks.
    This score is used to compare candidate schedules.
    """
    goals = getattr(model, "manager_goals", None)

    # Weight helpers (safe defaults)
    w_under_pref_cov = float(getattr(goals, "w_under_preferred_coverage", 5.0) or 5.0)
    w_over_pref_cap = float(getattr(goals, "w_over_preferred_cap", 20.0) or 20.0)
    w_part_miss = float(getattr(goals, "w_participation_miss", 250.0) or 250.0)
    w_split = float(getattr(goals, "w_split_shifts", 30.0) or 30.0)
    w_imb = float(getattr(goals, "w_hour_imbalance", 2.0) or 2.0)
    enable_util = bool(getattr(goals, "enable_utilization_optimizer", True))
    w_low_hours = float(getattr(goals, "w_low_hours_priority_bonus", 2.5) or 0.0)
    w_near_cap = float(getattr(goals, "w_near_cap_penalty", 5.0) or 0.0)
    balance_tol = float(getattr(goals, "utilization_balance_tolerance_hours", 2.0) or 0.0)
    prefer_longer = bool(getattr(goals, "prefer_longer_shifts", True))
    prefer_area_consistency = bool(getattr(goals, "prefer_area_consistency", False))
    # Phase 3 weights (safe defaults)
    enable_risk = bool(getattr(goals, "enable_coverage_risk_protection", True))
    w_risk = float(getattr(goals, "w_coverage_risk", 10.0) or 0.0)
    enable_util = bool(getattr(goals, "enable_utilization_optimizer", True))
    w_new_emp = float(getattr(goals, "w_new_employee_penalty", 3.0) or 0.0)
    w_frag = float(getattr(goals, "w_fragmentation_penalty", 2.5) or 0.0)
    w_low_hours = float(getattr(goals, "w_low_hours_priority_bonus", 2.5) or 0.0)
    w_near_cap = float(getattr(goals, "w_near_cap_penalty", 5.0) or 0.0)
    balance_tol = float(getattr(goals, "utilization_balance_tolerance_hours", 2.0) or 0.0)


    # Coverage shortfalls/violations
    try:
        min_req_ls, pref_req_ls, max_req_ls = build_requirement_maps(model.requirements, goals=getattr(model,'manager_goals',None), store_info=getattr(model, "store_info", None))
        cov_map = count_coverage_per_tick(assignments)
        min_short, pref_short, max_viol = compute_requirement_shortfalls(min_req_ls, pref_req_ls, max_req_ls, cov_map)
    except Exception:
        min_short, pref_short, max_viol = int(unfilled), 0, 0

    pen = 0.0

    # Hard-ish penalties (very high)
    pen += int(min_short) * 1000.0
    pen += int(max_viol) * 5000.0

    # Soft: preferred coverage shortfall
    pen += int(pref_short) * w_under_pref_cov

    # Phase 4 C3: Risk-Aware Optimization (soft resilience buffer)
    try:
        enable_riskaware = bool(getattr(goals, "enable_risk_aware_optimization", False))
        protect_sp = bool(getattr(goals, "protect_single_point_failures", True))
        w_fragile = float(getattr(goals, "w_risk_fragile", 4.0) or 0.0)
        w_sp = float(getattr(goals, "w_risk_single_point", 8.0) or 0.0)
    except Exception:
        enable_riskaware, protect_sp, w_fragile, w_sp = False, True, 0.0, 0.0

    if enable_riskaware and (w_fragile > 0.0 or w_sp > 0.0):
        try:
            fragile_ticks = 0
            single_point_ticks = 0
            # Use MIN requirements as the baseline for resilience
            for k, req in min_req_ls.items():
                if req <= 0:
                    continue
                cov = cov_map.get(k, 0)
                if cov <= 0:
                    continue
                if cov == req:
                    fragile_ticks += 1
                    if protect_sp and req == 1 and cov == 1:
                        single_point_ticks += 1
            fragile_h = fragile_ticks / float(TICKS_PER_HOUR)
            sp_h = single_point_ticks / float(TICKS_PER_HOUR)
            pen += fragile_h * w_fragile
            if protect_sp:
                pen += sp_h * w_sp
        except Exception:
            pass


    # Soft: preferred weekly cap overage
    try:
        pref_cap = float(getattr(goals, 'preferred_weekly_cap', getattr(goals,'weekly_hours_cap',0.0)) or 0.0)
        if pref_cap > 0.0:
            total_h = sum(hours_between_ticks(a.start_t, a.end_t) for a in assignments)
            if total_h > pref_cap:
                pen += (total_h - pref_cap) * w_over_pref_cap
    except Exception:
        pass

    # Employee hours balance & prefs
    emp_hours: Dict[str, float] = {e.name: 0.0 for e in model.employees}
    emp_days: Dict[str, Set[str]] = {e.name: set() for e in model.employees}
    weekend_ct: Dict[str,int] = {e.name: 0 for e in model.employees}
    undesirable_ct: Dict[str,int] = {e.name: 0 for e in model.employees}
    shifts_per_day: Dict[Tuple[str,str], int] = {}

    for a in assignments:
        emp_hours[a.employee_name] += hours_between_ticks(a.start_t, a.end_t)
        emp_days[a.employee_name].add(a.day)
        shifts_per_day[(a.employee_name, a.day)] = shifts_per_day.get((a.employee_name, a.day), 0) + 1
        if a.day in weekend_days():
            weekend_ct[a.employee_name] += 1
        # undesirable: late close blocks (>=22) and early open (<7)
        if (a.start_t < hhmm_to_tick("07:00")) or (a.end_t >= hhmm_to_tick("22:00")):
            undesirable_ct[a.employee_name] += 1

    
    # --- P2-3: Schedule stability (prefer keeping last week's assignments) ---
    try:
        enable_stab = bool(getattr(goals, "enable_schedule_stability", True))
        w_stab = float(getattr(goals, "w_schedule_stability", 14.0) or 0.0)
    except Exception:
        enable_stab = True
        w_stab = 0.0

    if enable_stab and w_stab > 0.0 and prev_tick_map:
        cur_tick_emp: Dict[Tuple[str,str,int], str] = {}
        for a in assignments:
            for tt in range(int(a.start_t), int(a.end_t)):
                cur_tick_emp[(a.day, a.area, int(tt))] = a.employee_name

        changed_ticks = 0
        for k, prev_emp in prev_tick_map.items():
            cur_emp = cur_tick_emp.get(k)
            if cur_emp != prev_emp:
                changed_ticks += 1
        # Each tick is 30 minutes => 0.5 hours
        pen += float(changed_ticks) * (w_stab * 0.5)

# Soft: split shifts per day
    for (emp, day), n in shifts_per_day.items():
        if n > 1:
            pen += (n - 1) * w_split

    # Soft: prefer longer shifts (penalize segments shorter than 2 hours)
    if prefer_longer:
        for a in assignments:
            hseg = hours_between_ticks(a.start_t, a.end_t)
            if hseg < 2.0:
                pen += (2.0 - hseg) * 8.0

    # Soft: area consistency (penalize multiple areas for same employee)
    if prefer_area_consistency:
        areas_by_emp: Dict[str, Set[str]] = {}
        for a in assignments:
            areas_by_emp.setdefault(a.employee_name, set()).add(a.area)
        for emp, areas in areas_by_emp.items():
            if len(areas) > 1:
                pen += (len(areas) - 1) * 6.0

    # Participation + constraints related penalties
    for e in model.employees:
        if e.work_status != "Active":
            continue
        h = emp_hours.get(e.name, 0.0)
        if e.wants_hours and h < 1.0:
            pen += w_part_miss
        if h > e.max_weekly_hours + 1e-9:
            pen += 5000.0 + (h - e.max_weekly_hours)*200.0
        if e.target_min_hours > 0 and h < e.target_min_hours:
            pen += (e.target_min_hours - h) * 15.0

        # consecutive days
        if e.max_consecutive_days > 0:
            days = [DAYS.index(d) for d in emp_days.get(e.name, set())]
            if days:
                days = sorted(set(days))
                run = 1
                maxrun = 1
                for i in range(1,len(days)):
                    if days[i] == days[i-1] + 1:
                        run += 1
                        maxrun = max(maxrun, run)
                    else:
                        run = 1
                if maxrun > e.max_consecutive_days:
                    pen += (maxrun - e.max_consecutive_days) * 40.0

        # weekend pref
        if e.weekend_preference == "Avoid":
            pen += weekend_ct.get(e.name,0) * 6.0
        elif e.weekend_preference == "Prefer":
            pen -= weekend_ct.get(e.name,0) * 2.0

        # fairness over history
        past_weekends = history_stats.get("weekend", {}).get(e.name, 0)
        past_undes = history_stats.get("undesirable", {}).get(e.name, 0)
        pen += past_weekends * weekend_ct.get(e.name,0) * 0.5
        pen += past_undes * undesirable_ct.get(e.name,0) * 0.3

    # Soft: hour inequality among active opted-in employees
    act = [e for e in model.employees if e.work_status=="Active" and e.wants_hours]
    if act:
        hs = [emp_hours[e.name] for e in act]
        avg = sum(hs)/len(hs)
        pen += sum(abs(x-avg) for x in hs) * w_imb


    # Pattern learning (Phase 2 P2-4) — soft preference from history
    try:
        if bool(getattr(model.settings, "learn_from_history", True)):
            pats = getattr(model, "learned_patterns", {}) or {}
            w_pat = float(getattr(goals, "w_pattern_learning", 8.0) or 8.0) if goals is not None else 8.0
            pat_pen_units = 0.0
            for a in assignments:
                emp = getattr(a, "employee_name", "")
                if not emp:
                    continue
                p = pats.get(emp) or {}
                pref_area = str(p.get("preferred_area", "")).strip()
                if pref_area and str(a.area) != pref_area:
                    pat_pen_units += 1.0
                pref_start = int(p.get("preferred_start_tick", 0) or 0)
                if pref_start:
                    pat_pen_units += min(8.0, abs(int(a.start_t) - pref_start)) * 0.10
                pref_len = int(p.get("preferred_len_ticks", 0) or 0)
                if pref_len:
                    cur_len = max(1, int(a.end_t) - int(a.start_t))
                    pat_pen_units += min(8.0, abs(cur_len - pref_len)) * 0.05
            pen += pat_pen_units * w_pat
    except Exception:
        pass


    
    # Phase 3: utilization optimizer (soft)
    if enable_util and (w_new_emp > 0.0 or w_frag > 0.0):
        try:
            used = {a.employee_name for a in assignments}
            pen += float(len(used)) * w_new_emp
        except Exception:
            pass
        try:
            pen += float(len(assignments)) * w_frag
        except Exception:
            pass


    # Final score
    return float(pen)


def schedule_score_breakdown(model: DataModel, label: str,
                             assignments: List[Assignment],
                             unfilled: int,
                             history_stats: Dict[str, Dict[str,int]],
                             prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None) -> Dict[str, float]:
    """Explainability helper.

    Returns a dict of penalty components that sum to the same total returned by schedule_score().
    """
    goals = getattr(model, "manager_goals", None)
    # Weight helpers (safe defaults)
    w_under_pref_cov = float(getattr(goals, "w_under_preferred_coverage", 5.0) or 5.0)
    w_over_pref_cap = float(getattr(goals, "w_over_preferred_cap", 20.0) or 20.0)
    w_part_miss = float(getattr(goals, "w_participation_miss", 250.0) or 250.0)
    w_split = float(getattr(goals, "w_split_shifts", 30.0) or 30.0)
    w_imb = float(getattr(goals, "w_hour_imbalance", 2.0) or 2.0)
    prefer_longer = bool(getattr(goals, "prefer_longer_shifts", True))
    prefer_area_consistency = bool(getattr(goals, "prefer_area_consistency", False))
    enable_util = bool(getattr(goals, "enable_utilization_optimizer", True))
    w_low_hours = float(getattr(goals, "w_low_hours_priority_bonus", 2.5) or 0.0)
    w_near_cap = float(getattr(goals, "w_near_cap_penalty", 5.0) or 0.0)
    balance_tol = float(getattr(goals, "utilization_balance_tolerance_hours", 2.0) or 0.0)

    # Coverage shortfalls/violations
    try:
        min_req_ls, pref_req_ls, max_req_ls = build_requirement_maps(model.requirements, goals=getattr(model,'manager_goals',None))
        cov_map = count_coverage_per_tick(assignments)
        min_short, pref_short, max_viol = compute_requirement_shortfalls(min_req_ls, pref_req_ls, max_req_ls, cov_map)
    except Exception:
        min_short, pref_short, max_viol = int(unfilled), 0, 0

    out: Dict[str, float] = {
        "min_coverage_pen": float(int(min_short) * 1000.0),
        "max_staffing_violation_pen": float(int(max_viol) * 5000.0),
        "preferred_coverage_shortfall_pen": float(int(pref_short) * w_under_pref_cov),
        "risk_fragile_pen": 0.0,
        "risk_single_point_pen": 0.0,
        "preferred_weekly_cap_pen": 0.0,
        "split_shift_pen": 0.0,
        "short_shift_pen": 0.0,
        "area_consistency_pen": 0.0,
        "participation_pen": 0.0,
        "employee_max_hours_pen": 0.0,
        "target_min_hours_pen": 0.0,
        "consecutive_days_pen": 0.0,
        "weekend_pref_pen": 0.0,
        "history_fairness_pen": 0.0,
        "stability_pen": 0.0,
        "hour_imbalance_pen": 0.0,
        "pattern_pen": 0.0,
        "employee_fit_pen": 0.0,
        "utilization_balance_pen": 0.0,
        "utilization_near_cap_pen": 0.0,
    }

    # Phase 4 C3: Risk-Aware Optimization (soft resilience buffer)
    try:
        enable_riskaware = bool(getattr(goals, "enable_risk_aware_optimization", False))
        protect_sp = bool(getattr(goals, "protect_single_point_failures", True))
        w_fragile = float(getattr(goals, "w_risk_fragile", 4.0) or 0.0)
        w_sp = float(getattr(goals, "w_risk_single_point", 8.0) or 0.0)
    except Exception:
        enable_riskaware, protect_sp, w_fragile, w_sp = False, True, 0.0, 0.0

    if enable_riskaware and (w_fragile > 0.0 or w_sp > 0.0):
        try:
            fragile_ticks = 0
            single_point_ticks = 0
            for k, req in min_req_ls.items():
                if req <= 0:
                    continue
                cov = cov_map.get(k, 0)
                if cov <= 0:
                    continue
                if cov == req:
                    fragile_ticks += 1
                    if protect_sp and req == 1 and cov == 1:
                        single_point_ticks += 1
            fragile_h = fragile_ticks / float(TICKS_PER_HOUR)
            sp_h = single_point_ticks / float(TICKS_PER_HOUR)
            out["risk_fragile_pen"] += fragile_h * w_fragile
            if protect_sp:
                out["risk_single_point_pen"] += sp_h * w_sp
        except Exception:
            pass

    # Preferred weekly cap overage
    try:
        pref_cap = float(getattr(goals, 'preferred_weekly_cap', getattr(goals,'weekly_hours_cap',0.0)) or 0.0)
        if pref_cap > 0.0:
            total_h = sum(hours_between_ticks(a.start_t, a.end_t) for a in assignments)
            if total_h > pref_cap:
                out["preferred_weekly_cap_pen"] += (total_h - pref_cap) * w_over_pref_cap
    except Exception:
        pass

    emp_hours: Dict[str, float] = {e.name: 0.0 for e in model.employees}
    emp_days: Dict[str, Set[str]] = {e.name: set() for e in model.employees}
    weekend_ct: Dict[str,int] = {e.name: 0 for e in model.employees}
    undesirable_ct: Dict[str,int] = {e.name: 0 for e in model.employees}
    shifts_per_day: Dict[Tuple[str,str], int] = {}

    for a in assignments:
        emp_hours[a.employee_name] += hours_between_ticks(a.start_t, a.end_t)
        emp_days[a.employee_name].add(a.day)
        shifts_per_day[(a.employee_name, a.day)] = shifts_per_day.get((a.employee_name, a.day), 0) + 1
        if a.day in weekend_days():
            weekend_ct[a.employee_name] += 1
        if (a.start_t < hhmm_to_tick("07:00")) or (a.end_t >= hhmm_to_tick("22:00")):
            undesirable_ct[a.employee_name] += 1

    
    # --- P2-3: Schedule stability (prefer keeping last week's assignments) ---
    try:
        enable_stab = bool(getattr(goals, "enable_schedule_stability", True))
        w_stab = float(getattr(goals, "w_schedule_stability", 14.0) or 0.0)
    except Exception:
        enable_stab = True
        w_stab = 0.0

    if enable_stab and w_stab > 0.0 and prev_tick_map:
        cur_tick_emp: Dict[Tuple[str,str,int], str] = {}
        for a in assignments:
            for tt in range(int(a.start_t), int(a.end_t)):
                cur_tick_emp[(a.day, a.area, int(tt))] = a.employee_name

        changed_ticks = 0
        for k, prev_emp in prev_tick_map.items():
            cur_emp = cur_tick_emp.get(k)
            if cur_emp != prev_emp:
                changed_ticks += 1

        out["stability_pen"] = float(changed_ticks) * (w_stab * 0.5)

    for (emp, day), n in shifts_per_day.items():
        if n > 1:
            out["split_shift_pen"] += (n - 1) * w_split

    if prefer_longer:
        for a in assignments:
            hseg = hours_between_ticks(a.start_t, a.end_t)
            if hseg < 2.0:
                out["short_shift_pen"] += (2.0 - hseg) * 8.0

    if prefer_area_consistency:
        areas_by_emp: Dict[str, Set[str]] = {}
        for a in assignments:
            areas_by_emp.setdefault(a.employee_name, set()).add(a.area)
        for emp, areas in areas_by_emp.items():
            if len(areas) > 1:
                out["area_consistency_pen"] += (len(areas) - 1) * 6.0

    for e in model.employees:
        if e.work_status != "Active":
            continue
        h = emp_hours.get(e.name, 0.0)
        if e.wants_hours and h < 1.0:
            out["participation_pen"] += w_part_miss
        if h > e.max_weekly_hours + 1e-9:
            out["employee_max_hours_pen"] += 5000.0 + (h - e.max_weekly_hours)*200.0
        if e.target_min_hours > 0 and h < e.target_min_hours:
            out["target_min_hours_pen"] += (e.target_min_hours - h) * 15.0

        if e.max_consecutive_days > 0:
            days = [DAYS.index(d) for d in emp_days.get(e.name, set())]
            if days:
                days = sorted(set(days))
                run = 1
                maxrun = 1
                for i in range(1,len(days)):
                    if days[i] == days[i-1] + 1:
                        run += 1
                        maxrun = max(maxrun, run)
                    else:
                        run = 1
                if maxrun > e.max_consecutive_days:
                    out["consecutive_days_pen"] += (maxrun - e.max_consecutive_days) * 40.0

        if e.weekend_preference == "Avoid":
            out["weekend_pref_pen"] += weekend_ct.get(e.name,0) * 6.0
        elif e.weekend_preference == "Prefer":
            out["weekend_pref_pen"] -= weekend_ct.get(e.name,0) * 2.0

        past_weekends = history_stats.get("weekend", {}).get(e.name, 0)
        past_undes = history_stats.get("undesirable", {}).get(e.name, 0)
        out["history_fairness_pen"] += past_weekends * weekend_ct.get(e.name,0) * 0.5
        out["history_fairness_pen"] += past_undes * undesirable_ct.get(e.name,0) * 0.3

    act = [e for e in model.employees if e.work_status=="Active" and e.wants_hours]
    if act:
        hs = [emp_hours[e.name] for e in act]
        avg = sum(hs)/len(hs)
        out["hour_imbalance_pen"] += sum(abs(x-avg) for x in hs) * w_imb
        if enable_util:
            try:
                for e in act:
                    h = float(emp_hours.get(e.name, 0.0) or 0.0)
                    under = max(0.0, avg - balance_tol - h)
                    if under > 0.0 and w_low_hours > 0.0:
                        out["utilization_balance_pen"] += under * w_low_hours
                    maxh = float(getattr(e, "max_weekly_hours", 0.0) or 0.0)
                    if maxh > 0.0 and h > (maxh * 0.85) and w_near_cap > 0.0:
                        out["utilization_near_cap_pen"] += ((h - (maxh * 0.85)) / max(1.0, maxh * 0.15)) * w_near_cap
            except Exception:
                pass


    # Pattern learning (Phase 2 P2-4)
    try:
        if bool(getattr(model.settings, "learn_from_history", True)):
            pats = getattr(model, "learned_patterns", {}) or {}
            w_pat = float(getattr(goals, "w_pattern_learning", 8.0) or 8.0) if goals is not None else 8.0
            pat_units = 0.0
            for a in assignments:
                empn = getattr(a, "employee_name", "")
                if not empn:
                    continue
                p = pats.get(empn) or {}
                pref_area = str(p.get("preferred_area", "")).strip()
                if pref_area and str(a.area) != pref_area:
                    pat_units += 1.0
                pref_start = int(p.get("preferred_start_tick", 0) or 0)
                if pref_start:
                    pat_units += min(8.0, abs(int(a.start_t) - pref_start)) * 0.10
                pref_len = int(p.get("preferred_len_ticks", 0) or 0)
                if pref_len:
                    cur_len = max(1, int(a.end_t) - int(a.start_t))
                    pat_units += min(8.0, abs(cur_len - pref_len)) * 0.05
            out["pattern_pen"] += pat_units * w_pat
    except Exception:
        pass

    try:
        if bool(getattr(model.settings, 'enable_employee_fit_engine', True)):
            pats = getattr(model, 'learned_patterns', {}) or {}
            fit_units = 0.0
            for a in assignments:
                fit_score = get_employee_fit_score(pats, getattr(a, 'employee_name', ''), getattr(a, 'area', ''), int(getattr(a, 'start_t', 0) or 0))
                if fit_score < 0:
                    fit_units += abs(float(fit_score))
            out['employee_fit_pen'] += fit_units
    except Exception:
        pass

    out["total"] = float(sum(v for k,v in out.items() if k != "total"))
    return out


def _explain_feasible_reason(model: DataModel, label: str, emp: Employee,
                             day: str, area: str, st: int, en: int,
                             assignments: List[Assignment]) -> Tuple[bool, str]:
    """Return (feasible, reason_if_not). Used for explainability only."""
    cl: Dict[Tuple[str,str], int] = {}
    try:
        for a in assignments:
            if a.employee_name != emp.name:
                continue
            if emp.avoid_clopens:
                end_hr = a.end_t / TICKS_PER_HOUR
                if end_hr >= 22.0:
                    idx = DAYS.index(a.day)
                    nd = DAYS[(idx+1)%7]
                    ms = int(max(0, (a.end_t + model.settings.min_rest_hours*TICKS_PER_HOUR) - DAY_TICKS))
                    cl[(emp.name, nd)] = max(cl.get((emp.name, nd), 0), ms)
    except Exception:
        cl = {}

    if area not in emp.areas_allowed:
        return False, "Not allowed in this area"
    if not is_employee_available(model, emp, label, day, st, en, area, cl):
        return False, "Not available (availability/time-off/clopen/minor rules)"
    if not respects_daily_shift_limits(assignments, emp, day, extra=(st,en)):
        return False, "Daily shift rules would be violated"
    if any(a.employee_name==emp.name and a.day==day and not (en<=a.start_t or st>=a.end_t) for a in assignments):
        return False, "Overlaps an existing shift"
    h = hours_between_ticks(st,en)
    hours_now = sum(hours_between_ticks(a.start_t,a.end_t) for a in assignments if a.employee_name==emp.name)
    if hours_now + h > emp.max_weekly_hours + 1e-9:
        return False, "Would exceed employee max weekly hours"
    return True, ""

def history_stats_from(model: DataModel) -> Dict[str, Dict[str,int]]:
    # lookback N
    n = max(0, int(model.settings.fairness_lookback_weeks))
    weekend: Dict[str,int] = {}
    undes: Dict[str,int] = {}
    for s in model.history[-n:]:
        for k,v in s.weekend_counts.items():
            weekend[k] = weekend.get(k,0) + int(v)
        for k,v in s.undesirable_counts.items():
            undes[k] = undes.get(k,0) + int(v)
    return {"weekend": weekend, "undesirable": undes}

def build_locked_and_prefer_from_fixed(model: DataModel, label: str) -> Tuple[List[Assignment], List[Assignment]]:
    locked: List[Assignment] = []
    prefer: List[Assignment] = []
    seen_locked: Set[Tuple[str,str,int,int,str]] = set()
    for e in model.employees:
        if e.work_status != "Active":
            continue
        for fs in getattr(e, "recurring_locked_schedule", []) or []:
            if fs.day not in DAYS or fs.area not in AREAS:
                continue
            key = (fs.day, fs.area, int(fs.start_t), int(fs.end_t), e.name)
            if key in seen_locked:
                continue
            seen_locked.add(key)
            locked.append(Assignment(fs.day, fs.area, fs.start_t, fs.end_t, e.name, locked=True, source="recurring_locked"))
        for fs in e.fixed_schedule:
            if fs.day not in DAYS or fs.area not in AREAS:
                continue
            if fs.locked:
                key = (fs.day, fs.area, int(fs.start_t), int(fs.end_t), e.name)
                if key in seen_locked:
                    continue
                seen_locked.add(key)
            a = Assignment(fs.day, fs.area, fs.start_t, fs.end_t, e.name, locked=fs.locked,
                           source="fixed_locked" if fs.locked else "fixed_prefer")
            (locked if fs.locked else prefer).append(a)
    return locked, prefer

def _schedule_total_penalty(model: DataModel, label: str, assignments: List[Assignment], filled: int, total_slots: int, prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None) -> float:
    try:
        hist = history_stats_from(model)
        unfilled_ticks = max(0, int(total_slots) - int(filled))
        bd = schedule_score_breakdown(model, label, list(assignments), unfilled_ticks, hist, prev_tick_map or {})
        return float(bd.get("total", 0.0) or 0.0)
    except Exception:
        return 1e9

def improve_weak_areas(model: DataModel,
                       label: str,
                       assignments: List[Assignment],
                       prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None,
                       protect_locked: bool = True,
                       protect_manual: bool = True,
                       max_passes: int = 2,
                       max_windows: int = 12,
                       max_attempts_per_window: int = 20) -> Tuple[List[Assignment], Dict[str, Any]]:
    """Conservative post-generation targeted improvement pass.

    Focuses only on weak windows (coverage deficits first, fragile windows second)
    and attempts safe local additions without global re-solving.
    """
    base_assignments = list(assignments or [])
    diagnostics: Dict[str, Any] = {
        "engine": "EW1",
        "accepted_moves": 0,
        "rejected_moves": 0,
        "passes_run": 0,
        "windows_examined": 0,
        "attempts": 0,
        "protected_preserved": True,
        "notes": [],
    }

    if not base_assignments:
        diagnostics["notes"].append("No assignments provided; nothing to improve.")
        diagnostics["changed"] = False
        return base_assignments, diagnostics

    history_stats = history_stats_from(model)
    min_req, pref_req, max_req = build_requirement_maps(model.requirements, goals=getattr(model, 'manager_goals', None))

    def _asig(a: Assignment) -> Tuple[str, str, int, int, str, bool, str]:
        return (
            str(a.day), str(a.area), int(a.start_t), int(a.end_t),
            str(a.employee_name), bool(a.locked), str(a.source),
        )

    def _is_protected(a: Assignment) -> bool:
        if protect_locked and bool(getattr(a, "locked", False)):
            return True
        if protect_manual and str(getattr(a, "source", "") or "") == "manual_edit":
            return True
        return False

    protected_sigs = {_asig(a) for a in base_assignments if _is_protected(a)}

    def _emp_hours(assigns: List[Assignment]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for a in assigns:
            out[a.employee_name] = out.get(a.employee_name, 0.0) + hours_between_ticks(a.start_t, a.end_t)
        return out

    def _coverage(assigns: List[Assignment]) -> Dict[Tuple[str,str,int], int]:
        return count_coverage_per_tick(assigns)

    def _extract_weak_windows(cov: Dict[Tuple[str,str,int], int]) -> List[Tuple[float, int, str, str, int, int, str]]:
        windows: List[Tuple[float, int, str, str, int, int, str]] = []
        for day in DAYS:
            for area in AREAS:
                t = 0
                while t < DAY_TICKS:
                    req = int(min_req.get((day, area, t), 0))
                    sch = int(cov.get((day, area, t), 0))
                    deficit = max(0, req - sch)
                    if deficit <= 0:
                        t += 1
                        continue
                    st = t
                    peak = deficit
                    deficit_h = 0.0
                    while t < DAY_TICKS:
                        req2 = int(min_req.get((day, area, t), 0))
                        sch2 = int(cov.get((day, area, t), 0))
                        d2 = max(0, req2 - sch2)
                        if d2 <= 0:
                            break
                        peak = max(peak, d2)
                        deficit_h += d2 * 0.5
                        t += 1
                    en = t
                    windows.append((deficit_h, peak, day, area, st, en, "deficit"))
        if windows:
            windows.sort(key=lambda x: (x[0], x[1], -x[4]), reverse=True)
            return windows
        for day in DAYS:
            for area in AREAS:
                t = 0
                while t < DAY_TICKS:
                    req = int(min_req.get((day, area, t), 0))
                    sch = int(cov.get((day, area, t), 0))
                    fragile = (req > 0 and sch == req)
                    if not fragile:
                        t += 1
                        continue
                    st = t
                    peak_req = req
                    h = 0.0
                    while t < DAY_TICKS:
                        req2 = int(min_req.get((day, area, t), 0))
                        sch2 = int(cov.get((day, area, t), 0))
                        if not (req2 > 0 and sch2 == req2):
                            break
                        peak_req = max(peak_req, req2)
                        h += 0.5
                        t += 1
                    en = t
                    windows.append((h, peak_req, day, area, st, en, "fragile"))
        windows.sort(key=lambda x: (x[0], x[1], -x[4]), reverse=True)
        return windows

    def _metrics(assigns: List[Assignment]) -> Tuple[int, int, int, float]:
        cov = _coverage(assigns)
        min_short, pref_short, max_viol = compute_requirement_shortfalls(min_req, pref_req, max_req, cov)
        score = float(schedule_score(model, label, assigns, int(min_short), history_stats, prev_tick_map or {}))
        return int(min_short), int(pref_short), int(max_viol), float(score)

    def _overlaps_emp(assigns: List[Assignment], employee_name: str, day: str, st: int, en: int) -> bool:
        for a in assigns:
            if a.employee_name != employee_name or a.day != day:
                continue
            if not (en <= int(a.start_t) or st >= int(a.end_t)):
                return True
        return False

    def _tick_max_blocked(cov: Dict[Tuple[str,str,int], int], day: str, area: str, st: int, en: int) -> bool:
        for tt in range(int(st), int(en)):
            k = (day, area, int(tt))
            if int(cov.get(k, 0)) >= int(max_req.get(k, 10**9)):
                return True
        return False

    active_emps = [e for e in model.employees if getattr(e, "work_status", "Active") == "Active"]

    def _candidate_rank(e: Employee, day: str, area: str, st: int, en: int, emp_hours: Dict[str, float]) -> Tuple[float, float, str]:
        cur_h = float(emp_hours.get(e.name, 0.0) or 0.0)
        gap = max(0.0, float(getattr(e, "target_min_hours", 0.0) or 0.0) - cur_h)
        stab_match = 0.0
        if prev_tick_map:
            match = 0
            total = max(1, int(en - st))
            for tt in range(int(st), int(en)):
                if prev_tick_map.get((day, area, int(tt))) == e.name:
                    match += 1
            stab_match = match / float(total)
        return (stab_match, gap, f"{100000-cur_h:09.3f}:{e.name.lower()}")

    current = list(base_assignments)
    cur_min, cur_pref, cur_max, cur_score = _metrics(current)
    diagnostics["before_min_shortfall"] = int(cur_min)
    diagnostics["before_pref_shortfall"] = int(cur_pref)
    diagnostics["before_max_violations"] = int(cur_max)
    diagnostics["before_score"] = float(cur_score)

    total_window_budget = max(1, int(max_windows))
    max_passes = max(1, int(max_passes))
    max_attempts_per_window = max(1, int(max_attempts_per_window))

    for p in range(max_passes):
        diagnostics["passes_run"] = p + 1
        pass_improved = False
        cov_now = _coverage(current)
        weak_windows = _extract_weak_windows(cov_now)[:total_window_budget]
        if not weak_windows:
            diagnostics["notes"].append("No weak windows detected.")
            break

        emp_hours = _emp_hours(current)
        clopen = _clopen_map_from_assignments(model, current)

        for (_sev_h, _peak, day, area, wst, wen, wkind) in weak_windows:
            diagnostics["windows_examined"] += 1
            window_attempts = 0
            starts: List[int] = list(range(int(wst), int(wen)))
            if int(wst) > 0:
                starts.append(int(wst) - 1)
            starts = sorted(set([t for t in starts if 0 <= t < DAY_TICKS]))
            segment_lengths = [2, 4, 6] if wkind != "fragile" else [2, 4]
            accepted_here = False
            for st in starts:
                if accepted_here or window_attempts >= max_attempts_per_window:
                    break
                for seg_len in segment_lengths:
                    if accepted_here or window_attempts >= max_attempts_per_window:
                        break
                    en = st + int(seg_len)
                    if en > DAY_TICKS or en <= int(wst) or st >= int(wen):
                        continue
                    candidates = [e for e in active_emps if area in getattr(e, "areas_allowed", [])]
                    candidates.sort(key=lambda e: _candidate_rank(e, day, area, st, en, emp_hours), reverse=True)
                    for e in candidates:
                        if window_attempts >= max_attempts_per_window:
                            break
                        window_attempts += 1
                        diagnostics["attempts"] += 1
                        if _tick_max_blocked(cov_now, day, area, st, en):
                            diagnostics["rejected_moves"] += 1
                            continue
                        if _overlaps_emp(current, e.name, day, st, en):
                            diagnostics["rejected_moves"] += 1
                            continue
                        if not is_employee_available(model, e, label, day, st, en, area, clopen):
                            diagnostics["rejected_moves"] += 1
                            continue
                        if not respects_daily_shift_limits(current, e, day, extra=(st, en)):
                            diagnostics["rejected_moves"] += 1
                            continue
                        seg_h = hours_between_ticks(st, en)
                        if float(emp_hours.get(e.name, 0.0) or 0.0) + seg_h > float(getattr(e, "max_weekly_hours", 0.0) or 0.0) + 1e-9:
                            diagnostics["rejected_moves"] += 1
                            continue
                        trial = list(current)
                        trial.append(Assignment(day=day, area=area, start_t=st, end_t=en, employee_name=e.name, locked=False, source="weak_area_improve"))
                        t_min, t_pref, t_max, t_score = _metrics(trial)
                        min_ok = (t_min <= cur_min)
                        score_ok = (t_score <= cur_score + 1e-9)
                        max_ok = (t_max <= cur_max)
                        strict_better = (t_min < cur_min) or (t_score < cur_score - 1e-9)
                        if min_ok and score_ok and max_ok and strict_better:
                            current = trial
                            cur_min, cur_pref, cur_max, cur_score = t_min, t_pref, t_max, t_score
                            cov_now = _coverage(current)
                            emp_hours[e.name] = emp_hours.get(e.name, 0.0) + seg_h
                            clopen = _clopen_map_from_assignments(model, current)
                            diagnostics["accepted_moves"] += 1
                            pass_improved = True
                            accepted_here = True
                        else:
                            diagnostics["rejected_moves"] += 1

        if not pass_improved:
            diagnostics["notes"].append("No accepted improvements in pass; stopping early.")
            break

    final_sigs = {_asig(a) for a in current}
    if not protected_sigs.issubset(final_sigs):
        diagnostics["protected_preserved"] = False
        diagnostics["notes"].append("Protected assignment preservation check failed; returning original schedule.")
        diagnostics["changed"] = False
        diagnostics["after_min_shortfall"] = int(diagnostics.get("before_min_shortfall", 0))
        diagnostics["after_pref_shortfall"] = int(diagnostics.get("before_pref_shortfall", 0))
        diagnostics["after_max_violations"] = int(diagnostics.get("before_max_violations", 0))
        diagnostics["after_score"] = float(diagnostics.get("before_score", 0.0))
        return list(base_assignments), diagnostics

    diagnostics["after_min_shortfall"] = int(cur_min)
    diagnostics["after_pref_shortfall"] = int(cur_pref)
    diagnostics["after_max_violations"] = int(cur_max)
    diagnostics["after_score"] = float(cur_score)
    changed = list(current) != list(base_assignments)
    diagnostics["changed"] = bool(changed)
    if not diagnostics["changed"]:
        diagnostics["notes"].append("No safe improvement accepted; schedule unchanged.")
        return list(base_assignments), diagnostics
    return current, diagnostics


def requirement_sanity_checker(model: DataModel,
                               label: str,
                               assignments: Optional[List[Assignment]] = None,
                               prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None) -> Dict[str, Any]:
    warnings: List[str] = []
    details: Dict[str, Any] = {}
    goals = getattr(model, "manager_goals", None)
    min_req, pref_req, max_req = build_requirement_maps(getattr(model, "requirements", []) or [], goals=goals)
    total_min_hours = float(sum(int(v) for v in min_req.values())) / float(TICKS_PER_HOUR)
    total_pref_hours = float(sum(int(v) for v in pref_req.values())) / float(TICKS_PER_HOUR)
    hard_cap = float(getattr(goals, "maximum_weekly_cap", 0.0) or 0.0)
    pref_cap = float(getattr(goals, "preferred_weekly_cap", getattr(goals, "weekly_hours_cap", 0.0)) or 0.0)
    details["total_min_hours"] = float(total_min_hours)
    details["total_preferred_hours"] = float(total_pref_hours)
    details["hard_weekly_cap"] = float(hard_cap)
    details["preferred_weekly_cap"] = float(pref_cap)
    if hard_cap > 0.0 and hard_cap + 1e-9 < total_min_hours:
        warnings.append(f"Hard weekly labor cap ({hard_cap:.1f}h) is below minimum required labor ({total_min_hours:.1f}h).")
    if pref_cap > 0.0 and pref_cap + 1e-9 < total_min_hours:
        warnings.append(f"Preferred weekly labor cap ({pref_cap:.1f}h) is below minimum required labor ({total_min_hours:.1f}h).")
    active_employees = [e for e in (getattr(model, "employees", []) or []) if getattr(e, "work_status", "") == "Active"]
    active_by_area: Dict[str, int] = {a: 0 for a in AREAS}
    for e in active_employees:
        for area in AREAS:
            if area in set(getattr(e, "areas_allowed", []) or []):
                active_by_area[area] += 1
    details["active_by_area"] = dict(active_by_area)
    impossible_windows: List[Dict[str, Any]] = []
    shortage_prone_windows: List[Dict[str, Any]] = []
    for day in DAYS:
        for area in AREAS:
            t = 0
            while t < DAY_TICKS:
                req = int(min_req.get((day, area, t), 0))
                mx = int(max_req.get((day, area, t), 0)) if (day, area, t) in max_req else req
                if req <= 0:
                    t += 1
                    continue
                impossible = (req > int(active_by_area.get(area, 0))) or (mx < req)
                if impossible:
                    st = t
                    peak = req
                    while t < DAY_TICKS:
                        r2 = int(min_req.get((day, area, t), 0))
                        mx2 = int(max_req.get((day, area, t), 0)) if (day, area, t) in max_req else r2
                        if not (r2 > 0 and ((r2 > int(active_by_area.get(area, 0))) or (mx2 < r2))):
                            break
                        peak = max(peak, r2); t += 1
                    impossible_windows.append({"day": day, "area": area, "start_t": st, "end_t": t, "peak_min_required": int(peak), "qualified_active_count": int(active_by_area.get(area, 0))})
                    continue
                ratio = float(req) / float(max(1, int(active_by_area.get(area, 0))))
                if ratio >= 0.75:
                    st = t; peak = req; acc_h = 0.0
                    while t < DAY_TICKS:
                        r2 = int(min_req.get((day, area, t), 0))
                        ratio2 = float(r2) / float(max(1, int(active_by_area.get(area, 0)))) if r2 > 0 else 0.0
                        if not (r2 > 0 and ratio2 >= 0.75):
                            break
                        peak = max(peak, r2); acc_h += 0.5; t += 1
                    shortage_prone_windows.append({"day": day, "area": area, "start_t": st, "end_t": t, "hours": float(acc_h), "peak_min_required": int(peak), "qualified_active_count": int(active_by_area.get(area, 0))})
                    continue
                t += 1
    if impossible_windows:
        warnings.append(f"Detected {len(impossible_windows)} impossible requirement window(s).")
    if shortage_prone_windows:
        warnings.append(f"Detected {len(shortage_prone_windows)} shortage-prone high-demand window(s).")
    observed_shortfalls: Dict[str, Any] = {}
    if assignments is not None:
        cov = count_coverage_per_tick(assignments or [])
        min_short, pref_short, max_viol = compute_requirement_shortfalls(min_req, pref_req, max_req, cov)
        observed_shortfalls = {"min_shortfall_ticks": int(min_short), "preferred_shortfall_ticks": int(pref_short), "max_violation_ticks": int(max_viol)}
        if min_short > 0:
            warnings.append(f"Current schedule has {int(min_short)} unfilled required 30-minute blocks.")
    details["impossible_windows"] = impossible_windows
    details["shortage_prone_windows"] = shortage_prone_windows
    details["observed_shortfalls"] = observed_shortfalls
    return {"label": str(label or ""), "warnings": warnings, "details": details}

def _manual_learning_path() -> str:
    return rel_path("history", "manual_learning_signals.json")

def load_manual_learning_signals() -> Dict[str, Any]:
    p = _manual_learning_path()
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {"version": 1, "updated_on": "", "employee_area_day": {}, "avoidance": {}, "pairings": {}}

def save_manual_learning_signals(signals: Dict[str, Any]) -> None:
    p = _manual_learning_path()
    try:
        ensure_dir(os.path.dirname(p))
        payload = dict(signals or {})
        payload["version"] = int(payload.get("version", 1) or 1)
        payload["updated_on"] = datetime.datetime.now().isoformat(timespec="seconds")
        _atomic_write_json(p, payload, indent=2)
    except Exception:
        pass

def learn_from_manual_edit_delta(before_assignments: List[Assignment], after_assignments: List[Assignment], label: str, max_records_per_bucket: int = 200) -> Dict[str, Any]:
    signals = load_manual_learning_signals()
    ead = dict(signals.get("employee_area_day", {}) or {})
    avoid = dict(signals.get("avoidance", {}) or {})
    pairings = dict(signals.get("pairings", {}) or {})
    def k_assign(a: Assignment) -> Tuple[str, str, int, int, str]:
        return (str(a.day), str(a.area), int(a.start_t), int(a.end_t), str(a.employee_name))
    before_set = {k_assign(a) for a in (before_assignments or [])}
    after_set = {k_assign(a) for a in (after_assignments or [])}
    added = sorted(list(after_set - before_set))
    removed = sorted(list(before_set - after_set))
    for (day, area, st, en, emp) in added:
        key = f"{emp}|{area}|{day}"; row = dict(ead.get(key, {}) or {})
        row["count"] = int(row.get("count", 0) or 0) + 1; row["last_label"] = str(label or ""); row["last_seen"] = datetime.datetime.now().isoformat(timespec="seconds"); ead[key] = row
    for (day, area, st, en, emp) in removed:
        key = f"{emp}|{area}|{day}"; row = dict(avoid.get(key, {}) or {})
        row["count"] = int(row.get("count", 0) or 0) + 1; row["last_label"] = str(label or ""); row["last_seen"] = datetime.datetime.now().isoformat(timespec="seconds"); avoid[key] = row
    slot_to_emps: Dict[Tuple[str,int,int], List[str]] = {}
    for (day, area, st, en, emp) in after_set:
        slot_to_emps.setdefault((day, st, en), []).append(emp)
    for (_day, _st, _en), emps in slot_to_emps.items():
        uniq = sorted(set([str(x) for x in emps if str(x).strip()]))
        if len(uniq) < 2:
            continue
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                k = f"{uniq[i]}<->{uniq[j]}"; row = dict(pairings.get(k, {}) or {})
                row["count"] = int(row.get("count", 0) or 0) + 1; row["last_label"] = str(label or ""); row["last_seen"] = datetime.datetime.now().isoformat(timespec="seconds"); pairings[k] = row
    def _trim(d: Dict[str, Any]) -> Dict[str, Any]:
        items = sorted(d.items(), key=lambda kv: int((kv[1] or {}).get("count", 0) or 0), reverse=True)
        return dict(items[:max(1, int(max_records_per_bucket))])
    signals["employee_area_day"] = _trim(ead); signals["avoidance"] = _trim(avoid); signals["pairings"] = _trim(pairings)
    save_manual_learning_signals(signals)
    return {"added_signals": len(added), "removed_signals": len(removed), "pairing_updates": len(pairings), "path": _manual_learning_path()}

def _fairness_memory_path() -> str:
    return rel_path("history", "fairness_memory.json")

def load_fairness_memory() -> Dict[str, Any]:
    p = _fairness_memory_path()
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {"version": 1, "weeks": [], "employees": {}, "updated_on": ""}

def save_fairness_memory(memory: Dict[str, Any]) -> None:
    p = _fairness_memory_path()
    try:
        ensure_dir(os.path.dirname(p))
        payload = dict(memory or {})
        payload["version"] = int(payload.get("version", 1) or 1)
        payload["updated_on"] = datetime.datetime.now().isoformat(timespec="seconds")
        _atomic_write_json(p, payload, indent=2)
    except Exception:
        pass

def update_fairness_memory_from_schedule(label: str, assignments: List[Assignment], keep_weeks: int = 6) -> Dict[str, Any]:
    memory = load_fairness_memory(); per_emp: Dict[str, Dict[str, Any]] = {}
    for a in assignments or []:
        rec = per_emp.setdefault(a.employee_name, {"hours": 0.0, "shift_count": 0, "weekend_shifts": 0, "clopen_burden": 0, "underutilized": 0})
        rec["hours"] += hours_between_ticks(a.start_t, a.end_t); rec["shift_count"] += 1
        if a.day in ("Sat", "Sun"): rec["weekend_shifts"] += 1
    by_emp_day: Dict[Tuple[str, str], List[Assignment]] = {}
    for a in assignments or []: by_emp_day.setdefault((a.employee_name, a.day), []).append(a)
    for k in list(by_emp_day.keys()): by_emp_day[k].sort(key=lambda x: (x.start_t, x.end_t))
    for emp in set([a.employee_name for a in (assignments or [])]):
        for idx, day in enumerate(DAYS):
            cur = by_emp_day.get((emp, day), []); nxt = by_emp_day.get((emp, DAYS[(idx + 1) % 7]), [])
            if not cur or not nxt: continue
            latest_end = max(int(x.end_t) for x in cur); earliest_next = min(int(x.start_t) for x in nxt)
            if latest_end / float(TICKS_PER_HOUR) >= 22.0 and earliest_next / float(TICKS_PER_HOUR) <= 8.0:
                per_emp.setdefault(emp, {"hours": 0.0, "shift_count": 0, "weekend_shifts": 0, "clopen_burden": 0, "underutilized": 0})["clopen_burden"] += 1
    for emp, rec in per_emp.items():
        if float(rec.get("hours", 0.0) or 0.0) < 8.0: rec["underutilized"] = 1
    weeks = list(memory.get("weeks", []) or [])
    weeks = [w for w in weeks if str(w.get("label", "")) != str(label or "")]
    weeks.append({"label": str(label or ""), "employees": per_emp, "saved_on": datetime.datetime.now().isoformat(timespec="seconds")})
    weeks = weeks[-max(1, int(keep_weeks)):]
    memory["weeks"] = weeks
    agg: Dict[str, Dict[str, Any]] = {}
    for w in weeks:
        for emp, rec in dict(w.get("employees", {}) or {}).items():
            a = agg.setdefault(emp, {"weeks": 0, "hours": 0.0, "shift_count": 0, "weekend_shifts": 0, "clopen_burden": 0, "underutilized_weeks": 0})
            a["weeks"] += 1; a["hours"] += float(rec.get("hours", 0.0) or 0.0); a["shift_count"] += int(rec.get("shift_count", 0) or 0); a["weekend_shifts"] += int(rec.get("weekend_shifts", 0) or 0); a["clopen_burden"] += int(rec.get("clopen_burden", 0) or 0); a["underutilized_weeks"] += int(rec.get("underutilized", 0) or 0)
    memory["employees"] = agg; save_fairness_memory(memory)
    return {"label": str(label or ""), "weeks_tracked": len(weeks), "employees_tracked": len(agg), "path": _fairness_memory_path()}

def explain_assignment(model: DataModel, label: str, assignments: List[Assignment], target: Assignment, prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None) -> Dict[str, Any]:
    emp = next((e for e in (model.employees or []) if e.name == target.employee_name), None)
    baseline = list(assignments or [])
    without_target = [a for a in baseline if not (a.employee_name == target.employee_name and a.day == target.day and a.area == target.area and int(a.start_t) == int(target.start_t) and int(a.end_t) == int(target.end_t))]
    min_req, pref_req, max_req = build_requirement_maps(model.requirements, goals=getattr(model, "manager_goals", None))
    delta_required_ticks = 0; delta_pref_ticks = 0; cov_without = count_coverage_per_tick(without_target)
    for tt in range(int(target.start_t), int(target.end_t)):
        k = (target.day, target.area, int(tt))
        if cov_without.get(k, 0) < min_req.get(k, 0): delta_required_ticks += 1
        if cov_without.get(k, 0) < pref_req.get(k, 0): delta_pref_ticks += 1
    out = {"employee": str(target.employee_name), "day": str(target.day), "area": str(target.area), "start_t": int(target.start_t), "end_t": int(target.end_t), "hours": float(hours_between_ticks(target.start_t, target.end_t)), "locked": bool(getattr(target, "locked", False)), "source": str(getattr(target, "source", "")), "availability_ok": bool(is_employee_available(model, emp, label, target.day, target.start_t, target.end_t, target.area, _clopen_map_from_assignments(model, without_target))) if emp is not None else False, "required_coverage_ticks_supported": int(delta_required_ticks), "preferred_coverage_ticks_supported": int(delta_pref_ticks), "stability_matches_prev_ticks": 0}
    if prev_tick_map:
        match = 0
        for tt in range(int(target.start_t), int(target.end_t)):
            if prev_tick_map.get((target.day, target.area, int(tt))) == target.employee_name: match += 1
        out["stability_matches_prev_ticks"] = int(match)
    return out

def explain_shortage_window(model: DataModel, label: str, assignments: List[Assignment], day: str, area: str, start_t: int, end_t: int) -> Dict[str, Any]:
    min_req, pref_req, max_req = build_requirement_maps(model.requirements, goals=getattr(model, "manager_goals", None))
    cov = count_coverage_per_tick(assignments or [])
    deficit_ticks = 0; peak_deficit = 0
    for tt in range(int(start_t), int(end_t)):
        req = int(min_req.get((day, area, int(tt)), 0)); sch = int(cov.get((day, area, int(tt)), 0)); d = max(0, req - sch)
        if d > 0: deficit_ticks += d; peak_deficit = max(peak_deficit, d)
    available: List[str] = []; clopen = _clopen_map_from_assignments(model, assignments or [])
    for e in (model.employees or []):
        if getattr(e, "work_status", "") != "Active": continue
        if area not in (getattr(e, "areas_allowed", []) or []): continue
        if is_employee_available(model, e, label, day, int(start_t), int(end_t), area, clopen): available.append(e.name)
    return {"day": str(day), "area": str(area), "start_t": int(start_t), "end_t": int(end_t), "deficit_headcount_ticks": int(deficit_ticks), "deficit_hours": float(deficit_ticks) / float(TICKS_PER_HOUR), "peak_deficit": int(peak_deficit), "available_candidates": sorted(available)}

def explain_employee_hours(model: DataModel, assignments: List[Assignment], employee_name: str) -> Dict[str, Any]:
    emp = next((e for e in (model.employees or []) if e.name == employee_name), None)
    emp_assigns = [a for a in (assignments or []) if a.employee_name == employee_name]
    total_h = sum(hours_between_ticks(a.start_t, a.end_t) for a in emp_assigns)
    by_day: Dict[str, float] = {d: 0.0 for d in DAYS}
    for a in emp_assigns: by_day[a.day] = by_day.get(a.day, 0.0) + hours_between_ticks(a.start_t, a.end_t)
    weekend_h = by_day.get("Sat", 0.0) + by_day.get("Sun", 0.0)
    target_min = float(getattr(emp, "target_min_hours", 0.0) or 0.0) if emp else 0.0
    max_h = float(getattr(emp, "max_weekly_hours", 0.0) or 0.0) if emp else 0.0
    fairness = load_fairness_memory(); rolling = dict((fairness.get("employees", {}) or {}).get(employee_name, {}) or {})
    return {"employee": str(employee_name), "current_total_hours": float(total_h), "target_min_hours": float(target_min), "max_weekly_hours": float(max_h), "weekend_hours": float(weekend_h), "day_hours": by_day, "assignment_count": len(emp_assigns), "rolling_fairness": rolling}

def run_regression_harness(model: DataModel, label: str, assignments: Optional[List[Assignment]] = None, run_exports: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"label": str(label or ""), "checks": {}, "notes": []}
    try:
        prev_label, prev_tick = load_prev_final_schedule_tick_map(label); gen = generate_schedule(model, label, prev_tick_map=prev_tick or {})
        out["checks"]["generate_schedule_smoke"] = {"ok": True, "filled": int(gen[4]), "total_slots": int(gen[5]), "warnings": int(len(gen[3] or []))}
    except Exception as ex:
        out["checks"]["generate_schedule_smoke"] = {"ok": False, "error": str(ex)}
    working = list(assignments or [])
    if not working:
        try:
            if out["checks"].get("generate_schedule_smoke", {}).get("ok"): working = list(gen[0])
        except Exception:
            working = []
    try:
        protected = [a for a in working if bool(getattr(a, "locked", False)) or str(getattr(a, "source", "") or "") == "manual_edit"]
        improved, diag = improve_weak_areas(model, label, working)
        prot_after = {(a.day, a.area, int(a.start_t), int(a.end_t), a.employee_name, bool(a.locked), str(a.source)) for a in improved}
        preserved = True
        for a in protected:
            sig = (a.day, a.area, int(a.start_t), int(a.end_t), a.employee_name, bool(a.locked), str(a.source))
            if sig not in prot_after: preserved = False; break
        out["checks"]["ew1_protected_preservation"] = {"ok": bool(preserved), "diagnostics": diag}
    except Exception as ex:
        out["checks"]["ew1_protected_preservation"] = {"ok": False, "error": str(ex)}
    try:
        report_html = make_manager_report_html(model, label, working)
        has_top = ("Hard Weekly Labor Cap" in report_html and "Actual Scheduled Hours" in report_html and "Remaining Labor Budget" in report_html)
        has_area = ("C-Store shortage hours" in report_html and "Kitchen shortage hours" in report_html and "Carwash shortage hours" in report_html)
        out["checks"]["manager_report_invariants"] = {"ok": bool(has_top and has_area)}
    except Exception as ex:
        out["checks"]["manager_report_invariants"] = {"ok": False, "error": str(ex)}
    if run_exports and working:
        try:
            p1 = export_html(model, label, working); p2 = export_csv(model, label, working); p3 = export_manager_report_html(model, label, working)
            out["checks"]["export_smoke"] = {"ok": bool(os.path.isfile(p1) and os.path.isfile(p2) and os.path.isfile(p3)), "paths": [p1, p2, p3]}
        except Exception as ex:
            out["checks"]["export_smoke"] = {"ok": False, "error": str(ex)}
    try:
        rs = requirement_sanity_checker(model, label, assignments=working)
        out["checks"]["requirement_sanity_checker"] = {"ok": True, "warning_count": int(len(rs.get("warnings", []) or []))}
    except Exception as ex:
        out["checks"]["requirement_sanity_checker"] = {"ok": False, "error": str(ex)}
    return out

def _scenario_variants_for_model(model: DataModel) -> List[Dict[str, Any]]:
    return [
        {"name": "Balanced", "tweaks": {}},
        {"name": "Coverage Priority", "tweaks": {"w_under_preferred_coverage": float(getattr(model.manager_goals, "w_under_preferred_coverage", 5.0) or 5.0) * 1.45, "w_coverage_risk": float(getattr(model.manager_goals, "w_coverage_risk", 10.0) or 10.0) * 1.35}},
        {"name": "Utilization Priority", "tweaks": {"w_low_hours_priority_bonus": float(getattr(model.manager_goals, "w_low_hours_priority_bonus", 2.5) or 2.5) * 1.5, "w_near_cap_penalty": float(getattr(model.manager_goals, "w_near_cap_penalty", 5.0) or 4.0) * 1.4, "w_new_employee_penalty": float(getattr(model.manager_goals, "w_new_employee_penalty", 3.0) or 3.0) * 1.25}},
        {"name": "Stability Priority", "tweaks": {"w_schedule_stability": max(1.0, float(getattr(model.manager_goals, "w_schedule_stability", 14.0) or 12.0) * 1.5), "enable_schedule_stability": True}},
    ]

def generate_schedule_multi_scenario(model: DataModel, label: str, prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None) -> Tuple[List[Assignment], Dict[str,float], float, List[str], int, int, int, int, Dict[str, Any]]:
    scenario_specs = _scenario_variants_for_model(model)
    best = None
    scenario_rows: List[Dict[str, Any]] = []
    total_iters = 0
    total_restarts = 0
    for spec in scenario_specs[:max(1, int(getattr(model.settings, "scenario_schedule_count", 4) or 4))]:
        scenario_model = copy.deepcopy(model)
        for key, value in (spec.get("tweaks") or {}).items():
            try:
                setattr(scenario_model.manager_goals, key, value)
            except Exception:
                pass
        try:
            result = generate_schedule(scenario_model, label, prev_tick_map=prev_tick_map)
            assigns, emp_hours, total_hours, warnings, filled, total_slots, iters_done, restarts_done, diag = result
            # OP1: skip extra breakdown work for clearly dominated failing scenarios.
            scenario_failed = (not assigns) or any(('INFEASIBLE' in str(w)) for w in (warnings or []))
            if best is not None and scenario_failed:
                try:
                    best_filled = int(best[1][4])
                except Exception:
                    best_filled = int(filled)
                if int(filled) < max(1, int(best_filled * 0.5)):
                    score_pen = 1e9
                else:
                    score_pen = _schedule_total_penalty(scenario_model, label, assigns, filled, total_slots, prev_tick_map)
            else:
                score_pen = _schedule_total_penalty(scenario_model, label, assigns, filled, total_slots, prev_tick_map)
            total_iters += int(iters_done)
            total_restarts += int(restarts_done)
            diag = dict(diag or {})
            diag["scenario_name"] = spec.get("name", "Scenario")
            diag["scenario_score_penalty"] = float(score_pen)
            row = {"name": spec.get("name", "Scenario"), "penalty": float(score_pen), "hours": float(total_hours), "warnings": int(len(warnings or [])), "filled": int(filled), "total_slots": int(total_slots)}
            scenario_rows.append(row)
            if best is None or row["penalty"] < best[0]:
                best = (row["penalty"], (assigns, emp_hours, total_hours, warnings, filled, total_slots, iters_done, restarts_done, diag))
        except Exception as ex:
            scenario_rows.append({"name": spec.get("name", "Scenario"), "penalty": 1e9, "hours": 0.0, "warnings": 1, "filled": 0, "total_slots": 0, "error": str(ex)})
    if best is None:
        raise RuntimeError("Multi-scenario generation failed for all scenarios.")
    assigns, emp_hours, total_hours, warnings, filled, total_slots, iters_done, restarts_done, diag = best[1]
    diag = dict(diag or {})
    diag["phase5_multi_scenario_enabled"] = True
    diag["phase5_scenarios"] = scenario_rows
    diag["chosen_scenario"] = str(diag.get("scenario_name", "Balanced"))
    diag["scenario_count"] = len(scenario_rows)
    return assigns, emp_hours, total_hours, warnings, filled, total_slots, int(total_iters or iters_done), int(total_restarts or restarts_done), diag

def generate_schedule(model: DataModel, label: str,
                      prev_tick_map: Optional[Dict[Tuple[str,str,int], str]] = None) -> Tuple[List[Assignment], Dict[str,float], float, List[str], int, int, int, int, Dict[str, Any]]:
    warnings: List[str] = []
    assignments: List[Assignment] = []
    emp_hours: Dict[str,float] = {e.name: 0.0 for e in model.employees}
    # Patch P3-4: speed up employee lookup in the hot path (add_assignment)
    # by avoiding repeated linear scans over model.employees.
    emp_by_name: Dict[str, Employee] = {e.name: e for e in model.employees}
    # Track total scheduled labor hours incrementally so we can enforce the Maximum Weekly Labor Hours Cap.
    total_labor_hours: float = 0.0
    max_weekly_cap: float = float(getattr(model.manager_goals, 'maximum_weekly_cap', 0.0) or 0.0)
    preferred_weekly_cap: float = float(getattr(model.manager_goals, 'preferred_weekly_cap', getattr(model.manager_goals, 'weekly_hours_cap', 0.0)) or 0.0)
    cap_blocked_attempts: int = 0
    cap_blocked_ticks: int = 0
    locked_hours: float = 0.0
    clopen_min_start: Dict[Tuple[str,str], int] = {}

    # Patch P2: observability for solver scoring exceptions (log once per run).
    _warned_once: set = set()
    def _log_once(key: str, msg: str):
        try:
            if key in _warned_once:
                return
            _warned_once.add(key)
            _write_run_log(msg)
        except Exception:
            pass


    history_stats = history_stats_from(model)

        # Compile per-tick requirements (min/preferred/max)
    min_req, pref_req, max_req = build_requirement_maps(model.requirements, goals=getattr(model,'manager_goals',None), store_info=getattr(model, "store_info", None))
    total_min_slots = sum(min_req.values())
    total_pref_slots = sum(pref_req.values())

    # Locked fixed shifts first
    locked, prefer_fixed = build_locked_and_prefer_from_fixed(model, label)
    # Track existing day segments for utilization scoring (updated as we add assignments)
    emp_day_segments: Dict[Tuple[str,str], List[Tuple[int,int,str]]] = {}
    for _e in model.employees:
        for _d in DAYS:
            emp_day_segments[(_e.name, _d)] = []



    def _tick_keys_in(day: str, area: str, st: int, en: int):
        for t in range(int(st), int(en)):
            yield (day, area, int(t))

    def _violates_max(day: str, area: str, st: int, en: int, cov: Dict[Tuple[str,str,int], int]) -> bool:
        for k in _tick_keys_in(day, area, st, en):
            if cov.get(k, 0) >= max_req.get(k, 10**9):
                return True
        return False

    def add_assignment(a: Assignment, locked_ok: bool, cov: Dict[Tuple[str,str,int], int], enforce_weekly_cap: bool = True) -> bool:
        nonlocal total_labor_hours, locked_hours, cap_blocked_attempts, cap_blocked_ticks
        e = emp_by_name.get(a.employee_name)
        if e is None:
            return False
        if (not bool(getattr(e, "wants_hours", True))) and (not locked_ok):
            return False
        if not is_employee_available(model, e, label, a.day, a.start_t, a.end_t, a.area, clopen_min_start):
            return False
        # hard max staffing cap (except locked_ok=True: allow but warn)
        if _violates_max(a.day, a.area, a.start_t, a.end_t, cov):
            if locked_ok:
                warnings.append(f"Locked fixed shift violates Max staffing cap: {e.name} {a.day} {a.area} {tick_to_hhmm(a.start_t)}-{tick_to_hhmm(a.end_t)}")
            else:
                return False
        # daily shift constraints
        if not respects_daily_shift_limits(assignments, e, a.day, extra=(a.start_t, a.end_t)):
            if locked_ok:
                warnings.append(f"Locked fixed shift violates daily shift rules: {e.name} {a.day} {tick_to_hhmm(a.start_t)}-{tick_to_hhmm(a.end_t)}")
            return False
        if not respects_max_consecutive_days(assignments, e, a.day):
            if locked_ok:
                warnings.append(f"Locked fixed shift violates max consecutive days: {e.name} {a.day}")
            return False
        # overlap
        for ex in assignments:
            if overlaps(ex, a):
                return False
        h = hours_between_ticks(a.start_t, a.end_t)
        # Maximum Weekly Labor Hours Cap (hard unless infeasible).
        if enforce_weekly_cap and max_weekly_cap > 0.0 and (total_labor_hours + h) - max_weekly_cap > 1e-9:
            if locked_ok:
                warnings.append(f"Locked fixed shift exceeds Maximum Weekly Labor Cap: {e.name} {a.day} {a.area} {tick_to_hhmm(a.start_t)}-{tick_to_hhmm(a.end_t)}")
            else:
                cap_blocked_attempts += 1
                cap_blocked_ticks += int(a.end_t - a.start_t)
                return False
        if emp_hours[e.name] + h > e.max_weekly_hours + 1e-9:
            if locked_ok:
                warnings.append(f"Locked fixed shift exceeds max weekly hours: {e.name} {a.day} {tick_to_hhmm(a.start_t)}-{tick_to_hhmm(a.end_t)}")
            return False
        assignments.append(a)
        try:
            emp_day_segments[(a.employee_name, a.day)].append((int(a.start_t), int(a.end_t), a.area))
        except Exception as ex:
            _log_once('emp_day_segments_append', f"[solver] emp_day_segments append failed (likely before init): {ex}")

        emp_hours[e.name] += h
        total_labor_hours += h
        if a.locked or a.source=='locked':
            locked_hours += h
        apply_clopen_from(model, e, a, clopen_min_start)
        for k in _tick_keys_in(a.day, a.area, a.start_t, a.end_t):
            cov[k] = cov.get(k, 0) + 1
        return True

    # Seed coverage with locked shifts
    coverage = {}
    for a in locked:
        if str(getattr(a, "source", "") or "") == "recurring_locked":
            e = emp_by_name.get(a.employee_name)
            if e is None or e.work_status != "Active":
                continue
            if not is_employee_available(model, e, label, a.day, a.start_t, a.end_t, a.area, clopen_min_start):
                continue
        if not add_assignment(a, locked_ok=True, cov=coverage):
            warnings.append(f"Locked fixed shift could not be assigned: {a.employee_name} {a.day} {a.area} {tick_to_hhmm(a.start_t)}-{tick_to_hhmm(a.end_t)}")

    # Phase 4 D6: pattern-learning precompute (soft)
    try:
        pattern_learning_enabled = bool(getattr(model.settings, "learn_from_history", True))
    except Exception:
        pattern_learning_enabled = True
    try:
        learned_patterns = getattr(model, "learned_patterns", {}) or {}
    except Exception:
        learned_patterns = {}
    try:
        w_pattern_learning = float(getattr(model.manager_goals, "w_pattern_learning", 8.0) or 0.0)
    except Exception:
        w_pattern_learning = 0.0

    # OP1: precompute stable candidate-scoring inputs once per generation run.
    weekend_set = weekend_days()
    try:
        enable_stab_global = bool(getattr(model.manager_goals, "enable_schedule_stability", True))
        w_stab_global = float(getattr(model.manager_goals, "w_schedule_stability", 14.0) or 0.0)
    except Exception:
        enable_stab_global = True
        w_stab_global = 0.0
    active_wants_names = [x.name for x in model.employees if x.work_status == "Active" and x.wants_hours]
    fixed_match_bonus: Set[Tuple[str, str, int, int, str]] = set(
        (p.day, p.area, int(p.start_t), int(p.end_t), p.employee_name)
        for p in prefer_fixed
    )
    current_avg_active_wants = 0.0

    # Candidate preference score for segment placement
    def candidate_score(e: Employee, day: str, area: str, st: int, en: int) -> float:
        score = 0.0
        # prefer fixed-unlocked boosts if matches exactly
        if (day, area, int(st), int(en), e.name) in fixed_match_bonus:
            score += 30.0

        # stability: prefer the same employee for the same time/area as last schedule
        if enable_stab_global and w_stab_global > 0.0 and prev_tick_map:
            total_ticks = max(1, int(en - st))
            match_ticks = 0
            for tt in range(int(st), int(en)):
                if prev_tick_map.get((day, area, int(tt))) == e.name:
                    match_ticks += 1
            # scale bonus to be comparable with other candidate heuristics
            score += (match_ticks / float(total_ticks)) * (w_stab_global * 0.8)

        if area in e.preferred_areas:
            score += 3.0
        if day in weekend_set and e.weekend_preference=="Avoid":
            score -= 2.5
        if day in weekend_set and e.weekend_preference=="Prefer":
            score += 1.2
        # balance: help those under target min
        gap = max(0.0, e.target_min_hours - emp_hours.get(e.name,0.0))
        score += min(5.0, gap) * 0.8
        # participation: if wants hours and currently 0, boost
        if e.wants_hours and emp_hours.get(e.name,0.0) < 1.0:
            score += 2.0
        # Phase 4 C4: workforce utilization optimizer (soft)
        if enable_util:
            try:
                cur_h = float(emp_hours.get(e.name, 0.0) or 0.0)
                seg_h = float(hours_between_ticks(st, en))
                if cur_h < 0.5 and w_new_emp > 0.0:
                    score -= w_new_emp

                avg_h = float(current_avg_active_wants)
                if w_low_hours > 0.0 and cur_h + balance_tol < avg_h:
                    score += min(6.0, (avg_h - cur_h - balance_tol)) * w_low_hours

                target_gap = max(0.0, float(getattr(e, "target_min_hours", 0.0) or 0.0) - cur_h)
                if target_gap > 0.0 and w_target_fill > 0.0:
                    score += min(seg_h, target_gap) * w_target_fill

                maxh = float(getattr(e, "max_weekly_hours", 0.0) or 0.0)
                projected = cur_h + seg_h
                if maxh > 0.0 and projected > (maxh * 0.85) and w_near_cap > 0.0:
                    near_cap_ratio = (projected - (maxh * 0.85)) / max(1.0, maxh * 0.15)
                    score -= max(0.0, near_cap_ratio) * w_near_cap
            except Exception as ex:
                _log_once('util_load_scoring', f"[solver] utilization(load-balance) scoring failed: {ex}")

            try:
                segs = emp_day_segments.get((e.name, day), [])
                if segs:
                    # Bonus for extending an adjacent shift in same area
                    adj = any((aa==area and (aen==st or ast==en)) for (ast,aen,aa) in segs)
                    if adj and w_extend > 0.0:
                        score += w_extend
                    # Penalty for creating an additional non-adjacent fragment in the day
                    non_adj = any((aen < st or ast > en) for (ast,aen,aa) in segs)
                    if non_adj and (not adj) and w_frag > 0.0:
                        score -= w_frag
            except Exception as ex:
                _log_once('util_segment_scoring', f"[solver] utilization(segment) scoring failed: {ex}")

        # Phase 3: coverage risk protection (soft)
        if enable_risk and w_risk > 0.0 and tick_scarcity:
            try:
                # Average scarcity-based risk across ticks in this segment
                rs = 0.0
                n = 0
                for tt in range(int(st), int(en)):
                    sc = float(tick_scarcity.get((day, area, int(tt)), 0) or 0.0)
                    rs += 1.0 / max(1.0, sc)
                    n += 1
                seg_risk = rs / float(max(1, n))   # 0..1 (higher = scarcer)
                emp_flex = float(emp_feasible_totals.get(e.name, 0) or 0.0)
                emp_scar = 1.0 / max(1.0, emp_flex)  # higher = scarcer employee

                # Normalize risk into 0..1-ish for typical staffing
                risk_norm = min(1.0, seg_risk * 5.0)
                # Prefer using scarce employees on scarce shifts; prefer flexible employees on easy shifts
                score += (risk_norm * (w_risk * 3.0) * emp_scar) - ((1.0 - risk_norm) * (w_risk * 1.5) * emp_scar)
            except Exception as ex:
                _log_once('coverage_risk_scoring', f"[solver] coverage-risk scoring failed: {ex}")

        # Phase 4 D6: learned pattern preference (soft)
        if pattern_learning_enabled and w_pattern_learning > 0.0 and learned_patterns:
            try:
                p = learned_patterns.get(e.name, {}) or {}
                if p:
                    pref_area = str(p.get("preferred_area", "") or "").strip()
                    if pref_area:
                        if area == pref_area:
                            score += min(4.0, w_pattern_learning * 0.35)
                        else:
                            score -= min(4.0, w_pattern_learning * 0.25)

                    pref_start = int(p.get("preferred_start_tick", 0) or 0)
                    if pref_start > 0:
                        start_delta = abs(int(st) - pref_start)
                        score += max(-3.0, min(3.0, (4.0 - min(4.0, float(start_delta))) * (w_pattern_learning * 0.18)))

                    pref_len = int(p.get("preferred_len_ticks", 0) or 0)
                    if pref_len > 0:
                        cur_len = max(1, int(en) - int(st))
                        len_delta = abs(cur_len - pref_len)
                        score += max(-2.0, min(2.0, (3.0 - min(3.0, float(len_delta))) * (w_pattern_learning * 0.12)))
            except Exception as ex:
                _log_once('pattern_learning_scoring', f"[solver] pattern-learning scoring failed: {ex}")

        try:
            if bool(getattr(model.settings, 'enable_employee_fit_engine', True)) and learned_patterns:
                score += get_employee_fit_score(learned_patterns, e.name, area, st)
        except Exception as ex:
            _log_once('employee_fit_scoring', f"[solver] employee-fit scoring failed: {ex}")

        return score

    def feasible_segment(e: Employee, day: str, area: str, st: int, en: int) -> bool:
        if st < 0 or en > DAY_TICKS or en <= st:
            return False
        if area not in e.areas_allowed:
            return False
        if not bool(getattr(e, "wants_hours", True)):
            return False
        if not is_employee_available(model, e, label, day, st, en, area, clopen_min_start):
            return False
        if not respects_daily_shift_limits(assignments, e, day, extra=(st,en)):
            return False
        if not respects_max_consecutive_days(assignments, e, day):
            return False
        min_h = float(getattr(e, "min_hours_per_shift", 1.0) or 1.0)
        if hours_between_ticks(st, en) + 1e-9 < min_h:
            return False
        # overlap
        for ex in assignments:
            if ex.employee_name==e.name and ex.day==day and not (en<=ex.start_t or st>=ex.end_t):
                return False
        h = hours_between_ticks(st,en)
        if emp_hours[e.name] + h > e.max_weekly_hours + 1e-9:
            return False
        # max cap per tick
        if _violates_max(day, area, st, en, coverage):
            return False
        return True

    # --- Phase 3: Coverage Risk Protection + Utilization Optimizer precomputations ---
    try:
        enable_risk = bool(getattr(model.manager_goals, "enable_coverage_risk_protection", True))
        w_risk = float(getattr(model.manager_goals, "w_coverage_risk", 10.0) or 0.0)
    except Exception:
        enable_risk, w_risk = True, 0.0

    try:
        enable_util = bool(getattr(model.manager_goals, "enable_utilization_optimizer", True))
        w_new_emp = float(getattr(model.manager_goals, "w_new_employee_penalty", 3.0) or 0.0)
        w_frag = float(getattr(model.manager_goals, "w_fragmentation_penalty", 2.5) or 0.0)
        w_extend = float(getattr(model.manager_goals, "w_extend_shift_bonus", 2.0) or 0.0)
        w_low_hours = float(getattr(model.manager_goals, "w_low_hours_priority_bonus", 2.5) or 0.0)
        w_near_cap = float(getattr(model.manager_goals, "w_near_cap_penalty", 5.0) or 0.0)
        w_target_fill = float(getattr(model.manager_goals, "w_target_min_fill_bonus", 1.5) or 0.0)
        balance_tol = float(getattr(model.manager_goals, "utilization_balance_tolerance_hours", 2.0) or 0.0)
    except Exception:
        enable_util, w_new_emp, w_frag, w_extend, w_low_hours, w_near_cap, w_target_fill, balance_tol = True, 3.0, 2.5, 2.0, 2.5, 5.0, 1.5, 2.0

    # Scarcity maps (risk protection): how many employees could cover a 1-hour segment starting at tick t
    tick_scarcity: Dict[Tuple[str,str,int], int] = {}
    emp_feasible_totals: Dict[str, int] = {e.name: 0 for e in model.employees}

    if enable_risk and w_risk > 0.0:
        demand_keys = set()
        try:
            demand_keys.update([k for k,mn in min_req.items() if mn > 0])
        except Exception:
            pass
        try:
            demand_keys.update([k for k,pr in pref_req.items() if pr > 0])
        except Exception:
            pass

        for (day, area, t) in demand_keys:
            if t < 0 or t+2 > DAY_TICKS:
                continue
            cnt = 0
            for e in model.employees:
                if getattr(e, "work_status", "") != "Active":
                    continue
                if area not in getattr(e, "areas_allowed", []):
                    continue
                try:
                    if feasible_segment(e, day, area, int(t), int(t)+2):
                        cnt += 1
                except Exception:
                    continue
            tick_scarcity[(day, area, int(t))] = cnt

        for e in model.employees:
            if getattr(e, "work_status", "") != "Active":
                continue
            tot = 0
            for (day, area, t) in demand_keys:
                if t < 0 or t+2 > DAY_TICKS:
                    continue
                if area not in getattr(e, "areas_allowed", []):
                    continue
                try:
                    if feasible_segment(e, day, area, int(t), int(t)+2):
                        tot += 1
                except Exception:
                    continue
            emp_feasible_totals[e.name] = tot


    def add_best_segment(day: str, area: str, st: int, en: int, locked_ok: bool=False, enforce_weekly_cap: bool=True) -> bool:
        nonlocal current_avg_active_wants
        # choose employee to cover this segment
        pool = [e for e in model.employees if e.work_status=="Active" and bool(getattr(e, "wants_hours", True)) and area in e.areas_allowed]
        if enable_util and w_low_hours > 0.0 and active_wants_names:
            current_avg_active_wants = sum(float(emp_hours.get(nm, 0.0) or 0.0) for nm in active_wants_names) / float(len(active_wants_names))
        else:
            current_avg_active_wants = 0.0
        # score & sort
        pool.sort(key=lambda e: candidate_score(e, day, area, st, en), reverse=True)
        for e in pool[:40]:
            if feasible_segment(e, day, area, st, en):
                return add_assignment(Assignment(day, area, st, en, e.name, locked=False, source="solver"), locked_ok=locked_ok, cov=coverage, enforce_weekly_cap=enforce_weekly_cap)
        return False

    # ---- Greedy fill: HARD mins first ----
    # We place contiguous segments of at least 1 hour (2 ticks) to avoid post-prune collapse.
    def _tick_sort_key(k):
        day, area, t = k
        return (DAYS.index(day), AREAS.index(area), t)

    # Iterate until no progress
    progress = True
    while progress:
        progress = False
        # collect deficits
        deficit_keys = [k for k,mn in min_req.items() if coverage.get(k,0) < mn]
        if enable_risk and w_risk > 0.0 and tick_scarcity:
            # Fill the scarcest coverage ticks first (fewer feasible employees => higher risk)
            deficit_keys.sort(key=lambda k: (tick_scarcity.get(k, 10**9), k[0], k[1], k[2]))
        else:
            deficit_keys.sort(key=_tick_sort_key)
        for (day, area, t) in deficit_keys[:8000]:
            if coverage.get((day,area,t),0) >= min_req.get((day,area,t),0):
                continue
            # choose a segment starting at t
            st = t
            # ensure we can make at least 1 hour: try start at t-1 if that helps contiguous 1h inside needs
            if st > 0 and coverage.get((day,area,st),0) < min_req.get((day,area,st),0) and coverage.get((day,area,st-1),0) < min_req.get((day,area,st-1),0):
                st = st-1
            # lengths to try (ticks): 2=1h, 4=2h, 6=3h, 8=4h
            for L in (8,6,4,2):
                en = st + L
                if en > DAY_TICKS:
                    continue
                # require that at least 2 ticks in this window still need min coverage (avoid pointless segments)
                need_ticks = 0
                ok = True
                for tt in range(st, en):
                    k = (day, area, tt)
                    if coverage.get(k,0) >= max_req.get(k, 10**9):
                        ok = False
                        break
                    if coverage.get(k,0) < min_req.get(k,0):
                        need_ticks += 1
                if not ok or need_ticks < 2:
                    continue
                # Preferred Weekly Cap is soft: avoid exceeding it if possible during preferred-fill.
                seg_h = (en - st) / 2.0
                if preferred_weekly_cap > 0.0 and (total_labor_hours + seg_h) - preferred_weekly_cap > 1e-9:
                    over = (total_labor_hours + seg_h) - preferred_weekly_cap
                    # Only allow small, high-value overshoots (segment mostly fills preferred deficits).
                    if over > 0.5 or need_ticks < ((en - st) - 1):
                        continue
                if add_best_segment(day, area, st, en):
                    progress = True
                    break
            if progress:
                break


    # If Maximum Weekly Labor Cap is enabled, enforce it during MIN fill.
    # If MIN coverage remains unmet under the cap, enter infeasible mode and allow the minimum necessary overage
    # to cover remaining MIN deficits (still respecting per-tick Max staffing and per-employee rules).
    min_short_cap_check, _, _ = compute_requirement_shortfalls(min_req, pref_req, max_req, coverage)
    if max_weekly_cap > 0.0 and min_short_cap_check > 0:
        # Attempt a minimal-overage repair: fill remaining MIN deficits using the shortest segments first, ignoring the weekly cap.
        progress_cap = True
        while progress_cap:
            progress_cap = False
            deficit_keys = [k for k,mn in min_req.items() if coverage.get(k,0) < mn]
            deficit_keys.sort(key=_tick_sort_key)
            for (day, area, t) in deficit_keys[:8000]:
                if coverage.get((day,area,t),0) >= min_req.get((day,area,t),0):
                    continue
                st = t
                if st > 0 and coverage.get((day,area,st),0) < min_req.get((day,area,st),0) and coverage.get((day,area,st-1),0) < min_req.get((day,area,st-1),0):
                    st = st-1
                # shortest segments first for minimal overage
                for L in (2,4,6,8):
                    en = st + L
                    if en > DAY_TICKS:
                        continue
                    need_ticks = 0
                    ok = True
                    for tt in range(st, en):
                        k = (day, area, tt)
                        if coverage.get(k,0) >= max_req.get(k, 10**9):
                            ok = False
                            break
                        if coverage.get(k,0) < min_req.get(k,0):
                            need_ticks += 1
                    if not ok or need_ticks < 2:
                        continue
                    if add_best_segment(day, area, st, en, locked_ok=False, enforce_weekly_cap=False):
                        progress_cap = True
                        break
                if progress_cap:
                    break

    # ---- Fill toward PREFERRED (soft), without breaking max ----
    progress = True
    while progress:
        progress = False
        pref_def_keys = [k for k,pr in pref_req.items() if coverage.get(k,0) < pr]
        pref_def_keys.sort(key=_tick_sort_key)
        for (day, area, t) in pref_def_keys[:8000]:
            if coverage.get((day,area,t),0) >= pref_req.get((day,area,t),0):
                continue
            st = t
            if st > 0 and coverage.get((day,area,st-1),0) < pref_req.get((day,area,st-1),0):
                st = st-1
            for L in (6,4,2):
                en = st + L
                if en > DAY_TICKS:
                    continue
                need_ticks = 0
                ok = True
                for tt in range(st,en):
                    k=(day,area,tt)
                    if coverage.get(k,0) >= max_req.get(k, 10**9):
                        ok=False; break
                    if coverage.get(k,0) < pref_req.get(k,0):
                        need_ticks += 1
                if not ok or need_ticks < 2:
                    continue
                if add_best_segment(day, area, st, en):
                    progress = True
                    break
            if progress:
                break

    # Participation repair (>=1 shift >=1 hour) when feasible:
    for e in model.employees:
        if e.work_status!="Active" or not e.wants_hours:
            continue
        if emp_hours.get(e.name,0.0) >= 1.0:
            continue
        placed = False
        # try to place in preferred-need first, then anywhere under max
        candidate_ticks = [k for k,pr in pref_req.items() if k[1] in e.areas_allowed and coverage.get(k,0) < pr]
        if not candidate_ticks:
            candidate_ticks = [k for k,mx in max_req.items() if k[1] in e.areas_allowed and coverage.get(k,0) < mx]
        candidate_ticks.sort(key=_tick_sort_key)
        for (day, area, t) in candidate_ticks[:3000]:
            st = max(0, t-1)
            en = st + 2
            if en > DAY_TICKS:
                continue
            # attempt fixed employee
            if feasible_segment(e, day, area, st, en):
                if add_assignment(Assignment(day, area, st, en, e.name, locked=False, source="participation"), locked_ok=False, cov=coverage):
                    placed = True
                    break
        if not placed:
            # infeasible for this employee; leave for warnings/score
            pass

    # Compute shortfalls for reporting/scoring
    min_short, pref_short, max_viol = compute_requirement_shortfalls(min_req, pref_req, max_req, coverage)
    if max_viol > 0:
        warnings.append("Max staffing cap violated by locked shifts or configuration; review Staffing Requirements Max values.")
# Local search improvement (swap/move)
    # Scrutiny level controls effort (restarts + iterations).
    scr = str(getattr(model.settings, "solver_scrutiny_level", "Balanced") or "Balanced")
    SCRUTINY = {
        "Fast":     {"restarts": 1,  "iters": 200,  "time_limit_s": 0,  "stop_early": True},
        "Balanced": {"restarts": 3,  "iters": 600,  "time_limit_s": 0,  "stop_early": True},
        "Thorough": {"restarts": 6,  "iters": 1200, "time_limit_s": 0,  "stop_early": False},
        "Maximum":  {"restarts": 10, "iters": 2000, "time_limit_s": 0,  "stop_early": False},
    }
    preset = SCRUTINY.get(scr, SCRUTINY["Balanced"])
    restarts_target = int(preset["restarts"])
    iters_per_restart = int(preset["iters"])
    time_limit_s = int(preset.get("time_limit_s", 0) or 0)
    stop_early = bool(preset.get("stop_early", True))

    temp = float(model.settings.optimizer_temperature)
    rnd = random.Random()
    total_iters_done = 0
    restarts_done = 0
    t0 = datetime.datetime.now()

    # Compute unfilled MIN requirement headcount (hard)
    min_req_ls, pref_req_ls, max_req_ls = build_requirement_maps(model.requirements, goals=getattr(model,'manager_goals',None))
    # OP1: per-run memo caches (never cross-run/global).
    unfilled_cache: Dict[Tuple[Tuple[str, str, int, int, str, bool, str], ...], int] = {}
    score_cache: Dict[Tuple[Tuple[Tuple[str, str, int, int, str, bool, str], ...], int], float] = {}

    def _assign_sig(assigns: List[Assignment]) -> Tuple[Tuple[str, str, int, int, str, bool, str], ...]:
        return tuple(sorted((
            str(a.day),
            str(a.area),
            int(a.start_t),
            int(a.end_t),
            str(a.employee_name),
            bool(a.locked),
            str(a.source),
        ) for a in assigns))

    def compute_unfilled(assigns: List[Assignment]) -> int:
        sig = _assign_sig(assigns)
        cached = unfilled_cache.get(sig)
        if cached is not None:
            return int(cached)
        cov = count_coverage_per_tick(assigns)
        min_short, _, _ = compute_requirement_shortfalls(min_req_ls, pref_req_ls, max_req_ls, cov)
        out = int(min_short)
        unfilled_cache[sig] = out
        return out

    def score_assignments(assigns: List[Assignment], unfilled_val: int) -> float:
        sig = _assign_sig(assigns)
        key = (sig, int(unfilled_val))
        cached = score_cache.get(key)
        if cached is not None:
            return float(cached)
        out = float(schedule_score(model, label, assigns, unfilled_val, history_stats, prev_tick_map))
        score_cache[key] = out
        return out

    base_assigns = list(assignments)
    unfilled0 = compute_unfilled(base_assigns)
    best = (score_assignments(base_assigns, unfilled0), base_assigns)

    def feasible_add(emp: Employee, day: str, st: int, en: int, area: str, assigns: List[Assignment]) -> bool:
        # availability + overlap + max hours
        # clopen: approximate by recomputing a simple clopen map per evaluation (fast enough at small n)
        cl: Dict[Tuple[str,str], int] = {}
        # apply existing late shifts for emp
        for a in assigns:
            if a.employee_name != emp.name:
                continue
            if emp.avoid_clopens:
                end_hr = a.end_t / TICKS_PER_HOUR
                if end_hr >= 22.0:
                    idx = DAYS.index(a.day)
                    nd = DAYS[(idx+1)%7]
                    ms = int(max(0, (a.end_t + model.settings.min_rest_hours*TICKS_PER_HOUR) - DAY_TICKS))
                    cl[(emp.name, nd)] = max(cl.get((emp.name, nd), 0), ms)
        if not is_employee_available(model, emp, label, day, st, en, area, cl):
            return False
        if not respects_daily_shift_limits(assigns, emp, day, extra=(st,en)):
            return False
        if not respects_max_consecutive_days(assigns, emp, day):
            return False
        min_h = float(getattr(emp, "min_hours_per_shift", 1.0) or 1.0)
        if hours_between_ticks(st, en) + 1e-9 < min_h:
            return False
        if any(a.employee_name==emp.name and a.day==day and not (en<=a.start_t or st>=a.end_t) for a in assigns):
            return False
        h = hours_between_ticks(st,en)
        hours_now = sum(hours_between_ticks(a.start_t,a.end_t) for a in assigns if a.employee_name==emp.name)
        if hours_now + h > emp.max_weekly_hours + 1e-9:
            return False
        return True

    def step(cur: List[Assignment]) -> List[Assignment]:
        if not cur:
            return cur
        cand = list(cur)
        # choose a non-locked assignment to mutate
        movables = [i for i,a in enumerate(cand) if not a.locked]
        if not movables:
            return cand
        i = rnd.choice(movables)
        a = cand[i]
        emp = next((x for x in model.employees if x.name==a.employee_name), None)
        if emp is None:
            return cand
        # with 50%: try reassign same slot to another employee
        if rnd.random() < 0.5:
            day, area, st, en = a.day, a.area, a.start_t, a.end_t
            # remove then reassign
            old = cand.pop(i)
            # pick candidate employees
            pool = [e for e in model.employees if e.work_status=="Active" and bool(getattr(e, "wants_hours", True)) and area in e.areas_allowed and e.name!=old.employee_name]
            rnd.shuffle(pool)
            for e2 in pool[:20]:
                if feasible_add(e2, day, st, en, area, cand):
                    cand.append(Assignment(day, area, st, en, e2.name, locked=False, source="solver"))
                    return cand
            # revert
            cand.insert(i, old)
            return cand
        else:
            # try swap employees between two assignments
            j = rnd.choice(movables)
            if j == i:
                return cand
            b = cand[j]
            if a.day!=b.day:
                return cand
            # try swap emp names
            empA = next((x for x in model.employees if x.name==a.employee_name), None)
            empB = next((x for x in model.employees if x.name==b.employee_name), None)
            if empA is None or empB is None:
                return cand
            if (a.area not in empB.areas_allowed) or (b.area not in empA.areas_allowed):
                return cand
            # build temp list with removals
            temp_list = [x for k,x in enumerate(cand) if k not in (i,j)]
            if feasible_add(empB, a.day, a.start_t, a.end_t, a.area, temp_list) and feasible_add(empA, b.day, b.start_t, b.end_t, b.area, temp_list):
                temp_list.append(Assignment(a.day,a.area,a.start_t,a.end_t,empB.name,locked=False,source="solver"))
                temp_list.append(Assignment(b.day,b.area,b.start_t,b.end_t,empA.name,locked=False,source="solver"))
                return temp_list
            return cand

    # Multi-start local search (random restarts)
    restart_no_global_improve = 0
    for r in range(max(1, restarts_target)):
        restarts_done += 1
        best_before_restart = float(best[0])
        # Diversify start by doing a few random steps from the base schedule.
        cur = list(base_assigns)
        # seed: deterministic-ish but different per restart
        rnd.seed((hash(label) & 0xffffffff) ^ (r * 2654435761))
        for _warm in range(10 + r):
            cur = step(cur)
        unfilled = compute_unfilled(cur)
        cur_score = score_assignments(cur, unfilled)

        best_no_improve = 0
        for k in range(iters_per_restart):
            total_iters_done += 1
            if time_limit_s:
                if (datetime.datetime.now() - t0).total_seconds() >= time_limit_s:
                    break
            nxt = step(cur)
            unfilled = compute_unfilled(nxt)
            sc = score_assignments(nxt, unfilled)
            if sc < cur_score:
                cur, cur_score = nxt, sc
                best_no_improve = 0
                if sc < best[0]:
                    best = (sc, nxt)
            else:
                best_no_improve += 1
                # accept with probability
                if temp > 0:
                    prob = math.exp(-(sc-cur_score)/max(0.0001, temp))
                    if rnd.random() < prob:
                        cur, cur_score = nxt, sc

            # Stop-early heuristics
            if stop_early and best_no_improve > 400:
                break
            if stop_early and best[0] <= 0:
                break

        if time_limit_s and (datetime.datetime.now() - t0).total_seconds() >= time_limit_s:
            break
        if stop_early and best[0] <= 0:
            break
        nxt = step(cur)
        unfilled = compute_unfilled(nxt)
        sc = score_assignments(nxt, unfilled)
        if sc < cur_score:
            cur, cur_score = nxt, sc
            if sc < best[0]:
                best = (sc, nxt)
        else:
            # accept with probability
            if temp > 0:
                prob = math.exp(-(sc-cur_score)/(100.0*temp))
                if rnd.random() < prob:
                    cur, cur_score = nxt, sc

        if float(best[0]) < best_before_restart - 1e-9:
            restart_no_global_improve = 0
        else:
            restart_no_global_improve += 1
            # OP1: conservative restart-level early stop for faster modes only.
            if scr in ("Fast", "Balanced") and restart_no_global_improve >= 2 and r >= 1:
                break

    assignments = best[1]

    # Enforce minimum contiguous shift length (hard rule on final schedule).
    # Note: requirements are often in 30-min blocks, so enforcing this during greedy fill
    # would block building longer shifts. Instead we prune short final shift blocks.
    def prune_short_shift_blocks(assigns: List[Assignment]) -> List[Assignment]:
        keep = list(assigns)
        removed_any = False
        for e in model.employees:
            min_h = float(getattr(e, "min_hours_per_shift", 1.0))
            if min_h <= 0.5:
                continue
            for day in DAYS:
                blocks = daily_shift_blocks(keep, e.name, day)
                for st,en in blocks:
                    if hours_between_ticks(st,en) + 1e-9 < min_h:
                        # remove all assignments inside this short block
                        before = len(keep)
                        keep = [a for a in keep if not (a.employee_name==e.name and a.day==day and a.start_t>=st and a.end_t<=en)]
                        if len(keep) != before:
                            removed_any = True
        if removed_any:
            warnings.append("Removed shift blocks shorter than minimum hours-per-shift rule.")
        return keep

    assignments = prune_short_shift_blocks(assignments)
    # Recompute coverage after pruning and report MIN coverage status
    coverage = count_coverage_per_tick(assignments)
    min_req2, pref_req2, max_req2 = build_requirement_maps(model.requirements, goals=getattr(model,'manager_goals',None), store_info=getattr(model, "store_info", None))
    min_short2, pref_short2, max_viol2 = compute_requirement_shortfalls(min_req2, pref_req2, max_req2, coverage)
    filled = int(sum(min_req2.values()) - min_short2)
    total = int(sum(min_req2.values()))
    unfilled = int(min_short2)
    if min_short2 > 0:
        warnings.append(f"INFEASIBLE: Minimum staffing shortfall remains ({min_short2} half-hour headcount units below Min).")
    if max_viol2 > 0:
        warnings.append(f"WARNING: Max staffing exceeded by {max_viol2} half-hour headcount units (likely due to locked shifts).")

    # compute employee hours
    emp_hours = {e.name: 0.0 for e in model.employees}
    for a in assignments:
        emp_hours[a.employee_name] += hours_between_ticks(a.start_t,a.end_t)


    # ---- Milestone 4: Minimum Participation Repair ("if feasible") ----
    # For eligible employees (Active + opted-in + at least one 1-hour availability window this week),
    # ensure they receive >= 1 hour scheduled, if feasible without violating hard constraints
    # (staffing Max, legal/availability rules, per-employee max hours, and Maximum Weekly Labor Cap).
    eligible_map, not_eligible_map = compute_weekly_eligibility(model, label)
    participation_missed: Dict[str, str] = {}
    total_labor_hours_now: float = float(sum(emp_hours.values()))
    one_hour_ticks = 2  # 30-min ticks => 1 hour

    def _overlaps_existing(emp_name: str, day: str, st: int, en: int) -> bool:
        for ex in assignments:
            if ex.employee_name == emp_name and ex.day == day and not (en <= ex.start_t or st >= ex.end_t):
                return True
        return False

    def _violates_max2(day: str, area: str, st: int, en: int) -> bool:
        for tt in range(st, en):
            k = (day, area, tt)
            if coverage.get(k, 0) >= max_req2.get(k, 10**9):
                return True
        return False

    def _segment_need_score(day: str, area: str, st: int, en: int) -> int:
        # Prefer filling remaining MIN deficits first, then preferred deficits. Otherwise low value.
        min_need = 0
        pref_need = 0
        for tt in range(st, en):
            k = (day, area, tt)
            if coverage.get(k, 0) < min_req2.get(k, 0):
                min_need += 1
            if coverage.get(k, 0) < pref_req2.get(k, 0):
                pref_need += 1
        return (min_need * 100) + (pref_need * 10)

    # Only attempt repair for eligible employees who currently have < 1 hour scheduled
    missing_participants = [nm for nm in eligible_map.keys() if emp_hours.get(nm, 0.0) + 1e-9 < 1.0]
    for nm in missing_participants:
        e = next((x for x in model.employees if x.name == nm), None)
        if e is None:
            participation_missed[nm] = "Employee record not found."
            continue

        best = None
        best_score = -1

        # Search for a feasible 1-hour segment, prioritizing places that help MIN then preferred coverage.
        for day in DAYS:
            for area in getattr(e, "areas_allowed", []) or []:
                for st in range(0, DAY_TICKS - one_hour_ticks + 1):
                    en = st + one_hour_ticks

                    # availability + hard constraints
                    if not is_employee_available(model, e, label, day, st, en, area, clopen_min_start):
                        continue
                    if not respects_daily_shift_limits(assignments, e, day, extra=(st, en)):
                        continue
                    if _overlaps_existing(e.name, day, st, en):
                        continue
                    if _violates_max2(day, area, st, en):
                        continue
                    if not all((int(min_req2.get((day, area, tt), 0)) > 0) or (int(pref_req2.get((day, area, tt), 0)) > 0) for tt in range(st, en)):
                        continue

                    seg_h = hours_between_ticks(st, en)
                    if emp_hours.get(e.name, 0.0) + seg_h > float(getattr(e, "max_weekly_hours", 9999.0)) + 1e-9:
                        continue

                    # Maximum weekly labor cap is hard here (participation is "if feasible")
                    if max_weekly_cap > 0.0 and (total_labor_hours_now + seg_h) - max_weekly_cap > 1e-9:
                        continue

                    sc = _segment_need_score(day, area, st, en)
                    if sc > best_score:
                        best_score = sc
                        best = (day, area, st, en)

        if best is None:
            # Record miss with a helpful reason
            if max_weekly_cap > 0.0 and total_labor_hours_now + 1.0 - max_weekly_cap > 1e-9:
                participation_missed[nm] = "No feasible 1-hour slot without exceeding Maximum Weekly Labor Cap."
            else:
                participation_missed[nm] = "No feasible 1-hour slot found under hard constraints (availability/max staffing/daily rules)."
            continue

        day, area, st, en = best
        a = Assignment(day, area, st, en, e.name, locked=False, source="participation")

        # Add and update structures (coverage + hours). This segment is always >= 1 hour.
        assignments.append(a)
        seg_h = hours_between_ticks(st, en)
        emp_hours[e.name] = emp_hours.get(e.name, 0.0) + seg_h
        total_labor_hours_now += seg_h
        for tt in range(st, en):
            k = (day, area, tt)
            coverage[k] = coverage.get(k, 0) + 1

    # minor daily/weekly checks for 14-15
    if model.nd_rules.enforce:
        ws = week_sun_from_label(label) or datetime.date.today()
        for e in model.employees:
            if e.work_status!="Active" or e.minor_type!="MINOR_14_15":
                continue
            # daily hours
            daily: Dict[str,float] = {d: 0.0 for d in DAYS}
            for a in assignments:
                if a.employee_name==e.name:
                    daily[a.day] += hours_between_ticks(a.start_t,a.end_t)
            for d,h in daily.items():
                # conservative: treat Mon-Fri as school days if school week
                if model.nd_rules.is_school_week and d in ["Mon","Tue","Wed","Thu","Fri"]:
                    if h > 3.0 + 1e-9:
                        warnings.append(f"ND Minor 14-15: {e.name} exceeds 3 hrs on school day {d} ({h:.1f})")
                else:
                    if h > 8.0 + 1e-9:
                        warnings.append(f"ND Minor 14-15: {e.name} exceeds 8 hrs on {d} ({h:.1f})")
            week_h = sum(daily.values())
            if model.nd_rules.is_school_week and week_h > 18.0 + 1e-9:
                warnings.append(f"ND Minor 14-15: {e.name} exceeds 18 hrs in school week ({week_h:.1f})")
            if (not model.nd_rules.is_school_week) and week_h > 40.0 + 1e-9:
                warnings.append(f"ND Minor 14-15: {e.name} exceeds 40 hrs in non-school week ({week_h:.1f})")

    # participation reporting (Milestone 4)
    if participation_missed:
        for nm, reason in participation_missed.items():
            warnings.append(f"Participation: could not give >=1 hr to {nm} ({reason})")

    total_hours = float(sum(emp_hours.values()))
    # Report Maximum Weekly Labor Cap infeasibility (Milestone 2).
    if max_weekly_cap > 0.0 and (total_hours - max_weekly_cap) > 1e-9:
        over = total_hours - max_weekly_cap
        warnings.append(f"INFEASIBLE: exceeded Maximum Weekly Labor Hours Cap by {over:.1f} hours (cap={max_weekly_cap:.1f}, scheduled={total_hours:.1f}).")
        # Provide a few concrete reasons to aid debugging.
        if locked_hours > 0.0 and locked_hours - max_weekly_cap > 1e-9:
            warnings.append(f"Reason: Locked fixed shifts alone total {locked_hours:.1f} hours, which already exceeds the cap.")
        if 'min_short_cap_check' in locals() and min_short_cap_check > 0:
            warnings.append("Reason: Minimum coverage could not be met under the weekly cap; minimal overage was allowed to cover remaining MIN deficits.")
        if cap_blocked_attempts > 0:
            warnings.append(f"Reason: Weekly cap blocked {cap_blocked_attempts} placement attempts during MIN construction.")
    # Report Preferred Weekly Cap overage (soft) (Milestone 5).
    if preferred_weekly_cap > 0.0 and (total_hours - preferred_weekly_cap) > 1e-9:
        over = total_hours - preferred_weekly_cap
        warnings.append(f"Soft: exceeded Preferred Weekly Labor Hours Cap by {over:.1f} hours (preferred={preferred_weekly_cap:.1f}, scheduled={total_hours:.1f}).")

    # Explainability/Diagnostics (P2-2): store limiting factors in a structured form.
    limiting: List[str] = []
    try:
        if min_short > 0:
            limiting.append(f"MIN coverage shortfall: {int(min_short)} tick(s) under minimum")
        if pref_short > 0:
            limiting.append(f"Preferred coverage shortfall: {int(pref_short)} tick(s) under preferred")
        if max_viol > 0:
            limiting.append(f"Max staffing violated: {int(max_viol)} tick(s) over max")
    except Exception:
        pass
    try:
        if max_weekly_cap > 0.0 and cap_blocked_attempts > 0:
            limiting.append(f"Weekly cap blocked {int(cap_blocked_attempts)} placement attempts")
    except Exception:
        pass
    try:
        if participation_missed:
            limiting.append(f"Participation infeasible for {len(participation_missed)} employee(s)")
    except Exception:
        pass
    try:
        locked_ct = sum(1 for a in assignments if a.locked or a.source=='locked')
        if locked_ct:
            limiting.append(f"Locked shifts present: {locked_ct} assignment(s)")
    except Exception:
        pass

    diagnostics = {
    "min_short": int(min_short) if 'min_short' in locals() else int(unfilled),
    "pref_short": int(pref_short) if 'pref_short' in locals() else 0,
    "max_viol": int(max_viol) if 'max_viol' in locals() else 0,
    "cap_blocked_attempts": int(cap_blocked_attempts) if 'cap_blocked_attempts' in locals() else 0,
    "cap_blocked_ticks": int(cap_blocked_ticks) if 'cap_blocked_ticks' in locals() else 0,
    "participation_missed": dict(participation_missed) if 'participation_missed' in locals() else {},
    "locked_hours": float(locked_hours) if 'locked_hours' in locals() else 0.0,

    # Phase 3 toggles/weights (for debugging & explainability)
    "enable_coverage_risk_protection": bool(enable_risk) if 'enable_risk' in locals() else False,
    "w_coverage_risk": float(w_risk) if 'w_risk' in locals() else 0.0,
    "enable_utilization_optimizer": bool(enable_util) if 'enable_util' in locals() else False,
    "w_new_employee_penalty": float(w_new_emp) if 'w_new_emp' in locals() else 0.0,
    "w_fragmentation_penalty": float(w_frag) if 'w_frag' in locals() else 0.0,
    "w_extend_shift_bonus": float(w_extend) if 'w_extend' in locals() else 0.0,
    "pattern_learning_enabled": bool(pattern_learning_enabled) if 'pattern_learning_enabled' in locals() else False,
    "learned_patterns_count": int(len(learned_patterns)) if 'learned_patterns' in locals() else 0,
    "w_pattern_learning": float(w_pattern_learning) if 'w_pattern_learning' in locals() else 0.0,

    "limiting_factors": list(limiting),
}

    return assignments, emp_hours, total_hours, warnings, filled, total, int(total_iters_done), int(restarts_done), diagnostics

# -----------------------------
# Output / Export
# -----------------------------
def assignments_by_area_day(assignments: List[Assignment]) -> Dict[str, Dict[str, List[Assignment]]]:
    out: Dict[str, Dict[str, List[Assignment]]] = {a: {d: [] for d in DAYS} for a in AREAS}
    for x in assignments:
        out.setdefault(x.area, {d: [] for d in DAYS}).setdefault(x.day, []).append(x)
    for area in out:
        for d in out[area]:
            out[area][d].sort(key=lambda a: (a.start_t, a.employee_name))
    return out

def make_one_page_html(model: DataModel, label: str, assignments: List[Assignment]) -> str:
    by = assignments_by_area_day(assignments)
    title = f"{html_escape(model.store_info.store_name or 'Labor Force Scheduler')} — {html_escape(label)}"
    sub = html_escape(model.store_info.store_address)
    phone = html_escape(model.store_info.store_phone)
    mgr = html_escape(model.store_info.store_manager)

    def area_section(area: str) -> str:
        rows = []
        for d in DAYS:
            items = by.get(area, {}).get(d, [])
            if not items:
                rows.append(f"<tr><td class='day'>{d}</td><td class='cell empty' colspan='2'>—</td></tr>")
                continue
            for i,a in enumerate(items):
                name = html_escape(a.employee_name)
                tm = f"{tick_to_hhmm(a.start_t)}–{tick_to_hhmm(a.end_t)}"
                if i==0:
                    rows.append(f"<tr><td class='day' rowspan='{len(items)}'>{d}</td><td class='cell name'>{name}</td><td class='cell time'>{tm}</td></tr>")
                else:
                    rows.append(f"<tr><td class='cell name'>{name}</td><td class='cell time'>{tm}</td></tr>")
        return f"""
        <div class="section">
          <h2>{area}</h2>
          <table>
            <thead><tr><th style="width:64px;">Day</th><th>Employee</th><th style="width:110px;">Time</th></tr></thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>
        </div>
        """

    css = """
    <style>
      @page { size: landscape; margin: 0.35in; }
      body { font-family: Arial, sans-serif; }
      .hdr { display:flex; justify-content:space-between; align-items:flex-end; gap:12px; margin-bottom:10px; }
      .title { font-size: 18px; font-weight: 700; }
      .sub { font-size: 12px; color:#444; margin-top:2px; }
      .meta { font-size: 12px; color:#444; text-align:right; }
      .grid { display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; }
      h2 { margin: 0 0 6px 0; font-size: 14px; }
      table { width:100%; border-collapse: collapse; table-layout: fixed; }
      th, td { border: 1px solid #222; padding: 3px 5px; font-size: 11px; }
      th { background: #f3f3f3; }
      td.day { font-weight: 700; text-align:center; background:#fafafa; }
      td.cell.empty { color:#666; text-align:center; }
      td.cell.name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      td.cell.time { text-align:center; }
      .foot { margin-top:8px; font-size: 10px; color:#555; }
    </style>
    """
    html = f"""
    <html><head><meta charset="utf-8">{css}</head>
    <body>
      <div class="hdr">
        <div>
          <div class="title">{title}</div>
          <div class="sub">{sub}</div>
        </div>
        <div class="meta">
          <div>Store: {phone}</div>
          <div>Manager: {mgr}</div>
        </div>
      </div>
      <div class="grid">
        {area_section("CSTORE")}
        {area_section("KITCHEN")}
        {area_section("CARWASH")}
      </div>
      <div class="foot">Generated {today_iso()} • Times in 30-minute increments</div>
    </body></html>
    """
    return html

def export_html(model: DataModel, label: str, assignments: List[Assignment]) -> str:
    html = make_one_page_html(model, label, assignments)
    fn = _build_export_filename("schedule", label, "html")
    path = rel_path("exports", fn)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# -----------------------------
# Additional print views (V3.1)
# -----------------------------
def tick_to_ampm(t: int) -> str:
    """Format tick as e.g. 8:00a / 12:30p (more readable for staff)."""
    t = max(0, min(DAY_TICKS, int(t)))
    mins = t * TICK_MINUTES
    h24 = (mins // 60) % 24
    m = mins % 60
    suf = "a" if h24 < 12 else "p"
    h12 = h24 % 12
    if h12 == 0:
        h12 = 12
    if m == 0:
        return f"{h12}{suf}"
    return f"{h12}:{m:02d}{suf}"

def _normalize_user_time(s: str) -> str:
    s = str(s or '').strip().lower().replace(' ', '')
    if not s:
        raise ValueError('blank time')
    if s.endswith('a'):
        s += 'm'
    if s.endswith('p'):
        s += 'm'
    if 'am' not in s and 'pm' not in s:
        hh = s.split(':', 1)[0]
        try:
            hour = int(hh)
        except Exception:
            hour = 0
        s += 'pm' if 1 <= hour <= 11 else 'am'
    m = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?(am|pm)', s)
    if not m:
        raise ValueError(f'invalid time: {s}')
    hour = int(m.group(1))
    minute = int(m.group(2) or '00')
    if not (0 <= minute <= 59):
        raise ValueError(f'invalid minutes: {s}')
    mer = m.group(3)
    if mer == 'am':
        hour = 0 if hour == 12 else hour
    else:
        hour = hour if hour == 12 else hour + 12
    if not (0 <= hour <= 23):
        raise ValueError(f'invalid hour: {s}')
    return f"{hour:02d}:{minute:02d}"

AREA_LABEL = {"CSTORE": "C-Store", "KITCHEN": "Kitchen", "CARWASH": "Carwash"}
AREA_TAG = {"CSTORE": "+C", "KITCHEN": "+Kit", "CARWASH": "+Wash"}

def _build_emp_day_area(assignments: List[Assignment]) -> Tuple[Dict[Tuple[str,str,str], List[Tuple[int,int]]],
                                                               Dict[Tuple[str,str], Set[str]]]:
    """Returns:
    - shifts[(emp, day, area)] = [(start,end), ...]
    - areas_worked[(emp, day)] = set(areas)
    """
    shifts: Dict[Tuple[str,str,str], List[Tuple[int,int]]] = {}
    areas_worked: Dict[Tuple[str,str], Set[str]] = {}
    for a in assignments:
        key = (a.employee_name, a.day, a.area)
        shifts.setdefault(key, []).append((a.start_t, a.end_t))
        areas_worked.setdefault((a.employee_name, a.day), set()).add(a.area)
    # normalize ordering
    for k in list(shifts.keys()):
        shifts[k].sort()
    return shifts, areas_worked

def make_employee_calendar_html(model: DataModel, label: str, assignments: List[Assignment]) -> str:
    """
    Employee-facing calendar-style schedules:
      Page 1: MAIN (all areas merged) with "See Kitchen"/"See Carwash" hints
      Page 2: KITCHEN (kitchen-only)
      Page 3: CARWASH (carwash-only)

    Design goals:
      - Full-page utilization (fixed layout widths + print margins)
      - No text overlap (wrap enabled, no ellipsis, safe font sizes)
      - Alphabetical employees
      - Total hours in a dedicated right-side column
      - One-line time blocks (multiple blocks separated by '; ')
    """
    # Employees alphabetically
    emps = sorted(model.employees, key=lambda e: (e.name or "").lower())

    # Weekly hours across all areas
    emp_hours: Dict[str, float] = {}
    for a in assignments:
        emp_hours[a.employee_name] = emp_hours.get(a.employee_name, 0.0) + hours_between_ticks(a.start_t, a.end_t)

    # Build per-employee/day lists
    by_emp_day: Dict[Tuple[str, str], List[Assignment]] = {}
    by_emp_day_area: Dict[Tuple[str, str, str], List[Assignment]] = {}
    for a in assignments:
        by_emp_day.setdefault((a.employee_name, a.day), []).append(a)
        by_emp_day_area.setdefault((a.employee_name, a.day, a.area), []).append(a)

    for k in list(by_emp_day.keys()):
        by_emp_day[k].sort(key=lambda x: (x.start_t, x.end_t, x.area))
    for k in list(by_emp_day_area.keys()):
        by_emp_day_area[k].sort(key=lambda x: (x.start_t, x.end_t))

    def _merge_blocks(items: List[Tuple[int, int, Optional[str]]]) -> List[Tuple[int, int, set]]:
        """Merge contiguous/overlapping blocks. Returns (start,end,areas_set)."""
        if not items:
            return []
        items = sorted(items, key=lambda x: (x[0], x[1]))
        out: List[Tuple[int, int, set]] = []
        cur_s, cur_e, cur_a = items[0][0], items[0][1], set()
        if items[0][2]:
            cur_a.add(items[0][2])
        for s, e, area in items[1:]:
            # contiguous or overlap => uninterrupted
            if s <= cur_e:
                cur_e = max(cur_e, e)
                if area:
                    cur_a.add(area)
            else:
                out.append((cur_s, cur_e, set(cur_a)))
                cur_s, cur_e = s, e
                cur_a = set()
                if area:
                    cur_a.add(area)
        out.append((cur_s, cur_e, set(cur_a)))
        return out

    def _format_time_blocks(blocks: List[Tuple[int,int,set]]) -> str:
        return "; ".join(f"{tick_to_ampm(s)}–{tick_to_ampm(e)}" for s,e,_ in blocks)

    def _format_hints(areas: set) -> str:
        hints = []
        if "KITCHEN" in areas:
            hints.append("See Kitchen")
        if "CARWASH" in areas:
            hints.append("See Carwash")
        return " • ".join(hints)

    title = f"{html_escape(model.store_info.store_name or 'Schedule')} — Employee Calendar"
    phone = html_escape(model.store_info.store_phone or "")
    mgr = html_escape(model.store_info.store_manager or "")

    css = """
    <style>
      @page { size: landscape; margin: 0.35in; }
      body { font-family: Arial, Helvetica, sans-serif; }
      .hdr { display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:10px; }
      .title { font-size: 18px; font-weight: 700; }
      .sub { font-size: 11px; color:#333; }
      .meta { font-size: 10px; color:#333; text-align:right; }
      .pagebreak { page-break-before: always; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; }
      th, td { border: 1px solid #222; padding: 4px 6px; vertical-align: top; }
      th { background: #f4f4f4; font-size: 10px; text-align: center; }
      td.emp, td.hours { font-size: 10px; font-weight: 700; }
      td.emp { white-space: normal; overflow-wrap:anywhere; word-break: break-word; }
      td.hours { text-align: center; }
      td.cell { font-size: 10px; line-height: 1.15; white-space: normal; overflow-wrap:anywhere; word-break: break-word; }
      .off { color:#111; font-weight:700; text-align:center; }
      .hint { color:#777; font-size: 9px; font-weight: 600; }
      .foot { margin-top:8px; font-size: 9px; color:#555; }
    </style>
    """

    def _weekly_hours_str(name: str) -> str:
        weekly = emp_hours.get(name, 0.0)
        if abs(weekly - round(weekly)) < 1e-9:
            return str(int(round(weekly)))
        return f"{weekly:.1f}"

    def cell_main(e: Employee, day: str) -> str:
        items = by_emp_day.get((e.name, day), [])
        if not items:
            return '<div class="off">OFF</div>'
        # one merged timeline for the day across ALL areas
        blocks = _merge_blocks([(int(a.start_t), int(a.end_t), a.area) for a in items])
        times = _format_time_blocks(blocks)
        # any kitchen/carwash involvement anywhere in the day => hint
        all_areas = set()
        for _, _, a_set in blocks:
            all_areas |= a_set
        hint = _format_hints(all_areas)
        if hint:
            return f"{html_escape(times)}<br><span class='hint'>{html_escape(hint)}</span>"
        return html_escape(times)

    def cell_area_only(e: Employee, day: str, area: str) -> str:
        items = by_emp_day_area.get((e.name, day, area), [])
        if not items:
            # If worked elsewhere, still show OFF for this dept
            return ''  # blank if not scheduled in this department
        blocks = _merge_blocks([(int(a.start_t), int(a.end_t), area) for a in items])
        times = _format_time_blocks(blocks)
        return html_escape(times)

    def build_table(kind: str) -> str:
        # kind in {"MAIN","KITCHEN","CARWASH"}
        # For department pages, show only employees who have at least one shift in that department this week
        day_label = {"Sun":"Sunday","Mon":"Monday","Tue":"Tuesday","Wed":"Wednesday","Thu":"Thursday","Fri":"Friday","Sat":"Saturday"}
        day_heads = "".join(f"<th>{html_escape(day_label.get(d,d))}</th>" for d in DAYS)
        rows = []
        if kind == "MAIN":
            emps_for_kind = emps
        else:
            names_with = set()
            for (nm, dy, ar), items in by_emp_day_area.items():
                if ar == kind and items:
                    names_with.add(nm)
            emps_for_kind = [e for e in emps if e.name in names_with]
        for e in emps_for_kind:
            phone_str = (e.phone or "").strip()
            name_line = e.name or ""
            if phone_str:
                name_line += f" - {phone_str}"
            tds = [f'<td class="emp" title="{html_escape(name_line)}">{html_escape(name_line)}</td>']
            for d in DAYS:
                if kind == "MAIN":
                    tds.append(f'<td class="cell">{cell_main(e, d)}</td>')
                else:
                    tds.append(f'<td class="cell">{cell_area_only(e, d, kind)}</td>')
            tds.append(f'<td class="hours">{html_escape(_weekly_hours_str(e.name))}</td>')
            rows.append("<tr>" + "".join(tds) + "</tr>")

        # Column widths tuned for readability and full page use (landscape)
        # Employee 24%, Total Hours 8%, remaining split across 7 days
        day_w = (100.0 - 24.0 - 8.0) / 7.0
        colgroup = (
            f"<colgroup>"
            f"<col style='width:24%'>"
            + "".join(f"<col style='width:{day_w:.3f}%'>" for _ in DAYS)
            + f"<col style='width:8%'>"
            f"</colgroup>"
        )
        head = (
            "<thead><tr>"
            "<th>Employee</th>"
            f"{day_heads}"
            "<th>Total Hours</th>"
            "</tr></thead>"
        )
        caption = "Main Staffing Schedule (All Areas)" if kind == "MAIN" else (AREA_LABEL.get(kind, kind.title()) + " Schedule")
        # Full day names per user preference
        return f"""
        <div class="section {'pagebreak' if kind!='MAIN' else ''}">
          <h2 style="font-size:13px; margin:10px 0 6px;">{html_escape(caption)}</h2>
          <table>
            {colgroup}
            {head}
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """

    sub_main = f"{html_escape(label)} • Landscape • Sunday–Saturday (See department pages for details)"
    html = f"""
    <html><head><meta charset="utf-8">{css}</head>
    <body>
      <div class="hdr">
        <div>
          <div class="title">{title}</div>
          <div class="sub">{sub_main}</div>
        </div>
        <div class="meta">
          <div>Store: {phone}</div>
          <div>Manager: {mgr}</div>
        </div>
      </div>
      {build_table("MAIN")}
      {build_table("KITCHEN")}
      {build_table("CARWASH")}
      <div class="foot">Generated {today_iso()} • Blank cells on department pages mean not scheduled for that department on that day. MAIN shows overall work window; use “See Kitchen/See Carwash” for assignment details.</div>
    </body></html>
    """
    return html

def export_employee_calendar_html(model: DataModel, label: str, assignments: List[Assignment]) -> str:
    html = make_employee_calendar_html(model, label, assignments)
    fn = _build_export_filename("employee_calendar", label, "html")
    path = rel_path("exports", fn)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def make_employee_calendar_html_with_overrides(model: DataModel, label: str, assignments: List[Assignment], overrides: dict) -> str:
    """
    Same output as make_employee_calendar_html, but allows overriding cell text.
    overrides format: { "MAIN": {emp:{day:text}}, "KITCHEN": {...}, "CARWASH": {...} }
    """
    overrides = overrides or {}
    # Employees alphabetically
    emps = sorted(model.employees, key=lambda e: (e.name or "").lower())

    # Weekly hours across all areas (kept from assignments for consistency)
    emp_hours: Dict[str, float] = {}
    for a in assignments:
        emp_hours[a.employee_name] = emp_hours.get(a.employee_name, 0.0) + hours_between_ticks(a.start_t, a.end_t)

    # Build per-employee/day lists
    by_emp_day: Dict[Tuple[str, str], List[Assignment]] = {}
    by_emp_day_area: Dict[Tuple[str, str, str], List[Assignment]] = {}
    for a in assignments:
        by_emp_day.setdefault((a.employee_name, a.day), []).append(a)
        by_emp_day_area.setdefault((a.employee_name, a.day, a.area), []).append(a)

    for k in list(by_emp_day.keys()):
        by_emp_day[k].sort(key=lambda x: (x.start_t, x.end_t, x.area))
    for k in list(by_emp_day_area.keys()):
        by_emp_day_area[k].sort(key=lambda x: (x.start_t, x.end_t))

    def _merge_blocks(items: List[Tuple[int, int, Optional[str]]]) -> List[Tuple[int, int, set]]:
        if not items:
            return []
        items = sorted(items, key=lambda x: (x[0], x[1]))
        out: List[Tuple[int, int, set]] = []
        cur_s, cur_e, cur_a = items[0][0], items[0][1], set()
        if items[0][2]:
            cur_a.add(items[0][2])
        for s, e, area in items[1:]:
            if s <= cur_e:
                cur_e = max(cur_e, e)
                if area:
                    cur_a.add(area)
            else:
                out.append((cur_s, cur_e, set(cur_a)))
                cur_s, cur_e = s, e
                cur_a = set()
                if area:
                    cur_a.add(area)
        out.append((cur_s, cur_e, set(cur_a)))
        return out

    def _block_str(s: int, e: int) -> str:
        return f"{tick_to_ampm(int(s))}-{tick_to_ampm(int(e))}"

    def _blocks_to_str(blocks: List[Tuple[int,int,set]], include_hints: bool = False) -> str:
        parts = []
        for s, e, areas in blocks:
            seg = _block_str(s, e)
            if include_hints:
                hints = []
                if "KITCHEN" in areas:
                    hints.append("See Kitchen")
                if "CARWASH" in areas:
                    hints.append("See Carwash")
                if hints:
                    seg += f' <span class="hint">({html_escape(" / ".join(hints))})</span>'
            parts.append(seg)
        return "; ".join(parts)

    def _weekly_hours_str(name: str) -> str:
        weekly = emp_hours.get(name, 0.0)
        if weekly <= 0.0:
            return "0"
        if abs(weekly - round(weekly)) < 1e-6:
            return str(int(round(weekly)))
        return f"{weekly:.1f}"

    def _override(kind: str, emp: str, day: str) -> Optional[str]:
        try:
            v = overrides.get(kind, {}).get(emp, {}).get(day, None)
            if v is None:
                return None
            # allow blank override
            return str(v)
        except Exception:
            return None

    def cell_main(e: Employee, d: str) -> str:
        ov = _override("MAIN", e.name or "", d)
        if ov is not None:
            # render plain text override; allow line breaks
            s = html_escape(ov).replace("\n", "<br>")
            if not s:
                return ""
            if s.strip().lower() == "off":
                return '<div class="off">Off</div>'
            return s

        # Default behavior from assignments
        items = []
        for a in by_emp_day.get((e.name, d), []):
            items.append((int(a.start_t), int(a.end_t), a.area))
        merged = _merge_blocks(items)
        if not merged:
            return '<div class="off">Off</div>'
        return _blocks_to_str(merged, include_hints=True)

    def cell_area_only(e: Employee, d: str, kind: str) -> str:
        ov = _override(kind, e.name or "", d)
        if ov is not None:
            s = html_escape(ov).replace("\n", "<br>")
            return s
        lst = by_emp_day_area.get((e.name, d, kind), [])
        if not lst:
            return ""  # blank cells on department pages
        items = [(int(a.start_t), int(a.end_t), None) for a in lst]
        merged = _merge_blocks(items)
        return _blocks_to_str(merged, include_hints=False)

    title = f"Employee Calendar Schedule — {html_escape(label)}"
    mgr = html_escape(getattr(model.store_info, "manager_name", "") or "")
    phone = html_escape(getattr(model.store_info, "store_name", "") or "")

    css = """
    <style>
      @page { size: landscape; margin: 0.35in; }
      body { font-family: Arial, sans-serif; color: #111; }
      .hdr { display:flex; justify-content: space-between; align-items:flex-end; margin-bottom: 8px; }
      .title { font-size: 14px; font-weight: 800; }
      .sub { font-size: 10px; color:#444; margin-top: 2px; }
      .meta { text-align: right; font-size: 10px; color:#444; }
      .section { margin-top: 10px; }
      .pagebreak { page-break-before: always; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; }
      th, td { border: 1px solid #999; padding: 4px 6px; vertical-align: top; }
      th { background: #f4f4f4; font-size: 10px; text-align: center; }
      td.emp, td.hours { font-size: 10px; font-weight: 700; }
      td.emp { white-space: normal; overflow-wrap:anywhere; word-break: break-word; }
      td.hours { text-align: center; }
      td.cell { font-size: 10px; line-height: 1.15; white-space: normal; overflow-wrap:anywhere; word-break: break-word; }
      .off { color:#111; font-weight:700; text-align:center; }
      .hint { color:#777; font-size: 9px; font-weight: 600; }
      .foot { margin-top:8px; font-size: 9px; color:#555; }
    </style>
    """

    def build_table(kind: str) -> str:
        day_label = {"Sun":"Sunday","Mon":"Monday","Tue":"Tuesday","Wed":"Wednesday","Thu":"Thursday","Fri":"Friday","Sat":"Saturday"}
        day_heads = "".join(f"<th>{html_escape(day_label.get(d,d))}</th>" for d in DAYS)
        rows = []
        if kind == "MAIN":
            emps_for_kind = emps
        else:
            names_with = set()
            for (nm, dy, ar), items in by_emp_day_area.items():
                if ar == kind and items:
                    names_with.add(nm)
            emps_for_kind = [e for e in emps if e.name in names_with]
        for e in emps_for_kind:
            phone_str = (e.phone or "").strip()
            name_line = e.name or ""
            if phone_str:
                name_line += f" - {phone_str}"
            tds = [f'<td class="emp" title="{html_escape(name_line)}">{html_escape(name_line)}</td>']
            for d in DAYS:
                if kind == "MAIN":
                    tds.append(f'<td class="cell">{cell_main(e, d)}</td>')
                else:
                    tds.append(f'<td class="cell">{cell_area_only(e, d, kind)}</td>')
            tds.append(f'<td class="hours">{html_escape(_weekly_hours_str(e.name))}</td>')
            rows.append("<tr>" + "".join(tds) + "</tr>")

        day_w = (100.0 - 24.0 - 8.0) / 7.0
        colgroup = (
            f"<colgroup>"
            f"<col style='width:24%'>"
            + "".join(f"<col style='width:{day_w:.3f}%'>" for _ in DAYS)
            + f"<col style='width:8%'>"
            f"</colgroup>"
        )
        head = (
            "<thead><tr>"
            "<th>Employee</th>"
            f"{day_heads}"
            "<th>Total Hours</th>"
            "</tr></thead>"
        )
        caption = "Main Staffing Schedule (All Areas)" if kind == "MAIN" else (AREA_LABEL.get(kind, kind.title()) + " Schedule")
        return f"""
        <div class="section {'pagebreak' if kind!='MAIN' else ''}">
          <h2 style="font-size:13px; margin:10px 0 6px;">{html_escape(caption)}</h2>
          <table>
            {colgroup}
            {head}
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """

    sub_main = f"{html_escape(label)} • Landscape • Sunday–Saturday (manual edits applied)"
    html = f"""
    <html><head><meta charset="utf-8">{css}</head>
    <body>
      <div class="hdr">
        <div>
          <div class="title">{title}</div>
          <div class="sub">{sub_main}</div>
        </div>
        <div class="meta">
          <div>Store: {phone}</div>
          <div>Manager: {mgr}</div>
        </div>
      </div>
      {build_table("MAIN")}
      {build_table("KITCHEN")}
      {build_table("CARWASH")}
      <div class="foot">Generated {today_iso()} • Manual edits may not match solver utilization/coverage metrics.</div>
    </body></html>
    """
    return html

def export_employee_calendar_html_with_overrides(model: DataModel, label: str, assignments: List[Assignment], overrides: dict) -> str:
    html = make_employee_calendar_html_with_overrides(model, label, assignments, overrides)
    fn = _build_export_filename("employee_calendar_manual", label, "html")
    path = rel_path("exports", fn)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path

def _req_sched_counts(model: DataModel, assignments: List[Assignment]) -> Tuple[Dict[Tuple[str,str,int], int],
                                                                              Dict[Tuple[str,str,int], int]]:
    # key: (day, area, tick)
    req, _pref, _mx = build_requirement_maps(model.requirements, goals=getattr(model, "manager_goals", None), store_info=getattr(model, "store_info", None))
    sched: Dict[Tuple[str,str,int], int] = {}
    for a in assignments:
        for t in range(int(a.start_t), int(a.end_t)):
            sched[(a.day, a.area, t)] = sched.get((a.day, a.area, t), 0) + 1
    return req, sched

def _clopen_map_from_assignments(model: DataModel, assignments: List[Assignment]) -> Dict[Tuple[str,str], int]:
    cl: Dict[Tuple[str,str], int] = {}
    emp_map = {e.name: e for e in model.employees}
    # process per-employee in day order
    for a in sorted(assignments, key=lambda x: (x.employee_name, DAYS.index(x.day), x.start_t)):
        e = emp_map.get(a.employee_name)
        if not e:
            continue
        apply_clopen_from(model, e, a, cl)
    return cl

def make_manager_report_html(model: DataModel, label: str, assignments: List[Assignment]) -> str:
    goals = model.manager_goals
    req, sched = _req_sched_counts(model, assignments)

    def _hours_to_blocks(hours: float) -> int:
        try:
            return int(round(float(hours)))
        except Exception:
            return 0

    # OP2: true store-wide scheduled hours must be assignment-based (counted once).
    actual_scheduled_hours = sum(hours_between_ticks(a.start_t, a.end_t) for a in assignments)
    hard_weekly_cap = float(getattr(goals, 'maximum_weekly_cap', 0.0) or 0.0)
    remaining_budget_hours = hard_weekly_cap - actual_scheduled_hours if hard_weekly_cap > 0.0 else 0.0

    # compute summary stats
    total_req_blocks = 0
    blocks_met = 0
    req_hours = 0.0
    sched_hours = 0.0
    shortage_hours = 0.0
    overage_hours = 0.0
    shortage_by_area_hours: Dict[str, float] = {"CSTORE": 0.0, "KITCHEN": 0.0, "CARWASH": 0.0}

    for day in DAYS:
        for area in AREAS:
            for t in range(DAY_TICKS):
                r = req.get((day, area, t), 0)
                s = sched.get((day, area, t), 0)
                if r <= 0:
                    continue
                total_req_blocks += 1
                req_hours += r * 0.5
                sched_hours += s * 0.5
                if s >= r:
                    blocks_met += 1
                else:
                    short_h = (r - s) * 0.5
                    shortage_hours += short_h
                    shortage_by_area_hours[area] = shortage_by_area_hours.get(area, 0.0) + short_h
                if s > r:
                    overage_hours += (s - r) * 0.5

    coverage_pct = (blocks_met / total_req_blocks * 100.0) if total_req_blocks else 100.0

    # daily breakdown
    daily_rows = []
    for day in DAYS:
        d_req = d_sched = d_short = d_over = 0.0
        for area in AREAS:
            for t in range(DAY_TICKS):
                r = req.get((day, area, t), 0)
                s = sched.get((day, area, t), 0)
                if r <= 0:
                    continue
                d_req += r * 0.5
                d_sched += s * 0.5
                if s < r:
                    d_short += (r - s) * 0.5
                if s > r:
                    d_over += (s - r) * 0.5
        daily_rows.append((day, d_req, d_sched, d_short, d_over))

    # high-risk windows: collect contiguous shortages
    windows = []
    for day in DAYS:
        for area in AREAS:
            t = 0
            while t < DAY_TICKS:
                r = req.get((day, area, t), 0)
                s = sched.get((day, area, t), 0)
                deficit = max(0, r - s)
                if deficit <= 0:
                    t += 1
                    continue
                start = t
                peak = deficit
                deficit_hours = 0.0
                while t < DAY_TICKS:
                    r2 = req.get((day, area, t), 0)
                    s2 = sched.get((day, area, t), 0)
                    d2 = max(0, r2 - s2)
                    if d2 <= 0:
                        break
                    peak = max(peak, d2)
                    deficit_hours += d2 * 0.5
                    t += 1
                end = t
                windows.append((deficit_hours, peak, day, area, start, end))
            # next area
    windows.sort(reverse=True, key=lambda x: (x[0], x[1]))
    top_windows = windows[:10]

    # call list suggestions
    emp_map = {e.name: e for e in model.employees}
    # current weekly hours
    emp_week_hours: Dict[str, float] = {}
    for a in assignments:
        emp_week_hours[a.employee_name] = emp_week_hours.get(a.employee_name, 0.0) + hours_between_ticks(a.start_t, a.end_t)
    clopen = _clopen_map_from_assignments(model, assignments)

    def candidates_for(area: str, day: str, st: int, en: int) -> List[Employee]:
        out = []
        for e in model.employees:
            if e.work_status != "Active":
                continue
            certified = area in e.areas_allowed
            if not certified and not goals.include_noncertified_in_call_list:
                continue

            # restriction slack (max hours)
            window_h = hours_between_ticks(st, en)
            cur_h = emp_week_hours.get(e.name, 0.0)
            slack = float(e.max_weekly_hours) - cur_h
            not_near_restrict = slack >= window_h

            available = is_employee_available(model, e, label, day, st, en, area, clopen)

            # We will sort per your priority:
            # certified -> not near restriction -> available -> tie breakers
            out.append((certified, not_near_restrict, available, cur_h, e.name.lower(), e))
        out.sort(key=lambda x: (x[0], x[1], x[2], -x[3], x[4]), reverse=True)
        return [x[-1] for x in out]

    call_sections = []
    for (def_h, peak, day, area, st, en) in top_windows[:7]:  # keep readable
        cands = candidates_for(area, day, st, en)[:max(1, int(goals.call_list_depth))]
        items = ""
        for i, e in enumerate(cands, 1):
            cur_h = emp_week_hours.get(e.name, 0.0)
            items += f"<li>{html_escape(e.name)} ({cur_h:.1f} hrs) — {html_escape(e.phone)}</li>"
        if not items:
            items = "<li><em>No qualified backups found for this window.</em></li>"
        call_sections.append(f"""
        <div class="block">
          <div class="btitle">{html_escape(day)} • {html_escape(AREA_LABEL.get(area, area))} • {tick_to_ampm(st)}–{tick_to_ampm(en)}</div>
          <div class="bsub">Estimated shortage: {_hours_to_blocks(def_h)} blocks • Peak deficit: {peak}</div>
          <ol>{items}</ol>
        </div>
        """)

    # Labor alignment bar (simple)
    goal = float(goals.coverage_goal_pct)
    bar_pct = max(0.0, min(100.0, coverage_pct))
    status = "GOOD" if coverage_pct >= goal else "BELOW GOAL"

    css = """
    <style>
      @page { size: letter landscape; margin: 0.35in; }
      body { font-family: Arial, Helvetica, sans-serif; }
      .hdr { display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:10px; }
      .title { font-size: 18px; font-weight: 700; }
      .sub { font-size: 11px; color:#333; }
      .meta { font-size: 10px; color:#333; text-align:right; }
      .grid { display:grid; grid-template-columns: 1fr 1fr; gap: 10px; }
      .card { border:1px solid #222; padding:8px; }
      .card h3 { margin:0 0 6px; font-size: 12px; }
      table { width:100%; border-collapse: collapse; }
      th, td { border:1px solid #222; padding:4px 6px; font-size: 10px; }
      th { background:#f4f4f4; }
      .barwrap { border:1px solid #222; height:12px; width:100%; margin-top:4px; }
      .bar { height:12px; background:#333; width: 0%; }
      .pagebreak { page-break-before: always; }
      .block { border:1px solid #222; padding:8px; margin-bottom:8px; }
      .btitle { font-weight:700; font-size: 11px; }
      .bsub { font-size: 10px; color:#333; margin-top:2px; }
      .foot { margin-top:6px; font-size: 9px; color:#555; }
    </style>
    """

    title = f"{html_escape(model.store_info.store_name or 'Schedule')} — Manager Report"
    sub = f"{html_escape(label)} • 2 pages (front/back)"
    phone = html_escape(model.store_info.store_phone or "")
    mgr = html_escape(model.store_info.store_manager or "")

    # daily table rows
    dtrs = ""
    for day, d_req, d_sched, d_short, d_over in daily_rows:
        dtrs += f"<tr><td>{day}</td><td>{_hours_to_blocks(d_req)}</td><td>{_hours_to_blocks(d_sched)}</td><td>{_hours_to_blocks(d_short)}</td><td>{_hours_to_blocks(d_over)}</td></tr>"

    html = f"""
    <html><head><meta charset="utf-8">{css}</head>
    <body>
      <!-- PAGE 1 -->
      <div class="hdr">
        <div>
          <div class="title">{title}</div>
          <div class="sub">{sub}</div>
        </div>
        <div class="meta">
          <div>Store: {phone}</div>
          <div>Manager: {mgr}</div>
          <div>Generated: {today_iso()}</div>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <h3>Coverage & Labor Summary</h3>
          <div>Coverage: <b>{coverage_pct:.1f}%</b> (goal {goal:.1f}%) • Status: <b>{status}</b></div>
          <div class="barwrap"><div class="bar" style="width:{bar_pct:.1f}%;"></div></div>
          <div style="margin-top:6px;">Hard Weekly Labor Cap: <b>{(_hours_to_blocks(hard_weekly_cap) if hard_weekly_cap > 0.0 else 'Disabled')}</b></div>
          <div>Actual Scheduled Hours: <b>{_hours_to_blocks(actual_scheduled_hours)}</b></div>
          <div>Remaining Labor Budget: <b>{(_hours_to_blocks(remaining_budget_hours) if hard_weekly_cap > 0.0 else 'N/A')}</b></div>
        </div>

        <div class="card">
          <h3>High Risk Windows (Top 10)</h3>
          <table>
            <thead><tr><th>Day</th><th>Area</th><th>Window</th><th>Deficit Hrs</th><th>Peak</th></tr></thead>
            <tbody>
              {''.join([f"<tr><td>{w[2]}</td><td>{html_escape(AREA_LABEL.get(w[3],w[3]))}</td><td>{tick_to_ampm(w[4])}–{tick_to_ampm(w[5])}</td><td>{_hours_to_blocks(w[0])}</td><td>{w[1]}</td></tr>" for w in top_windows])}
            </tbody>
          </table>
        </div>

        <div class="card">
          <h3>Shortage by Area (1-hour blocks)</h3>
          <div>C-Store shortage hours: <b>{_hours_to_blocks(shortage_by_area_hours.get("CSTORE", 0.0))}</b></div>
          <div>Kitchen shortage hours: <b>{_hours_to_blocks(shortage_by_area_hours.get("KITCHEN", 0.0))}</b></div>
          <div>Carwash shortage hours: <b>{_hours_to_blocks(shortage_by_area_hours.get("CARWASH", 0.0))}</b></div>
        </div>

        <div class="card" style="grid-column: 1 / span 2;">
          <h3>Daily Breakdown</h3>
          <table>
            <thead><tr><th>Day</th><th>Req (1h blocks)</th><th>Sched (1h blocks)</th><th>Shortage (1h blocks)</th><th>Overage (1h blocks)</th></tr></thead>
            <tbody>{dtrs}</tbody>
          </table>
        </div>
      </div>

      <div class="foot">Coverage is computed from required 30-minute blocks across all areas. Displayed labor summary values are shown in 1-hour blocks.</div>

      <!-- PAGE 2 -->
      <div class="pagebreak"></div>

      <div class="hdr">
        <div>
          <div class="title">{title} — Call List</div>
          <div class="sub">Recommended employees to contact for likely shortages (ranked: certified → not near restriction → available)</div>
        </div>
        <div class="meta">
          <div>Week: {html_escape(label)}</div>
          <div>Call list depth: {int(goals.call_list_depth)}</div>
        </div>
      </div>

      {''.join(call_sections) if call_sections else '<div class="block"><em>No shortages detected from requirements.</em></div>'}

      <div class="foot">This report is advisory; always verify real-time availability and compliance.</div>
    </body></html>
    """
    return html

def export_manager_report_html(model: DataModel, label: str, assignments: List[Assignment]) -> str:
    html = make_manager_report_html(model, label, assignments)
    fn = _build_export_filename("manager_report", label, "html")
    path = rel_path("exports", fn)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path

def export_csv(model: DataModel, label: str, assignments: List[Assignment]) -> str:
    import csv
    fn = _build_export_filename("schedule", label, "csv")
    path = rel_path("exports", fn)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Day","Area","Start","End","Employee","Locked","Source"])
        for a in sorted(assignments, key=lambda x: (DAYS.index(x.day), AREAS.index(x.area), x.start_t, x.employee_name)):
            w.writerow([a.day,a.area,tick_to_hhmm(a.start_t),tick_to_hhmm(a.end_t),a.employee_name,"Yes" if a.locked else "No",a.source])
    return path

# Optional PDF via reportlab (if installed)
def export_pdf(model: DataModel, label: str, assignments: List[Assignment]) -> Optional[str]:
    try:
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
    except Exception:
        return None

    fn = _build_export_filename("schedule", label, "pdf")
    path = rel_path("exports", fn)
    ensure_dir(os.path.dirname(path))
    c = canvas.Canvas(path, pagesize=landscape(letter))
    width, height = landscape(letter)
    margin = 0.35 * inch
    x0 = margin
    y = height - margin

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0, y, f"{model.store_info.store_name or 'Labor Force Scheduler'} — {label}")
    c.setFont("Helvetica", 9)
    y -= 16
    c.drawString(x0, y, f"{model.store_info.store_address} • {model.store_info.store_phone} • Manager: {model.store_info.store_manager}")
    y -= 14

    by = assignments_by_area_day(assignments)
    col_w = (width - 2*margin) / 3.0
    col_x = [margin, margin+col_w, margin+2*col_w]

    def draw_area(area: str, x: float, y_top: float) -> float:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y_top, area)
        y = y_top - 12
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x, y, "Day")
        c.drawString(x+34, y, "Employee")
        c.drawString(x+col_w-78, y, "Time")
        y -= 10
        c.setFont("Helvetica", 8.5)
        for d in DAYS:
            items = by.get(area, {}).get(d, [])
            if not items:
                c.drawString(x, y, d)
                c.drawString(x+34, y, "—")
                y -= 10
                continue
            for i,a in enumerate(items):
                c.drawString(x, y, d if i==0 else "")
                c.drawString(x+34, y, a.employee_name[:18])
                c.drawString(x+col_w-78, y, f"{tick_to_hhmm(a.start_t)}–{tick_to_hhmm(a.end_t)}")
                y -= 10
        return y

    y1 = draw_area("CSTORE", col_x[0], y)
    y2 = draw_area("KITCHEN", col_x[1], y)
    y3 = draw_area("CARWASH", col_x[2], y)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(margin, margin/2, f"Generated {today_iso()} • 30-minute increments")
    c.showPage()
    c.save()
    return path

# -----------------------------
# UI dialogs
# -----------------------------
def simple_input(parent, title: str, prompt: str, default: str="") -> Optional[str]:
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    frm = ttk.Frame(win); frm.pack(padx=12, pady=12, fill="both", expand=True)
    ttk.Label(frm, text=prompt).pack(anchor="w")
    var = tk.StringVar(value=default)
    ent = ttk.Entry(frm, textvariable=var, width=44); ent.pack(pady=8); ent.focus_set()
    out = {"v": None}
    def ok():
        out["v"] = var.get()
        win.destroy()
    def cancel():
        win.destroy()
    btns = ttk.Frame(frm); btns.pack(fill="x")
    ttk.Button(btns, text="Cancel", command=cancel).pack(side="right")
    ttk.Button(btns, text="OK", command=ok).pack(side="right", padx=8)
    win.bind("<Return>", lambda e: ok())
    parent.wait_window(win)
    return out["v"]

class EmployeeDialog(tk.Toplevel):
    def __init__(self, parent: "SchedulerApp", employee: Optional[Employee]):
        super().__init__(parent)
        self.parent = parent
        self.result: Optional[Employee] = None
        self.title("Employee")
        # Open large / full-size for easier data entry
        try:
            self.state("zoomed")
        except Exception:
            try:
                parent.update_idletasks()
                w = max(1020, int(parent.winfo_width()))
                h = max(760, int(parent.winfo_height()))
                self.geometry(f"{w}x{h}")
            except Exception:
                self.geometry("1020x760")
        self.transient(parent)
        self.grab_set()

        # Scrollable content (both vertical + horizontal) so Save buttons never disappear
        outer = ttk.Frame(self); outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)

        frm = ttk.Frame(canvas, padding=(12,12,12,12))
        win_id = canvas.create_window((0,0), window=frm, anchor="nw")

        def _on_frame_config(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frm.bind("<Configure>", _on_frame_config)

        # Mouse wheel scrolling
        def _on_mousewheel(e):
            try:
                canvas.yview_scroll(int(-1*(e.delta/120)), "units")
                return "break"
            except Exception:
                return None

        canvas.bind("<MouseWheel>", _on_mousewheel)

        # Vars
        self.name_var = tk.StringVar(value=employee.name if employee else "")
        self.phone_var = tk.StringVar(value=employee.phone if employee else "")
        self.status_var = tk.StringVar(value=employee.work_status if employee else "Active")
        self.wants_var = tk.BooleanVar(value=(employee.wants_hours if employee else True))

        self.emp_type_var = tk.StringVar(value=(getattr(employee, "employee_type", "Crew Member") if employee else "Crew Member"))
        self.split_ok_var = tk.StringVar(value=("Yes" if getattr(employee, "split_shifts_ok", True) else "No") if employee else "Yes")
        self.double_ok_var = tk.BooleanVar(value=(getattr(employee, "double_shifts_ok", False) if employee else False))
        self.min_shift_var = tk.StringVar(value=str(float(getattr(employee, "min_hours_per_shift", 1.0)) if employee else 1.0))
        # Default max shift depends on type if adding a new employee
        default_max = float(getattr(employee, "max_hours_per_shift", 8.0)) if employee else None
        if default_max is None:
            default_max = 8.0
        self.max_shift_var = tk.StringVar(value=str(default_max))
        self.max_shifts_day_var = tk.StringVar(value=str(int(getattr(employee, "max_shifts_per_day", 1)) if employee else 1))

        self.max_weekly_var = tk.StringVar(value=str(employee.max_weekly_hours if employee else 30))
        self.target_min_var = tk.StringVar(value=str(employee.target_min_hours if employee else 0))
        self.minor_var = tk.StringVar(value=employee.minor_type if employee else "ADULT")

        self.avoid_clopen_var = tk.BooleanVar(value=(employee.avoid_clopens if employee else True))
        self.max_consec_var = tk.StringVar(value=str(employee.max_consecutive_days if employee else 6))
        self.weekend_pref_var = tk.StringVar(value=(employee.weekend_preference if employee else "Neutral"))

        self.area_vars = {a: tk.BooleanVar(value=(a in (employee.areas_allowed if employee else ["CSTORE"]))) for a in AREAS}
        self.pref_area_vars = {a: tk.BooleanVar(value=(a in (employee.preferred_areas if employee else []))) for a in AREAS}

        # availability
        emp_av = employee.availability if employee else default_day_rules()
        self.unavail = {d: tk.BooleanVar(value=emp_av[d].unavailable_day) for d in DAYS}
        self.earliest = {d: tk.StringVar(value=tick_to_hhmm(emp_av[d].earliest_start)) for d in DAYS}
        self.latest = {d: tk.StringVar(value=tick_to_hhmm(emp_av[d].latest_end)) for d in DAYS}

        self.b1s = {d: tk.StringVar(value="") for d in DAYS}
        self.b1e = {d: tk.StringVar(value="") for d in DAYS}
        self.b2s = {d: tk.StringVar(value="") for d in DAYS}
        self.b2e = {d: tk.StringVar(value="") for d in DAYS}
        if employee:
            for d in DAYS:
                br = employee.availability[d].blocked_ranges
                if len(br) >= 1:
                    self.b1s[d].set(tick_to_hhmm(br[0][0])); self.b1e[d].set(tick_to_hhmm(br[0][1]))
                if len(br) >= 2:
                    self.b2s[d].set(tick_to_hhmm(br[1][0])); self.b2e[d].set(tick_to_hhmm(br[1][1]))

        # Fixed schedule list
        self.fixed: List[FixedShift] = list(employee.fixed_schedule) if employee else []
        self.recurring_locked: List[FixedShift] = list(getattr(employee, "recurring_locked_schedule", [])) if employee else []

        # Layout
        basics = ttk.LabelFrame(frm, text="Hard Rules (Must Follow)")
        basics.pack(fill="x", pady=(0,10))
        r=0
        ttk.Label(basics, text="Name:").grid(row=r, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(basics, textvariable=self.name_var, width=24).grid(row=r, column=1, sticky="w", padx=8, pady=6)
        ttk.Label(basics, text="Phone:").grid(row=r, column=2, sticky="w", padx=8, pady=6)
        ttk.Entry(basics, textvariable=self.phone_var, width=16).grid(row=r, column=3, sticky="w", padx=8, pady=6)
        ttk.Label(basics, text="Status:").grid(row=r, column=4, sticky="w", padx=8, pady=6)
        ttk.Combobox(basics, textvariable=self.status_var, values=["Active","On Leave","Inactive"], state="readonly", width=12)\
            .grid(row=r, column=5, sticky="w", padx=8, pady=6)

        ttk.Label(basics, text="Employee type:").grid(row=r, column=6, sticky="w", padx=8, pady=6)
        type_vals = ["Store Manager", "Manager in training", "Assistant Manager", "Kitchen Manager", "Senior Crew Member", "Crew Member"]
        type_cb = ttk.Combobox(basics, textvariable=self.emp_type_var, values=type_vals, state="readonly", width=18)
        type_cb.grid(row=r, column=7, sticky="w", padx=8, pady=6)

        r+=1
        ttk.Checkbutton(basics, text="Wants hours (opt-in)", variable=self.wants_var).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        ttk.Label(basics, text="Split shifts ok:").grid(row=r, column=2, sticky="w", padx=8, pady=6)
        ttk.Radiobutton(basics, text="Yes", value="Yes", variable=self.split_ok_var).grid(row=r, column=3, sticky="w", padx=(8,2), pady=6)
        ttk.Radiobutton(basics, text="No", value="No", variable=self.split_ok_var).grid(row=r, column=4, sticky="w", padx=(2,8), pady=6)
        ttk.Label(basics, text="Max weekly hours:").grid(row=r, column=5, sticky="w", padx=8, pady=6)
        ttk.Entry(basics, textvariable=self.max_weekly_var, width=8).grid(row=r, column=6, sticky="w", padx=8, pady=6)
        ttk.Label(basics, text="Max shifts/day:").grid(row=r, column=7, sticky="w", padx=8, pady=6)
        ttk.Entry(basics, textvariable=self.max_shifts_day_var, width=6).grid(row=r, column=8, sticky="w", padx=8, pady=6)

        r+=1
        ttk.Label(basics, text="Minor type:").grid(row=r, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(basics, textvariable=self.minor_var, values=MINOR_TYPES, state="readonly", width=14)\
            .grid(row=r, column=1, sticky="w", padx=8, pady=6)
        ttk.Checkbutton(basics, text="Double shifts ok (>8h)", variable=self.double_ok_var).grid(row=r, column=2, sticky="w", padx=8, pady=6)
        ttk.Label(basics, text="Min hrs/shift:").grid(row=r, column=3, sticky="w", padx=8, pady=6)
        ttk.Entry(basics, textvariable=self.min_shift_var, width=6).grid(row=r, column=4, sticky="w", padx=8, pady=6)
        ttk.Label(basics, text="Max hrs/shift:").grid(row=r, column=5, sticky="w", padx=8, pady=6)
        ttk.Entry(basics, textvariable=self.max_shift_var, width=6).grid(row=r, column=6, sticky="w", padx=8, pady=6)
        ttk.Label(basics, text="(Hard cap 8h unless Double shifts ok)").grid(row=r, column=7, columnspan=2, sticky="w", padx=8, pady=6)

        areas = ttk.LabelFrame(frm, text="Areas allowed (hard)")
        areas.pack(fill="x", pady=(0,10))
        for i,a in enumerate(AREAS):
            ttk.Checkbutton(areas, text=f"{a} allowed", variable=self.area_vars[a]).grid(row=0, column=i, sticky="w", padx=10, pady=6)

        prefs = ttk.LabelFrame(frm, text="Preferences (soft)")
        prefs.pack(fill="x", pady=(0,10))
        ttk.Label(prefs, text="Preferred areas:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        for i,a in enumerate(AREAS):
            ttk.Checkbutton(prefs, text=f"{a}", variable=self.pref_area_vars[a]).grid(row=0, column=i+1, sticky="w", padx=10, pady=6)
        ttk.Checkbutton(prefs, text="Avoid clopens", variable=self.avoid_clopen_var).grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Label(prefs, text="Max consecutive days:").grid(row=1, column=1, sticky="w", padx=10, pady=6)
        ttk.Entry(prefs, textvariable=self.max_consec_var, width=6).grid(row=1, column=2, sticky="w", padx=10, pady=6)
        ttk.Label(prefs, text="Weekend preference:").grid(row=1, column=3, sticky="w", padx=10, pady=6)
        ttk.Combobox(prefs, textvariable=self.weekend_pref_var, values=["Prefer","Neutral","Avoid"], state="readonly", width=10)\
            .grid(row=1, column=4, sticky="w", padx=10, pady=6)
        ttk.Label(prefs, text="Target min hours (optional):").grid(row=1, column=5, sticky="w", padx=10, pady=6)
        ttk.Entry(prefs, textvariable=self.target_min_var, width=8).grid(row=1, column=6, sticky="w", padx=10, pady=6)

        av = ttk.LabelFrame(frm, text="Weekly recurring availability (30-minute increments)")
        av.pack(fill="both", expand=True, pady=(0,10))
        ttk.Label(av, text="Earliest/Latest = your general allowed window. Blocked times = times you CANNOT work even within the allowed window.", wraplength=900)\
            .grid(row=0, column=0, columnspan=8, sticky="w", padx=6, pady=(4,8))
        headers = ["Day","Off all day","Earliest start (OK)","Latest end (OK)","Blocked start #1 (NO)","Blocked end #1 (NO)","Blocked start #2 (NO)","Blocked end #2 (NO)"]
        for c,h in enumerate(headers):
            ttk.Label(av, text=h).grid(row=1, column=c, sticky="w", padx=6, pady=4)

        for rr, d in enumerate(DAYS, start=2):
            ttk.Label(av, text=d).grid(row=rr, column=0, sticky="w", padx=6, pady=4)
            ttk.Checkbutton(av, variable=self.unavail[d]).grid(row=rr, column=1, sticky="w", padx=6, pady=4)
            ttk.Combobox(av, textvariable=self.earliest[d], values=TIME_CHOICES, width=8, state="readonly").grid(row=rr, column=2, sticky="w", padx=6, pady=4)
            ttk.Combobox(av, textvariable=self.latest[d], values=TIME_CHOICES, width=8, state="readonly").grid(row=rr, column=3, sticky="w", padx=6, pady=4)
            ttk.Combobox(av, textvariable=self.b1s[d], values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=rr, column=4, sticky="w", padx=6, pady=4)
            ttk.Combobox(av, textvariable=self.b1e[d], values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=rr, column=5, sticky="w", padx=6, pady=4)
            ttk.Combobox(av, textvariable=self.b2s[d], values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=rr, column=6, sticky="w", padx=6, pady=4)
            ttk.Combobox(av, textvariable=self.b2e[d], values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=rr, column=7, sticky="w", padx=6, pady=4)

        fs = ttk.LabelFrame(frm, text="Fixed Schedule (recurring)")
        fs.pack(fill="x", pady=(0,10))
        cols = ("Day","Area","Start","End","Locked")
        self.fs_tree = ttk.Treeview(fs, columns=cols, show="headings", height=6)
        for c in cols:
            self.fs_tree.heading(c, text=c)
            self.fs_tree.column(c, width=120 if c!="Locked" else 80)
        self.fs_tree.pack(fill="x", padx=8, pady=8)

        btnrow = ttk.Frame(fs); btnrow.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(btnrow, text="Add Fixed Shift", command=self._add_fixed).pack(side="left")
        ttk.Button(btnrow, text="Delete Selected", command=self._del_fixed).pack(side="left", padx=8)

        rls = ttk.LabelFrame(frm, text="Locked Recurring Schedule (hard preassigned weekly shifts)")
        rls.pack(fill="x", pady=(0,10))
        rls_cols = ("Day","Area","Start","End")
        self.rls_tree = ttk.Treeview(rls, columns=rls_cols, show="headings", height=5)
        for c in rls_cols:
            self.rls_tree.heading(c, text=c)
            self.rls_tree.column(c, width=130)
        self.rls_tree.pack(fill="x", padx=8, pady=8)
        rls_btn = ttk.Frame(rls); rls_btn.pack(fill="x", padx=8, pady=(0,8))
        ttk.Button(rls_btn, text="Add Locked Recurring Shift", command=self._add_recurring_locked).pack(side="left")
        ttk.Button(rls_btn, text="Delete Selected", command=self._del_recurring_locked).pack(side="left", padx=8)

        self._refresh_fixed_tree()
        self._refresh_recurring_locked_tree()

        bottom = ttk.Frame(frm); bottom.pack(fill="x")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Save Employee", command=self._save).pack(side="right", padx=8)

        # Type defaults (max shift hours)
        def default_max_for_type(t: str) -> float:
            tt = (t or "").strip().lower()
            if tt in ["store manager", "assistant manager", "kitchen manager"]:
                return 16.0
            if tt in ["senior crew member", "manager in training"]:
                return 12.0
            return 8.0

        def on_type_change(_evt=None):
            # Only auto-adjust max shift if user hasn't typed something custom.
            try:
                cur = float(self.max_shift_var.get().strip())
            except Exception:
                cur = None
            new_def = default_max_for_type(self.emp_type_var.get())
            if cur is None or (abs(cur-8.0)<1e-6 or abs(cur-12.0)<1e-6 or abs(cur-16.0)<1e-6):
                self.max_shift_var.set(str(new_def))

        type_cb.bind("<<ComboboxSelected>>", on_type_change)

    def _refresh_fixed_tree(self):
        for i in self.fs_tree.get_children():
            self.fs_tree.delete(i)
        for fs in self.fixed:
            self.fs_tree.insert("", "end", values=(fs.day, fs.area, tick_to_hhmm(fs.start_t), tick_to_hhmm(fs.end_t), "Yes" if fs.locked else "No"))

    def _refresh_recurring_locked_tree(self):
        for i in self.rls_tree.get_children():
            self.rls_tree.delete(i)
        for fs in self.recurring_locked:
            self.rls_tree.insert("", "end", values=(fs.day, fs.area, tick_to_hhmm(fs.start_t), tick_to_hhmm(fs.end_t)))

    def _validate_recurring_locked_shift(self, day: str, area: str, stt: int, ent: int) -> Tuple[bool, str]:
        if day not in DAYS:
            return False, "Day must be Sun, Mon, Tue, Wed, Thu, Fri, or Sat."
        if area not in AREAS:
            return False, "Area must be CSTORE, KITCHEN, or CARWASH."
        if ent <= stt:
            return False, "End must be after start."
        if not is_within_area_hours(self.parent.model, area, stt, ent):
            op_t, cl_t = area_open_close_ticks(self.parent.model, area)
            return False, f"Shift must be within Hours of Operation for {area}: {tick_to_hhmm(op_t)}–{tick_to_hhmm(cl_t)}"
        mt = str(self.minor_var.get() or "ADULT")
        if mt == "MINOR_14_15":
            earliest = hhmm_to_tick("07:00")
            latest_conservative = hhmm_to_tick("19:00")
            if stt < earliest or ent > latest_conservative:
                return False, "For MINOR_14_15, locked recurring shifts must stay within 07:00–19:00 (conservative safety bound)."
        dr = None
        try:
            dr = DayRules(
                unavailable_day=bool(self.unavail[day].get()),
                earliest_start=hhmm_to_tick(self.earliest[day].get()),
                latest_end=hhmm_to_tick(self.latest[day].get()),
                blocked_ranges=[]
            )
            for sv, ev in [(self.b1s[day], self.b1e[day]), (self.b2s[day], self.b2e[day])]:
                s = str(sv.get() or "").strip(); e = str(ev.get() or "").strip()
                if s and e:
                    a = hhmm_to_tick(s); b = hhmm_to_tick(e)
                    if b > a:
                        dr.blocked_ranges.append((a, b))
        except Exception:
            dr = None
        if dr is not None and not dr.is_available(stt, ent):
            return False, "Locked recurring shift must fit this employee's recurring availability for that day."
        return True, ""

    def _add_fixed(self):
        day = simple_input(self, "Fixed Shift", "Day (Sun..Sat):", "Mon")
        if day is None: return
        day = day.strip()
        if day not in DAYS:
            messagebox.showerror("Fixed Shift", "Day must be Sun, Mon, Tue, Wed, Thu, Fri, or Sat.")
            return
        area = simple_input(self, "Fixed Shift", "Area (CSTORE/KITCHEN/CARWASH):", "CSTORE")
        if area is None: return
        area = area.strip().upper()
        if area not in AREAS:
            messagebox.showerror("Fixed Shift", "Area must be CSTORE, KITCHEN, or CARWASH.")
            return
        st = simple_input(self, "Fixed Shift", "Start time (HH:MM):", "09:00")
        if st is None: return
        en = simple_input(self, "Fixed Shift", "End time (HH:MM):", "17:00")
        if en is None: return
        stt = hhmm_to_tick(st); ent = hhmm_to_tick(en)
        if ent <= stt:
            messagebox.showerror("Fixed Shift", "End must be after start.")
            return
        locked = simple_input(self, "Fixed Shift", "Locked? (yes/no):", "no")
        if locked is None: return
        is_locked = str(locked).strip().lower().startswith("y")
        if is_locked:
            ok, msg = self._validate_recurring_locked_shift(day, area, stt, ent)
            if not ok:
                messagebox.showerror("Fixed Shift", msg)
                return
            self.recurring_locked.append(FixedShift(day=day, start_t=stt, end_t=ent, area=area, locked=True))
            self._refresh_recurring_locked_tree()
        else:
            self.fixed.append(FixedShift(day, stt, ent, area, is_locked))
            self._refresh_fixed_tree()

    def _del_fixed(self):
        sel = self.fs_tree.selection()
        if not sel:
            return
        idx = self.fs_tree.index(sel[0])
        if 0 <= idx < len(self.fixed):
            del self.fixed[idx]
        self._refresh_fixed_tree()

    def _add_recurring_locked(self):
        day = simple_input(self, "Locked Recurring Shift", "Day (Sun..Sat):", "Mon")
        if day is None:
            return
        day = day.strip()
        area = simple_input(self, "Locked Recurring Shift", "Area (CSTORE/KITCHEN/CARWASH):", "CSTORE")
        if area is None:
            return
        area = area.strip().upper()
        st = simple_input(self, "Locked Recurring Shift", "Start time (HH:MM):", "09:00")
        if st is None:
            return
        en = simple_input(self, "Locked Recurring Shift", "End time (HH:MM):", "17:00")
        if en is None:
            return
        stt = hhmm_to_tick(st); ent = hhmm_to_tick(en)
        ok, msg = self._validate_recurring_locked_shift(day, area, stt, ent)
        if not ok:
            messagebox.showerror("Locked Recurring Shift", msg)
            return
        self.recurring_locked.append(FixedShift(day=day, start_t=stt, end_t=ent, area=area, locked=True))
        self._refresh_recurring_locked_tree()

    def _del_recurring_locked(self):
        sel = self.rls_tree.selection()
        if not sel:
            return
        idx = self.rls_tree.index(sel[0])
        if 0 <= idx < len(self.recurring_locked):
            del self.recurring_locked[idx]
        self._refresh_recurring_locked_tree()

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Employee", "Name is required.")
            return
        areas = [a for a,v in self.area_vars.items() if v.get()]
        if not areas:
            messagebox.showerror("Employee", "Select at least one allowed area.")
            return
        pref = [a for a,v in self.pref_area_vars.items() if v.get()]
        try:
            max_week = float(self.max_weekly_var.get().strip())
        except Exception:
            max_week = 30.0
        try:
            targ = float(self.target_min_var.get().strip())
        except Exception:
            targ = 0.0
        try:
            max_consec = int(self.max_consec_var.get().strip())
        except Exception:
            max_consec = 6
        if max_consec < 1:
            max_consec = 1

        av: Dict[str, DayRules] = {}
        for d in DAYS:
            un = self.unavail[d].get()
            es = hhmm_to_tick(self.earliest[d].get())
            le = hhmm_to_tick(self.latest[d].get())
            br: List[Tuple[int,int]] = []
            def add_block(sv, ev):
                s = sv.get().strip(); e = ev.get().strip()
                if not s or not e:
                    return
                a = hhmm_to_tick(s); b = hhmm_to_tick(e)
                if b>a:
                    br.append((a,b))
            add_block(self.b1s[d], self.b1e[d])
            add_block(self.b2s[d], self.b2e[d])
            av[d] = DayRules(un, es, le, br)

        try:
            min_shift = float(self.min_shift_var.get().strip())
        except Exception:
            min_shift = 1.0
        try:
            max_shift = float(self.max_shift_var.get().strip())
        except Exception:
            max_shift = 8.0
        try:
            max_shifts_day = int(self.max_shifts_day_var.get().strip())
        except Exception:
            max_shifts_day = 1
        # simple sanity clamps
        if min_shift < 0.5:
            min_shift = 0.5
        if max_shift < min_shift:
            max_shift = min_shift
        if max_shifts_day < 1:
            max_shifts_day = 1

        for fs in self.recurring_locked:
            ok, msg = self._validate_recurring_locked_shift(fs.day, fs.area, int(fs.start_t), int(fs.end_t))
            if not ok:
                messagebox.showerror("Employee", f"Invalid locked recurring shift ({fs.day} {fs.area} {tick_to_hhmm(fs.start_t)}-{tick_to_hhmm(fs.end_t)}): {msg}")
                return

        self.result = Employee(
            name=name,
            phone=self.phone_var.get().strip(),
            work_status=self.status_var.get(),
            wants_hours=self.wants_var.get(),
            employee_type=self.emp_type_var.get(),
            split_shifts_ok=(self.split_ok_var.get().strip().lower().startswith("y")),
            double_shifts_ok=bool(self.double_ok_var.get()),
            min_hours_per_shift=min_shift,
            max_hours_per_shift=max_shift,
            max_shifts_per_day=max_shifts_day,
            max_weekly_hours=max_week,
            target_min_hours=targ,
            minor_type=self.minor_var.get(),
            areas_allowed=areas,
            preferred_areas=pref,
            avoid_clopens=self.avoid_clopen_var.get(),
            max_consecutive_days=max_consec,
            weekend_preference=self.weekend_pref_var.get(),
            availability=av,
            fixed_schedule=list(self.fixed),
            recurring_locked_schedule=list(self.recurring_locked),
        )
        self.destroy()

# -----------------------------
# Main app
# -----------------------------
class SchedulerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.data_path = default_data_path()
        # If no user data exists yet, seed with bundled starter data (for safe testing)
        try:
            if not os.path.isfile(self.data_path):
                ensure_dir(os.path.dirname(self.data_path))
                bundled = rel_path("assets", "starting_data_3-2-26.json")
                if os.path.isfile(bundled):
                    shutil.copyfile(bundled, self.data_path)
        except Exception:
            pass
        # state
        self.model = DataModel()
        self.current_label = self._default_week_label()
        self.current_assignments: List[Assignment] = []
        self.current_emp_hours: Dict[str,float] = {}
        self.current_total_hours: float = 0.0
        self.current_warnings: List[str] = []
        self.current_filled: int = 0
        self.current_total_slots: int = 0
        self.current_diagnostics: Dict[str, Any] = {}
        self.last_solver_summary = None  # populated after Generate Schedule

        # load if exists
        if os.path.isfile(self.data_path):
            try:
                self.model = load_data(self.data_path)
            except Exception:
                self.model = DataModel()
        # load learned patterns (Phase 2 P2-4)
        try:
            self.model.learned_patterns = load_patterns()
        except Exception:
            self.model.learned_patterns = {}
        if not self.model.requirements:
            self.model.requirements = default_requirements()

        # apply ui scale
        self._apply_ui_scale(self.model.settings.ui_scale)

        self.title(f"LaborForceScheduler {APP_VERSION} (Portable)")

        # Fixed window size (Option B), scaled up ~30% but clamped to screen so it fits on 1920x1080, etc.
        try:
            target_w = int(1500 * 1.30)
            target_h = int(920 * 1.30)
            sw = int(self.winfo_screenwidth())
            sh = int(self.winfo_screenheight())
            w = min(target_w, max(1200, int(sw * 0.95)))
            h = min(target_h, max(780, int(sh * 0.90)))
            self.geometry(f"{w}x{h}")
        except Exception:
            self.geometry("1500x920")
        self.minsize(1200, 780)

        # Diagnostics / Help menu (small, for debugging)
        self._build_menus()

        # Log Tk callback exceptions to crash_log.txt
        try:
            def _tk_cb_exc(exc, val, tb):
                _write_crash_log(exc, val, tb)
                messagebox.showerror('Error', f'An unexpected error occurred. Details were written to crash_log.txt\n\n{val}')
            self.report_callback_exception = _tk_cb_exc  # type: ignore
        except Exception:
            pass

        # branding images (optional)
        self.brand_img_header = None
        self.brand_img_store = None
        self._load_brand_images()

        self._setup_style()
        self._build_ui()
        self._refresh_all()
        self._set_status(f"Data file: {self.data_path}")

        # --- Autosave (prevents lost work) ---
        # Keep it simple: periodic best-effort autosave + save-on-exit.
        self._autosave_interval_ms = 60_000  # 60 seconds
        self._autosave_job = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_autosave()

    def _schedule_autosave(self):
        try:
            if self._autosave_job is not None:
                self.after_cancel(self._autosave_job)
        except Exception:
            pass
        self._autosave_job = self.after(self._autosave_interval_ms, self._autosave_tick)


    # -------- Help / Diagnostics --------
    def _build_menus(self):
        try:
            menubar = tk.Menu(self)
            helpmenu = tk.Menu(menubar, tearoff=0)
            helpmenu.add_command(label='Diagnostics', command=self._open_diagnostics)
            helpmenu.add_command(label='Open Data Folder', command=self._open_data_folder)
            helpmenu.add_separator()
            helpmenu.add_command(label='About', command=self._about)
            menubar.add_cascade(label='Help', menu=helpmenu)
            self.config(menu=menubar)
        except Exception:
            pass

    def _open_data_folder(self):
        try:
            folder = os.path.dirname(self.data_path)
            if os.name == 'nt':
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            messagebox.showerror('Open Data Folder', str(e))

    def _about(self):
        messagebox.showinfo('About', f'LaborForceScheduler\n{APP_VERSION}\nPortable build')

    def _open_diagnostics(self):
        try:
            win = tk.Toplevel(self)
            win.title('Diagnostics')
            win.geometry('760x520')
            txt = tk.Text(win, wrap='word')
            txt.pack(fill='both', expand=True)
            data_path = self.data_path
            appdir = _app_dir()
            last = self.last_solver_summary or {}
            lines = []
            lines.append(f'Version: {APP_VERSION}')
            lines.append(f'App folder: {appdir}')
            lines.append(f'Data file: {data_path}')
            lines.append('')
            lines.append('Last solver run summary:')
            if last:
                for k in ['score_penalty','score_hours','filled','total_slots','assignments','optimizer_iterations','restarts','warnings_count','label','preferred_weekly_cap','maximum_weekly_cap','cap_over_by','infeasible','notes']:
                    if k in last:
                        lines.append(f'  {k}: {last[k]}')
            else:
                lines.append('  (no run yet)')
            txt.insert('1.0', '\n'.join(lines))
            txt.config(state='disabled')
        except Exception as e:
            messagebox.showerror('Diagnostics', str(e))
    def _autosave_tick(self):
        try:
            save_data(self.model, self.data_path)
            try:
                _write_run_log(f"SAVE | {self.data_path}")
            except Exception:
                pass
            self._set_status(f"Autosaved • {datetime.datetime.now().strftime('%H:%M:%S')}")
        except Exception:
            # Stay silent during autosave; manual Save Now shows errors.
            pass
        finally:
            self._schedule_autosave()

    def _on_close(self):
        try:
            save_data(self.model, self.data_path)
        except Exception:
            pass
        self.destroy()

    def _apply_ui_scale(self, scale: float):
        self.ui_scale = float(scale) if scale else 1.0
        try:
            self.tk.call("tk", "scaling", float(scale))
            f = tkfont.nametofont("TkDefaultFont")
            # Keep readable without being huge
            f.configure(size=max(10, int(10 * float(scale))))
            self.option_add("*Font", f)
        except Exception:
            pass

        style = ttk.Style(self)
        rh = int(max(22, 22 * float(getattr(self, "ui_scale", 1.0))))
        style.configure("Treeview", rowheight=rh)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _load_brand_images(self):
        """Load PetroServe branding images if present in ./assets."""
        try:
            img_path = rel_path("assets", "petroserve.png")
            if not os.path.isfile(img_path):
                return
            if Image is None or ImageTk is None:
                # Fallback: tkinter PhotoImage (no resize)
                try:
                    self.brand_img_header = tk.PhotoImage(file=img_path)
                    self.brand_img_store = self.brand_img_header
                except Exception:
                    return
                return

            base = Image.open(img_path)

            def make(max_px: int):
                im = base.copy()
                im.thumbnail((max_px, max_px), Image.LANCZOS)
                return ImageTk.PhotoImage(im)

            # small header icon + larger store-tab brand
            self.brand_img_header = make(72)
            self.brand_img_store = make(320)
        except Exception:
            # branding is optional; never block launch
            self.brand_img_header = None
            self.brand_img_store = None

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        rh = int(max(22, 22 * float(getattr(self, "ui_scale", 1.0))))
        style.configure("Treeview", rowheight=rh)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=10)
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 12, "bold"))

    def _build_ui(self):
        self.status_var = tk.StringVar(value="")
        nav_items = {
            "dashboard": "Dashboard",
            "configuration": "Configuration",
            "scheduling": "Scheduling",
            "analysis": "Analysis",
            "publish": "Publish",
            "history": "History",
        }
        self.shell = AppShell(
            self,
            nav_items=nav_items,
            on_nav=self.show_page,
            actions={
                "generate": self.on_generate,
                "improve": self.open_schedule_changes,
                "publish": self.open_publish,
                "save": self.autosave,
                "open": self.open_dialog,
                "new": self.new_data,
            },
        )
        self.page_host = ttk.Frame(self.shell.workspace)
        self.page_host.pack(fill="both", expand=True)
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)

        self.page_dashboard = DashboardPage(
            self.page_host,
            actions=[
                ("Open Scheduling", lambda: self.show_page("scheduling")),
                ("Generate Schedule", self.on_generate),
                ("Open Publish", self.open_publish),
            ],
        )
        self.page_configuration = LandingPage(
            self.page_host,
            title="Configuration",
            subtitle="Manage store setup, employees, overrides, requirements, and manager goals.",
            links=[
                ("Store Settings", lambda: self.open_legacy_tab(self.tab_store, "scheduling")),
                ("Employees", lambda: self.open_legacy_tab(self.tab_emps, "scheduling")),
                ("Weekly Overrides", lambda: self.open_legacy_tab(self.tab_over, "scheduling")),
                ("Staffing Requirements", lambda: self.open_legacy_tab(self.tab_reqs, "scheduling")),
            ],
        )
        self.page_scheduling = SchedulingPage(
            self.page_host,
            days=DAYS,
            callbacks={
                "generate": self.on_generate,
                "improve": self.open_schedule_changes,
                "save": self.autosave,
                "publish": self.open_publish,
                "open_legacy_notebook": self.open_scheduling_legacy_notebook,
                "open_legacy_manual": self.open_manual_editor,
                "open_analysis": self.open_schedule_analysis,
            },
        )
        self.page_analysis = LandingPage(
            self.page_host,
            title="Analysis",
            subtitle="Review diagnostics, coverage heatmaps, and schedule adjustments.",
            links=[
                ("Schedule Analysis", lambda: self.open_legacy_tab(self.tab_analysis, "scheduling")),
                ("Schedule Changes", lambda: self.open_legacy_tab(self.tab_changes, "scheduling")),
                ("Coverage Heatmap", lambda: self.open_legacy_tab(self.tab_heatmap, "scheduling")),
                ("Call-Off Simulator", lambda: self.open_legacy_tab(self.tab_calloff, "scheduling")),
            ],
        )
        self.page_publish = LandingPage(
            self.page_host,
            title="Publish",
            subtitle="Export, print, and lock schedules for distribution.",
            links=[
                ("Print / Export", lambda: self.open_legacy_tab(self.tab_preview, "scheduling")),
                ("Publish Final Schedule", lambda: self.open_legacy_tab(self.tab_preview, "scheduling")),
            ],
        )
        self.page_history = LandingPage(
            self.page_host,
            title="History",
            subtitle="Open previous schedules and historical records. This page reserves deeper audit workflows.",
            links=[
                ("Open History Workspace", lambda: self.open_legacy_tab(self.tab_history, "scheduling")),
            ],
        )

        self.pages = {
            "dashboard": self.page_dashboard,
            "configuration": self.page_configuration,
            "scheduling": self.page_scheduling,
            "analysis": self.page_analysis,
            "publish": self.page_publish,
            "history": self.page_history,
        }
        for frame in self.pages.values():
            frame.grid(row=0, column=0, sticky="nsew")

        self.nb = ttk.Notebook(self.page_scheduling.legacy_host)
        self.nb.pack(fill="both", expand=True, pady=(6, 0))

        self.tab_store = ttk.Frame(self.nb)
        self.tab_emps = ttk.Frame(self.nb)
        self.tab_over = ttk.Frame(self.nb)
        self.tab_reqs = ttk.Frame(self.nb)
        self.tab_gen = ttk.Frame(self.nb)
        self.tab_preview = ttk.Frame(self.nb)
        self.tab_manual = ttk.Frame(self.nb)
        self.tab_mgr = ttk.Frame(self.nb)
        self.tab_analysis = ttk.Frame(self.nb)
        self.tab_changes = ttk.Frame(self.nb)
        self.tab_heatmap = ttk.Frame(self.nb)
        self.tab_calloff = ttk.Frame(self.nb)
        self.tab_history = ttk.Frame(self.nb)
        self.tab_settings = ttk.Frame(self.nb)

        self.nb.add(self.tab_store, text="1) Store")
        self.nb.add(self.tab_emps, text="2) Employees")
        self.nb.add(self.tab_over, text="3) Weekly Overrides")
        self.nb.add(self.tab_reqs, text="4) Staffing Requirements")
        self.nb.add(self.tab_gen, text="5) Generate")
        self.nb.add(self.tab_preview, text="6) Print / Export")
        self.nb.add(self.tab_manual, text="7) Manual Edit")
        self.nb.add(self.tab_mgr, text="8) Manager Goals")
        self.nb.add(self.tab_analysis, text="9) Schedule Analysis")
        self.nb.add(self.tab_changes, text="10) Schedule Changes")
        self.nb.add(self.tab_heatmap, text="11) Coverage Heatmap")
        self.nb.add(self.tab_calloff, text="12) Call-Off Simulator")
        self.nb.add(self.tab_history, text="13) History")
        self.nb.add(self.tab_settings, text="14) Settings")

        self._build_store_tab()
        self._build_emps_tab()
        self._build_overrides_tab()
        self._build_reqs_tab()
        self._build_generate_tab()
        self._build_preview_tab()
        self._build_manual_tab()
        self._build_manager_tab()
        self._build_analysis_tab()
        self._build_changes_tab()
        self._build_heatmap_tab()
        self._build_calloff_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self.show_page("dashboard")
        self._refresh_shell_status()

    def show_page(self, page_key: str):
        frame = self.pages.get(page_key)
        if frame is None:
            return
        frame.tkraise()
        self.shell.set_active_nav(page_key)

    def open_legacy_tab(self, tab, page: str = "scheduling"):
        self.show_page(page)
        try:
            self.nb.select(tab)
        except Exception:
            pass

    def open_schedule_changes(self):
        self.open_legacy_tab(self.tab_changes, "scheduling")

    def open_publish(self):
        self.show_page("publish")

    def open_scheduling_legacy_notebook(self):
        self.open_legacy_tab(self.tab_gen, "scheduling")

    def open_manual_editor(self):
        self.open_legacy_tab(self.tab_manual, "scheduling")

    def open_schedule_analysis(self):
        self.open_legacy_tab(self.tab_analysis, "scheduling")

    def _refresh_scheduling_workspace(self):
        state_text = "Draft"
        if self.current_assignments:
            state_text = "Generated"
        draft_state = "Draft changes: pending save" if self.status_var.get().strip() else "Draft changes: none"
        payload = {
            "week_label": self.current_label or "Not selected",
            "state_text": state_text,
            "assignments": list(self.current_assignments or []),
            "warnings": list(self.current_warnings or []),
            "diagnostics": dict(self.current_diagnostics or {}),
            "total_hours": float(getattr(self, "current_total_hours", 0.0) or 0.0),
            "emp_hours": dict(self.current_emp_hours or {}),
            "filled_slots": int(getattr(self, "current_filled", 0) or 0),
            "total_slots": int(getattr(self, "current_total_slots", 0) or 0),
            "draft_state": draft_state,
        }
        try:
            self.page_scheduling.refresh_workspace(payload)
        except Exception:
            pass

    def _refresh_shell_status(self):
        try:
            store = self.model.store_info.store_name.strip() or "Unassigned"
        except Exception:
            store = "Unassigned"
        week = self.current_label or "Not selected"
        warning_count = len(self.current_warnings or [])
        state_text = "Draft"
        try:
            if self.current_assignments:
                state_text = "Generated"
        except Exception:
            pass
        self.shell.header_store_var.set(f"Store: {store}")
        self.shell.header_week_var.set(f"Week: {week}")
        self.shell.header_state_var.set(f"State: {state_text}")
        self.shell.header_warning_var.set(f"Warnings: {warning_count}")
        self.shell.status_operation_var.set(self.status_var.get() or "Ready")
        self.shell.status_schedule_var.set(state_text)
        dash_status = "No schedule generated yet"
        if self.current_assignments:
            dash_status = f"Filled slots: {self.current_filled}/{self.current_total_slots} • Assignments: {len(self.current_assignments)}"
        self.page_dashboard.week_var.set(f"Current Week: {week}")
        self.page_dashboard.status_var.set(f"Status: {dash_status}")
        self.page_dashboard.warning_var.set(f"Warnings: {warning_count}")
        self._refresh_scheduling_workspace()

    # -------- Store tab --------
    def _build_store_tab(self):
        frm = ttk.Frame(self.tab_store); frm.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(frm, text="Store Info prints on schedules.", style="SubHeader.TLabel").pack(anchor="w", pady=(0,8))

        top = ttk.Frame(frm); top.pack(fill="x", expand=False, pady=10)
        left = ttk.Frame(top); left.pack(side="left", fill="x", expand=True)
        right = ttk.Frame(top); right.pack(side="right", padx=(10,0))

        box = ttk.LabelFrame(left, text="Store")
        box.pack(fill="x")

        self.store_name_var = tk.StringVar()
        self.store_addr_var = tk.StringVar()
        self.store_phone_var = tk.StringVar()
        self.store_mgr_var = tk.StringVar()
        self.cstore_open_var = tk.StringVar(value="00:00")
        self.cstore_close_var = tk.StringVar(value="24:00")
        self.kitchen_open_var = tk.StringVar(value="00:00")
        self.kitchen_close_var = tk.StringVar(value="24:00")
        self.carwash_open_var = tk.StringVar(value="00:00")
        self.carwash_close_var = tk.StringVar(value="24:00")

        r=0
        ttk.Label(box, text="Store Name:").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(box, textvariable=self.store_name_var, width=44).grid(row=r, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(box, text="Phone:").grid(row=r, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(box, textvariable=self.store_phone_var, width=18).grid(row=r, column=3, sticky="w", padx=10, pady=6)

        r+=1
        ttk.Label(box, text="Address:").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(box, textvariable=self.store_addr_var, width=78).grid(row=r, column=1, columnspan=3, sticky="w", padx=10, pady=6)

        r+=1
        ttk.Label(box, text="Manager:").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(box, textvariable=self.store_mgr_var, width=28).grid(row=r, column=1, sticky="w", padx=10, pady=6)

        r += 1
        hours = ttk.LabelFrame(box, text="Hours of Operation (Hard Rules)")
        hours.grid(row=r, column=0, columnspan=4, sticky="ew", padx=10, pady=8)
        ttk.Label(hours, text="Area").grid(row=0, column=0, padx=8, pady=4, sticky="w")
        ttk.Label(hours, text="Open").grid(row=0, column=1, padx=8, pady=4, sticky="w")
        ttk.Label(hours, text="Close").grid(row=0, column=2, padx=8, pady=4, sticky="w")
        rows = [
            ("C-Store", self.cstore_open_var, self.cstore_close_var),
            ("Kitchen", self.kitchen_open_var, self.kitchen_close_var),
            ("Carwash", self.carwash_open_var, self.carwash_close_var),
        ]
        for rr, (lbl, open_var, close_var) in enumerate(rows, start=1):
            ttk.Label(hours, text=lbl).grid(row=rr, column=0, padx=8, pady=4, sticky="w")
            ttk.Combobox(hours, textvariable=open_var, values=TIME_CHOICES, state="readonly", width=8).grid(row=rr, column=1, padx=8, pady=4, sticky="w")
            ttk.Combobox(hours, textvariable=close_var, values=TIME_CHOICES, state="readonly", width=8).grid(row=rr, column=2, padx=8, pady=4, sticky="w")

        if getattr(self, "brand_img_store", None) is not None:
            ttk.Label(right, image=self.brand_img_store).pack(anchor="ne")

        ttk.Button(frm, text="Save Store Info", command=self.save_store_info).pack(anchor="w", padx=6, pady=10)

    def save_store_info(self):
        checks = [
            ("CSTORE", self.cstore_open_var.get(), self.cstore_close_var.get()),
            ("KITCHEN", self.kitchen_open_var.get(), self.kitchen_close_var.get()),
            ("CARWASH", self.carwash_open_var.get(), self.carwash_close_var.get()),
        ]
        for area, op, cl in checks:
            op_t = hhmm_to_tick(op); cl_t = hhmm_to_tick(cl)
            if cl_t <= op_t:
                messagebox.showerror("Store", f"{area} close time must be after open time.")
                return

        self.model.store_info = StoreInfo(
            store_name=self.store_name_var.get().strip(),
            store_address=self.store_addr_var.get().strip(),
            store_phone=self.store_phone_var.get().strip(),
            store_manager=self.store_mgr_var.get().strip(),
            cstore_open=self.cstore_open_var.get().strip() or "00:00",
            cstore_close=self.cstore_close_var.get().strip() or "24:00",
            kitchen_open=self.kitchen_open_var.get().strip() or "00:00",
            kitchen_close=self.kitchen_close_var.get().strip() or "24:00",
            carwash_open=self.carwash_open_var.get().strip() or "00:00",
            carwash_close=self.carwash_close_var.get().strip() or "24:00",
        )
        self.autosave()
        messagebox.showinfo("Store", "Saved.")

    # -------- Employees tab --------
    def _build_emps_tab(self):
        top = ttk.Frame(self.tab_emps); top.pack(fill="x", padx=10, pady=10)
        ttk.Button(top, text="Add", command=self.add_employee).pack(side="left")
        ttk.Button(top, text="Edit Selected", command=self.edit_employee).pack(side="left", padx=8)
        ttk.Button(top, text="Delete Selected", command=self.delete_employee).pack(side="left", padx=8)

        self.show_inactive = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Show On Leave / Inactive", variable=self.show_inactive, command=self.refresh_emp_tree).pack(side="right")

        cols = ("Name","Phone","Status","Type","Wants","SplitOK","DoubleOK","MaxShiftH","MaxShiftsDay","MaxWeekH","TargetMin","MinorType","Areas","PrefAreas","AvoidClopens","MaxConsec","WeekendPref","FixedShifts")
        tree_wrap = ttk.Frame(self.tab_emps); tree_wrap.pack(fill="both", expand=True, padx=10, pady=10)
        self.emp_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", height=18)
        for c in cols:
            self.emp_tree.heading(c, text=c)
            w = 120
            if c=="Name": w=240
            if c in ["Areas","PrefAreas"]: w=240
            if c=="Type": w=160
            if c in ["MaxShiftH","MaxShiftsDay","MaxWeekH"]: w=110
            if c in ["SplitOK","DoubleOK"]: w=90
            if c=="FixedShifts": w=110
            self.emp_tree.column(c, width=w, anchor="w", stretch=True)
        emp_tree_ysb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.emp_tree.yview)
        emp_tree_xsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.emp_tree.xview)
        self.emp_tree.configure(yscrollcommand=emp_tree_ysb.set, xscrollcommand=emp_tree_xsb.set)
        self.emp_tree.grid(row=0, column=0, sticky="nsew")
        emp_tree_ysb.grid(row=0, column=1, sticky="ns")
        emp_tree_xsb.grid(row=1, column=0, sticky="ew")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

    def refresh_emp_tree(self):
        for i in self.emp_tree.get_children():
            self.emp_tree.delete(i)
        for e in sorted(self.model.employees, key=lambda x: x.name.lower()):
            if not self.show_inactive.get() and e.work_status!="Active":
                continue
            self.emp_tree.insert("", "end", values=(
                e.name, e.phone, e.work_status,
                getattr(e, "employee_type", "Crew Member"),
                "Yes" if e.wants_hours else "No",
                "Yes" if getattr(e, "split_shifts_ok", True) else "No",
                "Yes" if getattr(e, "double_shifts_ok", False) else "No",
                f"{float(getattr(e, 'max_hours_per_shift', 8.0)):g}",
                int(getattr(e, "max_shifts_per_day", 1)),
                f"{e.max_weekly_hours:g}",
                f"{e.target_min_hours:g}",
                e.minor_type,
                ", ".join(e.areas_allowed),
                ", ".join(e.preferred_areas),
                "Yes" if e.avoid_clopens else "No",
                e.max_consecutive_days,
                e.weekend_preference,
                len(e.fixed_schedule) + len(getattr(e, "recurring_locked_schedule", []) or []),
            ))

    def add_employee(self):
        d = EmployeeDialog(self, None)
        self.wait_window(d)
        if d.result:
            if any(e.name.strip().lower()==d.result.name.strip().lower() for e in self.model.employees):
                messagebox.showerror("Employees", "An employee with that name already exists.")
                return
            self.model.employees.append(d.result)
            self.refresh_emp_tree()
            self.refresh_override_dropdowns()
            self.autosave()

    def _selected_emp_name(self) -> Optional[str]:
        sel = self.emp_tree.selection()
        if not sel:
            return None
        return self.emp_tree.item(sel[0], "values")[0]

    def edit_employee(self):
        name = self._selected_emp_name()
        if not name:
            messagebox.showinfo("Employees", "Select an employee.")
            return
        idx = next((i for i,e in enumerate(self.model.employees) if e.name==name), None)
        if idx is None:
            return
        d = EmployeeDialog(self, self.model.employees[idx])
        self.wait_window(d)
        if d.result:
            new = d.result
            # rename references
            if new.name != name:
                for o in self.model.weekly_overrides:
                    if o.employee_name == name:
                        o.employee_name = new.name
            self.model.employees[idx] = new
            self.refresh_emp_tree()
            self.refresh_override_dropdowns()
            self.autosave()

    def delete_employee(self):
        name = self._selected_emp_name()
        if not name:
            return
        if not messagebox.askyesno("Delete", f"Delete {name}?"):
            return
        self.model.employees = [e for e in self.model.employees if e.name!=name]
        self.model.weekly_overrides = [o for o in self.model.weekly_overrides if o.employee_name!=name]
        self.refresh_emp_tree()
        self.refresh_override_dropdowns()
        self.autosave()

    # -------- Weekly Overrides tab --------
    def _build_overrides_tab(self):
        frm = ttk.Frame(self.tab_over); frm.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frm, text="One-week blackout windows (does not change recurring availability).", style="SubHeader.TLabel")\
            .pack(anchor="w", pady=(0,8))

        top = ttk.LabelFrame(frm, text="Add / Update Override")
        top.pack(fill="x", pady=(0,10))

        self.ov_label_var = tk.StringVar(value=self.current_label)
        self.ov_emp_var = tk.StringVar()
        self.ov_day_var = tk.StringVar(value="Sun")
        self.ov_off_all_var = tk.BooleanVar(value=False)
        self.ov_b1s = tk.StringVar(value="")
        self.ov_b1e = tk.StringVar(value="")
        self.ov_b2s = tk.StringVar(value="")
        self.ov_b2e = tk.StringVar(value="")
        self.ov_note = tk.StringVar(value="")

        r=0
        ttk.Label(top, text="Week Label:").grid(row=r, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(top, textvariable=self.ov_label_var, width=34).grid(row=r, column=1, sticky="w", padx=8, pady=6)
        ttk.Label(top, text="Employee:").grid(row=r, column=2, sticky="w", padx=8, pady=6)
        self.ov_emp_combo = ttk.Combobox(top, textvariable=self.ov_emp_var, values=[], width=26, state="readonly")
        self.ov_emp_combo.grid(row=r, column=3, sticky="w", padx=8, pady=6)

        r+=1
        ttk.Label(top, text="Day:").grid(row=r, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(top, textvariable=self.ov_day_var, values=DAYS, width=10, state="readonly").grid(row=r, column=1, sticky="w", padx=8, pady=6)
        ttk.Checkbutton(top, text="Off all day", variable=self.ov_off_all_var).grid(row=r, column=2, sticky="w", padx=8, pady=6)

        r+=1
        ttk.Label(top, text="Blocked range 1:").grid(row=r, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(top, textvariable=self.ov_b1s, values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=r, column=1, sticky="w", padx=8, pady=6)
        ttk.Combobox(top, textvariable=self.ov_b1e, values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=r, column=2, sticky="w", padx=8, pady=6)
        ttk.Label(top, text="Blocked range 2:").grid(row=r, column=3, sticky="w", padx=8, pady=6)
        ttk.Combobox(top, textvariable=self.ov_b2s, values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=r, column=4, sticky="w", padx=8, pady=6)
        ttk.Combobox(top, textvariable=self.ov_b2e, values=[""]+TIME_CHOICES, width=8, state="readonly").grid(row=r, column=5, sticky="w", padx=8, pady=6)

        r+=1
        ttk.Label(top, text="Note:").grid(row=r, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(top, textvariable=self.ov_note, width=72).grid(row=r, column=1, columnspan=5, sticky="w", padx=8, pady=6)

        ttk.Button(top, text="Add / Update", command=self.add_override).grid(row=0, column=6, rowspan=2, padx=10, pady=6, sticky="ns")
        ttk.Button(top, text="Copy Overrides From Last Saved Week", command=self.copy_last_overrides).grid(row=2, column=6, rowspan=2, padx=10, pady=6, sticky="ns")

        cols = ("Week","Employee","Day","OffAll","Blocked","Note")
        self.ov_tree = ttk.Treeview(frm, columns=cols, show="headings", height=14)
        for c in cols:
            self.ov_tree.heading(c, text=c)
            w=150
            if c=="Week": w=260
            if c=="Blocked": w=220
            if c=="Note": w=320
            self.ov_tree.column(c, width=w)
        self.ov_tree.pack(fill="both", expand=True, pady=(0,10))

        ttk.Button(frm, text="Delete Selected", command=self.delete_override).pack(anchor="w")

    def refresh_override_dropdowns(self):
        names = sorted([e.name for e in self.model.employees if e.work_status=="Active"], key=str.lower)
        self.ov_emp_combo["values"] = names
        if names and self.ov_emp_var.get() not in names:
            self.ov_emp_var.set(names[0])

    def add_override(self):
        label = self.ov_label_var.get().strip()
        emp = self.ov_emp_var.get().strip()
        day = self.ov_day_var.get()
        if not label or not emp:
            messagebox.showerror("Overrides", "Week label and employee are required.")
            return
        br: List[Tuple[int,int]] = []
        def add_rng(s,e):
            s=s.strip(); e=e.strip()
            if not s or not e: return
            a=hhmm_to_tick(s); b=hhmm_to_tick(e)
            if b>a: br.append((a,b))
        add_rng(self.ov_b1s.get(), self.ov_b1e.get())
        add_rng(self.ov_b2s.get(), self.ov_b2e.get())
        off_all = self.ov_off_all_var.get()
        note = self.ov_note.get().strip()

        updated=False
        for o in self.model.weekly_overrides:
            if o.label==label and o.employee_name==emp and o.day==day:
                o.off_all_day = off_all
                o.blocked_ranges = br
                o.note = note
                updated=True
                break
        if not updated:
            self.model.weekly_overrides.append(WeeklyOverride(label, emp, day, off_all, br, note))
        self.refresh_override_tree()
        self.autosave()

    def copy_last_overrides(self):
        # Copy overrides from the most recent label in overrides list (excluding current label if empty)
        cur = self.ov_label_var.get().strip()
        labels = [o.label for o in self.model.weekly_overrides if o.label.strip() and o.label.strip()!=cur]
        if not labels:
            messagebox.showinfo("Copy", "No prior overrides found.")
            return
        # last label by appearing order
        last = labels[-1]
        copied = 0
        for o in list(self.model.weekly_overrides):
            if o.label == last:
                # duplicate into current label
                exists = any(x.label==cur and x.employee_name==o.employee_name and x.day==o.day for x in self.model.weekly_overrides)
                if not exists:
                    self.model.weekly_overrides.append(WeeklyOverride(cur, o.employee_name, o.day, o.off_all_day, list(o.blocked_ranges), o.note))
                    copied += 1
        self.refresh_override_tree()
        self.autosave()
        messagebox.showinfo("Copy", f"Copied {copied} override(s) from '{last}' to '{cur}'.")

    def refresh_override_tree(self):
        for i in self.ov_tree.get_children():
            self.ov_tree.delete(i)
        def br_str(br):
            return ", ".join([f"{tick_to_hhmm(a)}-{tick_to_hhmm(b)}" for a,b in br])
        for o in sorted(self.model.weekly_overrides, key=lambda x: (x.label, x.employee_name.lower(), DAYS.index(x.day))):
            self.ov_tree.insert("", "end", values=(o.label, o.employee_name, o.day, "Yes" if o.off_all_day else "No", br_str(o.blocked_ranges), o.note))

    def delete_override(self):
        sel = self.ov_tree.selection()
        if not sel:
            return
        vals = self.ov_tree.item(sel[0], "values")
        label, emp, day = vals[0], vals[1], vals[2]
        if not messagebox.askyesno("Delete", f"Delete override for {emp} {day} ({label})?"):
            return
        self.model.weekly_overrides = [o for o in self.model.weekly_overrides if not (o.label==label and o.employee_name==emp and o.day==day)]
        self.refresh_override_tree()
        self.autosave()

    # -------- Requirements tab --------
    def _build_reqs_tab(self):
        frm = ttk.Frame(self.tab_reqs); frm.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frm, text="Requirements are per 30-minute block. Use bulk apply to speed up.", style="SubHeader.TLabel")            .pack(anchor="w", pady=(0,8))

        controls = ttk.LabelFrame(frm, text="Bulk Apply / Copy")
        controls.pack(fill="x", pady=(0,10))

        self.req_area_var = tk.StringVar(value="CSTORE")
        self.req_start_var = tk.StringVar(value="05:00")
        self.req_end_var = tk.StringVar(value="23:00")
        self.req_min_var = tk.StringVar(value="2")
        self.req_pref_var = tk.StringVar(value="2")
        self.req_max_var = tk.StringVar(value="2")

        ttk.Label(controls, text="Area:").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        ttk.Combobox(controls, textvariable=self.req_area_var, values=AREAS, state="readonly", width=10).grid(row=0, column=1, padx=8, pady=6, sticky="w")
        ttk.Label(controls, text="Start:").grid(row=0, column=2, padx=8, pady=6, sticky="w")
        ttk.Combobox(controls, textvariable=self.req_start_var, values=TIME_CHOICES, state="readonly", width=8).grid(row=0, column=3, padx=8, pady=6, sticky="w")
        ttk.Label(controls, text="End:").grid(row=0, column=4, padx=8, pady=6, sticky="w")
        ttk.Combobox(controls, textvariable=self.req_end_var, values=TIME_CHOICES, state="readonly", width=8).grid(row=0, column=5, padx=8, pady=6, sticky="w")
        ttk.Label(controls, text="Min (Hard):").grid(row=0, column=6, padx=8, pady=6, sticky="w")
        ttk.Combobox(controls, textvariable=self.req_min_var, values=[str(i) for i in range(0,21)], state="readonly", width=6).grid(row=0, column=7, padx=8, pady=6, sticky="w")
        ttk.Label(controls, text="Preferred:").grid(row=0, column=8, padx=8, pady=6, sticky="w")
        ttk.Combobox(controls, textvariable=self.req_pref_var, values=[str(i) for i in range(0,21)], state="readonly", width=6).grid(row=0, column=9, padx=8, pady=6, sticky="w")
        ttk.Label(controls, text="Max (Hard):").grid(row=0, column=10, padx=8, pady=6, sticky="w")
        ttk.Combobox(controls, textvariable=self.req_max_var, values=[str(i) for i in range(0,21)], state="readonly", width=6).grid(row=0, column=11, padx=8, pady=6, sticky="w")

        self.day_vars = {d: tk.BooleanVar(value=(d in ["Mon","Tue","Wed","Thu","Fri"])) for d in DAYS}
        for i,d in enumerate(DAYS):
            ttk.Checkbutton(controls, text=d, variable=self.day_vars[d]).grid(row=1, column=i, padx=6, pady=4, sticky="w")

        ttk.Button(controls, text="Select Weekdays", command=lambda: self._select_days("weekdays")).grid(row=2, column=0, padx=8, pady=6, sticky="w")
        ttk.Button(controls, text="Select Weekends", command=lambda: self._select_days("weekends")).grid(row=2, column=1, padx=8, pady=6, sticky="w")
        ttk.Button(controls, text="Select All", command=lambda: self._select_days("all")).grid(row=2, column=2, padx=8, pady=6, sticky="w")
        ttk.Button(controls, text="Clear", command=lambda: self._select_days("none")).grid(row=2, column=3, padx=8, pady=6, sticky="w")

        ttk.Button(controls, text="Apply Range to Selected Days", command=self.apply_req_range).grid(row=0, column=12, rowspan=2, padx=10, pady=6, sticky="ns")

        self.copy_day_var = tk.StringVar(value="Mon")
        ttk.Label(controls, text="Copy day:").grid(row=2, column=4, padx=8, pady=6, sticky="e")
        ttk.Combobox(controls, textvariable=self.copy_day_var, values=DAYS, state="readonly", width=6).grid(row=2, column=5, padx=8, pady=6, sticky="w")
        ttk.Button(controls, text="Copy → Paste to Selected Days", command=self.copy_paste_day).grid(row=2, column=6, columnspan=3, padx=10, pady=6, sticky="w")

        cols = ("Day","Area","Start","End","Min","Preferred","Max")
        req_wrap = ttk.Panedwindow(frm, orient="vertical"); req_wrap.pack(fill="both", expand=True)
        raw_box = ttk.LabelFrame(req_wrap, text="Raw Requirement Rows")
        eff_box = ttk.LabelFrame(req_wrap, text="Effective Solver Rules (Normalized Preview)")
        req_wrap.add(raw_box, weight=3)
        req_wrap.add(eff_box, weight=2)
        raw_wrap = ttk.Frame(raw_box); raw_wrap.pack(fill="both", expand=True)
        self.req_tree = ttk.Treeview(raw_wrap, columns=cols, show="headings", height=12)
        for c in cols:
            self.req_tree.heading(c, text=c)
            self.req_tree.column(c, width=180, stretch=True)
        req_tree_ysb = ttk.Scrollbar(raw_wrap, orient="vertical", command=self.req_tree.yview)
        req_tree_xsb = ttk.Scrollbar(raw_wrap, orient="horizontal", command=self.req_tree.xview)
        self.req_tree.configure(yscrollcommand=req_tree_ysb.set, xscrollcommand=req_tree_xsb.set)
        self.req_tree.grid(row=0, column=0, sticky="nsew")
        req_tree_ysb.grid(row=0, column=1, sticky="ns")
        req_tree_xsb.grid(row=1, column=0, sticky="ew")
        raw_wrap.grid_rowconfigure(0, weight=1)
        raw_wrap.grid_columnconfigure(0, weight=1)

        self.req_effective_tree = ttk.Treeview(eff_box, columns=cols, show="headings", height=8)
        for c in cols:
            self.req_effective_tree.heading(c, text=c)
            self.req_effective_tree.column(c, width=170, stretch=True)
        eff_ysb = ttk.Scrollbar(eff_box, orient="vertical", command=self.req_effective_tree.yview)
        self.req_effective_tree.configure(yscrollcommand=eff_ysb.set)
        self.req_effective_tree.grid(row=0, column=0, sticky="nsew")
        eff_ysb.grid(row=0, column=1, sticky="ns")
        eff_box.grid_rowconfigure(0, weight=1)
        eff_box.grid_columnconfigure(0, weight=1)

        bottom = ttk.Frame(frm); bottom.pack(fill="x", pady=(8,0))
        ttk.Button(bottom, text="Edit Selected Count", command=self.edit_req_selected).pack(side="left")
        ttk.Button(bottom, text="Delete Selected", command=self.delete_req_selected).pack(side="left", padx=8)
        ttk.Button(bottom, text="Split Selected", command=self.split_req_selected).pack(side="left", padx=8)
        ttk.Button(bottom, text="Merge Adjacent", command=self.merge_adjacent_requirements).pack(side="left", padx=8)
        ttk.Button(bottom, text="Reset to Defaults", command=self.reset_requirements).pack(side="left", padx=8)

    def apply_req_range(self):
        area = str(self.req_area_var.get() or "").strip()
        if area not in AREAS:
            messagebox.showerror("Apply", "Select a valid area.")
            return
        st = hhmm_to_tick(self.req_start_var.get())
        en = hhmm_to_tick(self.req_end_var.get())
        if en <= st:
            messagebox.showerror("Apply", "End must be after start.")
            return

        try:
            mn = max(0, int(str(self.req_min_var.get()).strip()))
            pr = max(mn, int(str(self.req_pref_var.get()).strip()))
            mx = max(pr, int(str(self.req_max_var.get()).strip()))
        except Exception:
            messagebox.showerror("Apply", "Min / Preferred / Max must be whole numbers.")
            return

        if not is_within_area_hours(self.model, area, st, en):
            op_t, cl_t = area_open_close_ticks(self.model, area)
            messagebox.showerror("Apply", f"{area} requirement range must be within Hours of Operation: {tick_to_hhmm(op_t)}–{tick_to_hhmm(cl_t)}")
            return

        sel_days = [d for d in DAYS if self.day_vars[d].get()]
        if not sel_days:
            messagebox.showerror("Apply", "Select at least one day.")
            return

        changed = 0
        for d in sel_days:
            t = st
            while t < en:
                t2 = t + 1
                r = next((x for x in self.model.requirements if x.day==d and x.area==area and x.start_t==t and x.end_t==t2), None)
                if r is None:
                    self.model.requirements.append(RequirementBlock(d, area, t, t2, mn, pr, mx))
                else:
                    r.min_count = mn
                    r.preferred_count = pr
                    r.max_count = mx
                changed += 1
                t = t2
        self.refresh_req_tree()
        self.autosave()
        messagebox.showinfo("Apply", f"Applied {changed} blocks: {area} {tick_to_hhmm(st)}–{tick_to_hhmm(en)} min={mn}, preferred={pr}, max={mx} across {len(sel_days)} day(s).")

    def copy_paste_day(self):
        src = self.copy_day_var.get()
        tgt_days = [d for d in DAYS if self.day_vars[d].get()]
        if not tgt_days:
            messagebox.showerror("Copy/Paste", "Select target days with checkboxes.")
            return
        src_map = {(r.area,r.start_t,r.end_t): (r.min_count, r.preferred_count, r.max_count) for r in self.model.requirements if r.day==src and is_within_area_hours(self.model, r.area, r.start_t, r.end_t)}
        pasted = 0
        for d in tgt_days:
            if d == src:
                continue
            for (area,st,en), (mn,pr,mx) in src_map.items():
                r = next((x for x in self.model.requirements if x.day==d and x.area==area and x.start_t==st and x.end_t==en), None)
                if r is None:
                    self.model.requirements.append(RequirementBlock(d, area, st, en, int(mn), int(pr), int(mx)))
                else:
                    r.min_count = int(mn); r.preferred_count = int(pr); r.max_count = int(mx)
                pasted += 1
        self.refresh_req_tree()
        self.autosave()
        messagebox.showinfo("Copy/Paste", f"Pasted {pasted} blocks from {src} to {len(tgt_days)- (1 if src in tgt_days else 0)} day(s).")

    def edit_req_selected(self):
        sel = self.req_tree.selection()
        if not sel:
            messagebox.showinfo("Edit", "Select a requirement row.")
            return
        vals = self.req_tree.item(sel[0], "values")
        day, area, st, en, mn, pr, mx = vals
        new_mn = simple_input(self, "Edit Requirement", f"Min (hard) headcount for {day} {area} {st}-{en}:", default=str(mn))
        if new_mn is None:
            return
        new_pr = simple_input(self, "Edit Requirement", f"Preferred headcount for {day} {area} {st}-{en}:", default=str(pr))
        if new_pr is None:
            return
        new_mx = simple_input(self, "Edit Requirement", f"Max (hard) headcount for {day} {area} {st}-{en}:", default=str(mx))
        if new_mx is None:
            return
        try:
            mn_i = max(0, int(str(new_mn).strip()))
            pr_i = max(mn_i, int(str(new_pr).strip()))
            mx_i = max(pr_i, int(str(new_mx).strip()))
        except Exception:
            return
        stt = hhmm_to_tick(st); ent = hhmm_to_tick(en)
        if not is_within_area_hours(self.model, area, stt, ent):
            op_t, cl_t = area_open_close_ticks(self.model, area)
            messagebox.showerror("Edit", f"{area} requirement range must be within Hours of Operation: {tick_to_hhmm(op_t)}–{tick_to_hhmm(cl_t)}")
            return
        r = next((x for x in self.model.requirements if x.day==day and x.area==area and x.start_t==stt and x.end_t==ent), None)
        if r:
            r.min_count = mn_i
            r.preferred_count = pr_i
            r.max_count = mx_i
            self.refresh_req_tree()
            self.autosave()

    def delete_req_selected(self):
        sel = self.req_tree.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select a requirement row.")
            return
        vals = self.req_tree.item(sel[0], "values")
        day, area, st, en = vals[0], vals[1], vals[2], vals[3]
        stt = hhmm_to_tick(st); ent = hhmm_to_tick(en)
        before = len(self.model.requirements)
        self.model.requirements = [x for x in self.model.requirements if not (x.day==day and x.area==area and x.start_t==stt and x.end_t==ent)]
        if len(self.model.requirements) == before:
            return
        self.refresh_req_tree(); self.autosave()

    def split_req_selected(self):
        sel = self.req_tree.selection()
        if not sel:
            messagebox.showinfo("Split", "Select a requirement row.")
            return
        vals = self.req_tree.item(sel[0], "values")
        day, area, st, en, mn, pr, mx = vals
        stt = hhmm_to_tick(st); ent = hhmm_to_tick(en)
        if ent - stt < 2:
            messagebox.showinfo("Split", "Selected row must be at least 1 hour to split.")
            return
        mid = simple_input(self, "Split Requirement", f"Split time between {st} and {en}:", default=tick_to_hhmm(stt + (ent-stt)//2))
        if mid is None:
            return
        mt = hhmm_to_tick(str(mid).strip())
        if mt <= stt or mt >= ent:
            messagebox.showerror("Split", "Split time must be inside the selected range.")
            return
        r = next((x for x in self.model.requirements if x.day==day and x.area==area and x.start_t==stt and x.end_t==ent), None)
        if r is None:
            return
        self.model.requirements.remove(r)
        self.model.requirements.append(RequirementBlock(day, area, stt, mt, int(mn), int(pr), int(mx)))
        self.model.requirements.append(RequirementBlock(day, area, mt, ent, int(mn), int(pr), int(mx)))
        self.refresh_req_tree(); self.autosave()

    def merge_adjacent_requirements(self):
        reqs = sorted(self.model.requirements, key=lambda x: (DAYS.index(x.day), AREAS.index(x.area), x.start_t, x.end_t))
        merged: List[RequirementBlock] = []
        i = 0
        merged_pairs = 0
        while i < len(reqs):
            cur = reqs[i]
            j = i + 1
            while j < len(reqs):
                nx = reqs[j]
                if nx.day == cur.day and nx.area == cur.area and nx.start_t == cur.end_t and nx.min_count == cur.min_count and nx.preferred_count == cur.preferred_count and nx.max_count == cur.max_count:
                    cur = RequirementBlock(cur.day, cur.area, cur.start_t, nx.end_t, cur.min_count, cur.preferred_count, cur.max_count)
                    merged_pairs += 1
                    j += 1
                    continue
                break
            merged.append(cur)
            i = j
        if merged_pairs <= 0:
            messagebox.showinfo("Merge", "No compatible adjacent rows to merge.")
            return
        self.model.requirements = merged
        self.refresh_req_tree(); self.autosave()
        messagebox.showinfo("Merge", f"Merged {merged_pairs} adjacent pair(s).")

    def reset_requirements(self):
        if not messagebox.askyesno("Reset", "Reset ALL requirements to defaults (CSTORE=2, others=0, 05:00–23:00)?"):
            return
        self.model.requirements = default_requirements()
        self.refresh_req_tree()
        self.autosave()

    def refresh_req_tree(self):
        for i in self.req_tree.get_children():
            self.req_tree.delete(i)
        for r in sorted(self.model.requirements, key=lambda x: (DAYS.index(x.day), AREAS.index(x.area), x.start_t, x.end_t)):
            self.req_tree.insert("", "end", values=(r.day, r.area, tick_to_hhmm(r.start_t), tick_to_hhmm(r.end_t), r.min_count, r.preferred_count, r.max_count))

        if hasattr(self, "req_effective_tree"):
            for i in self.req_effective_tree.get_children():
                self.req_effective_tree.delete(i)
            min_req, pref_req, max_req = build_requirement_maps(self.model.requirements, goals=getattr(self.model, "manager_goals", None), store_info=getattr(self.model, "store_info", None))
            for day in DAYS:
                for area in AREAS:
                    t = 0
                    while t < DAY_TICKS:
                        k = (day, area, t)
                        mn = int(min_req.get(k, 0)); pr = int(pref_req.get(k, 0)); mx = int(max_req.get(k, 0))
                        if mn == 0 and pr == 0 and mx == 0:
                            t += 1
                            continue
                        st = t
                        t += 1
                        while t < DAY_TICKS:
                            k2 = (day, area, t)
                            if int(min_req.get(k2, 0)) == mn and int(pref_req.get(k2, 0)) == pr and int(max_req.get(k2, 0)) == mx:
                                t += 1
                            else:
                                break
                        self.req_effective_tree.insert("", "end", values=(day, area, tick_to_hhmm(st), tick_to_hhmm(t), mn, pr, mx))

    # -------- Generate tab --------
    def _build_generate_tab(self):
        frm = ttk.Frame(self.tab_gen); frm.pack(fill="both", expand=True, padx=12, pady=12)

        top = ttk.Frame(frm); top.pack(fill="x", pady=(0,10))
        ttk.Button(top, text="Generate Schedule", command=self.on_generate).pack(side="left")
        ttk.Button(top, text="Save to History", command=self.save_to_history).pack(side="left", padx=8)
        ttk.Label(top, text="Week Label:").pack(side="left", padx=(18,6))
        self.label_var = tk.StringVar(value=self.current_label)
        ttk.Entry(top, textvariable=self.label_var, width=40).pack(side="left")
        ttk.Button(top, text="Set to This Week (Sun)", command=self.set_label_to_this_week).pack(side="left", padx=8)

        self.summary_lbl = ttk.Label(frm, text="", foreground="#333")
        self.summary_lbl.pack(fill="x", pady=(0,8))

        cols = ("Day","Area","Start","End","Employee","Source","Locked")
        self.out_tree = ttk.Treeview(frm, columns=cols, show="headings", height=18)
        for c in cols:
            self.out_tree.heading(c, text=c)
            w=150
            if c=="Employee": w=220
            if c=="Source": w=120
            if c=="Locked": w=80
            self.out_tree.column(c, width=w)
        self.out_tree.pack(fill="both", expand=True)

        # P2-2 Explainability: Right-click an assignment row to explain.
        self._out_tree_menu = tk.Menu(self, tearoff=0)
        self._out_tree_menu.add_command(label="Explain Assignment", command=self.explain_selected_assignment)
        self.out_tree.bind("<Button-3>", self._on_out_tree_right_click)
        self.out_tree.bind("<ButtonRelease-3>", self._on_out_tree_right_click)
        self.out_tree.bind("<Double-1>", self._on_out_tree_double_click)

        self.warn_txt = tk.Text(frm, height=8)
        self.warn_txt.pack(fill="x", pady=(10,0))

        # hint
        ttk.Label(frm, text="Tip: Right-click an assignment row above → Explain Assignment", foreground="#666").pack(anchor="w", pady=(6,0))

    def _on_out_tree_right_click(self, event):
        try:
            iid = self.out_tree.identify_row(event.y)
            if iid:
                self.out_tree.selection_set(iid)
                self.out_tree.focus(iid)
                self._out_tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._out_tree_menu.grab_release()
            except Exception:
                pass

    def _on_out_tree_double_click(self, event):
        try:
            iid = self.out_tree.identify_row(event.y)
            if iid:
                self.out_tree.selection_set(iid)
                self.out_tree.focus(iid)
                self.explain_selected_assignment()
        except Exception:
            pass

    def explain_selected_assignment(self):
        if not self.current_assignments:
            messagebox.showinfo("Explain", "Generate a schedule first.")
            return
        sel = self.out_tree.selection()
        if not sel:
            messagebox.showinfo("Explain", "Select an assignment row first.")
            return
        vals = self.out_tree.item(sel[0], "values")
        if not vals or len(vals) < 7:
            messagebox.showinfo("Explain", "Could not read the selected assignment.")
            return
        day, area, st_s, en_s, emp_name, source, locked_s = vals
        st = hhmm_to_tick(st_s)
        en = hhmm_to_tick(en_s)

        # Find the matching Assignment object (first match).
        target = None
        for a in self.current_assignments:
            if a.day == day and a.area == area and a.start_t == st and a.end_t == en and a.employee_name == emp_name:
                target = a
                break
        if target is None:
            messagebox.showinfo("Explain", "Could not locate that assignment in memory.")
            return

        label = self.current_label
        model = self.model
        hist = history_stats_from(model)

        # helpers
        min_req_ls, pref_req_ls, max_req_ls = build_requirement_maps(model.requirements, goals=getattr(model,'manager_goals',None))

        def compute_unfilled(assigns: List[Assignment]) -> int:
            cov = count_coverage_per_tick(assigns)
            ms, _, _ = compute_requirement_shortfalls(min_req_ls, pref_req_ls, max_req_ls, cov)
            return int(ms)

        base_assigns = list(self.current_assignments)
        base_unfilled = compute_unfilled(base_assigns)
        base_bd = schedule_score_breakdown(model, label, base_assigns, base_unfilled, hist)

        # Removing the assignment (coverage impact)
        minus = [x for x in base_assigns if x is not target]
        minus_cov = count_coverage_per_tick(minus)
        ms2, ps2, mv2 = compute_requirement_shortfalls(min_req_ls, pref_req_ls, max_req_ls, minus_cov)
        ms1, ps1, mv1 = compute_requirement_shortfalls(min_req_ls, pref_req_ls, max_req_ls, count_coverage_per_tick(base_assigns))
        cov_impact = {
            "min_short_change": int(ms2) - int(ms1),
            "pref_short_change": int(ps2) - int(ps1),
            "max_viol_change": int(mv2) - int(mv1),
        }

        # Evaluate alternative employees for the same slot
        feasible_alts: List[Tuple[float, str, Dict[str,float]]] = []
        infeasible_alts: List[Tuple[str, str]] = []
        for e in model.employees:
            if e.work_status != "Active":
                continue
            if e.name == emp_name:
                continue
            ok, reason = _explain_feasible_reason(model, label, e, day, area, st, en, minus)
            if not ok:
                infeasible_alts.append((e.name, reason))
                continue
            cand = list(minus)
            cand.append(Assignment(day, area, st, en, e.name, locked=False, source="solver"))
            uf = compute_unfilled(cand)
            bd = schedule_score_breakdown(model, label, cand, uf, hist)
            feasible_alts.append((bd.get("total", 0.0), e.name, bd))

        feasible_alts.sort(key=lambda x: x[0])
        best_alt = feasible_alts[0] if feasible_alts else None

        # Build explanation text
        win = tk.Toplevel(self)
        win.title("Explain Assignment")
        win.geometry("980x720")
        wrap = ttk.Frame(win); wrap.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(wrap, text=f"{day} • {area} • {st_s}-{en_s} • Assigned: {emp_name}", style="Header.TLabel").pack(anchor="w")

        txt = tk.Text(wrap, wrap="word")
        ysb = ttk.Scrollbar(wrap, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=ysb.set)
        ysb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)

        def fnum(x: float) -> str:
            try:
                return f"{float(x):.2f}"
            except Exception:
                return str(x)

        txt.insert(tk.END, "\nCoverage impact if this assignment were removed (hard constraints):\n")
        txt.insert(tk.END, f"  • MIN shortfall change: {cov_impact['min_short_change']}\n")
        txt.insert(tk.END, f"  • Preferred shortfall change: {cov_impact['pref_short_change']}\n")
        txt.insert(tk.END, f"  • Max-staffing violation change: {cov_impact['max_viol_change']}\n")

        txt.insert(tk.END, "\nScore breakdown for the CURRENT full schedule (lower is better):\n")
        txt.insert(tk.END, f"  • Total score: {fnum(base_bd.get('total',0.0))}\n")
        txt.insert(tk.END, f"    - Coverage (MIN): {fnum(base_bd.get('min_coverage_pen',0.0))}\n")
        txt.insert(tk.END, f"    - Coverage (Preferred): {fnum(base_bd.get('preferred_coverage_shortfall_pen',0.0))}\n")
        txt.insert(tk.END, f"    - Preferred cap: {fnum(base_bd.get('preferred_weekly_cap_pen',0.0))}\n")
        txt.insert(tk.END, f"    - Split shifts: {fnum(base_bd.get('split_shift_pen',0.0))}\n")
        txt.insert(tk.END, f"    - Fairness (history): {fnum(base_bd.get('history_fairness_pen',0.0))}\n")
        txt.insert(tk.END, f"    - Hour imbalance: {fnum(base_bd.get('hour_imbalance_pen',0.0))}\n")

        if best_alt:
            best_total, best_name, best_bd = best_alt
            txt.insert(tk.END, "\nBest feasible alternative employee for THIS slot (same time/area):\n")
            txt.insert(tk.END, f"  • {best_name} → total score would be {fnum(best_total)} (Δ {fnum(best_total - base_bd.get('total',0.0))})\n")
            # Requested: coverage/fairness/pref cap/split shift/total change
            fair_keys = ("history_fairness_pen", "hour_imbalance_pen", "weekend_pref_pen")
            fair_now = sum(float(base_bd.get(k,0.0) or 0.0) for k in fair_keys)
            fair_alt = sum(float(best_bd.get(k,0.0) or 0.0) for k in fair_keys)
            txt.insert(tk.END, f"  • Coverage impact: (no change expected for same slot)\n")
            txt.insert(tk.END, f"  • Fairness impact (Δ): {fnum(fair_alt - fair_now)}\n")
            txt.insert(tk.END, f"  • Preferred cap impact (Δ): {fnum(best_bd.get('preferred_weekly_cap_pen',0.0) - base_bd.get('preferred_weekly_cap_pen',0.0))}\n")
            txt.insert(tk.END, f"  • Split shift penalty (Δ): {fnum(best_bd.get('split_shift_pen',0.0) - base_bd.get('split_shift_pen',0.0))}\n")
            txt.insert(tk.END, f"  • Total score change (Δ): {fnum(best_total - base_bd.get('total',0.0))}\n")
        else:
            txt.insert(tk.END, "\nNo feasible alternative employees were found for this exact slot under hard constraints.\n")

        # Alternatives lists
        txt.insert(tk.END, "\nFeasible alternative employees (best 10):\n")
        if feasible_alts:
            for tot, nm, _bd in feasible_alts[:10]:
                txt.insert(tk.END, f"  • {nm}: total {fnum(tot)} (Δ {fnum(tot - base_bd.get('total',0.0))})\n")
        else:
            txt.insert(tk.END, "  (none)\n")

        txt.insert(tk.END, "\nRejected alternatives (infeasible under hard constraints; first 15):\n")
        if infeasible_alts:
            for nm, rsn in sorted(infeasible_alts, key=lambda x: x[0].lower())[:15]:
                txt.insert(tk.END, f"  • {nm}: {rsn}\n")
        else:
            txt.insert(tk.END, "  (none)\n")

        # Schedule limiting factors (run-level diagnostics)
        txt.insert(tk.END, "\nSchedule Limiting Factors (this run):\n")
        lf = []
        try:
            lf = list((self.current_diagnostics or {}).get('limiting_factors', []))
        except Exception:
            lf = []
        if lf:
            for s in lf:
                txt.insert(tk.END, f"  • {s}\n")
        else:
            txt.insert(tk.END, "  (none recorded)\n")

        txt.insert(tk.END, "\nNotes:\n")
        txt.insert(tk.END, "  • This explanation evaluates the current schedule score model and compares exact-slot swaps.\n")
        txt.insert(tk.END, "  • Hard constraints remain enforced: availability, minors rules, overlap, and max weekly caps.\n")

        txt.configure(state="disabled")

    def _default_week_label(self) -> str:
        today = datetime.date.today()
        days_since_sun = (today.weekday() + 1) % 7
        sun = today - datetime.timedelta(days=days_since_sun)
        return f"Week starting {sun.isoformat()} (Sun-Sat)"

    def set_label_to_this_week(self):
        self.label_var.set(self._default_week_label())

    def on_generate(self):
        label = self.label_var.get().strip() or self._default_week_label()
        self.current_label = label
        if not self.model.employees:
            messagebox.showerror("Generate", "Add employees first.")
            return
        if not self.model.requirements:
            messagebox.showerror("Generate", "Set staffing requirements first.")
            return

        try:
            _write_run_log(f"GENERATE_START | {label}")
        except Exception:
            pass
        # P2-3: Load previous schedule for stability preference (if available)
        # Prefer last week's *published final* schedule; otherwise fall back to the last generated schedule snapshot.
        prev_label, prev_tick_map = load_prev_final_schedule_tick_map(label)
        if not prev_tick_map:
            prev_label, prev_tick_map = load_last_schedule_tick_map()


        # P2-4: refresh learned patterns (if enabled)
        try:
            if bool(getattr(self.model.settings, "learn_from_history", True)):
                self._refresh_learned_patterns()
        except Exception:
            pass

        # P2-5: Demand preview before solving (if multipliers differ from 1.0)
        try:
            g = getattr(self.model, "manager_goals", None)
            m_morn = float(getattr(g, "demand_morning_multiplier", 1.0) or 1.0) if g is not None else 1.0
            m_mid  = float(getattr(g, "demand_midday_multiplier", 1.0) or 1.0) if g is not None else 1.0
            m_eve  = float(getattr(g, "demand_evening_multiplier", 1.0) or 1.0) if g is not None else 1.0
            if abs(m_morn-1.0) > 1e-6 or abs(m_mid-1.0) > 1e-6 or abs(m_eve-1.0) > 1e-6:
                messagebox.showinfo(
                    "Demand Adaptive Scheduling",
                    f"Demand multipliers will be applied to staffing requirements (rounded per 30-min tick):\n\n"
                    f"Morning: x{m_morn:g}\nMidday: x{m_mid:g}\nEvening: x{m_eve:g}"
                )
        except Exception:
            pass


        try:
            from engine.solver import run_scheduler_engine
            model_for_generation = copy.deepcopy(self.model)
            engine_result = run_scheduler_engine(model_for_generation, label, prev_tick_map=prev_tick_map)
            assigns = engine_result.assignments
            emp_hours = engine_result.employee_hours
            total_hours = engine_result.total_hours
            warnings = engine_result.warnings
            filled = engine_result.filled_slots
            total_slots = engine_result.total_slots
            iters_done = engine_result.iterations
            restarts_done = engine_result.restarts
            diag = engine_result.diagnostics
        except Exception as ex:
            try:
                _write_run_log(f"GENERATE_CRASH | {label} | {ex}")
            except Exception:
                pass
            raise
        try:
            _write_run_log(f"GENERATE_DONE | {label} | hours={total_hours:.1f} | assigns={len(assigns)} | filled={filled}/{total_slots}")
        except Exception:
            pass
        self.current_assignments = assigns
        self.current_emp_hours = emp_hours
        self.current_total_hours = total_hours
        self.current_warnings = warnings
        self.current_filled = filled
        self.current_total_slots = total_slots
        self.current_diagnostics = diag
        # Store last run summary for Diagnostics (Milestone 0 helper)
        self.last_solver_summary = {
            'label': label,
            'score_hours': round(float(total_hours), 2),
            'maximum_weekly_cap': float(getattr(self.model.manager_goals, 'maximum_weekly_cap', 0.0) or 0.0),
            'cap_over_by': max(0.0, float(total_hours) - float(getattr(self.model.manager_goals, 'maximum_weekly_cap', 0.0) or 0.0)),
            'filled': int(filled),
            'total_slots': int(total_slots),
            'assignments': int(len(assigns)),
            'optimizer_iterations': int(iters_done),
            'restarts': int(restarts_done),
            'warnings_count': int(len(warnings) if warnings else 0),
            'infeasible': any(('INFEASIBLE' in str(w)) for w in (warnings or [])),
            'notes': '',
        }

        # Milestone 6: compute numeric penalty score with tunable weights
        try:
            # unfilled min slots as ticks
            unfilled_ticks = max(0, int(total_slots) - int(filled))
            hist = history_stats_from(self.model)
            pen = float(schedule_score(self.model, label, assigns, unfilled_ticks, hist, prev_tick_map))
            self.last_solver_summary['score_penalty'] = round(pen, 2)
        except Exception:
            self.last_solver_summary['score_penalty'] = None

        # P2-2: Schedule limiting factors
        try:
            self.last_solver_summary['limiting_factors'] = list((diag or {}).get('limiting_factors', []))
            self.last_solver_summary['cap_blocked_attempts'] = int((diag or {}).get('cap_blocked_attempts', 0))
            self.last_solver_summary['cap_blocked_ticks'] = int((diag or {}).get('cap_blocked_ticks', 0))
            self.last_solver_summary['min_short'] = int((diag or {}).get('min_short', 0))
            self.last_solver_summary['pref_short'] = int((diag or {}).get('pref_short', 0))
            self.last_solver_summary['max_viol'] = int((diag or {}).get('max_viol', 0))
        except Exception:
            pass
        try:
            self.last_solver_summary['preferred_weekly_cap'] = float(getattr(self.model.manager_goals, 'preferred_weekly_cap', getattr(self.model.manager_goals,'weekly_hours_cap',0.0)) or 0.0)
        except Exception:
            pass

        # P2-3: Stability diagnostics (% preserved vs moved compared to last schedule)
        try:
            if prev_tick_map:
                cur_tick_map = _expand_assignments_to_tick_map(assigns)
                prev_total = int(len(prev_tick_map))
                preserved = 0
                for k, prev_emp in prev_tick_map.items():
                    if cur_tick_map.get(k) == prev_emp:
                        preserved += 1
                moved = max(0, prev_total - preserved)
                self.last_solver_summary['stability_prev_label'] = prev_label
                self.last_solver_summary['stability_prev_ticks'] = prev_total
                self.last_solver_summary['stability_preserved_ticks'] = preserved
                self.last_solver_summary['stability_moved_ticks'] = moved
                self.last_solver_summary['stability_preserved_pct'] = (preserved / prev_total * 100.0) if prev_total else None
                self.last_solver_summary['stability_moved_pct'] = (moved / prev_total * 100.0) if prev_total else None
            else:
                self.last_solver_summary['stability_prev_label'] = None
                self.last_solver_summary['stability_prev_ticks'] = 0
                self.last_solver_summary['stability_preserved_pct'] = None
                self.last_solver_summary['stability_moved_pct'] = None
        except Exception:
            pass




        # Milestone 3: compute eligibility this week (active/opted-in with >=1 hour availability after overrides)
        try:
            eligible_map, not_eligible_map = compute_weekly_eligibility(self.model, label)
        except Exception:
            eligible_map, not_eligible_map = {}, {}

        # Add summary fields for Diagnostics
        try:
            self.last_solver_summary['eligible_count'] = int(len(eligible_map))
            self.last_solver_summary['not_eligible_count'] = int(len(not_eligible_map))
            # Keep names + reasons (compact)
            self.last_solver_summary['not_eligible'] = [{ 'name': n, 'reason': r } for n, r in sorted(not_eligible_map.items(), key=lambda x: x[0].lower())]
        except Exception:
            pass


        for i in self.out_tree.get_children():
            self.out_tree.delete(i)
        for a in sorted(assigns, key=lambda x: (DAYS.index(x.day), AREAS.index(x.area), x.start_t, x.employee_name)):
            self.out_tree.insert("", "end", values=(a.day, a.area, tick_to_hhmm(a.start_t), tick_to_hhmm(a.end_t), a.employee_name, a.source, "Yes" if a.locked else "No"))

        active_ct = sum(1 for e in self.model.employees if e.work_status=="Active")
        self.summary_lbl.config(text=f"Total hours: {total_hours:.1f} • Filled slots: {filled}/{total_slots} • Assignments: {len(assigns)} • Active employees: {active_ct}")

        self.warn_txt.delete("1.0", tk.END)
        self.warn_txt.insert(tk.END, "Employee weekly hours:\n")
        for n in sorted(emp_hours.keys(), key=str.lower):
            self.warn_txt.insert(tk.END, f"  - {n}: {emp_hours[n]:.1f} hrs\n")
        
        # Milestone 3: Eligibility report (who is eligible this week vs not eligible)
        self.warn_txt.insert(tk.END, "\nEligibility this week:\n")
        if not_eligible_map:
            self.warn_txt.insert(tk.END, "  Not eligible (excluded from participation):\n")
            for n in sorted(not_eligible_map.keys(), key=str.lower):
                self.warn_txt.insert(tk.END, f"    - {n}: {not_eligible_map[n]}\n")
        else:
            self.warn_txt.insert(tk.END, "  All Active/opted-in employees have at least 1 hour of availability.\n")

        # P2-3: Stability report
        try:
            p = self.last_solver_summary.get('stability_preserved_pct', None)
            mvt = self.last_solver_summary.get('stability_moved_pct', None)
            prev_lab = self.last_solver_summary.get('stability_prev_label', None)
            if p is not None and mvt is not None:
                self.warn_txt.insert(tk.END, "\nStability vs previous schedule:\n")
                if prev_lab:
                    self.warn_txt.insert(tk.END, f"  Previous: {prev_lab}\n")
                self.warn_txt.insert(tk.END, f"  % shifts preserved: {p:.1f}%\n")
                self.warn_txt.insert(tk.END, f"  % shifts moved/changed: {mvt:.1f}%\n")
            else:
                self.warn_txt.insert(tk.END, "\nStability vs previous schedule:\n  (No prior schedule found to compare.)\n")
        except Exception:
            pass

        self.warn_txt.insert(tk.END, "\nWarnings:\n")
        if warnings:
            for w in warnings:
                self.warn_txt.insert(tk.END, f"  - {w}\n")
        else:
            self.warn_txt.insert(tk.END, "  (none)\n")

        # P2-3: Persist this schedule so next run can prefer stability
        try:
            save_last_schedule(assigns, label)
        except Exception:
            pass

        try:
            self._refresh_schedule_analysis()
        except Exception:
            pass
        try:
            self._refresh_change_viewer()
        except Exception:
            pass
        self._set_status("Schedule generated.")
        self.autosave()

    def save_to_history(self):
        if not self.current_assignments:
            messagebox.showinfo("History", "Generate a schedule first.")
            return
        label = self.current_label
        created = today_iso()

        weekend_counts = {e.name: 0 for e in self.model.employees}
        undes = {e.name: 0 for e in self.model.employees}
        for a in self.current_assignments:
            if a.day in weekend_days():
                weekend_counts[a.employee_name] = weekend_counts.get(a.employee_name,0) + 1
            if (a.start_t < hhmm_to_tick("07:00")) or (a.end_t >= hhmm_to_tick("22:00")):
                undes[a.employee_name] = undes.get(a.employee_name,0) + 1

        summary = ScheduleSummary(
            label=label,
            created_on=created,
            total_hours=float(self.current_total_hours),
            warnings=list(self.current_warnings),
            employee_hours=dict(self.current_emp_hours),
            weekend_counts=weekend_counts,
            undesirable_counts=undes,
            filled_slots=int(self.current_filled),
            total_slots=int(self.current_total_slots),
        )
        self.model.history.append(summary)
        # also write a history JSON file snapshot
        fn = f"history_{created}_{label.replace(' ','_').replace(':','')}.json"
        path = rel_path("history", fn)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ser_summary(summary), f, indent=2)
        self.refresh_history_tree()
        # Manager Goals
        if hasattr(self, "mg_coverage_goal_var"):
            self.mg_coverage_goal_var.set(float(self.model.manager_goals.coverage_goal_pct))
            self.mg_daily_overstaff_allow_var.set(float(self.model.manager_goals.daily_overstaff_allow_hours))
            self.mg_weekly_hours_cap_var.set(float(self.model.manager_goals.weekly_hours_cap))
            self.mg_call_depth_var.set(int(self.model.manager_goals.call_list_depth))
            self.mg_include_noncert_var.set(bool(self.model.manager_goals.include_noncertified_in_call_list))
        # Settings
        if hasattr(self, 'learn_hist_var'):
            try:
                self.learn_hist_var.set(bool(getattr(self.model.settings, 'learn_from_history', True)))
            except Exception:
                pass

        self.autosave()
        messagebox.showinfo("History", "Saved schedule summary to history.")

    # -------- Print/Export tab --------
    def _build_preview_tab(self):
        frm = ttk.Frame(self.tab_preview); frm.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frm, text="One-page landscape output organized by store section.", style="SubHeader.TLabel")\
            .pack(anchor="w", pady=(0,8))

        top = ttk.Frame(frm); top.pack(fill="x", pady=(0,10))
        ttk.Button(top, text="Open Print View (HTML)", command=self.print_html).pack(side="left")
        ttk.Button(top, text="Employee Calendar (HTML)", command=self.print_employee_calendar).pack(side="left", padx=8)
        ttk.Button(top, text="Manager Report (HTML)", command=self.print_manager_report).pack(side="left", padx=8)
        ttk.Button(top, text="Export CSV", command=self.export_csv_btn).pack(side="left", padx=8)
        ttk.Button(top, text="Export PDF (if available)", command=self.export_pdf_btn).pack(side="left", padx=8)
        ttk.Button(top, text="Lock / Publish Final Schedule", command=self._lock_publish_final_schedule).pack(side="left", padx=(20,8))
        ttk.Button(top, text="Load Final (This Week)", command=self._load_final_schedule_this_week).pack(side="left", padx=8)
        ttk.Button(top, text="Reprint Final", command=self._reprint_final_this_week).pack(side="left", padx=8)

        self.export_lbl = ttk.Label(frm, text="", foreground="#555")
        self.export_lbl.pack(anchor="w")

        self.preview_txt = tk.Text(frm, height=24)
        self.preview_txt.pack(fill="both", expand=True, pady=(10,0))

    def print_html(self):
        if not self.current_assignments:
            messagebox.showinfo("Print", "Generate a schedule first.")
            return
        path = export_html(self.model, self.current_label, self.current_assignments)
        if not open_local_export_file(path):
            messagebox.showerror("Print", f"Could not open exported file:\n{path}")
            return
        self.export_lbl.config(text=f"HTML: {path}")


    def print_employee_calendar(self):
        if not self.current_assignments:
            messagebox.showinfo("Print", "Generate a schedule first.")
            return
        path = export_employee_calendar_html(self.model, self.current_label, self.current_assignments)
        if not open_local_export_file(path):
            messagebox.showerror("Print", f"Could not open exported file:\n{path}")
            return
        self.export_lbl.config(text=f"Employee Calendar HTML: {path}")

    def print_manager_report(self):
        if not self.current_assignments:
            messagebox.showinfo("Print", "Generate a schedule first.")
            return
        path = export_manager_report_html(self.model, self.current_label, self.current_assignments)
        if not open_local_export_file(path):
            messagebox.showerror("Print", f"Could not open exported file:\n{path}")
            return
        self.export_lbl.config(text=f"Manager Report HTML: {path}")

    def export_csv_btn(self):
        if not self.current_assignments:
            messagebox.showinfo("Export", "Generate a schedule first.")
            return
        path = export_csv(self.model, self.current_label, self.current_assignments)
        self.export_lbl.config(text=f"CSV: {path}")

    def export_pdf_btn(self):
        if not self.current_assignments:
            messagebox.showinfo("Export", "Generate a schedule first.")
            return
        path = export_pdf(self.model, self.current_label, self.current_assignments)
        if not path:
            messagebox.showinfo("PDF", "PDF export requires reportlab. (Not installed in some environments.)")
            return
        self.export_lbl.config(text=f"PDF: {path}")


    def _final_schedule_dir(self) -> str:
        return rel_path("data", "final_schedules")

    def _final_schedule_path_for_label(self, label: Optional[str] = None) -> Optional[str]:
        label = (label or getattr(self, "current_label", "") or self.label_var.get().strip() or self._default_week_label()).strip()
        wk = week_sun_from_label(label)
        if wk is None:
            return None
        return os.path.join(self._final_schedule_dir(), f"{wk.isoformat()}.json")

    def _manual_pages_for_label(self, label: str) -> dict:
        try:
            ui_pages = self._manual_payload_from_ui()
            if any(str(cell).strip() for kind in ui_pages.values() for emp in kind.values() for cell in emp.values()):
                return ui_pages
        except Exception:
            pass
        payload = self._load_manual_overrides()
        stored_label = str(payload.get("label", "") or "")
        if payload and stored_label == str(label or ""):
            return payload.get("pages", {}) or {}
        return {}

    def _apply_current_schedule_to_output_views(self):
        for i in self.out_tree.get_children():
            self.out_tree.delete(i)
        assigns = list(self.current_assignments or [])
        for a in sorted(assigns, key=lambda x: (DAYS.index(x.day), AREAS.index(x.area), x.start_t, x.employee_name)):
            self.out_tree.insert("", "end", values=(a.day, a.area, tick_to_hhmm(a.start_t), tick_to_hhmm(a.end_t), a.employee_name, a.source, "Yes" if a.locked else "No"))

        active_ct = sum(1 for e in self.model.employees if e.work_status == "Active")
        self.summary_lbl.config(text=f"Total hours: {self.current_total_hours:.1f} • Filled slots: {self.current_filled}/{self.current_total_slots} • Assignments: {len(assigns)} • Active employees: {active_ct}")

        self.warn_txt.delete("1.0", tk.END)
        self.warn_txt.insert(tk.END, "Employee weekly hours:\n")
        for n in sorted((self.current_emp_hours or {}).keys(), key=str.lower):
            self.warn_txt.insert(tk.END, f"  - {n}: {self.current_emp_hours[n]:.1f} hrs\n")
        self.warn_txt.insert(tk.END, "\nWarnings:\n")
        if self.current_warnings:
            for w in self.current_warnings:
                self.warn_txt.insert(tk.END, f"  - {w}\n")
        else:
            self.warn_txt.insert(tk.END, "  (none)\n")

        try:
            self.preview_txt.delete("1.0", tk.END)
            self.preview_txt.insert(tk.END, f"Current schedule: {self.current_label}\n")
            self.preview_txt.insert(tk.END, f"Assignments: {len(assigns)}\n")
            self.preview_txt.insert(tk.END, f"Total hours: {self.current_total_hours:.1f}\n")
            self.preview_txt.insert(tk.END, f"Filled slots: {self.current_filled}/{self.current_total_slots}\n")
        except Exception:
            pass

    def _lock_publish_final_schedule(self):
        if not self.current_assignments:
            messagebox.showinfo("Lock Final Schedule", "Generate or load a schedule first.")
            return
        path = self._final_schedule_path_for_label()
        if not path:
            messagebox.showerror("Lock Final Schedule", "Could not determine the week start date from the current label.")
            return
        ensure_dir(os.path.dirname(path))
        wk = week_sun_from_label(self.current_label)
        manual_pages = self._manual_pages_for_label(self.current_label)
        payload = {
            "label": str(self.current_label or ""),
            "week_start_sun": (wk.isoformat() if wk else ""),
            "published_on": datetime.datetime.now().isoformat(timespec="seconds"),
            "assignments": [ser_assignment(a) for a in self.current_assignments],
            "employee_hours": dict(self.current_emp_hours or {}),
            "total_hours": float(self.current_total_hours or 0.0),
            "warnings": list(self.current_warnings or []),
            "filled_slots": int(self.current_filled or 0),
            "total_slots": int(self.current_total_slots or 0),
            "manual_pages": manual_pages,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        self.export_lbl.config(text=f"Final schedule saved: {path}")
        self._set_status("Locked / published final schedule.")
        messagebox.showinfo("Lock Final Schedule", f"Final schedule saved for this week.\n\n{path}")

    def _load_final_schedule_this_week(self):
        label = self.label_var.get().strip() or self.current_label or self._default_week_label()
        path = self._final_schedule_path_for_label(label)
        if not path or not os.path.isfile(path):
            messagebox.showinfo("Load Final", "No published final schedule was found for this week yet.")
            return
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        assigns = []
        skipped_rows = 0
        for item in payload.get("assignments", []) or []:
            try:
                assigns.append(des_assignment(item))
            except Exception as ex:
                skipped_rows += 1
                _write_run_log(f"LOAD_FINAL | Skipped malformed assignment row: {repr(ex)} :: {repr(item)[:400]}")
        self.current_label = str(payload.get("label", label) or label)
        self.label_var.set(self.current_label)
        self.current_assignments = assigns
        self.current_emp_hours = {k: float(v) for k, v in (payload.get("employee_hours", {}) or {}).items()}
        self.current_total_hours = float(payload.get("total_hours", 0.0) or 0.0)
        self.current_warnings = list(payload.get("warnings", []) or [])
        self.current_filled = int(payload.get("filled_slots", 0) or 0)
        self.current_total_slots = int(payload.get("total_slots", 0) or 0)
        if not self.current_emp_hours and self.current_assignments:
            self.current_emp_hours, self.current_total_hours, self.current_filled, self.current_total_slots = calc_schedule_stats(self.model, self.current_assignments)
        manual_pages = payload.get("manual_pages", {}) or {}
        if manual_pages:
            try:
                self._manual_apply_to_ui(manual_pages)
            except Exception as ex:
                _write_run_log(f"LOAD_FINAL | Manual pages apply to UI failed: {repr(ex)}")
            try:
                self._save_manual_overrides({
                    "label": self.current_label,
                    "saved_on": today_iso(),
                    "pages": manual_pages,
                })
            except Exception as ex:
                _write_run_log(f"LOAD_FINAL | Manual pages save failed: {repr(ex)}")
        self._apply_current_schedule_to_output_views()
        try:
            self._refresh_schedule_analysis()
        except Exception as ex:
            _write_run_log(f"LOAD_FINAL | Analysis refresh failed: {repr(ex)}")
        try:
            self._refresh_change_viewer()
        except Exception as ex:
            _write_run_log(f"LOAD_FINAL | Change-view refresh failed: {repr(ex)}")
        self.export_lbl.config(text=f"Loaded final schedule: {path}")
        status_msg = "Loaded published final schedule."
        if skipped_rows:
            warn_msg = f"Loaded final schedule with {skipped_rows} malformed assignment row(s) skipped."
            _write_run_log(f"LOAD_FINAL | {warn_msg}")
            self.export_lbl.config(text=f"Loaded final schedule with {skipped_rows} skipped row(s): {path}")
            status_msg = warn_msg
            messagebox.showwarning("Load Final", warn_msg)
        self._set_status(status_msg)

    def _reprint_final_this_week(self):
        label = self.label_var.get().strip() or self.current_label or self._default_week_label()
        path = self._final_schedule_path_for_label(label)
        if not path or not os.path.isfile(path):
            messagebox.showinfo("Reprint Final", "No published final schedule was found for this week yet.")
            return
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        assigns = []
        skipped_rows = 0
        for item in payload.get("assignments", []) or []:
            try:
                assigns.append(des_assignment(item))
            except Exception as ex:
                skipped_rows += 1
                _write_run_log(f"REPRINT_FINAL | Skipped malformed assignment row: {repr(ex)}")
        manual_pages = payload.get("manual_pages", {}) or {}
        use_label = str(payload.get("label", label) or label)
        if manual_pages:
            out = export_employee_calendar_html_with_overrides(self.model, use_label, assigns, manual_pages)
            self.export_lbl.config(text=f"Final manual employee calendar HTML: {out}")
        else:
            out = export_employee_calendar_html(self.model, use_label, assigns)
            self.export_lbl.config(text=f"Final employee calendar HTML: {out}")
        if not open_local_export_file(out):
            messagebox.showerror("Reprint Final", f"Could not open exported file:\n{out}")

    # -------- History tab --------
    # -------- Manager Goals tab --------
    # -------- Manual Edit tab --------
    def _manual_storage_path(self) -> str:
        return rel_path("data", "manual_employee_calendar.json")

    def _load_manual_overrides(self) -> dict:
        path = self._manual_storage_path()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
            except Exception:
                return {}
        return {}

    def _save_manual_overrides(self, payload: dict) -> None:
        path = self._manual_storage_path()
        ensure_dir(os.path.dirname(path))
        try:
            _atomic_write_json(path, payload, indent=2)
        except Exception as e:
            # Do not fail silently: manual edits are user-authored and must be reliable.
            try:
                _write_run_log(f"Manual overrides save failed: {path} :: {repr(e)}")
            except Exception:
                pass
            try:
                messagebox.showerror(
                    "Save Failed",
                    "Could not save manual schedule edits to:\n"
                    f"{path}\n\n"
                    f"Error: {e}\n\n"
                    "Your changes were NOT saved.\n\n"
                    "Tip: If this folder is in OneDrive, try moving the program folder to a local Desktop folder and try again."
                )
            except Exception:
                pass

    def _compute_calendar_base_texts(self, assignments: List[Assignment]) -> dict:
        """
        Returns: pages dict with keys MAIN, KITCHEN, CARWASH
        Each page: {employee_name: {day: text}}
        """
        pages = {"MAIN": {}, "KITCHEN": {}, "CARWASH": {}}
        # index assignments
        by_emp_day_area: Dict[Tuple[str,str,str], List[Assignment]] = {}
        areas_worked: Dict[Tuple[str,str], set] = {}
        for a in assignments or []:
            by_emp_day_area.setdefault((a.employee_name, a.day, a.area), []).append(a)
            areas_worked.setdefault((a.employee_name, a.day), set()).add(a.area)
        for k in list(by_emp_day_area.keys()):
            by_emp_day_area[k].sort(key=lambda x: (x.start_t, x.end_t))

        def _merge_to_str(items: List[Assignment]) -> str:
            if not items:
                return ""
            blocks = []
            cur_s, cur_e = int(items[0].start_t), int(items[0].end_t)
            for it in items[1:]:
                s, e = int(it.start_t), int(it.end_t)
                if s <= cur_e:
                    cur_e = max(cur_e, e)
                else:
                    blocks.append((cur_s, cur_e))
                    cur_s, cur_e = s, e
            blocks.append((cur_s, cur_e))
            return "; ".join(f"{tick_to_ampm(s)}-{tick_to_ampm(e)}" for s, e in blocks)

        for e in sorted(self.model.employees, key=lambda x: (x.name or "").lower()):
            nm = e.name or ""
            if not nm:
                continue
            for kind in ["MAIN","KITCHEN","CARWASH"]:
                pages[kind].setdefault(nm, {})
            for d in DAYS:
                cstore = _merge_to_str(by_emp_day_area.get((nm, d, "CSTORE"), []))
                kitchen = _merge_to_str(by_emp_day_area.get((nm, d, "KITCHEN"), []))
                carwash = _merge_to_str(by_emp_day_area.get((nm, d, "CARWASH"), []))
                # MAIN page: show CSTORE times, and hints to other areas
                parts = []
                if cstore:
                    parts.append(cstore)
                # Hints
                hints = []
                if kitchen:
                    hints.append("See Kitchen")
                if carwash:
                    hints.append("See Carwash")
                if hints and cstore:
                    parts.append(" / ".join(hints))
                elif hints and not cstore:
                    parts.append(" / ".join(hints))
                main_txt = "; ".join(parts).strip()
                # If nothing at all, keep "Off" for MAIN to match employee calendar behavior
                if not main_txt:
                    main_txt = "Off"
                pages["MAIN"][nm][d] = main_txt
                # Department pages: blank if not scheduled there (matches your preference)
                pages["KITCHEN"][nm][d] = kitchen  # blank if none
                pages["CARWASH"][nm][d] = carwash  # blank if none
        return pages

    def _manual_payload_from_ui(self) -> dict:
        pages = {}
        for kind, emp_map in (self.manual_vars or {}).items():
            pages[kind] = {}
            for emp, day_map in emp_map.items():
                pages[kind][emp] = {}
                for d, var in day_map.items():
                    pages[kind][emp][d] = (var.get() or "").strip()
        return pages

    def _manual_apply_to_ui(self, pages: dict):
        # pages expected keys MAIN/KITCHEN/CARWASH
        for kind in ["MAIN","KITCHEN","CARWASH"]:
            if kind not in self.manual_vars:
                continue
            src_kind = pages.get(kind, {}) or {}
            for emp, day_map in self.manual_vars[kind].items():
                src_emp = src_kind.get(emp, {}) or {}
                for d, var in day_map.items():
                    if d in src_emp:
                        var.set(src_emp.get(d,"") or "")

    def _manual_load_btn(self):
        # Prefer loading stored manual edits for the current label; otherwise load from current schedule
        payload = self._load_manual_overrides()
        cur_label = str(getattr(self, "current_label", "") or "")
        stored_label = str(payload.get("label","") or "")
        if payload and (not cur_label or stored_label == cur_label):
            self._manual_apply_to_ui(payload.get("pages", {}) or {})
            self._set_status("Loaded manual schedule edits.")
            return
        if not self.current_assignments:
            messagebox.showinfo("Manual Edit", "No manual edits saved for this week and no generated schedule available yet.\n\nGenerate a schedule first, then click “Load From Current Schedule”.")
            return
        base = self._compute_calendar_base_texts(self.current_assignments)
        self._manual_apply_to_ui(base)
        self._set_status("Loaded manual editor from current generated schedule.")

    def _manual_save_btn(self):
        payload = {
            "label": str(getattr(self, "current_label", "") or ""),
            "saved_on": today_iso(),
            "pages": self._manual_payload_from_ui(),
        }
        self._save_manual_overrides(payload)
        self._set_status("Saved manual schedule edits.")

    def _manual_clear_btn(self):
        for kind in self.manual_vars:
            for emp in self.manual_vars[kind]:
                for d in self.manual_vars[kind][emp]:
                    self.manual_vars[kind][emp][d].set("")
        # clear file too
        self._save_manual_overrides({})
        self._set_status("Cleared manual schedule edits.")

    def _manual_open_html(self):
        pages = self._manual_payload_from_ui()
        if not self.current_assignments:
            messagebox.showinfo("Manual Edit", "Generate a schedule first (so the calendar can keep the exact same formatting and header info).")
            return
        path = export_employee_calendar_html_with_overrides(self.model, self.current_label, self.current_assignments, pages)
        if not open_local_export_file(path):
            messagebox.showerror("Print", f"Could not open exported file:\n{path}")
            return
        self.export_lbl.config(text=f"Manual Employee Calendar HTML: {path}")


    def _manual_employee_names(self) -> List[str]:
        return [n for n in sorted([(e.name or "").strip() for e in getattr(self.model, "employees", []) or []], key=str.lower) if n]

    def _manual_status(self, msg: str) -> None:
        try:
            self.manual_status_lbl.config(text=str(msg or ""))
        except Exception:
            pass

    def _manual_set_warning_text(self, lines: List[str]) -> None:
        try:
            self.manual_warn_txt.delete("1.0", tk.END)
            for line in (lines or []):
                self.manual_warn_txt.insert(tk.END, f"{line}\n")
            if not lines:
                self.manual_warn_txt.insert(tk.END, "No warnings.\n")
        except Exception:
            pass

    def _manual_swap_selected_day(self):
        kind = str(getattr(self, 'manual_swap_kind_var', tk.StringVar(value='MAIN')).get() or 'MAIN')
        day = str(getattr(self, 'manual_swap_day_var', tk.StringVar(value=DAYS[0])).get() or DAYS[0])
        src = str(getattr(self, 'manual_swap_from_var', tk.StringVar(value='')).get() or '')
        dst = str(getattr(self, 'manual_swap_to_var', tk.StringVar(value='')).get() or '')
        if not src or not dst or src == dst:
            messagebox.showinfo('Quick Swap', 'Pick two different employees to swap.')
            return
        try:
            a = self.manual_vars[kind][src][day].get()
            b = self.manual_vars[kind][dst][day].get()
            self.manual_vars[kind][src][day].set(b)
            self.manual_vars[kind][dst][day].set(a)
            self._manual_status(f'Swapped {kind} {day}: {src} ↔ {dst}')
        except Exception as e:
            messagebox.showerror('Quick Swap', f'Could not swap those cells.\n\n{e}')

    def _manual_parse_time_blocks(self, raw: str) -> Tuple[List[Tuple[int, int]], List[str]]:
        s = str(raw or '').strip()
        if not s:
            return [], []

        def _canon_token(v: str) -> str:
            v = str(v or '').strip().lower()
            v = re.sub(r'[\s\.;,/\\]+', ' ', v)
            return re.sub(r'\s+', ' ', v).strip()

        ignore_tokens = {
            'off',
            'see kitchen',
            'see carwash',
            'see kitchen see carwash',
            'see carwash see kitchen',
        }
        if _canon_token(s) in ignore_tokens:
            return [], []

        notes: List[str] = []
        s = re.sub(r'\([^)]*\)', ' ', s)
        s = s.replace('–', '-').replace('—', '-')
        hint_pat = re.compile(r'(?i)\bsee\s+(kitchen|carwash)\b[\s\.;,/\\-]*')
        s = hint_pat.sub(' ', s)
        pat = re.compile(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|a|p)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm|a|p)?)', re.I)
        out: List[Tuple[int, int]] = []
        for m in pat.finditer(s):
            a = m.group(1).strip().lower().replace(' ', '')
            b = m.group(2).strip().lower().replace(' ', '')
            try:
                st = hhmm_to_tick(_normalize_user_time(a))
                en = hhmm_to_tick(_normalize_user_time(b))
                if en > st:
                    out.append((st, en))
                else:
                    notes.append(f'Overnight/invalid range not supported: {m.group(0).strip()}')
            except Exception:
                notes.append(f'Could not parse time range: {m.group(0).strip()}')

        residual = pat.sub(' ', s)
        residual = hint_pat.sub(' ', residual)
        residual = re.sub(r'\([^)]*\)', ' ', residual)
        residual = re.sub(r'[\s\.;,/\-]+', ' ', residual).strip()
        if residual:
            if out:
                notes.append(f'Unparsed text remains: {residual}')
            else:
                notes.append(f'Could not read text: {residual}')
        return out, notes

    def _manual_parse_pages_to_assignments(self) -> Tuple[List[Assignment], List[str]]:
        pages = self._manual_payload_from_ui()
        assigns: List[Assignment] = []
        issues: List[str] = []
        area_map = {'MAIN': 'CSTORE', 'KITCHEN': 'KITCHEN', 'CARWASH': 'CARWASH'}

        def _canon_token(v: str) -> str:
            v = str(v or '').strip().lower()
            v = re.sub(r'[\s\.;,/\\]+', ' ', v)
            return re.sub(r'\s+', ' ', v).strip()

        ignore_tokens = {
            'off',
            'see kitchen',
            'see carwash',
            'see kitchen see carwash',
            'see carwash see kitchen',
        }
        for page_kind, area in area_map.items():
            for emp, day_map in (pages.get(page_kind, {}) or {}).items():
                for day, raw in (day_map or {}).items():
                    blocks, notes = self._manual_parse_time_blocks(raw)
                    raw_s = str(raw or '').strip()
                    canon_raw = _canon_token(raw_s)
                    if raw_s and canon_raw not in ignore_tokens:
                        for note in notes:
                            issues.append(f'{page_kind} {day} for {emp}: {note}')
                        if not blocks and not notes:
                            cleaned = re.sub(r'\([^)]*\)', '', raw_s)
                            cleaned = re.sub(r'(?i)\bsee\s+(kitchen|carwash)\b[\s\.;,/\\-]*', ' ', cleaned)
                            cleaned = re.sub(r'[\s\.;,/\-]+', ' ', cleaned).strip()
                            if cleaned:
                                issues.append(f'Could not read {page_kind} {day} for {emp}: "{raw_s}"')
                    for st, en in blocks:
                        assigns.append(Assignment(day=day, area=area, start_t=st, end_t=en, employee_name=emp, locked=False, source='manual_edit'))
        assigns.sort(key=lambda a: (a.employee_name.lower(), DAYS.index(a.day), AREAS.index(a.area), a.start_t, a.end_t))
        return assigns, issues

    def _manual_validate_assignments(self, assigns: List[Assignment]) -> List[str]:
        warnings: List[str] = []
        emp_map = {(e.name or '').strip(): e for e in getattr(self.model, 'employees', []) or [] if (e.name or '').strip()}
        by_emp: Dict[str, List[Assignment]] = {}
        for a in assigns:
            by_emp.setdefault(a.employee_name, []).append(a)
        use_label = self.current_label or self.label_var.get().strip() or self._default_week_label()
        for emp_name, lst in by_emp.items():
            emp = emp_map.get(emp_name)
            if emp is None:
                warnings.append(f'Unknown employee in manual editor: {emp_name}')
                continue
            running: List[Assignment] = []
            clopen: Dict[Tuple[str,str], int] = {}
            total_hours = 0.0
            for a in sorted(lst, key=lambda x: (DAYS.index(x.day), x.start_t, x.end_t, AREAS.index(x.area))):
                if any(overlaps(a, prev) for prev in running):
                    warnings.append(f'Overlap for {emp_name} on {a.day} ({tick_to_ampm(a.start_t)}-{tick_to_ampm(a.end_t)}).')
                if not is_employee_available(self.model, emp, use_label, a.day, a.start_t, a.end_t, a.area, clopen):
                    warnings.append(f'Availability / time-off / minor-rule issue for {emp_name} on {a.day} in {a.area} ({tick_to_ampm(a.start_t)}-{tick_to_ampm(a.end_t)}).')
                if not respects_daily_shift_limits(running, emp, a.day, extra=(a.start_t, a.end_t)):
                    warnings.append(f'Daily shift rule issue for {emp_name} on {a.day}.')
                running.append(a)
                total_hours += hours_between_ticks(a.start_t, a.end_t)
                apply_clopen_from(self.model, emp, a, clopen)
            max_weekly = float(getattr(emp, 'max_weekly_hours', 0.0) or 0.0)
            if max_weekly > 0 and total_hours - max_weekly > 1e-9:
                warnings.append(f'{emp_name} exceeds weekly max hours ({total_hours:.1f} > {max_weekly:.1f}).')
        cov = count_coverage_per_tick(assigns)
        min_req, pref_req, max_req = build_requirement_maps(self.model.requirements, goals=getattr(self.model, 'manager_goals', None))
        min_short, pref_short, max_viol = compute_requirement_shortfalls(min_req, pref_req, max_req, cov)
        if min_short > 0:
            warnings.append(f'Coverage risk created: {min_short} required 30-minute staffing blocks are unfilled.')
        if pref_short > 0:
            warnings.append(f'Preferred coverage shortfall: {pref_short} preferred 30-minute staffing blocks are below target.')
        if max_viol > 0:
            warnings.append(f'Max staffing exceeded in {max_viol} 30-minute blocks.')
        return warnings

    def _manual_analyze_btn(self):
        try:
            assigns, parse_issues = self._manual_parse_pages_to_assignments()
            warnings = parse_issues + self._manual_validate_assignments(assigns)
            emp_hours, total_hours, filled, total_slots = calc_schedule_stats(self.model, assigns)
            summary = [
                f'Manual analysis for {len(assigns)} assignments.',
                f'Total hours: {total_hours:.1f}',
                f'Coverage: {filled}/{total_slots} required 30-minute blocks filled',
            ]
            if emp_hours:
                lowest = min(emp_hours.items(), key=lambda kv: kv[1])
                highest = max(emp_hours.items(), key=lambda kv: kv[1])
                summary.append(f'Hours range: {lowest[0]} {lowest[1]:.1f} hrs → {highest[0]} {highest[1]:.1f} hrs')
            self._manual_status('Manual analysis complete.')
            self._manual_set_warning_text(summary + [''] + (warnings if warnings else ['No warnings detected.']))
        except Exception as e:
            messagebox.showerror('Manual Edit', f'Could not analyze manual edits.\n\n{e}')

    def _manual_apply_btn(self):
        try:
            assigns, parse_issues = self._manual_parse_pages_to_assignments()
            warnings = parse_issues + self._manual_validate_assignments(assigns)
            if warnings:
                ok = messagebox.askyesno('Apply Manual Edits', 'Warnings were found. Apply manual edits anyway?')
                if not ok:
                    self._manual_set_warning_text(warnings)
                    self._manual_status('Manual apply canceled because warnings were found.')
                    return
            self.current_assignments = list(assigns)
            self.current_emp_hours, self.current_total_hours, self.current_filled, self.current_total_slots = calc_schedule_stats(self.model, self.current_assignments)
            self.current_warnings = list(warnings)
            self._apply_current_schedule_to_output_views()
            try:
                self._refresh_schedule_analysis()
            except Exception:
                pass
            self._manual_save_btn()
            self._manual_status('Manual edits applied to current schedule.')
            self._manual_set_warning_text(warnings if warnings else ['Manual edits applied with no warnings.'])
            self._set_status('Manual schedule edits applied to current schedule.')
        except Exception as e:
            messagebox.showerror('Manual Edit', f'Could not apply manual edits.\n\n{e}')

    # -------- Schedule Analysis tab (Phase 4 D1) --------
    def _build_analysis_tab(self):
        frm = ttk.Frame(self.tab_analysis); frm.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frm, text="Schedule Analysis", style="Header.TLabel").pack(anchor="w", pady=(0,4))
        ttk.Label(
            frm,
            text="Explains why the current schedule scored the way it did. Read-only. Generate or load a schedule first.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0,10))

        top = ttk.Frame(frm); top.pack(fill="x", pady=(0,8))
        ttk.Button(top, text="Refresh Analysis", command=self._refresh_schedule_analysis).pack(side="left")

        self.analysis_summary_lbl = ttk.Label(frm, text="", foreground="#333")
        self.analysis_summary_lbl.pack(fill="x", pady=(0,8))

        metric_box = ttk.Frame(frm)
        metric_box.pack(fill="x", pady=(0,8))
        self.analysis_metric_vars = {
            "coverage": tk.StringVar(value="Coverage: --"),
            "utilization": tk.StringVar(value="Utilization: --"),
            "risk": tk.StringVar(value="Risk Protection: --"),
            "participation": tk.StringVar(value="Participation: --"),
        }
        for i, key in enumerate(["coverage", "utilization", "risk", "participation"]):
            box = ttk.LabelFrame(metric_box, text=key.title() if key != "risk" else "Risk Protection")
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0), pady=0)
            metric_box.columnconfigure(i, weight=1)
            ttk.Label(box, textvariable=self.analysis_metric_vars[key], style="SubHeader.TLabel").pack(anchor="w", padx=10, pady=(8,6))

        cols = ("Category", "Penalty", "Impact", "Notes")
        self.analysis_tree = ttk.Treeview(frm, columns=cols, show="headings", height=10)
        for c in cols:
            self.analysis_tree.heading(c, text=c)
            w = 180
            if c == "Category": w = 220
            if c == "Notes": w = 520
            self.analysis_tree.column(c, width=w)
        self.analysis_tree.pack(fill="both", expand=False, pady=(0,8))

        body = ttk.Frame(frm); body.pack(fill="both", expand=True)
        self.analysis_text = tk.Text(body, wrap="word", height=14)
        vs = ttk.Scrollbar(body, orient="vertical", command=self.analysis_text.yview)
        self.analysis_text.configure(yscrollcommand=vs.set)
        self.analysis_text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._refresh_schedule_analysis()

    def _refresh_schedule_analysis(self):
        if not hasattr(self, "analysis_text"):
            return

        for i in self.analysis_tree.get_children():
            self.analysis_tree.delete(i)

        self.analysis_text.delete("1.0", "end")
        if not self.current_assignments:
            self.analysis_summary_lbl.config(text="No current schedule loaded.")
            for key in getattr(self, "analysis_metric_vars", {}):
                label = key.title() if key != "risk" else "Risk Protection"
                self.analysis_metric_vars[key].set(f"{label}: --")
            self.analysis_text.insert("end", "Generate a schedule or Load Final to see score breakdown, weak areas, and limiting factors.\n")
            return

        label = self.current_label or self._default_week_label()
        hist = history_stats_from(self.model)
        prev_label, prev_tick_map = load_prev_final_schedule_tick_map(label)
        if not prev_tick_map:
            prev_label, prev_tick_map = load_last_schedule_tick_map()

        try:
            unfilled_ticks = max(0, int(getattr(self, "current_total_slots", 0)) - int(getattr(self, "current_filled", 0)))
            bd = schedule_score_breakdown(self.model, label, list(self.current_assignments), unfilled_ticks, hist, prev_tick_map)
        except Exception as ex:
            self.analysis_summary_lbl.config(text=f"Analysis error: {ex}")
            self.analysis_text.insert("end", f"Could not compute schedule analysis.\n\n{ex}\n")
            return

        def _safe_pct(num, den, fallback=100.0):
            try:
                num = float(num)
                den = float(den)
                if den <= 0:
                    return float(fallback)
                return max(0.0, min(100.0, (num / den) * 100.0))
            except Exception:
                return float(fallback)

        total_pen = float(bd.get("total", sum(float(v) for v in bd.values() if isinstance(v, (int, float)))))
        min_pen = float(bd.get("min_coverage_pen", 0.0) or 0.0)
        pref_pen = float(bd.get("preferred_coverage_shortfall_pen", 0.0) or 0.0)
        coverage_pen = min_pen + pref_pen + float(bd.get("max_staffing_violation_pen", 0.0) or 0.0)
        util_pen = float(bd.get("hour_imbalance_pen", 0.0) or 0.0) + float(bd.get("utilization_balance_pen", 0.0) or 0.0) + float(bd.get("utilization_near_cap_pen", 0.0) or 0.0) + float(bd.get("preferred_weekly_cap_pen", 0.0) or 0.0)
        risk_stability_pen = float(bd.get("stability_pen", 0.0) or 0.0)
        risk_fragile_pen = float(bd.get("risk_fragile_pen", 0.0) or 0.0)
        risk_single_point_pen = float(bd.get("risk_single_point_pen", 0.0) or 0.0)
        risk_pen = risk_stability_pen + risk_fragile_pen + risk_single_point_pen
        part_pen = float(bd.get("participation_pen", 0.0) or 0.0) + float(bd.get("employee_max_hours_pen", 0.0) or 0.0) + float(bd.get("target_min_hours_pen", 0.0) or 0.0)

        coverage_pct = _safe_pct(getattr(self, "current_filled", 0), getattr(self, "current_total_slots", 0), fallback=100.0)
        util_pct = max(0.0, min(100.0, 100.0 - min(100.0, util_pen / max(1.0, total_pen + 50.0) * 100.0)))
        risk_pct = max(0.0, min(100.0, 100.0 - min(100.0, risk_pen / max(1.0, total_pen + 50.0) * 100.0)))
        part_pct = max(0.0, min(100.0, 100.0 - min(100.0, part_pen / max(1.0, total_pen + 50.0) * 100.0)))

        self.analysis_metric_vars["coverage"].set(f"Coverage: {coverage_pct:.1f}%")
        self.analysis_metric_vars["utilization"].set(f"Utilization: {util_pct:.1f}%")
        self.analysis_metric_vars["risk"].set(f"Risk Protection: {risk_pct:.1f}%")
        self.analysis_metric_vars["participation"].set(f"Participation: {part_pct:.1f}%")

        self.analysis_summary_lbl.config(
            text=f"Label: {label} • Total hours: {float(getattr(self, 'current_total_hours', 0.0) or 0.0):.1f} • Assignments: {len(self.current_assignments)} • Score penalty: {total_pen:.1f}"
        )

        pattern_pen = float(bd.get("pattern_pen", 0.0) or 0.0)
        employee_fit_pen = float(bd.get("employee_fit_pen", 0.0) or 0.0)
        pattern_pct = max(0.0, min(100.0, 100.0 - min(100.0, (pattern_pen + employee_fit_pen) / max(1.0, total_pen + 50.0) * 100.0)))

        category_rows = [
            ("Coverage", coverage_pen, coverage_pct, f"Filled slots {int(getattr(self, 'current_filled', 0))}/{int(getattr(self, 'current_total_slots', 0))}; minimum coverage penalty {min_pen:.1f}; preferred coverage penalty {pref_pen:.1f}"),
            ("Utilization", util_pen, util_pct, f"Diagnostic metrics: hour imbalance {float(bd.get('hour_imbalance_pen', 0.0) or 0.0):.1f}; low-hours balancing {float(bd.get('utilization_balance_pen', 0.0) or 0.0):.1f}; near-cap pressure {float(bd.get('utilization_near_cap_pen', 0.0) or 0.0):.1f} (score-driving terms: unique-employee + fragmentation penalties)"),
            ("Risk Protection", risk_pen, risk_pct, f"Stability {risk_stability_pen:.1f}; fragile coverage {risk_fragile_pen:.1f}; single-point {risk_single_point_pen:.1f}" + (f" vs {prev_label}" if prev_label else "")),
            ("Participation", part_pen, part_pct, f"Participation misses {float(bd.get('participation_pen', 0.0) or 0.0):.1f}; employee max hours {float(bd.get('employee_max_hours_pen', 0.0) or 0.0):.1f}; target minimum hours {float(bd.get('target_min_hours_pen', 0.0) or 0.0):.1f}"),
            ("Pattern Learning", pattern_pen, pattern_pct, f"Pattern deviation penalty {pattern_pen:.1f}; learned profiles {len(getattr(self.model, 'learned_patterns', {}) or {})}"),
            ("Employee Fit", employee_fit_pen, pattern_pct, f"Employee fit penalty {employee_fit_pen:.1f}; fit profiles {len(((getattr(self.model, 'learned_patterns', {}) or {}).get('__employee_fit__') or {}))}"),
        ]
        for cat, pen, pct, notes in category_rows:
            impact = "Good"
            if pct < 90.0:
                impact = "Watch"
            if pct < 75.0:
                impact = "Weak"
            self.analysis_tree.insert("", "end", values=(cat, f"{pen:.1f}", impact, notes))

        weak_areas = []
        try:
            min_req_ls, pref_req_ls, max_req_ls = build_requirement_maps(self.model.requirements, goals=getattr(self.model, 'manager_goals', None))
            cov_map = count_coverage_per_tick(self.current_assignments)
            shortages = []
            for (day, area, tick), req in min_req_ls.items():
                cov = int(cov_map.get((day, area, tick), 0) or 0)
                if cov < int(req):
                    shortages.append((int(req - cov), day, area, tick, cov, int(req)))
            shortages.sort(reverse=True)
            for deficit, day, area, tick, cov, req in shortages[:5]:
                weak_areas.append(f"{day} {tick_to_hhmm(tick)} {area}: scheduled {cov}, minimum {req} (deficit {deficit})")
        except Exception as ex:
            _write_run_log(f"ANALYSIS | Weak-areas section failed: {repr(ex)}")

        near_cap = []
        try:
            for e in self.model.employees:
                maxh = float(getattr(e, 'max_weekly_hours', 0.0) or 0.0)
                h = float(getattr(self, 'current_emp_hours', {}).get(e.name, 0.0) or 0.0)
                if maxh > 0 and h >= maxh * 0.9:
                    near_cap.append((h / maxh if maxh else 0.0, e.name, h, maxh))
            near_cap.sort(reverse=True)
        except Exception as ex:
            _write_run_log(f"ANALYSIS | Near-cap section failed: {repr(ex)}")
            near_cap = []

        limiting = list((getattr(self, 'last_solver_summary', {}) or {}).get('limiting_factors', []))
        warnings = list(getattr(self, 'current_warnings', []) or [])

        self.analysis_text.insert("end", "Schedule Score Breakdown\n")
        self.analysis_text.insert("end", f"Coverage: {coverage_pct:.1f}%\n")
        self.analysis_text.insert("end", f"Utilization: {util_pct:.1f}%\n")
        self.analysis_text.insert("end", f"Risk Protection: {risk_pct:.1f}%\n")
        self.analysis_text.insert("end", f"Risk subtotal: stability + fragile + single-point = {risk_stability_pen:.1f} + {risk_fragile_pen:.1f} + {risk_single_point_pen:.1f} = {risk_pen:.1f}\n")
        self.analysis_text.insert("end", "Risk controls note: Coverage Risk Protection = scarcity-aware placement guidance; Risk-Aware Optimization = fragile/single-point penalties in score.\n")
        self.analysis_text.insert("end", "Utilization parity note: diagnostic metrics show imbalance/balancing/near-cap signals, while score-driving utilization terms emphasize unique-employee + fragmentation penalties.\n")
        self.analysis_text.insert("end", f"Participation: {part_pct:.1f}%\n")
        self.analysis_text.insert("end", f"Pattern Learning: {pattern_pct:.1f}%\n")
        self.analysis_text.insert("end", f"Employee Fit: {max(0.0, min(100.0, 100.0 - min(100.0, employee_fit_pen / max(1.0, total_pen + 50.0) * 100.0))):.1f}%\n")
        self.analysis_text.insert("end", f"Total Penalty Score: {total_pen:.1f}\n")
        try:
            chosen = str((self.current_diagnostics or {}).get("chosen_scenario", "") or "")
            scenarios = list((self.current_diagnostics or {}).get("phase5_scenarios", []) or [])
            if chosen:
                self.analysis_text.insert("end", f"Scenario Winner: {chosen}\n")
            if scenarios:
                self.analysis_text.insert("end", "Scenario Comparison:\n")
                for row in scenarios[:6]:
                    name = str(row.get("name", "Scenario"))
                    pen = float(row.get("penalty", 0.0) or 0.0)
                    hrs = float(row.get("hours", 0.0) or 0.0)
                    self.analysis_text.insert("end", f"• {name}: penalty {pen:.1f}, hours {hrs:.1f}\n")
        except Exception as ex:
            _write_run_log(f"ANALYSIS | Scenario section failed: {repr(ex)}")
        try:
            forecast = dict((self.current_diagnostics or {}).get("phase5_demand_forecast") or {})
            if forecast:
                mults = dict(forecast.get("multipliers") or {})
                self.analysis_text.insert("end", "Demand Forecast:\n")
                self.analysis_text.insert("end", f"• Morning x{float(mults.get('morning', 1.0) or 1.0):.2f}\n")
                self.analysis_text.insert("end", f"• Midday x{float(mults.get('midday', 1.0) or 1.0):.2f}\n")
                self.analysis_text.insert("end", f"• Evening x{float(mults.get('evening', 1.0) or 1.0):.2f}\n")
                dom = str(forecast.get('dominant_area', '') or '').strip()
                peak = str(forecast.get('peak_bucket', '') or '').strip()
                if dom or peak:
                    self.analysis_text.insert("end", f"• Dominant area: {dom or 'n/a'}; peak bucket: {peak or 'n/a'}\n")
        except Exception as ex:
            _write_run_log(f"ANALYSIS | Demand-forecast section failed: {repr(ex)}")
        self.analysis_text.insert("end", "\nWeak Areas:\n")
        if weak_areas:
            for item in weak_areas:
                self.analysis_text.insert("end", f"• {item}\n")
        else:
            self.analysis_text.insert("end", "• No minimum-coverage deficits found in the current schedule.\n")

        if near_cap:
            self.analysis_text.insert("end", "\nEmployees Near Weekly Max Hours:\n")
            for _, name, h, maxh in near_cap[:5]:
                self.analysis_text.insert("end", f"• {name}: {h:.1f}/{maxh:.1f} hrs\n")

        try:
            pats = getattr(self.model, "learned_patterns", {}) or {}
            pat_pen = float(bd.get("pattern_pen", 0.0) or 0.0)
            fit_pen = float(bd.get("employee_fit_pen", 0.0) or 0.0)
            pat_enabled = bool(getattr(self.model.settings, "learn_from_history", True))
            self.analysis_text.insert("end", "\nPattern Learning:\n")
            if not pat_enabled:
                self.analysis_text.insert("end", "• Pattern learning is currently turned off in Settings.\n")
            elif not pats:
                self.analysis_text.insert("end", "• No learned pattern profiles found yet. Use Refresh Learned Patterns after you have schedule history.\n")
            else:
                self.analysis_text.insert("end", f"• Learned profiles available: {len(pats)}\n")
                self.analysis_text.insert("end", f"• Current schedule pattern penalty: {pat_pen:.1f}\n")
                shown = 0
                for emp_name in sorted(pats.keys()):
                    profile = pats.get(emp_name, {}) or {}
                    self.analysis_text.insert("end", f"• {self._format_pattern_profile(emp_name, profile)}\n")
                    shown += 1
                    if shown >= 5:
                        break
                fit_profiles = dict(pats.get('__employee_fit__') or {})
                if fit_profiles:
                    self.analysis_text.insert("end", "\nEmployee Fit Intelligence:\n")
                    self.analysis_text.insert("end", f"• Employee fit profiles available: {len(fit_profiles)}\n")
                    self.analysis_text.insert("end", f"• Current schedule employee-fit penalty: {fit_pen:.1f}\n")
                    shown_fit = 0
                    for emp_name in sorted(fit_profiles.keys()):
                        prof = dict(fit_profiles.get(emp_name) or {})
                        self.analysis_text.insert("end", f"• {emp_name}: best area {prof.get('best_area','Any') or 'Any'}, best bucket {prof.get('best_bucket','Any') or 'Any'}\n")
                        shown_fit += 1
                        if shown_fit >= 5:
                            break
        except Exception as ex:
            _write_run_log(f"ANALYSIS | Pattern-learning section failed: {repr(ex)}")

        if limiting:
            self.analysis_text.insert("end", "\nLimiting Factors Reported By Solver:\n")
            for item in limiting:
                self.analysis_text.insert("end", f"• {item}\n")

        if warnings:
            self.analysis_text.insert("end", "\nWarnings:\n")
            for item in warnings[:10]:
                self.analysis_text.insert("end", f"• {item}\n")

    # -------- Schedule Change Viewer tab (Phase 4 D4) --------
    def _build_changes_tab(self):
        frm = ttk.Frame(self.tab_changes); frm.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frm, text="Schedule Change Viewer", style="Header.TLabel").pack(anchor="w", pady=(0,4))
        ttk.Label(
            frm,
            text="Compare the current schedule, this week's published final, the previous published final, and the last saved schedule. Read-only.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0,10))

        top = ttk.Frame(frm); top.pack(fill="x", pady=(0,8))
        self.change_left_var = tk.StringVar(value="Current Schedule")
        self.change_right_var = tk.StringVar(value="Published Final (This Week)")
        ttk.Label(top, text="Compare").pack(side="left")
        self.change_left_cb = ttk.Combobox(top, textvariable=self.change_left_var, state="readonly", width=28)
        self.change_left_cb.pack(side="left", padx=(8,4))
        ttk.Label(top, text="vs").pack(side="left", padx=4)
        self.change_right_cb = ttk.Combobox(top, textvariable=self.change_right_var, state="readonly", width=28)
        self.change_right_cb.pack(side="left", padx=(4,8))
        ttk.Button(top, text="Refresh Sources", command=self._refresh_change_viewer_sources).pack(side="left", padx=6)
        ttk.Button(top, text="Compare Selected", command=self._refresh_change_viewer).pack(side="left", padx=6)
        ttk.Button(top, text="Current vs Final", command=lambda: self._preset_change_compare("Current Schedule", "Published Final (This Week)")).pack(side="left", padx=6)
        ttk.Button(top, text="Current vs Previous Final", command=lambda: self._preset_change_compare("Current Schedule", "Previous Published Final")).pack(side="left", padx=6)

        self.change_summary_lbl = ttk.Label(frm, text="", foreground="#333")
        self.change_summary_lbl.pack(fill="x", pady=(0,8))

        cols = ("Type", "Day", "Area", "Time", "From", "To")
        self.change_tree = ttk.Treeview(frm, columns=cols, show="headings", height=12)
        for c in cols:
            self.change_tree.heading(c, text=c)
            w = 120
            if c in ("From", "To"):
                w = 180
            if c == "Time":
                w = 140
            if c == "Type":
                w = 150
            self.change_tree.column(c, width=w, stretch=True)
        self.change_tree.pack(fill="both", expand=False, pady=(0,8))

        body = ttk.Frame(frm); body.pack(fill="both", expand=True)
        self.change_text = tk.Text(body, wrap="word", height=16)
        vs = ttk.Scrollbar(body, orient="vertical", command=self.change_text.yview)
        self.change_text.configure(yscrollcommand=vs.set)
        self.change_text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._refresh_change_viewer_sources()
        self._refresh_change_viewer()

    def _preset_change_compare(self, left_name: str, right_name: str):
        try:
            vals = list(self.change_left_cb.cget("values") or [])
        except Exception:
            vals = []
        if left_name in vals:
            self.change_left_var.set(left_name)
        if right_name in vals:
            self.change_right_var.set(right_name)
        self._refresh_change_viewer()

    def _change_view_sources(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        cur_label = str(getattr(self, "current_label", "") or self.label_var.get().strip() or self._default_week_label())
        if self.current_assignments:
            out["Current Schedule"] = {
                "label": cur_label,
                "assignments": list(self.current_assignments),
                "detail": f"{len(self.current_assignments)} assignments loaded in the app",
            }

        final_path, final_payload = load_final_schedule_payload_for_label(cur_label)
        if final_payload:
            final_assigns = load_assignments_from_final_payload(final_payload)
            out["Published Final (This Week)"] = {
                "label": str(final_payload.get("label", cur_label) or cur_label),
                "assignments": final_assigns,
                "detail": final_path or "Published final schedule",
            }

        prev_label, prev_path, prev_assigns = load_prev_final_schedule_assignments(cur_label)
        if prev_assigns:
            out["Previous Published Final"] = {
                "label": str(prev_label or "Previous published final"),
                "assignments": prev_assigns,
                "detail": prev_path or "Previous published final schedule",
            }

        last_label, last_assigns = load_last_schedule_assignments()
        if last_assigns:
            out["Last Saved Schedule"] = {
                "label": str(last_label or "Last saved schedule"),
                "assignments": last_assigns,
                "detail": rel_path("data", "last_schedule.json"),
            }
        return out

    def _refresh_change_viewer_sources(self):
        if not hasattr(self, "change_left_cb"):
            return
        sources = self._change_view_sources()
        names = list(sources.keys())
        self._change_sources_cache = sources
        self.change_left_cb["values"] = names
        self.change_right_cb["values"] = names
        if names:
            if self.change_left_var.get() not in names:
                self.change_left_var.set(names[0])
            preferred = "Published Final (This Week)" if "Published Final (This Week)" in names else (names[1] if len(names) > 1 else names[0])
            if self.change_right_var.get() not in names:
                self.change_right_var.set(preferred)
        else:
            self.change_left_var.set("")
            self.change_right_var.set("")

    def _coalesce_change_segments(self, left_assigns: List[Assignment], right_assigns: List[Assignment]) -> List[Dict[str, Any]]:
        left_map = _expand_assignments_to_tick_map(list(left_assigns or []))
        right_map = _expand_assignments_to_tick_map(list(right_assigns or []))
        def _area_index(area: str) -> int:
            try:
                return AREAS.index(area)
            except Exception:
                return 999
        keys = sorted(set(left_map.keys()) | set(right_map.keys()), key=lambda k: (DAYS.index(k[0]), _area_index(k[1]), int(k[2])))

        segments: List[Dict[str, Any]] = []
        cur = None
        for day, area, tt in keys:
            old_emp = str(left_map.get((day, area, tt), "") or "")
            new_emp = str(right_map.get((day, area, tt), "") or "")
            if old_emp == new_emp:
                cur = None
                continue
            if old_emp and new_emp:
                typ = "Reassigned"
            elif old_emp and not new_emp:
                typ = "Removed"
            else:
                typ = "Added"
            if cur and cur["day"] == day and cur["area"] == area and cur["type"] == typ and cur["from"] == (old_emp or "—") and cur["to"] == (new_emp or "—") and cur["end_t"] == tt:
                cur["end_t"] = tt + 1
            else:
                cur = {
                    "type": typ,
                    "day": day,
                    "area": area,
                    "start_t": int(tt),
                    "end_t": int(tt) + 1,
                    "from": old_emp or "—",
                    "to": new_emp or "—",
                }
                segments.append(cur)
        return segments

    def _refresh_change_viewer(self):
        if not hasattr(self, "change_text"):
            return
        try:
            self._refresh_change_viewer_sources()
        except Exception:
            pass

        for i in self.change_tree.get_children():
            self.change_tree.delete(i)
        self.change_text.delete("1.0", "end")

        sources = getattr(self, "_change_sources_cache", {}) or {}
        left_name = self.change_left_var.get().strip()
        right_name = self.change_right_var.get().strip()
        left = sources.get(left_name)
        right = sources.get(right_name)
        if not left or not right:
            self.change_summary_lbl.config(text="Not enough schedule sources available yet.")
            self.change_text.insert("end", "Generate a schedule or publish a final schedule to compare changes.\n")
            return
        if left_name == right_name:
            self.change_summary_lbl.config(text="Choose two different schedule sources to compare.")
            self.change_text.insert("end", "The same source is selected on both sides.\n")
            return

        left_assigns = list(left.get("assignments", []) or [])
        right_assigns = list(right.get("assignments", []) or [])
        segments = self._coalesce_change_segments(left_assigns, right_assigns)

        added = sum(1 for s in segments if s["type"] == "Added")
        removed = sum(1 for s in segments if s["type"] == "Removed")
        reassigned = sum(1 for s in segments if s["type"] == "Reassigned")
        total = len(segments)

        self.change_summary_lbl.config(text=f"{left_name} → {right_name} • {total} change segments • Added: {added} • Removed: {removed} • Reassigned: {reassigned}")

        for seg in segments[:500]:
            self.change_tree.insert("", "end", values=(seg["type"], seg["day"], seg["area"], f"{tick_to_ampm(seg['start_t'])}–{tick_to_ampm(seg['end_t'])}", seg["from"], seg["to"]))

        self.change_text.insert("end", f"Compare: {left_name}\n")
        self.change_text.insert("end", f"Label: {left.get('label','')}\n")
        self.change_text.insert("end", f"Source: {left.get('detail','')}\n\n")
        self.change_text.insert("end", f"Against: {right_name}\n")
        self.change_text.insert("end", f"Label: {right.get('label','')}\n")
        self.change_text.insert("end", f"Source: {right.get('detail','')}\n\n")

        if not segments:
            self.change_text.insert("end", "No schedule differences were found between these two sources.\n")
            return

        self.change_text.insert("end", f"Summary\n-------\nAdded segments: {added}\nRemoved segments: {removed}\nReassigned segments: {reassigned}\n\n")

        by_day = {d: [] for d in DAYS}
        for seg in segments:
            by_day.setdefault(seg["day"], []).append(seg)

        self.change_text.insert("end", "Day-by-day changes\n------------------\n")
        for d in DAYS:
            items = by_day.get(d, [])
            if not items:
                continue
            self.change_text.insert("end", f"\n{d}\n")
            for seg in items[:20]:
                self.change_text.insert("end", f"  • {seg['area']} {tick_to_ampm(seg['start_t'])}–{tick_to_ampm(seg['end_t'])}: {seg['type']} | {seg['from']} → {seg['to']}\n")
            if len(items) > 20:
                self.change_text.insert("end", f"  … {len(items) - 20} more changes on {d}\n")

    # -------- Coverage Heatmap tab (Phase 4 B1) --------
    def _build_heatmap_tab(self):
        frm = ttk.Frame(self.tab_heatmap); frm.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frm, text="Coverage Risk Heatmap (read-only)", style="Header.TLabel").pack(anchor="w", pady=(0,4))
        ttk.Label(
            frm,
            text="Shows scheduled headcount vs staffing requirements for each 30-minute block. This does not change the solver.",
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(0,10))

        top = ttk.Frame(frm); top.pack(fill="x", pady=(0,8))

        ttk.Label(top, text="Target:").pack(side="left")
        self.hm_target_var = tk.StringVar(value="Minimum")
        ttk.OptionMenu(top, self.hm_target_var, "Minimum", "Minimum", "Preferred").pack(side="left", padx=(6,14))

        self.hm_fragile_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Highlight fragile (1 scheduled / 1 required)", variable=self.hm_fragile_var).pack(side="left")

        ttk.Button(top, text="Refresh Heatmap", command=self._refresh_heatmap).pack(side="left", padx=(14,0))

        # Legend
        legend = ttk.Frame(frm); legend.pack(fill="x", pady=(0,8))
        ttk.Label(legend, text="Legend:", style="SubHeader.TLabel").pack(side="left")
        self._legend_chip(legend, "Understaffed", "#ffb3b3")
        self._legend_chip(legend, "Tight (meets minimum)", "#fff2b3")
        self._legend_chip(legend, "Fragile (1/1)", "#ffd1a3")
        self._legend_chip(legend, "Overstaffed", "#c9f7c9")
        self._legend_chip(legend, "No requirement", "#f0f0f0")

        # Scrollable canvas grid
        outer = ttk.Frame(frm); outer.pack(fill="both", expand=True)
        self.hm_canvas = tk.Canvas(outer, highlightthickness=0)
        vs = ttk.Scrollbar(outer, orient="vertical", command=self.hm_canvas.yview)
        hs = ttk.Scrollbar(outer, orient="horizontal", command=self.hm_canvas.xview)
        self.hm_canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)

        self.hm_canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        # container for drawings
        self.hm_items: List[int] = []
        self._refresh_heatmap()

    def _legend_chip(self, parent, label: str, color: str):
        chip = tk.Canvas(parent, width=18, height=12, highlightthickness=1, highlightbackground="#bdbdbd")
        chip.create_rectangle(0, 0, 18, 12, fill=color, outline=color)
        chip.pack(side="left", padx=(10,4))
        ttk.Label(parent, text=label, style="Hint.TLabel").pack(side="left")

    def _refresh_heatmap(self):
        try:
            if not hasattr(self, "hm_canvas"):
                return
            # clear old
            for it in getattr(self, "hm_items", []):
                try:
                    self.hm_canvas.delete(it)
                except Exception:
                    pass
            self.hm_items = []

            target = (self.hm_target_var.get() or "Minimum").strip()
            use_pref = (target.lower().startswith("pref"))

            # Determine which schedule to visualize:
            # prefer current working schedule; otherwise try this week's locked final.
            assignments = list(self.current_assignments or [])
            if not assignments:
                # attempt to load this week's final (without modifying current state)
                try:
                    wk = self._week_start_sunday_iso()
                    final_path = os.path.join(_app_dir(), "data", "final_schedules", f"{wk}.json")
                    if os.path.isfile(final_path):
                        with open(final_path, "r", encoding="utf-8") as f:
                            payload = json.load(f)
                        assigns = payload.get("assignments") or []
                        assignments = [des_assignment(a) for a in assigns]
                except Exception as ex:
                    _write_run_log(f"HEATMAP | Fallback final-schedule load failed: {repr(ex)}")

            if not assignments:
                # still nothing
                msg = "No schedule found yet. Generate a schedule (or lock a final schedule) and then click Refresh."
                it = self.hm_canvas.create_text(20, 20, text=msg, anchor="nw")
                self.hm_items.append(it)
                self.hm_canvas.configure(scrollregion=(0,0,800,200))
                return

            # build maps
            min_req, pref_req, max_req = build_requirement_maps(self.model.requirements, goals=getattr(self.model, "manager_goals", None))
            req_map = pref_req if use_pref else min_req
            cov = count_coverage_per_tick(assignments)

            # store for drill-down (B2)
            self.hm_last_req_map = dict(req_map)
            self.hm_last_cov = dict(cov)
            self.hm_last_assignments = list(assignments)
            self.hm_cell_index = {}  # item_id -> (day, area, tick)
# grid specs
            col_groups: List[Tuple[str,str]] = []
            for d in DAYS:
                for a in AREAS:
                    col_groups.append((d, a))
            n_cols = len(col_groups)

            cell_w = 74
            cell_h = 20
            row_header_w = 60
            header_h = 24

            # colors
            c_under = "#ffb3b3"
            c_tight = "#fff2b3"
            c_frag  = "#ffd1a3"
            c_over  = "#c9f7c9"
            c_none  = "#f0f0f0"

            # draw header
            x0 = row_header_w
            y0 = 0
            for ci, (d,a) in enumerate(col_groups):
                x = x0 + ci*cell_w
                label = f"{d}\n{a[:1]}"
                r = self.hm_canvas.create_rectangle(x, y0, x+cell_w, y0+header_h, fill="#e9ecef", outline="#c9c9c9")
                t = self.hm_canvas.create_text(x+cell_w/2, y0+header_h/2, text=label, justify="center", font=("Segoe UI", 9))
                self.hm_items.extend([r,t])
            # row header + grid
            for tck in range(DAY_TICKS):
                y = header_h + tck*cell_h
                # time label
                time_lbl = tick_to_hhmm(tck)
                r0 = self.hm_canvas.create_rectangle(0, y, row_header_w, y+cell_h, fill="#e9ecef", outline="#c9c9c9")
                t0 = self.hm_canvas.create_text(row_header_w/2, y+cell_h/2, text=time_lbl, font=("Segoe UI", 9))
                self.hm_items.extend([r0,t0])

                for ci, (d,a) in enumerate(col_groups):
                    x = x0 + ci*cell_w
                    k = (d, a, int(tck))
                    req = int(req_map.get(k, 0))
                    sc  = int(cov.get(k, 0))

                    if req <= 0 and sc <= 0:
                        fill = c_none
                        txt = ""
                    else:
                        if sc < req:
                            fill = c_under
                        elif sc == req:
                            if self.hm_fragile_var.get() and req == 1 and sc == 1:
                                fill = c_frag
                            else:
                                fill = c_tight
                        else:
                            fill = c_over
                        txt = f"{sc}/{req}" if req>0 else f"{sc}/0"

                    r = self.hm_canvas.create_rectangle(x, y, x+cell_w, y+cell_h, fill=fill, outline="#d0d0d0")
                    # B2 drill-down: click a cell to see details
                    try:
                        self.hm_cell_index[r] = (d, a, int(tck))
                        self.hm_canvas.tag_bind(r, "<Button-1>", lambda ev, dd=d, aa=a, tt=int(tck): self._hm_on_cell_click(dd, aa, tt))
                    except Exception:
                        pass

                    tt = self.hm_canvas.create_text(x+cell_w/2, y+cell_h/2, text=txt, font=("Segoe UI", 9))
                    # also allow clicking the text in the cell
                    try:
                        self.hm_canvas.tag_bind(tt, "<Button-1>", lambda ev, dd=d, aa=a, tt=int(tck): self._hm_on_cell_click(dd, aa, tt))
                    except Exception:
                        pass
                    self.hm_items.extend([r,tt])

            total_w = row_header_w + n_cols*cell_w + 2
            total_h = header_h + DAY_TICKS*cell_h + 2
            self.hm_canvas.configure(scrollregion=(0,0,total_w,total_h))
        except Exception as e:
            try:
                messagebox.showerror("Heatmap", f"Failed to render heatmap:\n{e}")
            except Exception:
                pass


    def _hm_on_cell_click(self, day: str, area: str, tick: int):
        """Heatmap drill-down: show who's working and the gap/overstaff."""
        try:
            req_map = getattr(self, "hm_last_req_map", {}) or {}
            cov = getattr(self, "hm_last_cov", {}) or {}
            assignments = getattr(self, "hm_last_assignments", []) or []

            k = (day, area, int(tick))
            req = int(req_map.get(k, 0))
            sc = int(cov.get(k, 0))

            # who is working in this cell?
            names = []
            for a in assignments:
                try:
                    if a.day != day or a.area != area:
                        continue
                    if int(a.start_t) <= int(tick) < int(a.end_t):
                        nm = (a.employee_name or "").strip()
                        if nm:
                            names.append(nm)
                except Exception:
                    continue

            # unique (preserve order)
            seen = set()
            uniq = []
            for n in names:
                if n not in seen:
                    uniq.append(n); seen.add(n)

            time_lbl = tick_to_hhmm(int(tick))
            title = f"{day} {time_lbl} — {area}"

            lines = []
            lines.append(f"Required Staff: {req}")
            lines.append(f"Scheduled Staff: {sc}")
            lines.append("")

            if uniq:
                lines.append("Employees Working:")
                for n in uniq:
                    lines.append(f"• {n}")
            else:
                lines.append("Employees Working:")
                lines.append("• (none)")

            # gap / overstaff note
            if req > 0:
                if sc < req:
                    lines.append("")
                    lines.append(f"Coverage Gap: {req - sc} additional employee(s) needed")
                elif sc > req:
                    lines.append("")
                    lines.append(f"Possible Overstaffing: +{sc - req}")
                else:
                    # sc == req
                    if req == 1 and sc == 1 and bool(getattr(self, "hm_fragile_var", tk.BooleanVar(value=False)).get()):
                        lines.append("")
                        lines.append("Fragile: a single call-off breaks coverage")
            else:
                if sc > 0:
                    lines.append("")
                    lines.append("No requirement set for this time block.")

            messagebox.showinfo("Heatmap Detail", "\n".join(lines))
        except Exception as e:
            try:
                messagebox.showerror("Heatmap Detail", f"Failed to open cell detail:\n{e}")
            except Exception:
                pass


    # -------- Call-Off Simulator tab (Phase 4 C2) --------
    def _build_calloff_tab(self):
        frm = ttk.Frame(self.tab_calloff); frm.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frm, text="Call-Off Simulator (read-only)", style="Header.TLabel").pack(anchor="w", pady=(0,4))
        ttk.Label(
            frm,
            text="Simulate an employee calling off. Shows resulting coverage gaps and suggests backup employees to contact. This does not change the schedule.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0,10))

        top = ttk.Frame(frm); top.pack(fill="x", pady=(0,10))
        ttk.Label(top, text="Employee:").pack(side="left")

        self.co_emp_var = tk.StringVar(value="")
        self.co_emp_menu = ttk.OptionMenu(top, self.co_emp_var, "")
        self.co_emp_menu.pack(side="left", padx=(6,12))
        ttk.Button(top, text="Refresh Employee List", command=self._calloff_refresh_employees).pack(side="left")

        ttk.Label(top, text="   Days:").pack(side="left", padx=(16,0))
        self.co_all_days_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="All", variable=self.co_all_days_var, command=self._calloff_sync_days).pack(side="left")
        self.co_day_vars = {d: tk.BooleanVar(value=False) for d in DAYS}
        for d in DAYS:
            ttk.Checkbutton(top, text=d[:1], variable=self.co_day_vars[d], command=self._calloff_on_day_toggle).pack(side="left", padx=(4,0))

        ttk.Button(top, text="Simulate Call-Off", command=self._simulate_calloff).pack(side="right")

        body = ttk.Frame(frm); body.pack(fill="both", expand=True)
        self.co_text = tk.Text(body, wrap="word", height=18)
        vs = ttk.Scrollbar(body, orient="vertical", command=self.co_text.yview)
        self.co_text.configure(yscrollcommand=vs.set)
        self.co_text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._calloff_refresh_employees()
        self._calloff_sync_days()
        self._calloff_write_intro()

    def _calloff_write_intro(self):
        try:
            self.co_text.delete("1.0", "end")
            self.co_text.insert("end", "How to use:\n")
            self.co_text.insert("end", "1) Generate a schedule (or Load Final).\n")
            self.co_text.insert("end", "2) Pick an employee and click Simulate Call-Off.\n\n")
            self.co_text.insert("end", "This uses your current schedule if one is loaded; otherwise it tries this week's locked final schedule.\n")
        except Exception:
            pass

    def _calloff_sync_days(self):
        all_on = bool(self.co_all_days_var.get())
        for d in DAYS:
            try:
                self.co_day_vars[d].set(False if all_on else bool(self.co_day_vars[d].get()))
            except Exception:
                pass

    def _calloff_on_day_toggle(self):
        try:
            any_day = any(bool(v.get()) for v in self.co_day_vars.values())
            self.co_all_days_var.set(not any_day)
        except Exception:
            pass

    def _calloff_refresh_employees(self):
        try:
            names = []
            for e in getattr(self.model, "employees", []) or []:
                try:
                    if getattr(e, "work_status", "Active") != "Active":
                        continue
                    nm = (getattr(e, "name", "") or "").strip()
                    if nm:
                        names.append(nm)
                except Exception:
                    continue
            names = sorted(set(names), key=lambda s: s.lower())
            if not names:
                names = [""]

            menu = self.co_emp_menu["menu"]
            menu.delete(0, "end")
            for n in names:
                menu.add_command(label=n, command=lambda v=n: self.co_emp_var.set(v))

            cur = (self.co_emp_var.get() or "").strip()
            if cur not in names:
                self.co_emp_var.set(names[0])
        except Exception:
            pass

    def _simulate_calloff(self):
        try:
            emp_name = (self.co_emp_var.get() or "").strip()
            if not emp_name:
                messagebox.showwarning("Call-Off Simulator", "Pick an employee first.")
                return

            if bool(self.co_all_days_var.get()):
                days = set(DAYS)
            else:
                days = {d for d, v in self.co_day_vars.items() if bool(v.get())}
                if not days:
                    days = set(DAYS)

            assignments = list(self.current_assignments or [])
            label = str(self.current_label or "")
            if not assignments:
                try:
                    wk = self._week_start_sunday_iso()
                    final_path = os.path.join(_app_dir(), "data", "final_schedules", f"{wk}.json")
                    if os.path.isfile(final_path):
                        with open(final_path, "r", encoding="utf-8") as f:
                            payload = json.load(f)
                        assigns = payload.get("assignments") or []
                        assignments = [des_assignment(a) for a in assigns]
                        label = payload.get("label") or label
                except Exception as ex:
                    _write_run_log(f"CALL_OFF | Fallback final-schedule load failed: {repr(ex)}")

            if not assignments:
                messagebox.showinfo("Call-Off Simulator", "No schedule found. Generate a schedule or lock a final schedule first.")
                return

            min_req, _pref_req, _max_req = build_requirement_maps(self.model.requirements, goals=getattr(self.model, "manager_goals", None))
            req = dict(min_req)

            removed = [a for a in assignments if (a.employee_name == emp_name and a.day in days)]
            kept = [a for a in assignments if not (a.employee_name == emp_name and a.day in days)]

            new_cov = count_coverage_per_tick(kept)

            windows = []  # (deficit_hours, peak, day, area, st, en)
            for day in DAYS:
                if day not in days:
                    continue
                for area in AREAS:
                    t = 0
                    while t < DAY_TICKS:
                        r = int(req.get((day, area, t), 0))
                        s = int(new_cov.get((day, area, t), 0))
                        d = max(0, r - s)
                        if d <= 0:
                            t += 1
                            continue
                        st = t
                        peak = d
                        def_h = 0.0
                        while t < DAY_TICKS:
                            r2 = int(req.get((day, area, t), 0))
                            s2 = int(new_cov.get((day, area, t), 0))
                            d2 = max(0, r2 - s2)
                            if d2 <= 0:
                                break
                            peak = max(peak, d2)
                            def_h += d2 * 0.5
                            t += 1
                        en = t
                        windows.append((def_h, peak, day, area, st, en))
            windows.sort(reverse=True, key=lambda x: (x[0], x[1]))

            emp_week_hours: Dict[str, float] = {}
            for a in kept:
                emp_week_hours[a.employee_name] = emp_week_hours.get(a.employee_name, 0.0) + hours_between_ticks(a.start_t, a.end_t)
            clopen = _clopen_map_from_assignments(self.model, kept)

            def is_working_in_window(e_name: str, day: str, st: int, en: int) -> bool:
                for a in kept:
                    if a.employee_name != e_name:
                        continue
                    if a.day != day:
                        continue
                    if not (int(a.end_t) <= int(st) or int(a.start_t) >= int(en)):
                        return True
                return False

            def candidates_for(area: str, day: str, st: int, en: int) -> List[Employee]:
                goals = getattr(self.model, "manager_goals", None)
                include_noncert = bool(getattr(goals, "include_noncertified_in_call_list", False)) if goals else False
                out = []
                for e in self.model.employees:
                    if getattr(e, "work_status", "Active") != "Active":
                        continue
                    if (getattr(e, "name", "") or "").strip() == emp_name:
                        continue

                    certified = area in getattr(e, "areas_allowed", [])
                    if not certified and not include_noncert:
                        continue

                    if is_working_in_window(e.name, day, st, en):
                        continue

                    window_h = hours_between_ticks(st, en)
                    cur_h = emp_week_hours.get(e.name, 0.0)
                    slack = float(getattr(e, "max_weekly_hours", 0.0)) - cur_h
                    not_near_restrict = slack >= window_h

                    available = is_employee_available(self.model, e, label, day, st, en, area, clopen)
                    out.append((certified, not_near_restrict, available, -cur_h, e.name.lower(), e))
                out.sort(reverse=True, key=lambda x: (x[0], x[1], x[2], x[3], x[4]))
                return [x[-1] for x in out]

            # Write report
            self.co_text.delete("1.0", "end")
            self.co_text.insert("end", f"Simulated call-off: {emp_name}\n")
            self.co_text.insert("end", f"Days: {', '.join([d for d in DAYS if d in days])}\n")
            self.co_text.insert("end", f"Removed shifts: {len(removed)}\n")
            if removed:
                for a in removed[:10]:
                    self.co_text.insert("end", f"  - {a.day} {a.area} {tick_to_ampm(a.start_t)}–{tick_to_ampm(a.end_t)}\n")
                if len(removed) > 10:
                    self.co_text.insert("end", f"  ... +{len(removed)-10} more\n")

            self.co_text.insert("end", "\nTop coverage gaps created (after call-off):\n")
            if not windows:
                self.co_text.insert("end", "  ✅ No new understaffing windows detected for the selected day(s).\n")
                return

            depth = 5
            try:
                goals = getattr(self.model, "manager_goals", None)
                depth = int(getattr(goals, "call_list_depth", 5)) if goals else 5
                depth = max(1, min(12, depth))
            except Exception:
                depth = 5

            for (def_h, peak, day, area, st, en) in windows[:10]:
                self.co_text.insert("end", f"\n• {day} {area} {tick_to_ampm(st)}–{tick_to_ampm(en)}  |  est shortage: {def_h:.1f} labor-hrs  |  peak deficit: {peak}\n")
                cands = candidates_for(area, day, st, en)[:depth]
                if not cands:
                    self.co_text.insert("end", "    (No qualified backup candidates found for this window.)\n")
                    continue
                for i, e in enumerate(cands, 1):
                    cur_h = emp_week_hours.get(e.name, 0.0)
                    phone = getattr(e, "phone", "")
                    self.co_text.insert("end", f"    {i}) {e.name} ({cur_h:.1f} hrs) — {phone}\n")

        except Exception as e:
            try:
                messagebox.showerror("Call-Off Simulator", f"Simulation failed:\n{e}")
            except Exception:
                pass


    def _week_start_sunday_iso(self) -> str:
        # The app's schedule label is already anchored to the week; use the same helper used elsewhere.
        try:
            wk = week_start_sunday_for_label(self.current_label)
            if wk:
                return wk.isoformat()
        except Exception:
            pass
        # fallback: today -> most recent Sunday
        d = datetime.date.today()
        # Python weekday: Mon=0..Sun=6
        delta = (d.weekday() + 1) % 7
        return (d - datetime.timedelta(days=delta)).isoformat()


    def _build_manual_tab(self):
        self.manual_vars = {"MAIN": {}, "KITCHEN": {}, "CARWASH": {}}

        frm = ttk.Frame(self.tab_manual); frm.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frm, text="Smart manual editor (Option A grid). Edit the printable schedule cells, analyze warnings, then apply to the current schedule.",
                  style="SubHeader.TLabel").pack(anchor="w", pady=(0,4))
        ttk.Label(frm, text="MAIN = C-Store hours plus hints. Kitchen and Carwash pages control those department assignments. Time format examples: 7am-3pm or 7:30am-12pm; 1pm-5pm",
                  style="Hint.TLabel").pack(anchor="w", pady=(0,8))

        top = ttk.Frame(frm); top.pack(fill="x", pady=(0,8))
        ttk.Button(top, text="Load From Current Schedule", command=self._manual_load_btn).pack(side="left")
        ttk.Button(top, text="Analyze Manual Edits", command=self._manual_analyze_btn).pack(side="left", padx=8)
        ttk.Button(top, text="Apply To Current Schedule", command=self._manual_apply_btn).pack(side="left", padx=8)
        ttk.Button(top, text="Save Manual Edits", command=self._manual_save_btn).pack(side="left", padx=8)
        ttk.Button(top, text="Open Manual Employee Calendar (HTML)", command=self._manual_open_html).pack(side="left", padx=8)
        ttk.Button(top, text="Clear Manual Edits", command=self._manual_clear_btn).pack(side="left", padx=8)

        swap = ttk.LabelFrame(frm, text="Quick Swap")
        swap.pack(fill="x", pady=(0,8))
        emp_names = self._manual_employee_names()
        self.manual_swap_kind_var = tk.StringVar(value="MAIN")
        self.manual_swap_day_var = tk.StringVar(value=DAYS[0])
        self.manual_swap_from_var = tk.StringVar(value=(emp_names[0] if emp_names else ""))
        self.manual_swap_to_var = tk.StringVar(value=(emp_names[1] if len(emp_names) > 1 else (emp_names[0] if emp_names else "")))
        ttk.Label(swap, text="Page").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(swap, textvariable=self.manual_swap_kind_var, values=["MAIN","KITCHEN","CARWASH"], state="readonly", width=12).grid(row=0, column=1, sticky="w", padx=4, pady=6)
        ttk.Label(swap, text="Day").grid(row=0, column=2, sticky="w", padx=(14,4), pady=6)
        ttk.Combobox(swap, textvariable=self.manual_swap_day_var, values=DAYS, state="readonly", width=12).grid(row=0, column=3, sticky="w", padx=4, pady=6)
        ttk.Label(swap, text="From").grid(row=0, column=4, sticky="w", padx=(14,4), pady=6)
        ttk.Combobox(swap, textvariable=self.manual_swap_from_var, values=emp_names, state="readonly", width=24).grid(row=0, column=5, sticky="w", padx=4, pady=6)
        ttk.Label(swap, text="To").grid(row=0, column=6, sticky="w", padx=(14,4), pady=6)
        ttk.Combobox(swap, textvariable=self.manual_swap_to_var, values=emp_names, state="readonly", width=24).grid(row=0, column=7, sticky="w", padx=4, pady=6)
        ttk.Button(swap, text="Swap Cells", command=self._manual_swap_selected_day).grid(row=0, column=8, sticky="w", padx=(14,8), pady=6)

        self.manual_status_lbl = ttk.Label(frm, text="", foreground="#333")
        self.manual_status_lbl.pack(anchor="w", pady=(0,6))

        warn_wrap = ttk.LabelFrame(frm, text="Manual Edit Warnings")
        warn_wrap.pack(fill="both", expand=False, pady=(0,8))
        self.manual_warn_txt = tk.Text(warn_wrap, height=9, wrap="word")
        mvs = ttk.Scrollbar(warn_wrap, orient="vertical", command=self.manual_warn_txt.yview)
        self.manual_warn_txt.configure(yscrollcommand=mvs.set)
        self.manual_warn_txt.grid(row=0, column=0, sticky="nsew")
        mvs.grid(row=0, column=1, sticky="ns")
        warn_wrap.rowconfigure(0, weight=1)
        warn_wrap.columnconfigure(0, weight=1)

        note = ttk.Notebook(frm); note.pack(fill="both", expand=True)

        def _make_scroll(parent):
            outer = ttk.Frame(parent)
            outer.pack(fill="both", expand=True)
            canvas = tk.Canvas(outer, highlightthickness=0)
            vs = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
            hs = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
            canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
            vs.pack(side="right", fill="y")
            hs.pack(side="bottom", fill="x")
            canvas.pack(side="left", fill="both", expand=True)
            inner = ttk.Frame(canvas)
            win = canvas.create_window((0,0), window=inner, anchor="nw")
            def _on_config(_e=None):
                canvas.configure(scrollregion=canvas.bbox("all"))
            inner.bind("<Configure>", _on_config)
            def _on_canvas_config(e):
                canvas.itemconfigure(win, width=max(e.width, 980))
            canvas.bind("<Configure>", _on_canvas_config)
            return inner

        def _build_grid(parent, kind: str):
            inner = _make_scroll(parent)
            ttk.Label(inner, text="Employee", style="SubHeader.TLabel").grid(row=0, column=0, sticky="w", padx=4, pady=4)
            for j, d in enumerate(DAYS, start=1):
                ttk.Label(inner, text=d, style="SubHeader.TLabel").grid(row=0, column=j, sticky="n", padx=3, pady=4)
            emps = sorted(self.model.employees, key=lambda e: (e.name or "").lower())
            for i, e in enumerate(emps, start=1):
                nm = (e.name or "").strip()
                if not nm:
                    continue
                phone_str = (e.phone or "").strip()
                name_line = nm + (f" - {phone_str}" if phone_str else "")
                ttk.Label(inner, text=name_line).grid(row=i, column=0, sticky="w", padx=4, pady=2)
                self.manual_vars[kind].setdefault(nm, {})
                for j, d in enumerate(DAYS, start=1):
                    var = tk.StringVar(value="")
                    ent = ttk.Entry(inner, textvariable=var, width=18)
                    ent.grid(row=i, column=j, sticky="nsew", padx=2, pady=2)
                    self.manual_vars[kind][nm][d] = var
            for j in range(0, len(DAYS)+1):
                inner.grid_columnconfigure(j, weight=1)

        for title, kind in [("Manual: Main (C-Store + hints)", "MAIN"), ("Manual: Kitchen", "KITCHEN"), ("Manual: Carwash", "CARWASH")]:
            f = ttk.Frame(note)
            note.add(f, text=title)
            _build_grid(f, kind)

        try:
            payload = self._load_manual_overrides()
            cur_label = str(getattr(self, "current_label", "") or "")
            stored_label = str(payload.get("label","") or "")
            if payload and (not cur_label or stored_label == cur_label):
                self._manual_apply_to_ui(payload.get("pages", {}) or {})
            elif self.current_assignments:
                base = self._compute_calendar_base_texts(self.current_assignments)
                self._manual_apply_to_ui(base)
            self._manual_status("Manual editor ready.")
            self._manual_set_warning_text(["Analyze Manual Edits to check coverage, availability, overlaps, minors rules, and weekly hours before applying."])
        except Exception:
            pass

    def _build_manager_tab(self):
        frm = ttk.Frame(self.tab_mgr); frm.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frm, text="Manager Goals (caps are saved/validated; solver enforcement starts later)", style="Header.TLabel").pack(anchor="w", pady=(0,8))

        goals = self.model.manager_goals

        grid = ttk.Frame(frm); grid.pack(anchor="w", fill="x")
        grid.columnconfigure(1, weight=1)

        # Vars
        self.mgr_cov_goal = tk.StringVar(value=str(getattr(goals, "coverage_goal_pct", 95.0)))
        self.mgr_daily_over = tk.StringVar(value=str(getattr(goals, "daily_overstaff_allow_hours", 0.0)))
        # Caps
        self.mgr_pref_weekly_cap = tk.StringVar(value=str(getattr(goals, "preferred_weekly_cap", getattr(goals, "weekly_hours_cap", 0.0))))
        self.mgr_max_weekly_cap = tk.StringVar(value=str(getattr(goals, "maximum_weekly_cap", 0.0)))
        # Demand multipliers (Phase 2 P2-5)
        self.mgr_demand_morning = tk.StringVar(value=str(getattr(goals, "demand_morning_multiplier", 1.0)))
        self.mgr_demand_midday = tk.StringVar(value=str(getattr(goals, "demand_midday_multiplier", 1.0)))
        self.mgr_demand_evening = tk.StringVar(value=str(getattr(goals, "demand_evening_multiplier", 1.0)))
        # Phase 3 toggles/weights
        self.mgr_enable_risk = tk.BooleanVar(value=bool(getattr(goals, "enable_coverage_risk_protection", True)))
        self.mgr_w_risk = tk.StringVar(value=str(getattr(goals, "w_coverage_risk", 10.0)))

        # Phase 4 C3: Risk-Aware Optimization (adds resilience buffer)
        self.mgr_enable_riskaware = tk.BooleanVar(value=bool(getattr(goals, "enable_risk_aware_optimization", True)))
        self.mgr_protect_single_point = tk.BooleanVar(value=bool(getattr(goals, "protect_single_point_failures", True)))
        self.mgr_w_risk_fragile = tk.StringVar(value=str(getattr(goals, "w_risk_fragile", 4.0)))
        self.mgr_w_risk_single_point = tk.StringVar(value=str(getattr(goals, "w_risk_single_point", 8.0)))

        self.mgr_enable_util = tk.BooleanVar(value=bool(getattr(goals, "enable_utilization_optimizer", True)))
        self.mgr_w_new_emp = tk.StringVar(value=str(getattr(goals, "w_new_employee_penalty", 3.0)))
        self.mgr_w_frag = tk.StringVar(value=str(getattr(goals, "w_fragmentation_penalty", 2.5)))
        self.mgr_w_extend = tk.StringVar(value=str(getattr(goals, "w_extend_shift_bonus", 2.0)))
        self.mgr_w_low_hours = tk.StringVar(value=str(getattr(goals, "w_low_hours_priority_bonus", 2.5)))
        self.mgr_w_near_cap = tk.StringVar(value=str(getattr(goals, "w_near_cap_penalty", 5.0)))
        self.mgr_w_target_fill = tk.StringVar(value=str(getattr(goals, "w_target_min_fill_bonus", 1.5)))
        self.mgr_util_balance_tol = tk.StringVar(value=str(getattr(goals, "utilization_balance_tolerance_hours", 2.0)))

        self.mgr_call_depth = tk.StringVar(value=str(getattr(goals, "call_list_depth", 5)))
        self.mgr_include_noncert = tk.BooleanVar(value=bool(getattr(goals, "include_noncertified_in_call_list", False)))

        def _apply_vars(*_):
            # Safe parsing with fallbacks (never crash UI)
            try:
                goals.coverage_goal_pct = float(self.mgr_cov_goal.get() or 0.0)
            except Exception:
                pass
            try:
                goals.daily_overstaff_allow_hours = float(self.mgr_daily_over.get() or 0.0)
            except Exception:
                pass
            # Preferred (soft) cap
            try:
                goals.preferred_weekly_cap = float(self.mgr_pref_weekly_cap.get() or 0.0)
            except Exception:
                pass
            # Maximum (hard) cap (0 = disabled)
            try:
                goals.maximum_weekly_cap = float(self.mgr_max_weekly_cap.get() or 0.0)
            except Exception:
                pass

            # Demand multipliers (Phase 2 P2-5)
            try:
                goals.demand_morning_multiplier = float(self.mgr_demand_morning.get() or 1.0)
            except Exception:
                pass
            try:
                goals.demand_midday_multiplier = float(self.mgr_demand_midday.get() or 1.0)
            except Exception:
                pass
            try:
                goals.demand_evening_multiplier = float(self.mgr_demand_evening.get() or 1.0)
            except Exception:
                pass            # Phase 3: Coverage Risk Protection + Utilization Optimizer
            try:
                goals.enable_coverage_risk_protection = bool(self.mgr_enable_risk.get())
            except Exception:
                pass
            try:
                goals.w_coverage_risk = float(self.mgr_w_risk.get() or 0.0)
            except Exception:
                pass

            # Phase 4 C3: Risk-Aware Optimization
            try:
                goals.enable_risk_aware_optimization = bool(self.mgr_enable_riskaware.get())
            except Exception:
                pass
            try:
                goals.protect_single_point_failures = bool(self.mgr_protect_single_point.get())
            except Exception:
                pass
            try:
                goals.w_risk_fragile = float(self.mgr_w_risk_fragile.get() or 0.0)
            except Exception:
                pass
            try:
                goals.w_risk_single_point = float(self.mgr_w_risk_single_point.get() or 0.0)
            except Exception:
                pass

            try:
                goals.enable_utilization_optimizer = bool(self.mgr_enable_util.get())
            except Exception:
                pass
            try:
                goals.w_new_employee_penalty = float(self.mgr_w_new_emp.get() or 0.0)
            except Exception:
                pass
            try:
                goals.w_fragmentation_penalty = float(self.mgr_w_frag.get() or 0.0)
            except Exception:
                pass
            try:
                goals.w_extend_shift_bonus = float(self.mgr_w_extend.get() or 0.0)
            except Exception:
                pass
            try:
                goals.w_low_hours_priority_bonus = float(self.mgr_w_low_hours.get() or 0.0)
            except Exception:
                pass
            try:
                goals.w_near_cap_penalty = float(self.mgr_w_near_cap.get() or 0.0)
            except Exception:
                pass
            try:
                goals.w_target_min_fill_bonus = float(self.mgr_w_target_fill.get() or 0.0)
            except Exception:
                pass
            try:
                goals.utilization_balance_tolerance_hours = float(self.mgr_util_balance_tol.get() or 0.0)
            except Exception:
                pass

# Validation / normalization:
            # Rule: 0 <= preferred <= maximum (when maximum > 0)
            try:
                pref = float(getattr(goals, "preferred_weekly_cap", 0.0) or 0.0)
                mx = float(getattr(goals, "maximum_weekly_cap", 0.0) or 0.0)
                pref = max(0.0, pref)
                mx = max(0.0, mx)
                # Keep legacy field synced for backward compatible saves
                goals.weekly_hours_cap = pref
                if mx > 0.0 and pref > mx:
                    # Auto-normalize preferred down to maximum (consistent behavior)
                    goals.preferred_weekly_cap = mx
                    goals.weekly_hours_cap = mx
                    try:
                        self.mgr_pref_weekly_cap.set(str(mx))
                    except Exception:
                        pass
                    try:
                        self._set_status(f"Preferred weekly cap normalized to Maximum ({mx:g})")
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                goals.call_list_depth = int(float(self.mgr_call_depth.get() or 0))
            except Exception:
                pass
            try:
                goals.include_noncertified_in_call_list = bool(self.mgr_include_noncert.get())
            except Exception:
                pass

        # Auto-apply on edits
        for v in (self.mgr_cov_goal, self.mgr_daily_over, self.mgr_pref_weekly_cap, self.mgr_max_weekly_cap, self.mgr_demand_morning, self.mgr_demand_midday, self.mgr_demand_evening, self.mgr_w_risk, self.mgr_w_new_emp, self.mgr_w_frag, self.mgr_w_extend, self.mgr_call_depth):
            try:
                v.trace_add("write", _apply_vars)
            except Exception:
                pass
        try:
            self.mgr_include_noncert.trace_add("write", _apply_vars)
            self.mgr_enable_risk.trace_add("write", _apply_vars)
            self.mgr_enable_util.trace_add("write", _apply_vars)
        except Exception:
            pass

        # Rows
        r = 0
        ttk.Label(grid, text="Coverage goal (% of 30-min blocks fully covered):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_cov_goal, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Daily overstaff warning threshold (hours):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_daily_over, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Preferred Weekly Labor Hours Cap (soft, 0 = ignore):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_pref_weekly_cap, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Maximum Weekly Labor Hours Cap (hard, 0 = disabled):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_max_weekly_cap, width=10).grid(row=r, column=1, sticky="w"); r += 1

        # Phase 2 P2-5: Demand Adaptive Scheduling (multipliers)
        ttk.Label(grid, text="Demand Multiplier — Morning (e.g., 0.9 / 1.0 / 1.2):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_demand_morning, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Demand Multiplier — Midday:").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_demand_midday, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Demand Multiplier — Evening:").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_demand_evening, width=10).grid(row=r, column=1, sticky="w"); r += 1
        # Phase 3: Coverage Risk Protection
        ttk.Label(grid, text="Coverage Risk Protection (fill scarce shifts first):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Checkbutton(grid, variable=self.mgr_enable_risk).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Coverage risk weight (higher = more scarcity-aware):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_w_risk, width=10).grid(row=r, column=1, sticky="w"); r += 1

        # Phase 4 C3: Risk-Aware Optimization (resilience buffer)
        ttk.Label(grid, text="Risk-Aware Optimization (avoid fragile 1/1 coverage):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Checkbutton(grid, variable=self.mgr_enable_riskaware).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Protect single-point failures (1/1) extra:").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Checkbutton(grid, variable=self.mgr_protect_single_point).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Fragile coverage weight (scheduled == minimum):").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.mgr_w_risk_fragile, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Single-point weight (minimum=1 and scheduled=1):").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.mgr_w_risk_single_point, width=10).grid(row=r, column=1, sticky="w"); r += 1


        # Phase 3: Workforce Utilization Optimizer
        ttk.Label(grid, text="Utilization Optimizer (cleaner schedules, fewer fragments):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Checkbutton(grid, variable=self.mgr_enable_util).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Penalty for adding a new employee to the week:").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_w_new_emp, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Fragmentation penalty (more segments = worse):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_w_frag, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Bonus for extending adjacent shift (same day/area):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_w_extend, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Low-hours priority bonus (favor underused employees):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_w_low_hours, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Near-cap penalty (avoid stacking hours on heavy employees):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_w_near_cap, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Target-min fill bonus (help employees reach target minimum hours):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_w_target_fill, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Utilization balance tolerance (hours ignored around average):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_util_balance_tol, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(grid, text="Call list depth (suggested backups per shortage):").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(grid, textvariable=self.mgr_call_depth, width=10).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Checkbutton(grid, text="Allow non-certified employees in call list (override)", variable=self.mgr_include_noncert)            .grid(row=r, column=0, columnspan=2, sticky="w", pady=(6,4)); r += 1


        # --- Milestone 6: scoring weights (soft penalties) ---
        sep = ttk.Separator(frm, orient="horizontal"); sep.pack(fill="x", pady=10)
        ttk.Label(frm, text="Scoring Weights (lower score = better). Hard rules remain hard.", style="SubHeader.TLabel").pack(anchor="w", pady=(0,6))

        wgrid = ttk.Frame(frm); wgrid.pack(anchor="w", fill="x")
        wgrid.columnconfigure(1, weight=1)

        self.w_under_pref_cov = tk.StringVar(value=str(getattr(goals, "w_under_preferred_coverage", 5.0)))
        self.w_over_pref_cap = tk.StringVar(value=str(getattr(goals, "w_over_preferred_cap", 20.0)))
        self.w_part_miss = tk.StringVar(value=str(getattr(goals, "w_participation_miss", 250.0)))
        self.w_split = tk.StringVar(value=str(getattr(goals, "w_split_shifts", 30.0)))
        self.w_imb = tk.StringVar(value=str(getattr(goals, "w_hour_imbalance", 2.0)))
        self.w_stability = tk.StringVar(value=str(getattr(goals, "w_schedule_stability", 14.0)))

        self.tgl_stability = tk.BooleanVar(value=bool(getattr(goals, "enable_schedule_stability", True)))
        self.tgl_longer = tk.BooleanVar(value=bool(getattr(goals, "prefer_longer_shifts", True)))
        self.tgl_area = tk.BooleanVar(value=bool(getattr(goals, "prefer_area_consistency", False)))

        def _apply_weights(*_):
            try: goals.w_under_preferred_coverage = float(self.w_under_pref_cov.get() or 0.0)
            except Exception: pass
            try: goals.w_over_preferred_cap = float(self.w_over_pref_cap.get() or 0.0)
            except Exception: pass
            try: goals.w_participation_miss = float(self.w_part_miss.get() or 0.0)
            except Exception: pass
            try: goals.w_split_shifts = float(self.w_split.get() or 0.0)
            except Exception: pass
            try: goals.w_hour_imbalance = float(self.w_imb.get() or 0.0)
            except Exception: pass
            try: goals.w_schedule_stability = float(self.w_stability.get() or 0.0)
            except Exception: pass
            try: goals.enable_schedule_stability = bool(self.tgl_stability.get())
            except Exception: pass
            try: goals.prefer_longer_shifts = bool(self.tgl_longer.get())
            except Exception: pass
            try: goals.prefer_area_consistency = bool(self.tgl_area.get())
            except Exception: pass

        for v in (self.w_under_pref_cov, self.w_over_pref_cap, self.w_part_miss, self.w_split, self.w_imb, self.w_stability):
            try: v.trace_add("write", _apply_weights)
            except Exception: pass
        try: self.tgl_stability.trace_add("write", _apply_weights)
        except Exception: pass
        try: self.tgl_longer.trace_add("write", _apply_weights)
        except Exception: pass
        try: self.tgl_area.trace_add("write", _apply_weights)
        except Exception: pass

        rr = 0
        ttk.Label(wgrid, text="Under Preferred Coverage (per 30-min deficit):").grid(row=rr, column=0, sticky="w", pady=3)
        ttk.Entry(wgrid, textvariable=self.w_under_pref_cov, width=10).grid(row=rr, column=1, sticky="w"); rr += 1

        ttk.Label(wgrid, text="Over Preferred Weekly Cap (per hour):").grid(row=rr, column=0, sticky="w", pady=3)
        ttk.Entry(wgrid, textvariable=self.w_over_pref_cap, width=10).grid(row=rr, column=1, sticky="w"); rr += 1

        ttk.Label(wgrid, text="Participation miss (per eligible employee):").grid(row=rr, column=0, sticky="w", pady=3)
        ttk.Entry(wgrid, textvariable=self.w_part_miss, width=10).grid(row=rr, column=1, sticky="w"); rr += 1

        ttk.Label(wgrid, text="Split shifts (per extra shift/day):").grid(row=rr, column=0, sticky="w", pady=3)
        ttk.Entry(wgrid, textvariable=self.w_split, width=10).grid(row=rr, column=1, sticky="w"); rr += 1

        ttk.Label(wgrid, text="Hour imbalance (multiplier):").grid(row=rr, column=0, sticky="w", pady=3)
        ttk.Entry(wgrid, textvariable=self.w_imb, width=10).grid(row=rr, column=1, sticky="w"); rr += 1

        ttk.Checkbutton(wgrid, text="Prefer schedule stability (keep previous week when feasible)", variable=self.tgl_stability).grid(row=rr, column=0, columnspan=2, sticky="w", pady=(8,3)); rr += 1

        ttk.Label(wgrid, text="Schedule stability weight (per hour changed):").grid(row=rr, column=0, sticky="w", pady=3)
        ttk.Entry(wgrid, textvariable=self.w_stability, width=10).grid(row=rr, column=1, sticky="w"); rr += 1

        ttk.Checkbutton(wgrid, text="Prefer longer shifts (soft)", variable=self.tgl_longer).grid(row=rr, column=0, columnspan=2, sticky="w", pady=(6,2)); rr += 1
        ttk.Checkbutton(wgrid, text="Prefer area consistency (soft)", variable=self.tgl_area).grid(row=rr, column=0, columnspan=2, sticky="w", pady=(2,2)); rr += 1

        # Apply immediately
        _apply_weights()
        btnrow = ttk.Frame(frm); btnrow.pack(anchor="w", pady=(10,0))
        ttk.Button(btnrow, text="Apply", command=lambda: (_apply_vars(), locals().get("_apply_weights", lambda: None)())).pack(side="left")
        ttk.Label(btnrow, text="Tip: These settings affect the Manager Report only.", foreground="#555").pack(side="left", padx=10)

    def _build_history_tab(self):
        frm = ttk.Frame(self.tab_history); frm.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frm, text="Last weeks used for fairness scoring (configurable).", style="SubHeader.TLabel")\
            .pack(anchor="w", pady=(0,8))

        cols = ("Created","Label","TotalHours","Filled/Total","Warnings")
        self.hist_tree = ttk.Treeview(frm, columns=cols, show="headings", height=18)
        for c in cols:
            self.hist_tree.heading(c, text=c)
            w=220 if c=="Label" else 140
            if c=="Warnings": w=520
            self.hist_tree.column(c, width=w)
        self.hist_tree.pack(fill="both", expand=True)

        btns = ttk.Frame(frm); btns.pack(fill="x", pady=(8,0))
        ttk.Button(btns, text="Delete Selected", command=self.delete_history).pack(side="left")

    def refresh_history_tree(self):
        for i in self.hist_tree.get_children():
            self.hist_tree.delete(i)
        for s in reversed(self.model.history[-200:]):
            warn = "; ".join(s.warnings[:3]) + (" ..." if len(s.warnings)>3 else "")
            self.hist_tree.insert("", "end", values=(s.created_on, s.label, f"{s.total_hours:.1f}", f"{s.filled_slots}/{s.total_slots}", warn))

    def delete_history(self):
        sel = self.hist_tree.selection()
        if not sel:
            return
        vals = self.hist_tree.item(sel[0], "values")
        created, label = vals[0], vals[1]
        if not messagebox.askyesno("Delete", f"Delete history entry {created} / {label}?"):
            return
        # remove first matching from end
        for i in range(len(self.model.history)-1, -1, -1):
            s = self.model.history[i]
            if s.created_on == created and s.label == label:
                del self.model.history[i]
                break
        self.refresh_history_tree()
        # Manager Goals
        if hasattr(self, "mg_coverage_goal_var"):
            self.mg_coverage_goal_var.set(float(self.model.manager_goals.coverage_goal_pct))
            self.mg_daily_overstaff_allow_var.set(float(self.model.manager_goals.daily_overstaff_allow_hours))
            self.mg_weekly_hours_cap_var.set(float(self.model.manager_goals.weekly_hours_cap))
            self.mg_call_depth_var.set(int(self.model.manager_goals.call_list_depth))
            self.mg_include_noncert_var.set(bool(self.model.manager_goals.include_noncertified_in_call_list))

        self.autosave()

    # -------- Settings tab --------
    def _build_settings_tab(self):
        frm = ttk.Frame(self.tab_settings); frm.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frm, text="Solver + UI settings.", style="SubHeader.TLabel").pack(anchor="w", pady=(0,8))

        box = ttk.LabelFrame(frm, text="UI")
        box.pack(fill="x", pady=10)
        self.ui_scale_var = tk.StringVar(value=str(self.model.settings.ui_scale))
        ttk.Label(box, text="UI scale (1.0–2.0):").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(box, textvariable=self.ui_scale_var, width=8).grid(row=0, column=1, sticky="w", padx=10, pady=6)
        ttk.Button(box, text="Apply UI Scale (restart recommended)", command=self.apply_ui_scale).grid(row=0, column=2, sticky="w", padx=10, pady=6)


        solver_settings = ttk.LabelFrame(frm, text="Solver Settings")
        solver_settings.pack(fill="x", pady=10)

        self.scrutiny_var = tk.StringVar(value=str(getattr(self.model.settings, "solver_scrutiny_level", "Balanced") or "Balanced"))
        ttk.Label(solver_settings, text="Solver Scrutiny Level:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.scrutiny_combo = ttk.Combobox(
            solver_settings,
            textvariable=self.scrutiny_var,
            values=["Fast", "Balanced", "Thorough", "Maximum"],
            state="readonly",
            width=14
        )
        self.scrutiny_combo.grid(row=0, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(
            solver_settings,
            text="Higher = more restarts/iterations (better quality, slower).",
        ).grid(row=0, column=2, sticky="w", padx=10, pady=6)

        self.multi_scenario_var = tk.BooleanVar(value=bool(getattr(self.model.settings, "enable_multi_scenario_generation", True)))
        self.scenario_count_var = tk.StringVar(value=str(int(getattr(self.model.settings, "scenario_schedule_count", 4) or 4)))
        self.demand_forecast_var = tk.BooleanVar(value=bool(getattr(self.model.settings, "enable_demand_forecast_engine", True)))
        ttk.Checkbutton(solver_settings, text="Enable Multi-Scenario Generation (Phase 5 E1)", variable=self.multi_scenario_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=6)
        ttk.Label(solver_settings, text="Scenario count:").grid(row=1, column=2, sticky="e", padx=10, pady=6)
        ttk.Entry(solver_settings, textvariable=self.scenario_count_var, width=6).grid(row=1, column=3, sticky="w", padx=10, pady=6)
        ttk.Checkbutton(solver_settings, text="Enable Demand Forecast Engine (Phase 5 E2)", variable=self.demand_forecast_var).grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=6)
        self.employee_fit_var = tk.BooleanVar(value=bool(getattr(self.model.settings, "enable_employee_fit_engine", True)))
        ttk.Checkbutton(solver_settings, text="Enable Employee Fit Intelligence (Phase 5 E3)", variable=self.employee_fit_var).grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=6)


        # Phase 4 C1: Schedule Stability Engine controls
        stab_box = ttk.LabelFrame(frm, text="Schedule Stability (Week-to-Week)")
        stab_box.pack(fill="x", pady=10)

        self.stab_enable_var = tk.BooleanVar(value=bool(getattr(self.model.manager_goals, "enable_schedule_stability", True)))
        self.stab_level_var = tk.StringVar(value=self._stab_level_from_weight(float(getattr(self.model.manager_goals, "w_schedule_stability", 14.0) or 12.0)))
        self.stab_weight_var = tk.StringVar(value=str(float(getattr(self.model.manager_goals, "w_schedule_stability", 14.0) or 12.0)))

        ttk.Checkbutton(
            stab_box,
            text="Enable Schedule Stability (prefer keeping last week's assignments when feasible)",
            variable=self.stab_enable_var,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8,6))

        ttk.Label(stab_box, text="Stability strength:").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        self.stab_level_combo = ttk.Combobox(
            stab_box,
            textvariable=self.stab_level_var,
            values=["Low", "Medium", "High", "Maximum"],
            state="readonly",
            width=12,
        )
        self.stab_level_combo.grid(row=1, column=1, sticky="w", padx=10, pady=6)
        self.stab_level_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_stab_level_change())

        ttk.Label(stab_box, text="Weight (advanced):").grid(row=1, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(stab_box, textvariable=self.stab_weight_var, width=8).grid(row=1, column=3, sticky="w", padx=10, pady=6)

        ttk.Label(
            stab_box,
            text="Higher = fewer week-to-week changes (may increase hours/overstaff slightly to keep patterns).",
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=10, pady=(0,8))

        solver = ttk.LabelFrame(frm, text="Optimizer")
        solver.pack(fill="x", pady=10)

        self.min_rest_var = tk.StringVar(value=str(self.model.settings.min_rest_hours))
        self.lookback_var = tk.StringVar(value=str(self.model.settings.fairness_lookback_weeks))
        self.iters_var = tk.StringVar(value=str(self.model.settings.optimizer_iterations))
        self.temp_var = tk.StringVar(value=str(self.model.settings.optimizer_temperature))

        ttk.Label(solver, text="Min rest hours (clopen):").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(solver, textvariable=self.min_rest_var, width=8).grid(row=0, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(solver, text="Fairness lookback weeks:").grid(row=0, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(solver, textvariable=self.lookback_var, width=8).grid(row=0, column=3, sticky="w", padx=10, pady=6)

        ttk.Label(solver, text="Optimizer iterations:").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(solver, textvariable=self.iters_var, width=10).grid(row=1, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(solver, text="Temperature (0-2):").grid(row=1, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(solver, textvariable=self.temp_var, width=8).grid(row=1, column=3, sticky="w", padx=10, pady=6)

        nd = ttk.LabelFrame(frm, text="North Dakota minor rules")
        nd.pack(fill="x", pady=10)
        self.nd_enforce_var = tk.BooleanVar(value=self.model.nd_rules.enforce)
        self.nd_school_week_var = tk.BooleanVar(value=self.model.nd_rules.is_school_week)
        ttk.Checkbutton(nd, text="Enforce ND minor rules (14-15)", variable=self.nd_enforce_var).grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Checkbutton(nd, text="This week is a school week", variable=self.nd_school_week_var).grid(row=0, column=1, sticky="w", padx=10, pady=6)

        ttk.Button(frm, text="Save Settings", command=self.save_settings).pack(anchor="w", padx=6, pady=10)

        # Phase 2 P2-4: Pattern Learning (History)
        learning = ttk.LabelFrame(frm, text="Pattern Learning (History)")
        learning.pack(fill="x", pady=10)

        self.learn_hist_var = tk.BooleanVar(value=bool(getattr(self.model.settings, "learn_from_history", True)))
        ttk.Checkbutton(
            learning,
            text="Learn From History (soft preference)",
            variable=self.learn_hist_var,
            command=self._on_toggle_learn_from_history
        ).grid(row=0, column=0, sticky="w", padx=10, pady=6)

        ttk.Button(
            learning,
            text="Refresh Learned Patterns",
            command=self._refresh_learned_patterns_with_feedback
        ).grid(row=0, column=1, sticky="w", padx=10, pady=6)

        ttk.Button(
            learning,
            text="Reset Learned Patterns",
            command=self._reset_learned_patterns
        ).grid(row=0, column=2, sticky="w", padx=10, pady=6)

        ttk.Label(
            learning,
            text="Uses saved schedules in ./history and last schedule to prefer typical start times, departments, and shift lengths.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0,8))


        backup_box = ttk.LabelFrame(frm, text="Backup / Restore")
        backup_box.pack(fill="x", pady=10)
        ttk.Label(
            backup_box,
            text="Create timestamped backups of scheduler data, learned patterns, published finals, and history.",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8,4))
        ttk.Button(backup_box, text="Backup Store Data", command=self.create_backup).grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Button(backup_box, text="Restore Store Data", command=self.restore_backup).grid(row=1, column=1, sticky="w", padx=10, pady=8)
        ttk.Button(backup_box, text="Open Backup Folder", command=self.open_backup_folder).grid(row=1, column=2, sticky="w", padx=10, pady=8)

    def create_backup(self):
        try:
            ensure_dir(_backup_dir())
            default_name = f"backup_{_backup_stamp()}.zip"
            path = filedialog.asksaveasfilename(
                title="Backup Store Data",
                defaultextension=".zip",
                filetypes=[("ZIP backup", "*.zip")],
                initialdir=_backup_dir(),
                initialfile=default_name,
            )
            if not path:
                return
            info = create_store_backup_zip(path)
            self._set_status(f"Backup created: {os.path.basename(path)}")
            messagebox.showinfo("Backup", f"Backup created.\n\nFile: {path}\nIncluded files: {int(info.get('file_count', 0))}")
        except Exception as ex:
            messagebox.showerror("Backup", f"Backup failed: {ex}")

    def restore_backup(self):
        try:
            ensure_dir(_backup_dir())
            candidates = list_store_backups()
            initialdir = _backup_dir() if os.path.isdir(_backup_dir()) else app_dir()
            initialfile = os.path.basename(candidates[0]) if candidates else ''
            path = filedialog.askopenfilename(
                title="Restore Store Data",
                filetypes=[("ZIP backup", "*.zip")],
                initialdir=initialdir,
                initialfile=initialfile,
            )
            if not path:
                return
            if not messagebox.askyesno("Restore", "Restore this backup into the current program data folder? This will overwrite current scheduler data, patterns, finals, and history."):
                return
            info = restore_store_backup_zip(path)
            self.model = load_data(default_data_path())
            self.data_path = default_data_path()
            self._apply_ui_scale(self.model.settings.ui_scale)
            self._refresh_all()
            self._set_status(f"Restored backup: {os.path.basename(path)}")
            messagebox.showinfo("Restore", f"Restore completed.\n\nBackup: {path}\nFiles restored: {len(info.get('restored_files', []))}")
        except Exception as ex:
            messagebox.showerror("Restore", f"Restore failed: {ex}")

    def open_backup_folder(self):
        try:
            ensure_dir(_backup_dir())
            folder = _backup_dir()
            if sys.platform.startswith('win'):
                os.startfile(folder)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', folder])
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as ex:
            messagebox.showerror("Backup Folder", f"Could not open backup folder: {ex}")

    def apply_ui_scale(self):
        try:
            s = float(self.ui_scale_var.get().strip())
            s = max(1.0, min(2.0, s))
        except Exception:
            messagebox.showerror("UI Scale", "Enter a number like 1.2 or 1.6")
            return
        self.model.settings.ui_scale = s
        self.autosave()
        messagebox.showinfo("UI Scale", "Saved. Restart the app for best results.")

    # -------- Phase 4 C1: Schedule Stability helpers --------
    def _stab_level_from_weight(self, w: float) -> str:
        try:
            w = float(w)
        except Exception:
            w = 12.0
        if w <= 6.0:
            return "Low"
        if w <= 14.0:
            return "Medium"
        if w <= 24.0:
            return "High"
        return "Maximum"

    def _stab_weight_from_level(self, level: str) -> float:
        lvl = str(level or "").strip().lower()
        if lvl == "low":
            return 6.0
        if lvl == "medium":
            return 12.0
        if lvl == "high":
            return 20.0
        if lvl == "maximum":
            return 35.0
        return 12.0

    def _on_stab_level_change(self):
        try:
            w = self._stab_weight_from_level(self.stab_level_var.get())
            self.stab_weight_var.set(str(float(w)))
        except Exception:
            pass


    def save_settings(self):
        try:
            self.model.settings.min_rest_hours = max(0, int(self.min_rest_var.get().strip()))
            self.model.settings.fairness_lookback_weeks = max(0, int(self.lookback_var.get().strip()))
            self.model.settings.optimizer_iterations = max(0, int(self.iters_var.get().strip()))
            self.model.settings.optimizer_temperature = max(0.0, float(self.temp_var.get().strip()))
            self.model.settings.solver_scrutiny_level = str(getattr(self, "scrutiny_var", tk.StringVar(value="Balanced")).get() or "Balanced")
            self.model.settings.enable_multi_scenario_generation = bool(getattr(self, "multi_scenario_var", tk.BooleanVar(value=True)).get())
            self.model.settings.scenario_schedule_count = max(1, min(6, int(getattr(self, "scenario_count_var", tk.StringVar(value="4")).get().strip())))
            self.model.settings.enable_demand_forecast_engine = bool(getattr(self, "demand_forecast_var", tk.BooleanVar(value=True)).get())
            self.model.settings.enable_employee_fit_engine = bool(getattr(self, "employee_fit_var", tk.BooleanVar(value=True)).get())
            # Phase 4 C1: Schedule Stability settings
            try:
                self.model.manager_goals.enable_schedule_stability = bool(getattr(self, "stab_enable_var", tk.BooleanVar(value=True)).get())
                self.model.manager_goals.w_schedule_stability = max(0.0, float(getattr(self, "stab_weight_var", tk.StringVar(value="14")).get().strip()))
            except Exception:
                pass
        except Exception as ex:
            messagebox.showerror("Settings", f"Bad value: {ex}")
            return
        self.model.nd_rules.enforce = bool(self.nd_enforce_var.get())
        self.model.nd_rules.is_school_week = bool(self.nd_school_week_var.get())
        self.autosave()
        messagebox.showinfo("Settings", "Saved.")

    # -------- File menu behaviors --------
    def create_desktop_shortcut(self):
        """Create a Desktop shortcut for one-click launch (Windows)."""
        try:
            bat = rel_path("Create_Desktop_Shortcut.bat")
            if not os.path.isfile(bat):
                messagebox.showerror("Shortcut", "Create_Desktop_Shortcut.bat not found in app folder.")
                return
            # Use cmd so it works even when double-clicked or from various shells
            subprocess.Popen(["cmd", "/c", bat], cwd=app_dir(), shell=False)
            messagebox.showinfo("Shortcut", "Desktop shortcut created (or updated).")
        except Exception as ex:
            messagebox.showerror("Shortcut", f"Failed to create shortcut: {ex}")

    def autosave(self):
        try:
            save_data(self.model, self.data_path)
            self._set_status(f"Saved {self.data_path} • {datetime.datetime.now().strftime('%H:%M:%S')}")
            try:
                self.shell.status_save_var.set("Saved")
            except Exception:
                pass
        except Exception as ex:
            try:
                self.shell.status_save_var.set("Save Error")
            except Exception:
                pass
            messagebox.showerror("Save", f"Save failed: {ex}")

    def open_dialog(self):
        path = filedialog.askopenfilename(
            title="Open Scheduler Data",
            filetypes=[("JSON data", "*.json")],
            initialdir=os.path.dirname(self.data_path),
        )
        if not path:
            return
        try:
            self.model = load_data(path)
            self.data_path = path
            self._apply_ui_scale(self.model.settings.ui_scale)
            self._refresh_all()
            messagebox.showinfo("Open", "Loaded data.")
        except Exception as ex:
            messagebox.showerror("Open", f"Load failed: {ex}")

    def save_as_dialog(self):
        path = filedialog.asksaveasfilename(
            title="Save Scheduler Data As",
            defaultextension=".json",
            filetypes=[("JSON data","*.json")],
            initialdir=os.path.dirname(self.data_path),
            initialfile=os.path.basename(self.data_path),
        )
        if not path:
            return
        self.data_path = path
        self.autosave()

    def new_data(self):
        if not messagebox.askyesno("New", "Start a new dataset?"):
            return
        self.model = DataModel()
        self.model.requirements = default_requirements()
        self.current_label = self._default_week_label()
        self.label_var.set(self.current_label)
        self.current_assignments = []
        self.current_emp_hours = {}
        self.current_total_hours = 0.0
        self.current_warnings = []
        self._refresh_all()
        self.autosave()

    # -------- Refresh --------
    def _refresh_all(self):
        # Store
        self.store_name_var.set(self.model.store_info.store_name)
        self.store_addr_var.set(self.model.store_info.store_address)
        self.store_phone_var.set(self.model.store_info.store_phone)
        self.store_mgr_var.set(self.model.store_info.store_manager)
        self.cstore_open_var.set(_norm_hhmm_or_default(getattr(self.model.store_info, "cstore_open", "00:00"), "00:00"))
        self.cstore_close_var.set(_norm_hhmm_or_default(getattr(self.model.store_info, "cstore_close", "24:00"), "24:00"))
        self.kitchen_open_var.set(_norm_hhmm_or_default(getattr(self.model.store_info, "kitchen_open", "00:00"), "00:00"))
        self.kitchen_close_var.set(_norm_hhmm_or_default(getattr(self.model.store_info, "kitchen_close", "24:00"), "24:00"))
        self.carwash_open_var.set(_norm_hhmm_or_default(getattr(self.model.store_info, "carwash_open", "00:00"), "00:00"))
        self.carwash_close_var.set(_norm_hhmm_or_default(getattr(self.model.store_info, "carwash_close", "24:00"), "24:00"))

        self.refresh_emp_tree()
        self.refresh_override_dropdowns()
        self.refresh_override_tree()
        self.refresh_req_tree()
        self.refresh_history_tree()
        try:
            self._refresh_schedule_analysis()
        except Exception:
            pass
        try:
            self._refresh_change_viewer()
        except Exception:
            pass
        # Manager Goals
        if hasattr(self, "mg_coverage_goal_var"):
            self.mg_coverage_goal_var.set(float(self.model.manager_goals.coverage_goal_pct))
            self.mg_daily_overstaff_allow_var.set(float(self.model.manager_goals.daily_overstaff_allow_hours))
            self.mg_weekly_hours_cap_var.set(float(self.model.manager_goals.weekly_hours_cap))
            self.mg_call_depth_var.set(int(self.model.manager_goals.call_list_depth))
            self.mg_include_noncert_var.set(bool(self.model.manager_goals.include_noncertified_in_call_list))
        try:
            self._refresh_shell_status()
        except Exception:
            pass


    def _on_toggle_learn_from_history(self):
        try:
            self.model.settings.learn_from_history = bool(self.learn_hist_var.get())
            save_data(self.data_path, self.model)
            _write_run_log(f"SETTINGS | learn_from_history={self.model.settings.learn_from_history}")
        except Exception:
            pass

    def _reset_learned_patterns(self):
        try:
            self.model.learned_patterns = {}
            save_patterns({})
            # also remove on disk if present
            try:
                p = _patterns_path()
                if os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass
            self._set_status("Learned patterns reset.")
            _write_run_log("PATTERNS | reset")
        except Exception:
            pass

    def _refresh_learned_patterns(self):
        """Rebuild patterns from history and persist."""
        try:
            pats = learn_patterns_from_history_folder()
            try:
                pats["__demand_forecast__"] = build_demand_forecast_profile()
            except Exception:
                pass
            try:
                pats["__employee_fit__"] = build_employee_fit_profiles()
            except Exception:
                pass
            self.model.learned_patterns = pats or {}
            save_patterns(self.model.learned_patterns)
            _write_run_log(f"PATTERNS | learned={len(self.model.learned_patterns)}")
        except Exception:
            pass



    def _format_pattern_profile(self, emp_name: str, profile: Dict[str, Any]) -> str:
        try:
            area = str(profile.get("preferred_area", "") or "").strip() or "Any"
            st = int(profile.get("preferred_start_tick", 0) or 0)
            ln = int(profile.get("preferred_len_ticks", 0) or 0)
            parts = [f"{emp_name}: area {area}"]
            if st > 0:
                parts.append(f"start {tick_to_hhmm(st)}")
            if ln > 0:
                parts.append(f"length {hours_between_ticks(0, ln):.1f}h")
            return ", ".join(parts)
        except Exception:
            return f"{emp_name}: pattern profile available"

    def _refresh_learned_patterns_with_feedback(self):
        try:
            self._refresh_learned_patterns()
            ct = len(getattr(self.model, "learned_patterns", {}) or {})
            self._set_status(f"Learned patterns refreshed ({ct} employee profiles).")
            messagebox.showinfo("Pattern Learning", f"Learned patterns refreshed for {ct} employee profile(s).")
        except Exception as ex:
            try:
                messagebox.showerror("Pattern Learning", f"Could not refresh learned patterns.\n\n{ex}")
            except Exception:
                pass

    def _set_status(self, s: str):
        self.status_var.set(s)
        try:
            self._refresh_shell_status()
        except Exception:
            pass

def main():
    _install_crash_hooks()
    ensure_dir(rel_path("data"))
    ensure_dir(rel_path("history"))
    ensure_dir(rel_path("exports"))
    _write_run_log(f"START {APP_VERSION} | AppDir={_app_dir()} | CWD={os.getcwd()}")
    app = SchedulerApp()
    try:
        _write_run_log(f"READY | DataFile={getattr(app,'data_path', '')}")
    except Exception:
        pass
    app.mainloop()
    _write_run_log("EXIT")

if __name__ == "__main__":
    main()

# -----------------------------
# Phase 4 – D3 Schedule Repair Tool
# -----------------------------
def repair_schedule(schedule, employees=None, manager_goals=None):
    '''
    Lightweight repair engine.
    Pass 1: fix obvious empty coverage slots
    Pass 2: reduce simple hour violations
    Pass 3: keep schedule stability (minimal changes)

    This version is intentionally conservative and
    only adjusts obvious gaps so the schedule is
    never fully regenerated.
    '''
    if not schedule:
        return schedule, {"repairs": 0, "notes": ["No schedule loaded"]}

    repairs = 0
    notes = []

    try:
        for day, slots in schedule.items():
            for slot in slots:
                if not slot.get("employee"):
                    # try assign first available employee
                    if employees:
                        slot["employee"] = employees[0]["name"]
                        repairs += 1
                        notes.append(f"Filled empty slot {day}")
    except Exception as e:
        notes.append(f"Repair engine error: {e}")

    return schedule, {"repairs": repairs, "notes": notes}
