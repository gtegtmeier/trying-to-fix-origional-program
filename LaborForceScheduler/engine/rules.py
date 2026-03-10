"""Hard constraint auditing for generated assignments."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from scheduler_app_v3_final import Assignment

from .models import NormalizedInput


def audit_hard_constraints(nrm: NormalizedInput, assignments: List[Assignment]) -> List[str]:
    violations: List[str] = []
    by_emp_day: Dict[tuple, List[Assignment]] = defaultdict(list)
    weekly_hours: Dict[str, float] = defaultdict(float)

    for a in assignments:
        by_emp_day[(a.employee_name, a.day)].append(a)
        weekly_hours[a.employee_name] += max(0, a.end_t - a.start_t) * 0.5

    limits = nrm.hard_inputs.get("employee_shift_limits", {})
    for (emp, day), segs in by_emp_day.items():
        segs.sort(key=lambda x: x.start_t)
        emp_l = limits.get(emp, {})
        if not emp_l:
            violations.append(f"{emp} has assignments but no normalized limits ({day}).")
            continue
        max_shifts = int(emp_l.get("max_shifts_per_day", 1) or 1)
        if len(segs) > max_shifts:
            violations.append(f"{emp} exceeds max shifts/day on {day}: {len(segs)} > {max_shifts}.")

        allowed = set(emp_l.get("areas_allowed", []) or [])
        for s in segs:
            if allowed and s.area not in allowed:
                violations.append(f"{emp} assigned to disallowed area {s.area} on {day}.")

    for emp, hrs in weekly_hours.items():
        mx = float(limits.get(emp, {}).get("max_weekly_hours", 0.0) or 0.0)
        if mx and hrs > mx + 1e-9:
            violations.append(f"{emp} exceeds max weekly hours: {hrs:.1f} > {mx:.1f}.")

    return violations
