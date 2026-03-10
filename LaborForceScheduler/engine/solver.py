"""Top-level engine solver orchestrator with clean pipeline stages."""
from __future__ import annotations

import math
from collections import defaultdict
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

from scheduler_app_v3_final import Assignment, DAYS, DataModel

from .explain import build_engine_diagnostics
from .models import EngineResult, RequirementKey
from .normalization import normalize_model
from .rules import audit_hard_constraints
from .scoring import compute_soft_score
from .validation import validate_normalized_input


def _assignment_hours(a: Assignment) -> float:
    return max(0, int(a.end_t) - int(a.start_t)) * 0.5


def _is_available(model: DataModel, emp, day: str, start_t: int, end_t: int) -> bool:
    dr = (getattr(emp, "availability", {}) or {}).get(day)
    if dr is None:
        return True
    return bool(dr.is_available(start_t, end_t))


def _is_blocked_by_override(model: DataModel, emp_name: str, day: str, start_t: int, end_t: int, label: str) -> bool:
    for ov in getattr(model, "weekly_overrides", []) or []:
        if str(getattr(ov, "label", "")) != str(label):
            continue
        if str(getattr(ov, "employee_name", "")) != emp_name or str(getattr(ov, "day", "")) != day:
            continue
        if bool(getattr(ov, "off_all_day", False)):
            return True
        for bs, be in list(getattr(ov, "blocked_ranges", []) or []):
            if not (end_t <= int(bs) or start_t >= int(be)):
                return True
    return False


def _has_overlap(assignments: List[Assignment], emp_name: str, day: str, start_t: int, end_t: int) -> bool:
    for a in assignments:
        if a.employee_name != emp_name or a.day != day:
            continue
        if not (end_t <= a.start_t or start_t >= a.end_t):
            return True
    return False


def _projected_shift_count(assignments: List[Assignment], emp_name: str, day: str, new_start: int, new_end: int) -> int:
    segs = [(a.start_t, a.end_t) for a in assignments if a.employee_name == emp_name and a.day == day]
    segs.append((new_start, new_end))
    segs.sort()
    merged: List[List[int]] = []
    for s, e in segs:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    return len(merged)


def _projected_segment_hours(assignments: List[Assignment], emp_name: str, day: str, new_start: int, new_end: int) -> float:
    segs = [(a.start_t, a.end_t) for a in assignments if a.employee_name == emp_name and a.day == day]
    segs.append((new_start, new_end))
    segs.sort()
    merged: List[List[int]] = []
    for s, e in segs:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    for s, e in merged:
        if s <= new_start and e >= new_end:
            return max(0, e - s) * 0.5
    return max(0, new_end - new_start) * 0.5


def _rest_ok(assignments: List[Assignment], emp_name: str, day: str, start_t: int, end_t: int, min_rest_hours: int) -> bool:
    day_index = {d: i for i, d in enumerate(DAYS)}
    cur_idx = day_index.get(day, 0)
    min_rest_ticks = int(min_rest_hours) * 2
    for a in assignments:
        if a.employee_name != emp_name:
            continue
        idx = day_index.get(a.day, 0)
        a_abs_start = idx * 48 + a.start_t
        a_abs_end = idx * 48 + a.end_t
        n_abs_start = cur_idx * 48 + start_t
        n_abs_end = cur_idx * 48 + end_t
        if idx != cur_idx and 0 <= n_abs_start - a_abs_end < min_rest_ticks:
            return False
        if idx != cur_idx and 0 <= a_abs_start - n_abs_end < min_rest_ticks:
            return False
    return True


def _minor_limits(nrm, name: str, day: str) -> Dict[str, float]:
    limits = nrm.hard_inputs["employee_shift_limits"].get(name, {})
    if not bool(nrm.hard_inputs.get("nd_minor_enforce", True)):
        return {}
    if str(limits.get("minor_type", "ADULT")) != "MINOR_14_15":
        return {}
    school_week = bool(nrm.hard_inputs.get("nd_school_week", True))
    is_school_day = school_week and day in {"Mon", "Tue", "Wed", "Thu", "Fri"}
    daily_max = 3.0 if is_school_day else 8.0
    weekly_max = 18.0 if school_week else 40.0
    latest = 38 if school_week else 42  # 19:00 or 21:00
    return {"daily_max": daily_max, "weekly_max": weekly_max, "earliest": 14, "latest": latest}


