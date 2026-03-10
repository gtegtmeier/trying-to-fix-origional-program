# Manager Intelligence Handoff

## Phase 1 — Coverage Risk Map
### Added
- New engine helper `build_coverage_risk_map(...)` in `engine/manager_intelligence.py`.
- Scheduling workspace **Coverage Risk Map** table with severity/day/time/area/reason.
- Risk row selection now triggers focus callback and manager-readable explanation in inspector text.
- Dashboard risk snapshot now shows top active risk window.

### Fully implemented
- Severity labels (`High`, `Medium`, `Low`) with deterministic sorting.
- Risk reasons for gaps, thin staffing, single-point coverage, one-qualified pools, near-cap pools, and no viable backups.
- Workspace + dashboard integration using current live schedule state.

### First-version / bridge behavior
- Risk view is structured table/list (heatmap-ready adapter shape) rather than full graphical heatmap in the shell workspace.

### Where risk logic lives
- `engine/manager_intelligence.py` (`build_coverage_risk_map`).

## Phase 2 — Call-Off Impact + Replacement Suggestions
### Added
- New engine helper `simulate_calloff_impact(...)`.
- Scheduling workspace call-off controls (employee selection + simulate action).
- Impact windows list with deficit metrics and ranked top suggestion with rationale.

### Fully implemented
- Simulation is non-mutating (uses cloned assignment lists).
- Replacement candidates are filtered through current availability and qualification checks.
- Suggestions include rationale and capacity context (slack/current hours).

### First-version / bridge behavior
- Current UI displays top suggestion per impacted window in table form; deeper multi-strategy expansion is possible with same payload structure.

### Where call-off logic lives
- `engine/manager_intelligence.py` (`simulate_calloff_impact`).

## Phase 3 — Schedule Health / Improve Schedule Panel
### Added
- New engine helper `build_schedule_health_summary(...)`.
- Workspace scorecard panel with Coverage/Risk/Fairness/Stability/Compliance dimensions.
- Action buttons for `Improve Fairness`, `Reduce Risk`, `Improve Stability`, `Fill Weak Coverage`, `Improve Overall`.

### Fully implemented
- Health panel renders from live schedule state every workspace refresh.
- Improvement actions route to existing proven flows (analysis, changes, generate) without pretending hidden optimization.

### First-version / heuristic behavior
- Fairness and compliance are intentionally marked as first-version heuristic rollups based on warnings + limiting factors.
- Coverage and risk dimensions are live schedule-state derived.

### Where health logic lives
- `engine/manager_intelligence.py` (`build_schedule_health_summary`).

## Best next refinement
1. Add richer candidate rejection reason logging for call-off simulation (hard/soft rule attribution).
2. Expand health panel dimensions using native solver breakdown components (stability deltas and fairness deltas from history).
3. Add day/time filter chips and grouped risk views for high-volume schedules.
