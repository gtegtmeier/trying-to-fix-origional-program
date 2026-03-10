# UI Handoff

## New shell structure introduced
The Tkinter app now initializes a shell layout that wraps the legacy notebook in a page-host architecture:
- **Top header**: app title, store/week context, action buttons (Generate/Improve/Publish/Save/Open/New), schedule state and warning summary.
- **Left navigation**: Dashboard, Configuration, Scheduling, Analysis, Publish, History.
- **Center workspace/page host**: page-level navigation and landing pages.
- **Bottom status bar**: save status, operation status, and schedule state.

Implementation location:
- `LaborForceScheduler/ui/shell.py`
- `LaborForceScheduler/ui/pages/__init__.py`
- integrated into `LaborForceScheduler/scheduler_app_v3_final.py`

## Page map
- **Dashboard**: week, status summary, warning count, quick actions.
- **Configuration** (landing): links to Store, Employees, Weekly Overrides, Requirements.
- **Scheduling**: host page containing the existing full legacy notebook workflows.
- **Analysis** (landing): links to Analysis, Changes, Heatmap, Call-Off.
- **Publish** (landing): links to Print/Export and publish flow.
- **History** (landing): links to history workspace.

## What was bridged instead of rewritten
This PR intentionally **bridges** existing complex workflows rather than rewriting them:
- Existing 14-tab legacy notebook remains intact and is hosted inside the new Scheduling page.
- Navigation entries open the proper legacy tab through `open_legacy_tab(...)`.
- Existing generation/save/load logic and engine integration remain in current methods.
- Existing print/export/manual edit/manager goals/history/settings screens remain reachable via bridge links.

## What should happen in the next UI PR
1. Split large legacy tab builders into dedicated page/widget modules (incremental extraction).
2. Move old notebook tabs into domain pages under `ui/pages/` one-by-one.
3. Introduce reusable widgets (summary cards, KPI tiles, action rails) under `ui/widgets/`.
4. Add explicit dirty-state tracking and richer status bar operation lifecycle.
5. Replace remaining direct-tab jumps with true routed page content.
6. Add integration tests for shell navigation and bridge reachability.
