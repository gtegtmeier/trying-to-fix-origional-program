# UI Handoff – Scheduling Workspace (Edit & Review)

## What is new in this PR
A new manager-focused **Scheduling workspace** now lives directly in the shell-hosted Scheduling page and is intended to be the primary review/edit surface.

### New workspace structure
1. **Scheduling toolbar/subheader**
   - Week, state, issue count.
   - Quick actions: Generate, Improve, Save, Publish.
   - Legacy fallback shortcut button.

2. **Workflow step rail**
   - Inputs → Generate → Review → Edit → Publish → Lock.
   - Orientation aid (not a hard wizard).

3. **Weekly schedule grid**
   - Rows: employees.
   - Columns: Sun–Sat + total hours.
   - Cells: area + shift window text + duration.
   - Selection support with row/cell focus behavior.

4. **Inspector / editor panel**
   - Selected employee/day details.
   - Assigned shifts and areas.
   - Weekly hour summary.
   - Edit bridge button into legacy manual editor.
   - Analysis bridge button.

5. **Issue / risk panel**
   - Shows engine warnings.
   - Shows diagnostics limiting factors when present.
   - Clickable issue rows to load message into inspector issue text.

6. **Summary / health strip**
   - Total scheduled hours.
   - Coverage filled/total slots.
   - Health score placeholder (coverage adjusted by warning pressure).
   - Draft-change status text.

## Fully implemented in this PR
- New scheduling workspace layout and data wiring from current app state.
- Grid + inspector selection/update flow.
- Warning + diagnostics issue list feed.
- Scheduling toolbar actions wired to existing app actions.
- Legacy fallback preservation via embedded notebook host.

## What bridges old edit behavior
- **Edit Selected (Legacy Manual)** button opens the existing legacy Manual Edit tab.
- **Open Explain / Analysis** opens existing analysis tab.
- **Legacy Notebook** action opens the legacy scheduling notebook context.

## What still relies on legacy scheduling views
- Deep/manual shift editing mechanics remain in legacy Manual Edit tab.
- Existing print/export and publish flows remain in legacy notebook tabs.
- Existing advanced analysis/heatmap/call-off/history flows remain legacy-hosted.

## Next extraction step (recommended)
1. Extract legacy manual-edit operations into dedicated widgets callable from inspector context.
2. Add direct assignment edit commit path on the new page (keep legacy as fallback during rollout).
3. Add richer issue-to-grid focusing (parse day/employee/timeslot targeting from warnings).
4. Move print/export/publish controls into shell-native publish surface after parity verification.
