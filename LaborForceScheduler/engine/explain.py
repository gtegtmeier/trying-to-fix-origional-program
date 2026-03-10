"""Diagnostic/explainability helpers for rebuilt engine pipeline."""
from __future__ import annotations

from typing import Any, Dict, List

from .models import NormalizedInput, ValidationResult


def build_engine_diagnostics(
    nrm: NormalizedInput,
    validation: ValidationResult,
    hard_violations: List[str],
    score: float,
    score_breakdown: Dict[str, Any],
    legacy_diag: Dict[str, Any],
) -> Dict[str, Any]:
    diag = dict(legacy_diag or {})
    diag["engine_pipeline"] = {
        "label": nrm.label,
        "validation_errors": list(validation.errors),
        "validation_warnings": list(validation.warnings),
        "hard_rule_violations": list(hard_violations),
        "soft_score": float(score),
        "soft_score_breakdown": score_breakdown,
        "input_classification": {
            "hard_enforced": sorted(nrm.hard_inputs.keys()),
            "soft_scored": sorted(nrm.soft_inputs.keys()),
            "informational_only": sorted(nrm.informational_inputs.keys()),
            "deprecated": sorted(nrm.deprecated_inputs.keys()),
        },
        "disconnected_inputs": disconnected_inputs(nrm),
    }
    return diag


def disconnected_inputs(nrm: NormalizedInput) -> List[str]:
    out: List[str] = []
    if nrm.deprecated_inputs.get("weekly_hours_cap_legacy", 0.0):
        out.append("manager_goals.weekly_hours_cap (legacy compatibility field)")
    return out