def _minor_ok(
    nrm,
    assignments: List[Assignment],
    name: str,
    day: str,
    start_t: int,
    end_t: int,
    emp_hours: Dict[str, float],
    block_reasons: Dict[str, int],
) -> bool:
    lim = _minor_limits(nrm, name, day)
    if not lim:
        return True
    if start_t < int(lim["earliest"]) or end_t > int(lim["latest"]):
        block_reasons["minor_time_window"] += 1
        return False
    day_hours = 0.0
    for a in assignments:
        if a.employee_name == name and a.day == day:
            day_hours += _assignment_hours(a)
    proj_day = day_hours + max(0, end_t - start_t) * 0.5
    if proj_day > float(lim["daily_max"]) + 1e-9:
        block_reasons["minor_daily_hours"] += 1
        return False
    proj_week = float(emp_hours.get(name, 0.0)) + max(0, end_t - start_t) * 0.5
    if proj_week > float(lim["weekly_max"]) + 1e-9:
        block_reasons["minor_weekly_hours"] += 1
        return False
    return True


def _candidate_sort_key(name: str, area: str, emp_hours: Dict[str, float], nrm) -> Tuple[float, float, str]:
    emp = nrm.employee_index[name]
    pref = list(getattr(emp, "preferred_areas", []) or [])
    pref_bonus = 0.0 if area in pref else 1.0
    return (float(emp_hours.get(name, 0.0)), pref_bonus, name.lower())


def _can_assign(
    name: str,
    req: RequirementKey,
    assignments: List[Assignment],
    emp_hours: Dict[str, float],
    nrm,
    start_t: int,
    end_t: int,
    block_reasons: Dict[str, int],
) -> bool:
    limits = nrm.hard_inputs["employee_shift_limits"].get(name, {})
    emp = nrm.employee_index[name]

    if req.area not in set(limits.get("areas_allowed", []) or []):
        block_reasons["area_not_allowed"] += 1
        return False
    if not _is_available(nrm.model, emp, req.day, start_t, end_t):
        block_reasons["availability"] += 1
        return False
    if _is_blocked_by_override(nrm.model, name, req.day, start_t, end_t, nrm.label):
        block_reasons["weekly_override"] += 1
        return False
    if _has_overlap(assignments, name, req.day, start_t, end_t):
        block_reasons["overlap"] += 1
        return False
    if not _minor_ok(nrm, assignments, name, req.day, start_t, end_t, emp_hours, block_reasons):
        return False

    seg_h = max(0, end_t - start_t) * 0.5
    max_weekly = float(limits.get("max_weekly_hours", 0.0) or 0.0)
    if max_weekly > 0 and emp_hours.get(name, 0.0) + seg_h > max_weekly + 1e-9:
        block_reasons["max_weekly_hours"] += 1
        return False

    global_cap = float(nrm.hard_inputs.get("max_weekly_cap", 0.0) or 0.0)
    if global_cap > 0 and (sum(emp_hours.values()) + seg_h) > global_cap + 1e-9:
        block_reasons["global_weekly_cap"] += 1
        return False

    shift_count = _projected_shift_count(assignments, name, req.day, start_t, end_t)
    if shift_count > int(limits.get("max_shifts_per_day", 1) or 1):
        block_reasons["max_shifts_per_day"] += 1
        return False
    if not bool(limits.get("split_shifts_ok", True)) and shift_count > 1:
        block_reasons["split_shift_disabled"] += 1
        return False

    max_shift = float(limits.get("max_hours_per_shift", 8.0) or 8.0)
    if _projected_segment_hours(assignments, name, req.day, start_t, end_t) > max_shift + 1e-9:
        block_reasons["max_shift_length"] += 1
        return False

    if bool(limits.get("avoid_clopens", True)) and not _rest_ok(assignments, name, req.day, start_t, end_t, int(nrm.hard_inputs.get("min_rest_hours", 10) or 10)):
        block_reasons["min_rest_hours"] += 1
        return False

    return True


def _assign_segment(
    chosen: str,
    req: RequirementKey,
    start_t: int,
    end_t: int,
    assignments: List[Assignment],
    emp_hours: Dict[str, float],
    slots: Dict[Tuple[str, str, int], int],
) -> None:
    assignments.append(Assignment(day=req.day, area=req.area, start_t=start_t, end_t=end_t, employee_name=chosen, locked=False, source="solver"))
    hrs = max(0, end_t - start_t) * 0.5
    emp_hours[chosen] = emp_hours.get(chosen, 0.0) + hrs
    for t in range(start_t, end_t):
        slots[(req.day, req.area, t)] += 1


