from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from scheduler_app_v3_final import (
    AREAS,
    DAYS,
    Assignment,
    DataModel,
    _clopen_map_from_assignments,
    build_requirement_maps,
    count_coverage_per_tick,
    hours_between_ticks,
    is_employee_available,
    tick_to_ampm,
)


def _window_employee_set(assignments: Sequence[Assignment], day: str, st: int, en: int, area: Optional[str] = None) -> Set[str]:
    names: Set[str] = set()
    for a in assignments:
        if a.day != day:
            continue
        if area and a.area != area:
            continue
        if int(a.end_t) <= st or int(a.start_t) >= en:
            continue
        names.add(str(a.employee_name))
    return names


def build_coverage_risk_map(model: DataModel, label: str, assignments: Sequence[Assignment]) -> List[Dict[str, Any]]:
    min_req, _pref_req, _ = build_requirement_maps(model.requirements, goals=getattr(model, "manager_goals", None))
    cov = count_coverage_per_tick(list(assignments or []))

    emp_hours: Dict[str, float] = {}
    for a in assignments:
        emp_hours[a.employee_name] = emp_hours.get(a.employee_name, 0.0) + hours_between_ticks(a.start_t, a.end_t)

    clopen = _clopen_map_from_assignments(model, list(assignments or []))
    active = [e for e in (model.employees or []) if getattr(e, "work_status", "Active") == "Active"]
    risks: List[Dict[str, Any]] = []

    for day in DAYS:
        for area in AREAS:
            t = 0
            while t < 48:
                req = int(min_req.get((day, area, t), 0))
                if req <= 0:
                    t += 1
                    continue
                st = t
                deficits: List[int] = []
                reqs: List[int] = []
                scheds: List[int] = []
                while t < 48 and int(min_req.get((day, area, t), 0)) > 0:
                    rt = int(min_req.get((day, area, t), 0))
                    sc = int(cov.get((day, area, t), 0))
                    reqs.append(rt)
                    scheds.append(sc)
                    deficits.append(max(0, rt - sc))
                    t += 1
                en = t
                win_h = hours_between_ticks(st, en)

                qualified = [e for e in active if area in getattr(e, "areas_allowed", [])]
                assigned_here = _window_employee_set(assignments, day, st, en, area)
                viable: List[str] = []
                near_cap = 0
                for e in qualified:
                    if e.name in assigned_here:
                        continue
                    if not is_employee_available(model, e, label, day, st, en, area, clopen):
                        continue
                    slack = float(getattr(e, "max_weekly_hours", 0.0) or 0.0) - float(emp_hours.get(e.name, 0.0))
                    if slack <= 0:
                        continue
                    viable.append(e.name)
                    if slack <= max(1.0, win_h):
                        near_cap += 1

                has_gap = any(d > 0 for d in deficits)
                thin_staff = (not has_gap) and any((r - s) <= 0 for r, s in zip(reqs, scheds))
                single_point = all(r == 1 for r in reqs) and all(s == 1 for s in scheds)
                one_qualified = len(qualified) <= 1
                no_backup = len(viable) == 0
                near_cap_pool = len(viable) > 0 and near_cap >= len(viable)

                tags: List[str] = []
                if has_gap:
                    tags.append("coverage_gap")
                if thin_staff:
                    tags.append("thin_staffing")
                if single_point:
                    tags.append("single_point_coverage")
                if one_qualified:
                    tags.append("only_one_qualified")
                if near_cap_pool:
                    tags.append("near_cap_replacement_pool")
                if no_backup:
                    tags.append("no_viable_backup")
                if not tags:
                    continue

                sev = "Low"
                if has_gap or no_backup or (single_point and one_qualified):
                    sev = "High"
                elif thin_staff or single_point or near_cap_pool:
                    sev = "Medium"

                reasons: List[str] = []
                if has_gap:
                    reasons.append(f"Coverage gap up to {max(deficits)} employee(s) in window")
                if thin_staff:
                    reasons.append("Window is meeting minimum coverage with no spare depth")
                if single_point:
                    reasons.append("Single-point coverage (1 required / 1 scheduled)")
                if one_qualified:
                    reasons.append("Only one qualified employee available for this area")
                if near_cap_pool:
                    reasons.append("Backup pool is near weekly-hour cap")
                if no_backup:
                    reasons.append("No viable backup candidate is currently available")

                focus_employee = next(iter(assigned_here), None) if single_point else None
                risks.append({
                    "severity": sev,
                    "day": day,
                    "area": area,
                    "start_t": st,
                    "end_t": en,
                    "time": f"{tick_to_ampm(st)}-{tick_to_ampm(en)}",
                    "tags": tags,
                    "reason": "; ".join(reasons),
                    "backup_count": len(viable),
                    "focus_employee": focus_employee,
                })

    risks.sort(key=lambda r: ({"High": 0, "Medium": 1, "Low": 2}.get(r["severity"], 3), DAYS.index(r["day"]), r["start_t"], r["area"]))
    return risks


