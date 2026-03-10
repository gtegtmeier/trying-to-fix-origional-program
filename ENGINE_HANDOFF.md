# Engine Handoff — Manager Intelligence Layer

## Scope statement
This change adds enterprise manager-intelligence adapters while preserving the rebuilt engine architecture and existing solver pathways.

## New engine-side helpers
- `build_coverage_risk_map(model, label, assignments)`
- `simulate_calloff_impact(model, label, assignments, employee_name, days)`
- `build_schedule_health_summary(filled_slots, total_slots, warnings, risk_windows, diagnostics)`

All are implemented in:
- `LaborForceScheduler/engine/manager_intelligence.py`

## Architectural notes
- Helpers use existing engine data and rule-check mechanisms (`build_requirement_maps`, `count_coverage_per_tick`, `is_employee_available`, clopen map helpers).
- No solver rewrite or core-generation replacement was introduced.
- UI wiring consumes helper outputs through scheduling workspace payload composition in `SchedulerApp._refresh_scheduling_workspace()`.

## Safety and state integrity
- Call-off simulation is non-mutating; it computes from copied assignment lists.
- Live schedule data remains sourced from `current_assignments/current_*` app state.
- Improvement actions are routed to existing proven flows rather than speculative optimizer branches.

## First-version heuristic disclosure
- Fairness and compliance scores in health summary are heuristic rollups over warnings/limiting factors.
- Coverage and risk dimensions are direct schedule-state computations.

## Verification summary
- Static compile checks passed.
- Engine smoke execution passed for generation/risk/call-off/health/save-load path.
- UI runtime launch in this environment is headless-limited (no display server).
