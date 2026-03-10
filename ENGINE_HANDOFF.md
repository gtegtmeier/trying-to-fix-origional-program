# Engine Handoff

## What Was Preserved
- Existing LaborForceScheduler desktop workflows and UI intent.
- Existing persistence model (`DataModel` JSON save/load compatibility).
- Existing solver behavior backend (`generate_schedule` + multi-scenario variant) to reduce regression risk.

## What Was Rebuilt
A clean orchestration pipeline under `LaborForceScheduler/engine`:
- `models.py`: canonical engine data contracts.
- `normalization.py`: deterministic mapping from app model to engine-ready inputs.
- `validation.py`: contradiction/missing-data checks.
- `rules.py`: hard-rule audit pass over generated assignments.
- `scoring.py`: soft scoring integration and breakdown capture.
- `explain.py`: explainability payload with disconnected/deprecated input reporting.
- `solver.py`: orchestration of all phases and bridging to legacy generator.

## UI Reconnection
- `SchedulerApp.on_generate` now calls `run_scheduler_engine` and receives structured `EngineResult` output.
- Existing downstream UI state updates (assignments/hours/warnings/diagnostics) remain intact.

## Assumptions
- Legacy generation/scoring functions already encode critical production behavior and should remain until parity-tested extraction is complete.
- The current phase prioritizes architecture clarity, traceability, and diagnostics over algorithm replacement.

## Ambiguous / Partial / Deferred
- Some hard constraints are audited post-solve (visibility) while deep enforcement remains in legacy solver internals.
- Full decomposition of legacy monolithic solver into pure modular engine internals is intentionally deferred to reduce risk.

## First Things Future Developers Should Read
1. `engine/solver.py` (pipeline orchestration)
2. `engine/normalization.py` (input mapping)
3. `engine/explain.py` (diagnostic schema)
4. `TRACEABILITY_MATRIX.md` (field-level handling status)
5. `scheduler_app_v3_final.py::on_generate` (UI integration point)