def _run_pass(target_key: str, nrm, assignments: List[Assignment], emp_hours: Dict[str, float], warnings: List[str], block_reasons: Dict[str, int]) -> None:
    slots: Dict[Tuple[str, str, int], int] = defaultdict(int)
    for a in assignments:
        for t in range(int(a.start_t), int(a.end_t)):
            slots[(a.day, a.area, t)] += 1
    day_index = {d: i for i, d in enumerate(DAYS)}
    reqs = sorted(nrm.requirements.items(), key=lambda kv: (day_index.get(kv[0].day, 99), kv[0].start_t, kv[0].area))

    for req, cfg in reqs:
        target = max(0, int(cfg.get(target_key, 0) or 0))
        mx = max(target, int(cfg.get("max_count", 0) or 0))
        if target == 0:
            continue
        for t in range(req.start_t, req.end_t):
            while slots[(req.day, req.area, t)] < target:
                candidates = sorted(nrm.employee_index.keys(), key=lambda n: _candidate_sort_key(n, req.area, emp_hours, nrm))
                chosen = None
                chosen_end = t + 1
                for name in candidates:
                    limits = nrm.hard_inputs["employee_shift_limits"].get(name, {})
                    min_ticks = max(1, int(math.ceil(float(limits.get("min_hours_per_shift", 1.0) or 1.0) * 2.0)))
                    # Extend constructively to meet minimum shift when this would create a new segment.
                    can_link_left = any(a.employee_name == name and a.day == req.day and a.end_t == t for a in assignments)
                    desired_end = min(req.end_t, t + (1 if can_link_left else min_ticks))
                    if desired_end <= t:
                        desired_end = t + 1
                    if any(slots[(req.day, req.area, tt)] >= mx for tt in range(t, desired_end)):
                        continue
                    if _can_assign(name, req, assignments, emp_hours, nrm, t, desired_end, block_reasons):
                        chosen = name
                        chosen_end = desired_end
                        break
                if chosen is None:
                    warnings.append(f"Unable to fill {target_key} for {req.day}/{req.area} t={t}.")
                    break
                _assign_segment(chosen, req, t, chosen_end, assignments, emp_hours, slots)


def run_scheduler_engine(
    model: DataModel,
    label: str,
    prev_tick_map: Optional[Dict[Tuple[str, str, int], str]] = None,
) -> EngineResult:
    prev_tick_map = prev_tick_map or {}
    model_for_generation = deepcopy(model)
    nrm = normalize_model(model_for_generation, label)
    validation = validate_normalized_input(nrm)
    if not validation.is_valid:
        raise ValueError("; ".join(validation.errors))

    assignments: List[Assignment] = []
    emp_hours: Dict[str, float] = {n: 0.0 for n in nrm.employee_index.keys()}
    warnings: List[str] = []
    block_reasons: Dict[str, int] = defaultdict(int)

    _run_pass("min_count", nrm, assignments, emp_hours, warnings, block_reasons)
    _run_pass("preferred_count", nrm, assignments, emp_hours, warnings, block_reasons)

    total_slots = 0
    filled_slots = 0
    slots: Dict[Tuple[str, int, str], int] = defaultdict(int)
    for a in assignments:
        for t in range(a.start_t, a.end_t):
            slots[(a.day, t, a.area)] += 1

    for req, cfg in nrm.requirements.items():
        pref = max(0, int(cfg.get("preferred_count", 0) or 0))
        for t in range(req.start_t, req.end_t):
            total_slots += pref
            filled_slots += min(pref, slots.get((req.day, t, req.area), 0))

    total_hours = sum(emp_hours.values())
    unfilled_ticks = max(0, total_slots - filled_slots)
    score, score_breakdown = compute_soft_score(nrm, assignments, unfilled_ticks, prev_tick_map)
    hard_violations = audit_hard_constraints(nrm, assignments)

    info_notes = [
        "Store identity and employee type fields are informational-only for scheduling.",
        "Deprecated weekly_hours_cap is surfaced in disconnected input reporting.",
        "Demand multipliers are actively applied during requirement normalization.",
    ]
    coverage = {
        "filled_slots": int(filled_slots),
        "total_slots": int(total_slots),
        "coverage_pct": float((100.0 * filled_slots / total_slots) if total_slots else 100.0),
        "unfilled_slots": int(unfilled_ticks),
        "candidate_block_reasons": dict(sorted(block_reasons.items())),
    }
    diagnostics = build_engine_diagnostics(
        nrm,
        validation,
        hard_violations,
        score,
        score_breakdown,
        coverage,
        info_notes,
    )

    return EngineResult(
        assignments=assignments,
        employee_hours=emp_hours,
        total_hours=total_hours,
        warnings=sorted(set(warnings)),
        filled_slots=filled_slots,
        total_slots=total_slots,
        iterations=1,
        restarts=0,
        diagnostics=diagnostics,
        score=score,
    )
