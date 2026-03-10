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
    w_imb = float(weights.get("w_hour_imbalance", 2.0) or 2.0)
    w_part = float(weights.get("w_participation_miss", 250.0) or 250.0)
    w_low = float(weights.get("w_low_hours_priority_bonus", 2.5) or 0.0)
    w_near = float(weights.get("w_near_cap_penalty", 5.0) or 0.0)
    w_target_fill = float(weights.get("w_target_min_fill_bonus", 1.5) or 0.0)
    w_new = float(weights.get("w_new_employee_penalty", 3.0) or 0.0)
    w_risk_frag = float(weights.get("w_risk_fragile", 4.0) or 0.0)
    w_risk_sp = float(weights.get("w_risk_single_point", 8.0) or 0.0)

    coverage_pen = float(unfilled_ticks) * w_cov

    emp_hours = defaultdict(float)
    by_emp_day = defaultdict(list)
    by_tick = defaultdict(int)
    used_employees = set()
    for a in assignments:
        h = max(0, int(a.end_t) - int(a.start_t)) * 0.5
        emp_hours[a.employee_name] += h
        by_emp_day[(a.employee_name, a.day)].append(a)
        used_employees.add(a.employee_name)
        for t in range(int(a.start_t), int(a.end_t)):
            by_tick[(a.day, a.area, t)] += 1

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

    # Fairness and participation.
    wants = [
        n for n, e in nrm.employee_index.items()
        if bool(getattr(e, "wants_hours", True)) and str(getattr(e, "work_status", "Active")) == "Active"
    ]
    imbalance_pen = 0.0
    low_hours_pen = 0.0
    near_cap_pen = 0.0
    participation_pen = 0.0
    target_fill_pen = 0.0
    new_employee_pen = 0.0
    if wants:
        hs = [float(emp_hours.get(n, 0.0)) for n in wants]
        avg = sum(hs) / float(len(hs))
        imbalance_pen = sum(abs(x - avg) for x in hs) * w_imb
        for n in wants:
            h = float(emp_hours.get(n, 0.0))
            if h < 1.0:
                participation_pen += w_part
            if h < avg and w_low > 0.0:
                low_hours_pen += (avg - h) * w_low
            lim = nrm.hard_inputs.get("employee_shift_limits", {}).get(n, {})
            maxh = float(lim.get("max_weekly_hours", 0.0) or 0.0)
            target_h = float(getattr(nrm.employee_index[n], "target_min_hours", 0.0) or 0.0)
            if target_h > 0.0 and h < target_h and w_target_fill > 0.0:
                target_fill_pen += (target_h - h) * w_target_fill
            if maxh > 0 and h > 0.85 * maxh and w_near > 0.0:
                near_cap_pen += ((h - 0.85 * maxh) / max(1.0, 0.15 * maxh)) * w_near
            if h > 0.0 and n not in prev_tick_map.values() and w_new > 0.0:
                new_employee_pen += w_new

    # Risk-aware coverage terms.
    risk_fragile_pen = 0.0
    risk_single_point_pen = 0.0
    if nrm.soft_inputs.get("risk_enabled", True):
        protect_sp = bool(nrm.soft_inputs.get("protect_single_point_failures", True))
        for req, cfg in nrm.requirements.items():
            mn = int(cfg.get("min_count", 0) or 0)
            if mn <= 0:
                continue
            for t in range(req.start_t, req.end_t):
                cov = int(by_tick.get((req.day, req.area, t), 0))
                if cov <= 0:
                    continue
                if cov == mn:
                    risk_fragile_pen += 0.5 * w_risk_frag
                    if protect_sp and mn == 1 and cov == 1:
                        risk_single_point_pen += 0.5 * w_risk_sp

    total = (
        coverage_pen
        + pref_cap_pen
        + split_pen
        + stability_pen
        + imbalance_pen
        + participation_pen
        + low_hours_pen
        + near_cap_pen
        + target_fill_pen
        + risk_fragile_pen
        + risk_single_point_pen
        + new_employee_pen
    )
    breakdown = {
        "total": total,
        "min_coverage_pen": 0.0,
        "preferred_coverage_shortfall_pen": coverage_pen,
        "preferred_weekly_cap_pen": pref_cap_pen,
        "split_shift_pen": split_pen,
        "stability_pen": stability_pen,
        "history_fairness_pen": 0.0,
        "hour_imbalance_pen": imbalance_pen,
        "participation_pen": participation_pen,
        "utilization_balance_pen": low_hours_pen,
        "utilization_near_cap_pen": near_cap_pen,
        "target_min_fill_pen": target_fill_pen,
        "risk_fragile_pen": risk_fragile_pen,
        "risk_single_point_pen": risk_single_point_pen,
        "new_employee_pen": new_employee_pen,
    }
    return total, breakdown
