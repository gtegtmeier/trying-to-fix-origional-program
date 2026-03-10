"""Normalization layer: converts app model into canonical engine input with explicit field classification."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Set

from scheduler_app_v3_final import AREAS, DAYS, DataModel

from .models import NormalizedInput, RequirementKey


def _active_employees(model: DataModel) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for e in model.employees:
        name = str(getattr(e, "name", "") or "").strip()
        if not name:
            continue
        if str(getattr(e, "work_status", "Active") or "Active") != "Active":
            continue
        out[name] = e
    return out


def normalize_model(model: DataModel, label: str) -> NormalizedInput:
    reqs: Dict[RequirementKey, Dict[str, int]] = {}
    for r in model.requirements:
        reqs[RequirementKey(r.day, r.area, int(r.start_t), int(r.end_t))] = {
            "min_count": int(r.min_count),
            "preferred_count": int(r.preferred_count),
            "max_count": int(r.max_count),
        }

    employees = _active_employees(model)

    hard_inputs = {
        "nd_minor_enforce": bool(getattr(model.nd_rules, "enforce", True)),
        "nd_school_week": bool(getattr(model.nd_rules, "is_school_week", True)),
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
                "split_shifts_ok": bool(getattr(e, "split_shifts_ok", True)),
                "double_shifts_ok": bool(getattr(e, "double_shifts_ok", False)),
                "minor_type": str(getattr(e, "minor_type", "ADULT") or "ADULT"),
            }
            for n, e in employees.items()
        },
    }

    soft_inputs = {
        "preferred_weekly_cap": float(getattr(model.manager_goals, "preferred_weekly_cap", 0.0) or 0.0),
        "coverage_goal_pct": float(getattr(model.manager_goals, "coverage_goal_pct", 95.0) or 95.0),
        "weights": {
            k: float(getattr(model.manager_goals, k) or 0.0)
            for k in dir(model.manager_goals)
            if k.startswith("w_")
        },
        "stability_enabled": bool(getattr(model.manager_goals, "enable_schedule_stability", True)),
        "risk_enabled": bool(getattr(model.manager_goals, "enable_risk_aware_optimization", True)),
        "demand_multipliers": {
            "morning": float(getattr(model.manager_goals, "demand_morning_multiplier", 1.0) or 1.0),
            "midday": float(getattr(model.manager_goals, "demand_midday_multiplier", 1.0) or 1.0),
            "evening": float(getattr(model.manager_goals, "demand_evening_multiplier", 1.0) or 1.0),
        },
    }

    informational = {
        "employee_type": {n: getattr(e, "employee_type", "Crew Member") for n, e in employees.items()},
        "store_info": {
            "name": getattr(model.store_info, "store_name", ""),
            "manager": getattr(model.store_info, "store_manager", ""),
        },
        "enabled_areas": list(AREAS),
        "days": list(DAYS),
        "settings_flags": {
            "learn_from_history": bool(getattr(model.settings, "learn_from_history", True)),
            "enable_employee_fit_engine": bool(getattr(model.settings, "enable_employee_fit_engine", True)),
            "enable_multi_scenario_generation": bool(getattr(model.settings, "enable_multi_scenario_generation", True)),
            "enable_demand_forecast_engine": bool(getattr(model.settings, "enable_demand_forecast_engine", True)),
        },
    }

    deprecated = {
        "weekly_hours_cap_legacy": float(getattr(model.manager_goals, "weekly_hours_cap", 0.0) or 0.0),
    }

    disconnected: Set[str] = set()
    manager_goals = asdict(model.manager_goals)
    classified_mg: Set[str] = {
        "maximum_weekly_cap",
        "preferred_weekly_cap",
        "coverage_goal_pct",
        "enable_schedule_stability",
        "enable_risk_aware_optimization",
        "demand_morning_multiplier",
        "demand_midday_multiplier",
        "demand_evening_multiplier",
        "weekly_hours_cap",
    }
    classified_mg.update(k for k in manager_goals.keys() if k.startswith("w_"))
    for k in sorted(manager_goals.keys() - classified_mg):
        disconnected.add(f"manager_goals.{k}")

    settings_all = asdict(model.settings)
    classified_settings = {
        "min_rest_hours",
        "learn_from_history",
        "enable_employee_fit_engine",
        "enable_multi_scenario_generation",
        "enable_demand_forecast_engine",
    }
    for k in sorted(settings_all.keys() - classified_settings):
        disconnected.add(f"settings.{k}")

    return NormalizedInput(
        label=label,
        model=model,
        requirements=reqs,
        employee_index=employees,
        hard_inputs=hard_inputs,
        soft_inputs=soft_inputs,
        informational_inputs=informational,
        deprecated_inputs=deprecated,
        disconnected_inputs=sorted(disconnected),
    )
