# Traceability Matrix

| UI field / workflow | Normalized engine input | Classification | Code locations | Status |
|---|---|---|---|---|
| Generate button (`on_generate`) | `normalize_model(..., label)` + `run_scheduler_engine(...)` | Pipeline entrypoint | `scheduler_app_v3_final.py` (`on_generate`), `engine/solver.py` | Connected |
| Employee `areas_allowed` | `hard_inputs.employee_shift_limits[*].areas_allowed` | Hard constraint (audited) | `engine/normalization.py`, `engine/rules.py` | Connected |
| Employee `max_weekly_hours` | `hard_inputs.employee_shift_limits[*].max_weekly_hours` | Hard constraint (audited) | `engine/normalization.py`, `engine/rules.py` | Connected |
| Employee `max_shifts_per_day` | `hard_inputs.employee_shift_limits[*].max_shifts_per_day` | Hard constraint (audited) | `engine/normalization.py`, `engine/rules.py` | Connected |
| Employee min/max shift length fields | `hard_inputs.employee_shift_limits[*].min_hours_per_shift` / `max_hours_per_shift` | Hard (validated for consistency) | `engine/normalization.py`, `engine/validation.py` | Partially connected |
| ND minor enforcement toggle | `hard_inputs.nd_minor_enforce` | Hard (delegated to legacy solver) | `engine/normalization.py`, `scheduler_app_v3_final.py` (legacy solver) | Connected |
| Manager max weekly cap | `hard_inputs.max_weekly_cap` | Hard (delegated + surfaced) | `engine/normalization.py`, `scheduler_app_v3_final.py` solver/scoring | Connected |
| Manager preferred weekly cap | `soft_inputs.preferred_weekly_cap` | Soft scored | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Coverage goal % | `soft_inputs.coverage_goal_pct` | Soft scored / reporting | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Soft weights (`w_*`) | `soft_inputs.weights` | Soft scored | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Schedule stability toggle | `soft_inputs.stability_enabled` | Soft scored | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Risk-aware optimization toggle | `soft_inputs.risk_enabled` | Soft scored | `engine/normalization.py`, `engine/scoring.py` | Connected |
| Legacy `weekly_hours_cap` | `deprecated_inputs.weekly_hours_cap_legacy` | Deprecated/disconnected reporting | `engine/normalization.py`, `engine/explain.py` | Connected (explicitly deprecated) |
| Store identity fields (name, manager) | `informational_inputs.store_info` | Informational-only | `engine/normalization.py` | Connected (informational) |
| Employee `employee_type` | `informational_inputs.employee_type` | Informational-only | `engine/normalization.py` | Connected (informational) |
| Requirements grid | `requirements[RequirementKey]` | Hard/soft source data | `engine/normalization.py` | Connected |
| Manual edit parse/apply workflow | Legacy manual parser + assignment validators | Informational/manual override path | `scheduler_app_v3_final.py` (`_manual_*` methods) | Connected (outside solver pipeline) |
| Save / Load | JSON DataModel persistence | Foundational input source | `scheduler_app_v3_final.py` `save_data`/`load_data` | Connected |
| Multi-scenario generation toggle | Branch in orchestrator to legacy multi-scenario solver | Solver strategy control | `engine/solver.py` | Connected |
| Demand forecast enable toggle | Pre-solve model mutation via `apply_demand_forecast_to_model` | Solver pre-processing | `engine/solver.py` | Connected |

## Status Legend
- **Connected**: Input currently reaches the pipeline with intentional handling.
- **Partially connected**: Input is validated/reported but deeper solver-level enforcement remains delegated to legacy implementation.
- **Disconnected**: UI captures field but pipeline does not use it.
- **Duplicated**: Multiple paths enforce same logic with risk of drift.
- **Broken**: Expected behavior currently failing.