def simulate_calloff_impact(model: DataModel, label: str, assignments: Sequence[Assignment], employee_name: str, days: Set[str]) -> Dict[str, Any]:
    min_req, _pref_req, _ = build_requirement_maps(model.requirements, goals=getattr(model, "manager_goals", None))
    req = dict(min_req)
    base = list(assignments or [])
    removed = [a for a in base if a.employee_name == employee_name and a.day in days]
    kept = [a for a in base if not (a.employee_name == employee_name and a.day in days)]

    cov = count_coverage_per_tick(kept)
    emp_hours: Dict[str, float] = {}
    for a in kept:
        emp_hours[a.employee_name] = emp_hours.get(a.employee_name, 0.0) + hours_between_ticks(a.start_t, a.end_t)
    clopen = _clopen_map_from_assignments(model, kept)

    impacted: List[Dict[str, Any]] = []
    for day in DAYS:
        if day not in days:
            continue
        for area in AREAS:
            t = 0
            while t < 48:
                d = max(0, int(req.get((day, area, t), 0)) - int(cov.get((day, area, t), 0)))
                if d <= 0:
                    t += 1
                    continue
                st = t
                peak = d
                def_h = 0.0
                while t < 48:
                    d2 = max(0, int(req.get((day, area, t), 0)) - int(cov.get((day, area, t), 0)))
                    if d2 <= 0:
                        break
                    peak = max(peak, d2)
                    def_h += d2 * 0.5
                    t += 1
                en = t

                candidates: List[Dict[str, Any]] = []
                for e in (model.employees or []):
                    if getattr(e, "work_status", "Active") != "Active" or e.name == employee_name:
                        continue
                    if area not in getattr(e, "areas_allowed", []):
                        continue
                    available = is_employee_available(model, e, label, day, st, en, area, clopen)
                    if not available:
                        continue
                    overlap = bool(_window_employee_set(kept, day, st, en) & {e.name})
                    if overlap:
                        continue
                    cur_h = float(emp_hours.get(e.name, 0.0))
                    max_h = float(getattr(e, "max_weekly_hours", 0.0) or 0.0)
                    slack = max_h - cur_h
                    if slack < hours_between_ticks(st, en):
                        rank_reason = "Near weekly-hour cap"
                    elif cur_h < 24.0:
                        rank_reason = "Best fairness option (lower current hours)"
                    else:
                        rank_reason = "Lowest disruption option"
                    score = (10.0 if slack >= hours_between_ticks(st, en) else 4.0) + max(0.0, 30.0 - cur_h)
                    candidates.append({
                        "employee": e.name,
                        "score": round(score, 2),
                        "reason": rank_reason,
                        "current_hours": round(cur_h, 1),
                        "slack_hours": round(slack, 1),
                    })
                candidates.sort(key=lambda c: (-c["score"], c["employee"].lower()))
                impacted.append({
                    "day": day,
                    "area": area,
                    "start_t": st,
                    "end_t": en,
                    "time": f"{tick_to_ampm(st)}-{tick_to_ampm(en)}",
                    "deficit_hours": round(def_h, 1),
                    "peak_deficit": peak,
                    "suggestions": candidates[:5],
                })

    impacted.sort(key=lambda w: (-w["deficit_hours"], -w["peak_deficit"], DAYS.index(w["day"]), w["start_t"]))
    return {
        "employee": employee_name,
        "days": [d for d in DAYS if d in days],
        "removed": removed,
        "windows": impacted,
    }


def build_schedule_health_summary(filled_slots: int, total_slots: int, warnings: Sequence[str], risk_windows: Sequence[Dict[str, Any]], diagnostics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    coverage_pct = (float(filled_slots) / float(total_slots) * 100.0) if total_slots else 0.0
    high_risk = sum(1 for r in risk_windows if r.get("severity") == "High")
    med_risk = sum(1 for r in risk_windows if r.get("severity") == "Medium")
    fairness = max(0.0, 100.0 - (len(warnings) * 3.0))
    stability = 100.0
    limiting_count = len(list((diagnostics or {}).get("limiting_factors", []) or [])) if isinstance(diagnostics, dict) else 0
    compliance = max(0.0, 100.0 - (limiting_count * 4.0))

    risk_score = max(0.0, 100.0 - (high_risk * 15.0 + med_risk * 6.0))
    overall = round((coverage_pct * 0.35) + (risk_score * 0.25) + (fairness * 0.15) + (stability * 0.15) + (compliance * 0.10), 1)
    return {
        "overall": overall,
        "dimensions": {
            "Coverage": round(coverage_pct, 1),
            "Risk": round(risk_score, 1),
            "Fairness": round(fairness, 1),
            "Stability": round(stability, 1),
            "Compliance": round(compliance, 1),
        },
        "notes": [
            "Coverage and risk use live schedule-state metrics.",
            "Fairness/compliance are first-version heuristic summaries based on warnings and diagnostics.",
        ],
    }
