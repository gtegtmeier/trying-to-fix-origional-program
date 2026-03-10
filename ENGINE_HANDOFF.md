# Engine Handoff

## Scope statement for this PR
This PR is a **UI shell/navigation refactor**. The scheduling engine behavior is intentionally preserved.

## Engine impact
- No solver rewrite was performed.
- No business rule logic was intentionally changed.
- Existing generation/save/load workflows continue to call current engine/data methods.

## Minimal wiring impact
- Header and dashboard now surface generated schedule summary values already maintained by existing app state (`current_assignments`, `current_filled`, `current_total_slots`, warning count).
- Status bar now reflects operation text and schedule state derived from existing state without altering solver decisions.

## Verification references
- Syntax/import checks passed.
- Direct schedule generation smoke and save/load roundtrip smoke passed in headless mode.
- Full Tk runtime smoke (launch/navigation) is environment-limited in this container due to missing display.

## Next engine-related caution
As future UI extraction proceeds, keep all engine calls centralized and avoid duplicating scheduling invocation logic across pages.
