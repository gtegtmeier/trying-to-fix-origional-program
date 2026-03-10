# Traceability Matrix

| Rule / input path | Engine handling | Classification | Status | Notes |
|---|---|---|---|---|
| ND minor enforcement toggle (`nd_rules.enforce`) | Checked during candidate feasibility (`_minor_ok`) and hard audit (`audit_hard_constraints`) | Hard enforced | Restored | Minor constraints now actively block assignment attempts, not only diagnostics. |
| School-week behavior (`nd_rules.is_school_week`) | Drives 14-15 daily cap (3h school day / 8h otherwise), weekly cap (18h school week / 40h non-school), and time-window cutoffs (19:00 school week / 21:00 non-school) | Hard enforced | Restored | Applies during solver candidacy and post-solve audit. |
| Minor daily/weekly caps | Candidate rejection + audit violations | Hard enforced | Restored | Candidate block reasons are surfaced in diagnostics (`minor_daily_hours`, `minor_weekly_hours`). |
| Minor allowed work windows | Candidate rejection + audit violations | Hard enforced | Restored | Earliest 07:00 enforced with school/non-school late cutoffs. |
| Minor department/shift restrictions | Uses standard `areas_allowed`, `max_shifts_per_day`, `split_shifts_ok`, and shift-length limits | Hard enforced | Preserved | No separate ND area blacklist exists in source model; existing area controls remain authoritative. |
| Demand multipliers (`demand_*_multiplier`) | Applied directly during requirement normalization (`min/preferred/max` scaling) and reported in diagnostics notes | Hard+soft shaping | Restored | Demand now materially affects requirement counts used by the solver. |
| Requirement min/preferred/max | Constructive generation pass for min then preferred coverage | Hard+soft | Preserved | Max still audited and guarded during segment placement. |
| Minimum shift length (`min_hours_per_shift`) | Constructive segment sizing when starting a new shift block; still audited post-solve | Hard enforced | Improved | Engine avoids creating sub-minimum fragments when feasible. |
| Maximum shift length, weekly hours, shifts/day, split shifts, rest windows, overrides | Candidate feasibility checks + hard audit | Hard enforced | Preserved | Includes clopen avoidance and weekly override blocked ranges. |
| Hour imbalance (`w_hour_imbalance`) | Active soft penalty in score breakdown | Soft scored | Restored | No dead placeholder remains. |
| Participation minimum opportunity (`w_participation_miss`) | Active soft penalty for active wants-hours employees under 1 hour | Soft scored | Restored | Influences ranking outcomes through total score. |
| Low-hours priority (`w_low_hours_priority_bonus`) | Active utilization-balance soft penalty term | Soft scored | Restored | Penalizes schedules that leave under-utilized employees far from average. |
| Near-cap pressure (`w_near_cap_penalty`) | Active soft penalty above 85% of max weekly hours | Soft scored | Restored | Reduces piling onto high-load employees. |
| Target minimum fill bonus (`w_target_min_fill_bonus`) | Active soft penalty for target-min shortfall | Soft scored | Restored | Included as `target_min_fill_pen` in breakdown. |
| Risk-aware fragile coverage (`w_risk_fragile`) | Active soft penalty when staffing equals minimum | Soft scored | Restored | Controlled by `enable_risk_aware_optimization`. |
| Single-point failure (`w_risk_single_point`) | Active soft penalty for 1-required/1-filled windows | Soft scored | Restored | Controlled by `protect_single_point_failures`. |
| New employee penalty (`w_new_employee_penalty`) | Active soft penalty when assignment introduces names absent from prior tick map | Soft scored | Restored | Uses previous schedule signal if available. |
| Stability/history (`enable_schedule_stability`, `w_schedule_stability`) | Active changed-tick penalty against previous schedule map | Soft scored | Preserved | Pattern-learning/history fairness remain informational in engine core. |
| Pattern-learning and history fairness knobs | Explicitly left informational in engine-core scoring | Informational-only | Reclassified | Kept out of core solver for modularity and data-dependency separation. |
| Legacy weekly cap (`weekly_hours_cap`) | Explicit deprecated reporting path | Deprecated | Preserved | Surfaced in disconnected/deprecated diagnostics. |

## Explicit informational/deprecated decisions
- `settings.learn_from_history` and pattern-learning weights are intentionally informational in engine-core scoring because they depend on learned artifacts not present in deterministic core inputs.
- `history_fairness` remains informational-only in core (not silently ignored; score breakdown keeps the field at 0 for transparent traceability).
- `manager_goals.weekly_hours_cap` remains deprecated compatibility input and is explicitly surfaced.
