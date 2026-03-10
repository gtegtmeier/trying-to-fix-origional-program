"""Validation rules for normalized engine input."""
from __future__ import annotations

from .models import NormalizedInput, ValidationResult


def validate_normalized_input(nrm: NormalizedInput) -> ValidationResult:
    result = ValidationResult()

    if not nrm.employee_index:
        result.errors.append("No active employees found.")
    if not nrm.requirements:
        result.errors.append("No staffing requirements found.")

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

    return result
