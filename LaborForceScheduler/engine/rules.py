"""Hard constraint auditing for generated assignments."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from scheduler_app_v3_final import Assignment, DAYS

from .models import NormalizedInput


def _hours(a: Assignment) -> float:
    return max(0, int(a.end_t) - int(a.start_t)) * 0.5


def _overlap(a: Assignment, b: Assignment) -> bool:
    return not (a.end_t <= b.start_t or a.start_t >= b.end_t)


def audit_hard_constraints(nrm: NormalizedInput, assignments: List[Assignment]) -> List[str]:
    violations: List[str] = []
    by_emp_day: Dict[Tuple[str, str], List[Assignment]] = defaultdict(list)
    by_day_slot_area: Dict[Tuple[str, int, str], int] = defaultdict(int)
    weekly_hours: Dict[str, float] = defaultdict(float)

    for a in assignments:
        by_emp_day[(a.employee_name, a.day)].append(a)
        weekly_hours[a.employee_name] += _hours(a)
        for t in range(int(a.start_t), int(a.end_t)):
            by_day_slot_area[(a.day, t, a.area)] += 1

    limits = nrm.hard_inputs.get("employee_shift_limits", {})
    day_idx = {d: i for i, d in enumerate(DAYS)}

    for (emp, day), segs in by_emp_day.items():
        segs.sort(key=lambda x: x.start_t)
        emp_l = limits.get(emp, {})
        if not emp_l:
            violations.append(f"{emp} has assignments but no normalized limits ({day}).")
            continue

        max_shifts = int(emp_l.get("max_shifts_per_day", 1) or 1)
        shifts = 1 if segs else 0
        for i in range(1, len(segs)):
            if segs[i].start_t != segs[i - 1].end_t:
                shifts += 1
            if _overlap(segs[i], segs[i - 1]):
                violations.append(f"{emp} has overlapping assignments on {day}.")
        if shifts > max_shifts:
            violations.append(f"{emp} exceeds max shifts/day on {day}: {shifts} > {max_shifts}.")

        allowed = set(emp_l.get("areas_allowed", []) or [])
        for s in segs:
            if allowed and s.area not in allowed:
                violations.append(f"{emp} assigned to disallowed area {s.area} on {day}.")
            seg_hours = _hours(s)
            if seg_hours > float(emp_l.get("max_hours_per_shift", 8.0) or 8.0) + 1e-9:
                violations.append(f"{emp} exceeds max shift length on {day}: {seg_hours:.1f}h.")
            if seg_hours + 1e-9 < float(emp_l.get("min_hours_per_shift", 1.0) or 1.0):
                violations.append(f"{emp} below min shift length on {day}: {seg_hours:.1f}h.")

    min_rest_ticks = int(nrm.hard_inputs.get("min_rest_hours", 10) or 10) * 2
    for emp in nrm.employee_index.keys():
        all_segments: List[Assignment] = []
        for d in DAYS:
            all_segments.extend(by_emp_day.get((emp, d), []))
        all_segments.sort(key=lambda a: (day_idx.get(a.day, 99), a.start_t))
        for i in range(1, len(all_segments)):
            prev = all_segments[i - 1]
            curr = all_segments[i]
            prev_abs_end = day_idx.get(prev.day, 0) * 48 + prev.end_t
            curr_abs_start = day_idx.get(curr.day, 0) * 48 + curr.start_t
            if curr_abs_start - prev_abs_end < min_rest_ticks:
                violations.append(f"{emp} violates minimum rest between {prev.day} and {curr.day}.")

    global_cap = float(nrm.hard_inputs.get("max_weekly_cap", 0.0) or 0.0)
    total_weekly_hours = sum(weekly_hours.values())
    if global_cap > 0 and total_weekly_hours > global_cap + 1e-9:
        violations.append(f"Schedule exceeds maximum weekly cap: {total_weekly_hours:.1f} > {global_cap:.1f}.")

    for emp, hrs in weekly_hours.items():
        mx = float(limits.get(emp, {}).get("max_weekly_hours", 0.0) or 0.0)
        if mx and hrs > mx + 1e-9:
            violations.append(f"{emp} exceeds max weekly hours: {hrs:.1f} > {mx:.1f}.")


    if bool(nrm.hard_inputs.get("nd_minor_enforce", True)):
        school_week = bool(nrm.hard_inputs.get("nd_school_week", True))
        for emp, lim in limits.items():
            if str(lim.get("minor_type", "ADULT")) != "MINOR_14_15":
                continue
            weekly = 0.0
            for day in DAYS:
                day_h = sum(_hours(a) for a in by_emp_day.get((emp, day), []))
                weekly += day_h
                is_school_day = school_week and day in {"Mon", "Tue", "Wed", "Thu", "Fri"}
                day_cap = 3.0 if is_school_day else 8.0
                if day_h > day_cap + 1e-9:
                    violations.append(f"ND Minor 14-15 {emp} exceeds daily cap on {day}: {day_h:.1f} > {day_cap:.1f}.")
                latest = 38 if school_week else 42
                earliest = 14
                for seg in by_emp_day.get((emp, day), []):
                    if int(seg.start_t) < earliest or int(seg.end_t) > latest:
                        violations.append(f"ND Minor 14-15 {emp} outside allowed window on {day}: {seg.start_t}-{seg.end_t}.")
            week_cap = 18.0 if school_week else 40.0
            if weekly > week_cap + 1e-9:
                violations.append(f"ND Minor 14-15 {emp} exceeds weekly cap: {weekly:.1f} > {week_cap:.1f}.")

    for req_key, req in nrm.requirements.items():
        mn = int(req.get("min_count", 0) or 0)
        staffed = sum(by_day_slot_area.get((req_key.day, t, req_key.area), 0) for t in range(req_key.start_t, req_key.end_t))
        needed = mn * max(0, req_key.end_t - req_key.start_t)
        if staffed < needed:
            violations.append(f"Min coverage unmet for {req_key.day}/{req_key.area} {req_key.start_t}-{req_key.end_t}.")

    return violations
