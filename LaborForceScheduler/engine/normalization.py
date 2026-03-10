"""Normalization layer: converts UI/stateful app model into canonical engine input."""
from __future__ import annotations

from typing import Any, Dict

from scheduler_app_v3_final import AREAS, DAYS, DataModel

from .models import NormalizedInput, RequirementKey


def normalize_model(model: DataModel, label: str) -> NormalizedInput:
    reqs: Dict[RequirementKey, Dict[str, int]] = {}
    for r in model.requirements:
        reqs[RequirementKey(r.day, r.area, int(r.start_t), int(r.end_t))] = {
            "min_count": int(r.min_count),
            "preferred_count": int(r.preferred_count),
            "max_count": int(r.max_count),
        }

    employees = {e.name: e for e in model.employees if getattr(e, "name", "").strip()}

    hard_inputs = {
        "nd_minor_enforce": bool(getattr(model.nd_rules, "enforce", True)),
        "max_weekly_cap": float(getattr(model.manager_goals, "maximum_weekly_cap", 0.0) or 0.0),
        "min_rest_hours": int(getattr(model.settings, "min_rest_hours", 10) or 10),
        "employee_shift_limits": {
            n: {
                "min_hours_per_shift": float(getattr(e, "min_hours_per_shift", 1.0) or 1.0),
                "max_hours_per_shift": float(getattr(e, "max_hours_per_shift", 8.0) or 8.0),
                "max_weekly_hours": float(getattr(e, "max_weekly_hours", 30.0) or 30.0),
                "max_shifts_per_day": int(getattr(e, "max_shifts_per_day", 1) or 1),
                "avoid_clopens": bool(getattr(e, "avoid_clopens", True)),
                "areas_allowed": list(getattr(e, "areas_allowed", []) or []),
            }
            for n, e in employees.items()
        },
    }

    soft_inputs = {
        "preferred_weekly_cap": float(getattr(model.manager_goals, "preferred_weekly_cap", 0.0) or 0.0),
        "coverage_goal_pct": float(getattr(model.manager_goals, "coverage_goal_pct", 95.0) or 95.0),
        "weights": {
            k: getattr(model.manager_goals, k)
            for k in dir(model.manager_goals)
            if k.startswith("w_")
        },
        "stability_enabled": bool(getattr(model.manager_goals, "enable_schedule_stability", True)),
        "risk_enabled": bool(getattr(model.manager_goals, "enable_risk_aware_optimization", True)),
    }

    informational = {
        "employee_type": {n: getattr(e, "employee_type", "Crew Member") for n, e in employees.items()},
        "store_info": {
            "name": getattr(model.store_info, "store_name", ""),
            "manager": getattr(model.store_info, "store_manager", ""),
        },
        "enabled_areas": list(AREAS),
        "days": list(DAYS),
    }

    deprecated = {
        "weekly_hours_cap_legacy": float(getattr(model.manager_goals, "weekly_hours_cap", 0.0) or 0.0),
    }

    return NormalizedInput(
        label=label,
        model=model,
        requirements=reqs,
        employee_index=employees,
        hard_inputs=hard_inputs,
        soft_inputs=soft_inputs,
        informational_inputs=informational,
        deprecated_inputs=deprecated,
    )
