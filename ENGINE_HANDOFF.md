# Engine Handoff

## Phase 2 Outcome
The rebuilt `engine` package is now the primary owner of scheduling logic for generation, hard-rule feasibility checks, soft scoring, and diagnostics.

## Legacy Solver Dependency Removal / Isolation
### Removed from `engine/solver.py`
- Direct imports/calls to:
  - `generate_schedule`
  - `generate_schedule_multi_scenario`
  - `apply_demand_forecast_to_model`
- Legacy diagnostics passthrough (`legacy_diag`) merge path.

### Removed from `engine/scoring.py`
- Direct dependency on legacy scoring helpers:
  - `history_stats_from`
  - `schedule_score`
  - `schedule_score_breakdown`

### Remaining legacy adapters (isolated, non-core solve)
- `engine/analysis.py` still wraps app-level analysis/explanation helpers for UI analytics tabs.
- `engine/parsing.py` still wraps manual schedule text parsing helpers.
- `engine/persistence.py` still re-exports save/load functions from app module.

These remaining wrappers are outside core schedule generation/constraint/scoring execution path.

## What Is Now Enforced in Engine Core
- Active-employee filtering.
- Area eligibility.
- Day availability.
- Weekly override blocking.
- No overlap per employee/day.
- Per-employee weekly max hours.
- Global weekly max cap.
- Max shifts per day.
- Split-shift prohibition when disabled.
- Max shift length at candidate time.
- Minimum rest window for clopen avoidance.
- Post-solve hard audits including min/max shift duration and min coverage checks.

## Diagnostics & Explainability Changes
- Explicit input classification buckets: hard, soft, informational, deprecated.
- Automatic disconnected input detection for unclassified `settings` and `manager_goals` fields.
- Validation warnings now include disconnected-input summary.
- Run diagnostics now include:
  - hard-rule violations
  - soft score + breakdown
  - coverage summary
  - informational notes
  - limiting factors and infeasible signal

## Known Gaps / Remaining Work
- Risk-related toggles/knobs are surfaced explicitly, but not yet expanded into standalone risk score terms beyond current soft model.
- Phase-2 solver is deterministic greedy coverage-first and does not yet replicate all advanced search heuristics from monolithic legacy implementation.
