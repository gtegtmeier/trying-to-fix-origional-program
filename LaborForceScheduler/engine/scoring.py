"""Soft scoring for rebuilt engine."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple


def compute_soft_score(
    nrm,
    assignments: List[Any],
    unfilled_ticks: int,
    prev_tick_map: Dict[Tuple[str, str, int], str],
):
    weights = dict(nrm.soft_inputs.get("weights", {}))
    w_cov = float(weights.get("w_under_preferred_coverage", 5.0) or 5.0)
    w_pref_cap = float(weights.get("w_over_preferred_cap", 20.0) or 20.0)
    w_split = float(weights.get("w_split_shifts", 30.0) or 30.0)
    w_stability = float(weights.get("w_schedule_stability", 14.0) or 14.0)

    coverage_pen = float(unfilled_ticks) * w_cov

    emp_hours = defaultdict(float)
    by_emp_day = defaultdict(list)
    for a in assignments:
        h = max(0, int(a.end_t) - int(a.start_t)) * 0.5
        emp_hours[a.employee_name] += h
        by_emp_day[(a.employee_name, a.day)].append(a)

    pref_cap = float(nrm.soft_inputs.get("preferred_weekly_cap", 0.0) or 0.0)
    total_hours = sum(emp_hours.values())
    pref_cap_pen = max(0.0, total_hours - pref_cap) * w_pref_cap if pref_cap > 0 else 0.0

    split_count = 0
    for segs in by_emp_day.values():
        segs.sort(key=lambda a: a.start_t)
        if not segs:
            continue
        shifts = 1
        for i in range(1, len(segs)):
            if segs[i].start_t != segs[i - 1].end_t:
                shifts += 1
        split_count += max(0, shifts - 1)
    split_pen = float(split_count) * w_split

    stability_pen = 0.0
    if nrm.soft_inputs.get("stability_enabled", True):
        cur_tick_map: Dict[Tuple[str, str, int], str] = {}
        for a in assignments:
            for t in range(int(a.start_t), int(a.end_t)):
                cur_tick_map[(a.day, a.area, t)] = a.employee_name
        changed = 0
        for k, prev_emp in prev_tick_map.items():
            if prev_emp and cur_tick_map.get(k, "") != prev_emp:
                changed += 1
        stability_pen = float(changed) * 0.5 * w_stability

    total = coverage_pen + pref_cap_pen + split_pen + stability_pen
    breakdown = {
        "total": total,
        "min_coverage_pen": 0.0,
        "preferred_coverage_shortfall_pen": coverage_pen,
        "preferred_weekly_cap_pen": pref_cap_pen,
        "split_shift_pen": split_pen,
        "stability_pen": stability_pen,
        "history_fairness_pen": 0.0,
        "hour_imbalance_pen": 0.0,
    }
    return total, breakdown
