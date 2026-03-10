"""Canonical engine models for the rebuilt scheduling pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from scheduler_app_v3_final import Assignment, DataModel


@dataclass(frozen=True)
class RequirementKey:
    day: str
    area: str
    start_t: int
    end_t: int


@dataclass
class NormalizedInput:
    label: str
    model: DataModel
    requirements: Dict[RequirementKey, Dict[str, int]]
    employee_index: Dict[str, Any]
    hard_inputs: Dict[str, Any]
    soft_inputs: Dict[str, Any]
    informational_inputs: Dict[str, Any]
    deprecated_inputs: Dict[str, Any]
    disconnected_inputs: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass
class EngineResult:
    assignments: List[Assignment]
    employee_hours: Dict[str, float]
    total_hours: float
    warnings: List[str]
    filled_slots: int
    total_slots: int
    iterations: int
    restarts: int
    diagnostics: Dict[str, Any]
    score: Optional[float] = None
