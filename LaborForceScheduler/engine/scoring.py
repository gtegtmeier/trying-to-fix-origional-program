"""Soft scoring wrappers and traceability metadata."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from scheduler_app_v3_final import history_stats_from, schedule_score, schedule_score_breakdown

from .models import NormalizedInput


def compute_soft_score(nrm: NormalizedInput, assignments: List[Any], unfilled_ticks: int, prev_tick_map: Dict[Tuple[str, str, int], str]):
    hist = history_stats_from(nrm.model)
    score = float(schedule_score(nrm.model, nrm.label, assignments, unfilled_ticks, hist, prev_tick_map))
    breakdown = schedule_score_breakdown(nrm.model, nrm.label, assignments, unfilled_ticks, hist, prev_tick_map)
    return score, breakdown
