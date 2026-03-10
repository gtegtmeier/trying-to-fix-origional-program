"""Validation rules for normalized engine input."""
from __future__ import annotations

from .models import NormalizedInput, ValidationResult


def validate_normalized_input(nrm: NormalizedInput) -> ValidationResult:
    result = ValidationResult()

    if not nrm.employee_index:
        result.errors.append("No active employees found.")
    if not nrm.requirements:
        result.errors.append("No staffing requirements found.")

    for req_key, req in nrm.requirements.items():
        mn = int(req.get("min_count", 0) or 0)
        pref = int(req.get("preferred_count", 0) or 0)
        mx = int(req.get("max_count", 0) or 0)
        if mn < 0 or pref < 0 or mx < 0:
            result.errors.append(f"{req_key.day}/{req_key.area}/{req_key.start_t}: negative requirement counts are invalid.")
        if mn > pref:
            result.warnings.append(f"{req_key.day}/{req_key.area}/{req_key.start_t}: min_count exceeds preferred_count.")
        if pref > mx:
            result.errors.append(f"{req_key.day}/{req_key.area}/{req_key.start_t}: preferred_count exceeds max_count.")

    for name, limits in nrm.hard_inputs.get("employee_shift_limits", {}).items():
        if limits["max_hours_per_shift"] < limits["min_hours_per_shift"]:
            result.errors.append(f"{name}: max_hours_per_shift is less than min_hours_per_shift.")
        if limits["max_weekly_hours"] <= 0:
            result.warnings.append(f"{name}: max_weekly_hours is non-positive and may block scheduling.")
        if not limits["areas_allowed"]:
            result.warnings.append(f"{name}: no allowed work areas configured.")

    max_cap = float(nrm.hard_inputs.get("max_weekly_cap", 0.0) or 0.0)
    pref_cap = float(nrm.soft_inputs.get("preferred_weekly_cap", 0.0) or 0.0)
    if max_cap and pref_cap and pref_cap > max_cap:
        result.warnings.append("Preferred weekly cap is higher than maximum weekly cap.")


    for bucket, mult in (nrm.soft_inputs.get("demand_multipliers", {}) or {}).items():
        if float(mult) <= 0:
            result.errors.append(f"Demand multiplier for {bucket} must be positive.")

    if nrm.disconnected_inputs:
        result.warnings.append(
            f"Disconnected inputs detected: {', '.join(nrm.disconnected_inputs[:8])}"
            + (" ..." if len(nrm.disconnected_inputs) > 8 else "")
        )

    return result
