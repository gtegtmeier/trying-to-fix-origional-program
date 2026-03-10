# UI Handoff — Manager Intelligence Integration

## What changed in the shell workspace

### Scheduling workspace additions
- Added a **Coverage Risk Map** table to the new Scheduling workspace (severity/day/time/area/reason).
- Added **Call-Off Impact + Replacements** controls and impact table directly in Scheduling.
- Added **Schedule Health / Improve Schedule** scorecard and guided action buttons.

### Dashboard additions
- Added dashboard health summary line (`Schedule Health: ...`).
- Added a top risk snapshot card showing highest-severity active risk with explanation.

## Interaction and manager workflow fit
- Risk rows are selectable and route into a focus callback, while exposing manager-readable reason text.
- Call-off simulation is manager-facing in the same workspace context as schedule review/edit.
- Improve actions are visible and intentionally routed to existing stable actions (analysis/changes/generate) for safe first-version behavior.

## UI-first version boundaries
- Coverage Risk Map is delivered as a structured list/table (heatmap-ready data shape remains available for future layer).
- Call-off panel currently surfaces top-ranked suggestion per impacted window in the table.
- Health panel combines live metrics and explicit first-version heuristic dimensions.

## Files owning UI behavior
- `LaborForceScheduler/ui/pages/__init__.py`
- `LaborForceScheduler/scheduler_app_v3_final.py`

## Recommended next UI refinement
1. Add grouped filtering for risk windows (day/area chips).
2. Add expandable detail row for call-off candidate rationale matrix.
3. Add color-coded health badges and trend deltas versus previous week.
