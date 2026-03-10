# Engine Rewrite Plan

## Objective
Preserve LaborForceScheduler product behavior while introducing an auditable and modular scheduling engine pipeline.

## Implemented Plan
1. **Audit and mapping**
   - Identified entrypoints, model classes, scheduling calls, and manual-edit paths.
   - Created explicit input classification matrix.
2. **Canonical model layer**
   - Added engine-level canonical dataclasses (`NormalizedInput`, `ValidationResult`, `EngineResult`).
3. **Normalization stage**
   - Added deterministic mapping from persisted/UI model to normalized hard/soft/informational/deprecated buckets.
4. **Validation stage**
   - Added pre-solve contradiction checks and warnings.
5. **Hard-rule auditing stage**
   - Added post-solve hard-rule audit for key employee constraints to ensure rule visibility.
6. **Soft scoring stage**
   - Added explicit scoring stage using legacy score functions but with structured output.
7. **Explainability stage**
   - Added structured `engine_pipeline` diagnostic payload with disconnected-input reporting.
8. **UI reconnection**
   - Rewired `on_generate` to call `run_scheduler_engine` orchestrator.

## Legacy Compatibility Strategy
- Legacy solver core (`generate_schedule` and `generate_schedule_multi_scenario`) remains active as the schedule-construction backend in this phase.
- Compatibility retained to minimize regression risk while introducing architecture boundaries around normalization, validation, scoring, and diagnostics.

## Next Steps (deferred)
- Incrementally extract internals of `generate_schedule` into dedicated engine modules.
- Expand hard-rule audit to include all per-day rest and contiguous-block policy checks.
- Add direct unit tests for each rule class and normalization mapping branch.
