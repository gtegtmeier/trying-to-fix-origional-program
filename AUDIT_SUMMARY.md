# LaborForceScheduler Engine Audit Summary

## Scope
Audit performed against the current repository content after extracting `LaborForceScheduler_V3_5_Phase5_E3_M12_EMPLOYEE_LOCKED_PATCH.zip`.

## Repository / Entry Points
- Desktop launcher compatibility module: `LaborForceScheduler/LaborForceScheduler.py`.
- Main UI + legacy engine implementation: `LaborForceScheduler/scheduler_app_v3_final.py`.
- Alternate launcher shim: `LaborForceScheduler/scheduler_app.py`.
- Existing `engine/` package existed but was primarily pass-through wrappers to functions inside `scheduler_app_v3_final.py`.

## Current UI Structure (before rebuild)
- Single Tkinter app class (`SchedulerApp`) with tabbed workflows for setup, generation, manual editing, and diagnostics.
- Generation entrypoint is `SchedulerApp.on_generate`, which deep-copies model state and calls module-level solver functions.
- Manual edit flow parses UI manual pages into assignments and validates conflicts before apply.

## Data Model / Persistence
- Canonical persisted dataclasses live in `scheduler_app_v3_final.py` (`DataModel`, `Employee`, `RequirementBlock`, `ManagerGoals`, etc.).
- Save/load remains JSON via `save_data` / `load_data` with backward-compat migration behavior.
- Inputs include employee-level hard limits, store hours, area requirements, weekly overrides, manager weights/goals, and feature toggles.

## Legacy Engine Findings
1. **Engine responsibilities were mixed into one large UI module** (normalization, rule enforcement, scoring, scenario generation, diagnostics).
2. **Modular `engine/` package did not implement modular behavior**; wrappers simply re-exported legacy functions.
3. **Input handling was difficult to audit end-to-end** because hard/soft/informational classifications were not centralized.
4. **Diagnostics did not provide one consolidated input-classification report** (hard vs soft vs informational vs deprecated).
5. **Legacy compatibility fields (e.g., `weekly_hours_cap`) persisted without centralized disconnected-input reporting**.

## Rebuild Actions (this change)
- Replaced wrapper-only engine package with an explicit staged engine pipeline:
  - `engine/models.py`
  - `engine/normalization.py`
  - `engine/validation.py`
  - `engine/rules.py`
  - `engine/scoring.py`
  - `engine/solver.py`
  - `engine/explain.py`
- Reconnected `SchedulerApp.on_generate` to call the new pipeline orchestrator `run_scheduler_engine`.
- Added structured diagnostics block (`engine_pipeline`) containing:
  - validation outcomes
  - hard-rule audit results
  - soft score + breakdown
  - input classification buckets
  - disconnected/deprecated input reporting

## Known Remaining Debt
- Core optimization algorithm is still delegated to existing legacy `generate_schedule` / `generate_schedule_multi_scenario` functions for behavior preservation.
- Additional full decomposition of legacy solver internals into engine modules is still an incremental follow-up item.
