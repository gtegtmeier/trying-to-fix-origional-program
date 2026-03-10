# Engine Handoff

## Phase 3 Parity Pass Outcome
The modular engine now restores core business-rule depth that was reduced during Phase 2 while preserving the rebuilt architecture.

## What changed in core scheduling behavior

### 1) Minor-rule parity moved into constructive feasibility
- ND minor enforcement is now checked at candidate-evaluation time in `engine/solver.py`.
- School-week behavior now directly controls:
  - daily caps (3h school days / 8h otherwise for `MINOR_14_15`),
  - weekly caps (18h school week / 40h non-school week),
  - allowed time windows (07:00 start floor, 19:00 school-week latest, 21:00 non-school latest).
- Hard audits in `engine/rules.py` mirror these checks so violations are explicit if introduced.
- Diagnostics now expose minor-block reasons from the solver (e.g., `minor_daily_hours`, `minor_time_window`).

### 2) Constructive minimum-shift behavior
- `min_hours_per_shift` is no longer only a post-hoc audit concept.
- When a new shift block is started, the solver attempts to place a segment sized to the employee minimum shift length (bounded by requirement window and max coverage).
- Post-solve min-shift audit remains as a safety net, but generation now avoids creating tiny fragments where feasible.

### 3) Demand input is now operationally connected
- Demand multipliers are applied during normalization to shape requirement min/preferred/max counts before solving.
- Diagnostics include explicit notes that demand multipliers were applied.

### 4) Soft scoring depth restored
`engine/scoring.py` now actively scores previously reduced dimensions:
- hour imbalance,
- participation miss,
- low-hours utilization pressure,
- near-cap pressure,
- target-minimum-fill pressure,
- risk fragile coverage,
- single-point failure risk,
- new-employee introduction penalty,
- plus existing coverage, preferred-cap, split-shift, and stability terms.

### 5) Rest-window behavior correction
- Rest-window checks are enforced cross-day, avoiding accidental same-day adjacency blocking while preserving clopen protection intent.

## Intentional informational/deprecated classifications (unchanged by design)
- Pattern-learning/history-fairness data remains informational in engine core (explicitly traceable in matrix and score breakdown).
- Legacy `weekly_hours_cap` remains deprecated compatibility input.

## Remaining known gaps
- Full historical pattern/learned-fit optimization is not reintroduced into core solver search in this phase.
- Department-specific behavior beyond explicit area eligibility is still represented through configured employee area permissions rather than special-case departmental rule tables.
