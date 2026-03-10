# Verification Report

## Checks Run
1. Syntax/import validation for rebuilt engine modules.
2. Schedule generation smoke test against a minimal in-memory `DataModel`.
3. Save/load smoke test (`save_data` then `load_data`) followed by generation.
4. App launch smoke test (Tk init) in this environment.
5. Validation that disconnected inputs are surfaced in diagnostics.
6. Scan for legacy solver/scoring calls remaining under `engine/`.

## Results
- Syntax/import check passed.
- Schedule generation smoke passed (`assignments=1`, `filled=1`, `total=2` for test model).
- Save/load smoke passed and loaded model generated successfully.
- App launch smoke could not fully run due headless environment (`$DISPLAY` missing).
- Disconnected inputs are explicitly surfaced (`disconnected_count=15` in smoke output).
- No remaining calls in `engine/` to legacy generation/scoring functions (`generate_schedule*`, `schedule_score`, `history_stats_from`, demand-forecast mutator).

## Commands Executed
- `python -m py_compile LaborForceScheduler/engine/models.py LaborForceScheduler/engine/normalization.py LaborForceScheduler/engine/validation.py LaborForceScheduler/engine/rules.py LaborForceScheduler/engine/scoring.py LaborForceScheduler/engine/solver.py LaborForceScheduler/engine/explain.py`
- `python - <<'PY' ... run_scheduler_engine(...) + save_data/load_data smoke ... PY` (run from `LaborForceScheduler/`)
- `python - <<'PY' ... tkinter.Tk() launch smoke ... PY` (run from `LaborForceScheduler/`)
- `rg -n "generate_schedule|generate_schedule_multi_scenario|schedule_score|history_stats_from|apply_demand_forecast_to_model|legacy_diag" LaborForceScheduler/engine -g '!*.pyc'`

## Notes / Limitations
- UI runtime launch is limited by headless CI/container environment (no X display).
- This phase intentionally prioritizes explicit enforcement/diagnostics in `engine/` over reproducing every heuristic from the legacy monolithic solver.
