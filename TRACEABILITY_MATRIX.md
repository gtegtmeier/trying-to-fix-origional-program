# Traceability Matrix

| UI field / workflow | Normalized engine input | Classification | Final handling | Code locations | Status |
|---|---|---|---|---|---|
| Generate button (`on_generate`) | `normalize_model(..., label)` + `run_scheduler_engine(...)` | Pipeline entrypoint | Directly invokes in-engine normalization/validation/solve/audit/score pipeline | `LaborForceScheduler/scheduler_app_v3_final.py`, `LaborForceScheduler/engine/solver.py` | Connected |
| Requirements grid (`min/preferred/max`) | `requirements[RequirementKey]` | Hard+soft source | `min_count` enforced in generation pass 1, `preferred_count` targeted in pass 2, `max_count` audited | `engine/normalization.py`, `engine/solver.py`, `engine/rules.py` | Connected |
| Employee `areas_allowed` | `hard_inputs.employee_shift_limits[*].areas_allowed` | Hard enforced | Assignment candidacy hard-filtered + audited post-solve | `engine/normalization.py`, `engine/solver.py`, `engine/rules.py` | Connected |
| Employee `max_weekly_hours` | `hard_inputs.employee_shift_limits[*].max_weekly_hours` | Hard enforced | Candidate rejection if exceeded + post-audit violation | `engine/normalization.py`, `engine/solver.py`, `engine/rules.py` | Connected |
| Employee `max_shifts_per_day` | `hard_inputs.employee_shift_limits[*].max_shifts_per_day` | Hard enforced | Candidate rejection via projected merge-count + post-audit | `engine/normalization.py`, `engine/solver.py`, `engine/rules.py` | Connected |
| Employee `min_hours_per_shift` | `hard_inputs.employee_shift_limits[*].min_hours_per_shift` | Hard enforced | Post-solve hard audit catches below-min contiguous segments | `engine/normalization.py`, `engine/rules.py` | Connected |
| Employee `max_hours_per_shift` | `hard_inputs.employee_shift_limits[*].max_hours_per_shift` | Hard enforced | Candidate rejection via projected segment length + post-audit | `engine/normalization.py`, `engine/solver.py`, `engine/rules.py` | Connected |
| Employee `split_shifts_ok` | `hard_inputs.employee_shift_limits[*].split_shifts_ok` | Hard enforced | Candidate rejection when projected split count > 1 while toggle is false | `engine/normalization.py`, `engine/solver.py` | Connected |
| Employee `avoid_clopens` + settings `min_rest_hours` | `hard_inputs.min_rest_hours` + per-employee flag | Hard enforced | Candidate rejection when rest-window projection violates minimum rest | `engine/normalization.py`, `engine/solver.py`, `engine/rules.py` | Connected |
| Weekly overrides (off-day / blocked ranges) | `model.weekly_overrides` (consumed in solver) | Hard enforced | Candidate rejection for matching week-label/day/employee blocked windows | `engine/solver.py` | Connected |
| Manager `maximum_weekly_cap` | `hard_inputs.max_weekly_cap` | Hard enforced | Candidate rejection once global hours cap would be exceeded + post-audit | `engine/normalization.py`, `engine/solver.py`, `engine/rules.py` | Connected |
| Manager `preferred_weekly_cap` | `soft_inputs.preferred_weekly_cap` | Soft scored | Applied in soft penalty (`preferred_weekly_cap_pen`) | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Coverage goal + scoring weights (`w_*`) | `soft_inputs.coverage_goal_pct`, `soft_inputs.weights` | Soft scored | Coverage shortfall/split/stability penalties weighted by settings | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Stability toggle + previous schedule map | `soft_inputs.stability_enabled` + `prev_tick_map` | Soft scored | Tick-level assignment drift penalty in breakdown | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Risk toggle and risk-related knobs | Classified under `soft_inputs` or disconnected | Soft/informational surfaced | Explicitly reported in diagnostics; currently not separate score term in Phase 2 solver | `engine/normalization.py`, `engine/explain.py` | Connected (explicitly surfaced) |
| Employee `employee_type`, store identity fields | `informational_inputs.*` | Informational only | Included in diagnostics only, never used for feasibility/scoring | `engine/normalization.py`, `engine/explain.py` | Connected (informational) |
| Legacy `weekly_hours_cap` | `deprecated_inputs.weekly_hours_cap_legacy` | Deprecated/dead | Explicitly flagged in disconnected/deprecated diagnostics | `engine/normalization.py`, `engine/explain.py` | Connected (deprecated) |
| Unclassified settings/manager-goal fields | `disconnected_inputs` | Disconnected surfaced | Auto-detected and listed in validation + diagnostics (no silent ignore) | `engine/normalization.py`, `engine/validation.py`, `engine/explain.py` | Connected (explicitly surfaced) |
| Save / Load | JSON `DataModel` persistence | Foundational input source | Existing persistence preserved; engine consumes loaded model directly | `scheduler_app_v3_final.py`, `engine/persistence.py`, `engine/solver.py` | Connected |

## Status Legend
- **Connected**: Input reaches the engine with explicit handling (enforced/scored/informational/deprecated/disconnected).
- **Disconnected surfaced**: Input is not used for solve decisions but is explicitly reported (never silently ignored).
