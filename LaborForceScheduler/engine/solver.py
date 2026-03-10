"""Top-level engine solver orchestrator with clean pipeline stages."""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from scheduler_app_v3_final import (
    DataModel,
    apply_demand_forecast_to_model,
    generate_schedule,
    generate_schedule_multi_scenario,
)

from .explain import build_engine_diagnostics
from .models import EngineResult
from .normalization import normalize_model
from .rules import audit_hard_constraints
from .scoring import compute_soft_score
from .validation import validate_normalized_input


def run_scheduler_engine(
    model: DataModel,
    label: str,
    prev_tick_map: Optional[Dict[Tuple[str, str, int], str]] = None,
) -> EngineResult:
    prev_tick_map = prev_tick_map or {}
    nrm = normalize_model(model, label)
    validation = validate_normalized_input(nrm)
    if not validation.is_valid:
        raise ValueError("; ".join(validation.errors))

    forecast_used = {}
    model_for_generation = model
    if bool(getattr(model.settings, "enable_demand_forecast_engine", True)):
        forecast_used = apply_demand_forecast_to_model(
            model_for_generation,
            (getattr(model, "learned_patterns", {}) or {}).get("__demand_forecast__"),
        )

    if bool(getattr(model.settings, "enable_multi_scenario_generation", True)):
        out = generate_schedule_multi_scenario(model_for_generation, label, prev_tick_map=prev_tick_map)
    else:
        out = generate_schedule(model_for_generation, label, prev_tick_map=prev_tick_map)

    assigns, emp_hours, total_hours, warnings, filled, total_slots, iters, restarts, legacy_diag = out
    unfilled_ticks = max(0, int(total_slots) - int(filled))
    score, score_breakdown = compute_soft_score(nrm, assigns, unfilled_ticks, prev_tick_map)
    hard_violations = audit_hard_constraints(nrm, assigns)
    diagnostics = build_engine_diagnostics(nrm, validation, hard_violations, score, score_breakdown, legacy_diag)
    diagnostics["phase5_demand_forecast"] = forecast_used
    diagnostics["phase5_demand_forecast_enabled"] = bool(getattr(model.settings, "enable_demand_forecast_engine", True))

    return EngineResult(
        assignments=assigns,
        employee_hours=emp_hours,
        total_hours=total_hours,
        warnings=warnings,
        filled_slots=filled,
        total_slots=total_slots,
        iterations=iters,
        restarts=restarts,
        diagnostics=diagnostics,
        score=score,
    )
