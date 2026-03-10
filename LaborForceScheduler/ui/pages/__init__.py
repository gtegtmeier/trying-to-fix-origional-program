import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Tuple


class DashboardPage(ttk.Frame):
    def __init__(self, master, actions: List[Tuple[str, Callable[[], None]]]):
        super().__init__(master)
        self.week_var = tk.StringVar(value="Current Week: N/A")
        self.status_var = tk.StringVar(value="Status: No schedule generated yet")
        self.warning_var = tk.StringVar(value="Warnings: 0")
        self.health_var = tk.StringVar(value="Schedule Health: --")

        ttk.Label(self, text="Dashboard", style="SubHeader.TLabel").pack(anchor="w", pady=(4, 8))
        ttk.Label(self, textvariable=self.week_var).pack(anchor="w")
        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", pady=(2, 0))
        ttk.Label(self, textvariable=self.warning_var).pack(anchor="w", pady=(2, 0))
        ttk.Label(self, textvariable=self.health_var).pack(anchor="w", pady=(2, 10))

        quick = ttk.LabelFrame(self, text="Quick Actions")
        quick.pack(fill="x", pady=(0, 12))
        for txt, cb in actions:
            ttk.Button(quick, text=txt, command=cb).pack(side="left", padx=6, pady=8)

        self.risk_summary = ttk.LabelFrame(self, text="Coverage Risk Snapshot")
        self.risk_summary.pack(fill="x")
        self.risk_summary_var = tk.StringVar(value="No risk windows yet. Generate or open a schedule to populate this summary.")
        ttk.Label(self.risk_summary, textvariable=self.risk_summary_var, wraplength=920, justify="left").pack(anchor="w", padx=8, pady=8)


class LandingPage(ttk.Frame):
    def __init__(self, master, title: str, subtitle: str, links: List[Tuple[str, Callable[[], None]]]):
        super().__init__(master)
        ttk.Label(self, text=title, style="SubHeader.TLabel").pack(anchor="w", pady=(4, 8))
        ttk.Label(self, text=subtitle, foreground="#555").pack(anchor="w", pady=(0, 10))
        actions = ttk.LabelFrame(self, text="Open")
        actions.pack(fill="x")
        for txt, cb in links:
            ttk.Button(actions, text=txt, command=cb).pack(side="left", padx=6, pady=8)


class SchedulingPage(ttk.Frame):
    def __init__(self, master, days: Optional[List[str]] = None, callbacks: Optional[Dict[str, Callable[..., None]]] = None):
        super().__init__(master)
        self.days = list(days or ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
        self.callbacks = callbacks or {}

        self.week_var = tk.StringVar(value="Week: Not selected")
        self.state_var = tk.StringVar(value="State: Draft")
        self.issue_count_var = tk.StringVar(value="Issues: 0")
        self.total_hours_var = tk.StringVar(value="Total Hours: 0.0")
        self.coverage_var = tk.StringVar(value="Coverage: --")
        self.health_var = tk.StringVar(value="Health: --")
        self.change_state_var = tk.StringVar(value="Draft changes: none")

        self.selection_emp_var = tk.StringVar(value="Employee: --")
        self.selection_day_var = tk.StringVar(value="Day: --")
        self.selection_shift_var = tk.StringVar(value="Shift(s): --")
        self.selection_area_var = tk.StringVar(value="Area: --")
        self.selection_hours_var = tk.StringVar(value="Hours: --")

        self._assignment_index: Dict[Tuple[str, str], List[Any]] = {}
        self._emp_hours: Dict[str, float] = {}
        self._selected_key: Optional[Tuple[str, str]] = None
        self._risk_windows: List[Dict[str, Any]] = []

        ttk.Label(self, text="Edit & Review Schedule", style="SubHeader.TLabel").pack(anchor="w", pady=(4, 6))
        self._build_toolbar()
        self._build_workflow_rail()
        self._build_summary_strip()
        self._build_workspace()
        self._build_issue_panel()
        self._build_manager_intelligence_panel()
        self.legacy_host = ttk.Frame(self)
        self.legacy_host.pack(fill="both", expand=True, pady=(6, 0))

    def _build_toolbar(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))

        left = ttk.Frame(top)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, textvariable=self.week_var).pack(side="left", padx=(0, 10))
        ttk.Label(left, textvariable=self.state_var).pack(side="left", padx=10)
        ttk.Label(left, textvariable=self.issue_count_var).pack(side="left", padx=10)

        right = ttk.Frame(top)
        right.pack(side="right")
        for label, key in [
            ("Generate", "generate"),
            ("Improve", "improve"),
            ("Save", "save"),
            ("Publish", "publish"),
            ("Legacy Notebook", "open_legacy_notebook"),
        ]:
            ttk.Button(right, text=label, command=lambda k=key: self._invoke(k)).pack(side="left", padx=4)

    def _build_workflow_rail(self):
        rail = ttk.LabelFrame(self, text="Workflow")
        rail.pack(fill="x", pady=(0, 6))
        for step in ["Inputs", "Generate", "Review", "Edit", "Publish", "Lock"]:
            ttk.Label(rail, text=f"{step}", relief="ridge", padding=(8, 4)).pack(side="left", padx=4, pady=6)

    def _build_summary_strip(self):
        strip = ttk.LabelFrame(self, text="Schedule Health")
        strip.pack(fill="x", pady=(0, 6))
        ttk.Label(strip, textvariable=self.total_hours_var).pack(side="left", padx=8, pady=6)
        ttk.Label(strip, textvariable=self.coverage_var).pack(side="left", padx=8)
        ttk.Label(strip, textvariable=self.health_var).pack(side="left", padx=8)
        ttk.Label(strip, textvariable=self.change_state_var).pack(side="left", padx=8)

    def _build_workspace(self):
        work = ttk.Frame(self)
        work.pack(fill="both", expand=True)

        grid_wrap = ttk.LabelFrame(work, text="Weekly Grid")
        grid_wrap.pack(side="left", fill="both", expand=True, padx=(0, 8))

        cols = ["employee"] + self.days + ["total"]
        self.grid_tree = ttk.Treeview(grid_wrap, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            title = "Employee" if c == "employee" else ("Total Hrs" if c == "total" else c)
            self.grid_tree.heading(c, text=title)
            width = 170 if c == "employee" else (88 if c == "total" else 145)
            self.grid_tree.column(c, width=width, anchor="w", stretch=True)
        self.grid_tree.pack(side="left", fill="both", expand=True)
        ysb = ttk.Scrollbar(grid_wrap, orient="vertical", command=self.grid_tree.yview)
        self.grid_tree.configure(yscrollcommand=ysb.set)
        ysb.pack(side="right", fill="y")
        self.grid_tree.bind("<ButtonRelease-1>", self._on_grid_click)
        self.grid_tree.bind("<<TreeviewSelect>>", self._on_grid_select)

        insp = ttk.LabelFrame(work, text="Selection Details")
        insp.pack(side="right", fill="y")
        ttk.Label(insp, textvariable=self.selection_emp_var).pack(anchor="w", padx=10, pady=(8, 2))
        ttk.Label(insp, textvariable=self.selection_day_var).pack(anchor="w", padx=10)
        ttk.Label(insp, textvariable=self.selection_area_var).pack(anchor="w", padx=10)
        ttk.Label(insp, textvariable=self.selection_hours_var).pack(anchor="w", padx=10)
        ttk.Label(insp, textvariable=self.selection_shift_var, wraplength=360, justify="left").pack(anchor="w", padx=10, pady=(2, 8))

        ttk.Label(insp, text="Warnings / Issues").pack(anchor="w", padx=10, pady=(8, 2))
        self.issue_text = tk.Text(insp, height=8, width=42, wrap="word")
        self.issue_text.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        actions = ttk.Frame(insp)
        actions.pack(fill="x", padx=10, pady=(2, 10))
        ttk.Button(actions, text="Edit Selected (Legacy Manual)", command=lambda: self._invoke("open_legacy_manual")).pack(fill="x", pady=2)
        ttk.Button(actions, text="Open Explain / Analysis", command=lambda: self._invoke("open_analysis")).pack(fill="x", pady=2)

    def _build_issue_panel(self):
        frame = ttk.LabelFrame(self, text="Issue / Risk Panel")
        frame.pack(fill="x", pady=(6, 0))
        self.issue_tree = ttk.Treeview(frame, columns=("type", "message"), show="headings", height=6)
        self.issue_tree.heading("type", text="Type")
        self.issue_tree.heading("message", text="Issue")
        self.issue_tree.column("type", width=130, anchor="w")
        self.issue_tree.column("message", width=820, anchor="w")
        self.issue_tree.pack(side="left", fill="both", expand=True)
        ysb = ttk.Scrollbar(frame, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=ysb.set)
        ysb.pack(side="right", fill="y")
        self.issue_tree.bind("<<TreeviewSelect>>", self._on_issue_select)

    def _build_manager_intelligence_panel(self):
        wrap = ttk.LabelFrame(self, text="Manager Intelligence")
        wrap.pack(fill="x", pady=(6, 0))

        left = ttk.Frame(wrap)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ttk.Label(left, text="Coverage Risk Map").pack(anchor="w")
        self.risk_tree = ttk.Treeview(left, columns=("severity", "day", "time", "area", "reason"), show="headings", height=7)
        for key, title, width in [
            ("severity", "Severity", 80),
            ("day", "Day", 70),
            ("time", "Time", 140),
            ("area", "Area", 110),
            ("reason", "Why this window is risky", 520),
        ]:
            self.risk_tree.heading(key, text=title)
            self.risk_tree.column(key, width=width, anchor="w")
        self.risk_tree.pack(fill="x", expand=True)
        self.risk_tree.bind("<<TreeviewSelect>>", self._on_risk_select)

        right = ttk.Frame(wrap)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ttk.Label(right, text="Call-Off Impact + Replacements").pack(anchor="w")
        top = ttk.Frame(right)
        top.pack(fill="x", pady=(2, 4))
        self.calloff_emp_var = tk.StringVar(value="")
        self.calloff_emp_menu = ttk.Combobox(top, textvariable=self.calloff_emp_var, state="readonly", width=24)
        self.calloff_emp_menu.pack(side="left")
        ttk.Button(top, text="Simulate", command=self._trigger_calloff).pack(side="left", padx=6)

        self.calloff_tree = ttk.Treeview(right, columns=("window", "impact", "suggestion"), show="headings", height=7)
        self.calloff_tree.heading("window", text="Window")
        self.calloff_tree.heading("impact", text="Impact")
        self.calloff_tree.heading("suggestion", text="Top replacement suggestion")
        self.calloff_tree.column("window", width=210, anchor="w")
        self.calloff_tree.column("impact", width=120, anchor="w")
        self.calloff_tree.column("suggestion", width=360, anchor="w")
        self.calloff_tree.pack(fill="x", expand=True)

        health = ttk.LabelFrame(self, text="Schedule Health / Improve Schedule")
        health.pack(fill="x", pady=(6, 0))
        self.health_score_var = tk.StringVar(value="Overall Health: --")
        ttk.Label(health, textvariable=self.health_score_var).pack(anchor="w", padx=8, pady=(6, 4))
        self.health_detail_var = tk.StringVar(value="Coverage -- | Risk -- | Fairness -- | Stability -- | Compliance --")
        ttk.Label(health, textvariable=self.health_detail_var).pack(anchor="w", padx=8, pady=(0, 6))
        action_bar = ttk.Frame(health)
        action_bar.pack(fill="x", padx=8, pady=(0, 8))
        for label, key in [
            ("Improve Fairness", "improve_fairness"),
            ("Reduce Risk", "reduce_risk"),
            ("Improve Stability", "improve_stability"),
            ("Fill Weak Coverage", "fill_weak_coverage"),
            ("Improve Overall", "improve_overall"),
        ]:
            ttk.Button(action_bar, text=label, command=lambda k=key: self._invoke_improve(k)).pack(side="left", padx=3)

    def _invoke(self, key: str):
        cb = self.callbacks.get(key)
        if cb:
            cb()

    def _invoke_improve(self, action: str):
        cb = self.callbacks.get("improve_action")
        if cb:
            cb(action)

    def _trigger_calloff(self):
        cb = self.callbacks.get("simulate_calloff")
        if cb:
            cb(self.calloff_emp_var.get())

    def refresh_workspace(self, payload: Dict[str, Any]):
        self.week_var.set(f"Week: {payload.get('week_label', 'Not selected')}")
        self.state_var.set(f"State: {payload.get('state_text', 'Draft')}")
        warnings = list(payload.get("warnings", []) or [])
        diagnostics = dict(payload.get("diagnostics", {}) or {})
        self.issue_count_var.set(f"Issues: {len(warnings)}")

        total_hours = float(payload.get("total_hours", 0.0) or 0.0)
        filled = int(payload.get("filled_slots", 0) or 0)
        total_slots = int(payload.get("total_slots", 0) or 0)
        self.total_hours_var.set(f"Total Hours: {total_hours:.1f}")
        self.coverage_var.set(f"Coverage: {filled}/{total_slots} slots")
        self.health_var.set(f"Health: {self._compute_health(total_slots, filled, len(warnings))}")
        self.change_state_var.set(payload.get("draft_state", "Draft changes: none"))

        self._emp_hours = dict(payload.get("emp_hours", {}) or {})
        self._build_assignment_index(list(payload.get("assignments", []) or []))
        self._rebuild_grid()
        self._rebuild_issue_list(warnings, diagnostics)

        self._risk_windows = list(payload.get("risk_windows", []) or [])
        self._rebuild_risk_map()
        self._load_calloff_employees(list(payload.get("employee_names", []) or []))
        self._rebuild_calloff_results(list(payload.get("calloff_windows", []) or []))
        self._render_health_summary(dict(payload.get("health_summary", {}) or {}))

    def _compute_health(self, total_slots: int, filled: int, warning_count: int) -> str:
        if total_slots <= 0:
            return "N/A"
        coverage_score = (float(filled) / float(total_slots)) * 100.0
        adjusted = max(0.0, min(100.0, coverage_score - (warning_count * 1.5)))
        return f"{adjusted:.1f}%"

    def _build_assignment_index(self, assignments: List[Any]):
        self._assignment_index = {}
        for a in assignments:
            day = str(getattr(a, "day", ""))
            emp = str(getattr(a, "employee_name", ""))
            if not day or not emp:
                continue
            self._assignment_index.setdefault((emp, day), []).append(a)

    def _fmt_assignment(self, assignment: Any) -> str:
        start = getattr(assignment, "start_t", 0)
        end = getattr(assignment, "end_t", 0)
        area = str(getattr(assignment, "area", ""))
        hours = max(0.0, (float(end) - float(start)) * 0.5)
        return f"{area} {int(start//2):02d}:{'30' if start % 2 else '00'}-{int(end//2):02d}:{'30' if end % 2 else '00'} ({hours:.1f}h)"

    def _rebuild_grid(self):
        for iid in self.grid_tree.get_children():
            self.grid_tree.delete(iid)

        employees = sorted({emp for emp, _ in self._assignment_index.keys()}, key=str.lower)
        for emp in employees:
            values: List[str] = [emp]
            for d in self.days:
                slots = self._assignment_index.get((emp, d), [])
                values.append("\n".join([self._fmt_assignment(s) for s in slots]) if slots else "—")
            values.append(f"{float(self._emp_hours.get(emp, 0.0) or 0.0):.1f}")
            self.grid_tree.insert("", "end", values=values)

    def _rebuild_issue_list(self, warnings: List[str], diagnostics: Dict[str, Any]):
        for iid in self.issue_tree.get_children():
            self.issue_tree.delete(iid)
        for w in warnings:
            self.issue_tree.insert("", "end", values=("Warning", str(w)))
        for note in list(diagnostics.get("limiting_factors", []) or []):
            self.issue_tree.insert("", "end", values=("Diagnostic", str(note)))

    def _rebuild_risk_map(self):
        for iid in self.risk_tree.get_children():
            self.risk_tree.delete(iid)
        for idx, risk in enumerate(self._risk_windows):
            self.risk_tree.insert("", "end", iid=f"risk-{idx}", values=(risk.get("severity", "--"), risk.get("day", "--"), risk.get("time", "--"), risk.get("area", "--"), risk.get("reason", "")))

    def _load_calloff_employees(self, names: List[str]):
        self.calloff_emp_menu["values"] = names
        if names and self.calloff_emp_var.get() not in names:
            self.calloff_emp_var.set(names[0])

    def _rebuild_calloff_results(self, windows: List[Dict[str, Any]]):
        for iid in self.calloff_tree.get_children():
            self.calloff_tree.delete(iid)
        for idx, w in enumerate(windows):
            top = (w.get("suggestions") or [{}])[0]
            sug = "No valid replacement"
            if top and top.get("employee"):
                sug = f"{top.get('employee')} — {top.get('reason', '')}"
            self.calloff_tree.insert("", "end", iid=f"co-{idx}", values=(f"{w.get('day')} {w.get('area')} {w.get('time')}", f"{w.get('deficit_hours', 0)}h / peak {w.get('peak_deficit', 0)}", sug))

    def _render_health_summary(self, health: Dict[str, Any]):
        if not health:
            self.health_score_var.set("Overall Health: --")
            self.health_detail_var.set("Coverage -- | Risk -- | Fairness -- | Stability -- | Compliance --")
            return
        self.health_score_var.set(f"Overall Health: {health.get('overall', '--')}")
        dims = dict(health.get("dimensions", {}) or {})
        self.health_detail_var.set(
            f"Coverage {dims.get('Coverage', '--')} | Risk {dims.get('Risk', '--')} | Fairness {dims.get('Fairness', '--')} | Stability {dims.get('Stability', '--')} | Compliance {dims.get('Compliance', '--')}"
        )

    def _on_grid_click(self, event):
        iid = self.grid_tree.identify_row(event.y)
        col_id = self.grid_tree.identify_column(event.x)
        if not iid or not col_id:
            return
        row = self.grid_tree.item(iid, "values")
        if not row:
            return
        emp = str(row[0])
        col_idx = int(col_id.lstrip("#")) - 1
        if col_idx < 1 or col_idx > len(self.days):
            return
        day = self.days[col_idx - 1]
        self._show_selection(emp, day)

    def _on_grid_select(self, _event):
        sel = self.grid_tree.selection()
        if not sel:
            return
        row = self.grid_tree.item(sel[0], "values")
        if row:
            self._show_selection(str(row[0]), self.days[0])

    def _show_selection(self, emp: str, day: str):
        self._selected_key = (emp, day)
        slots = self._assignment_index.get((emp, day), [])
        self.selection_emp_var.set(f"Employee: {emp}")
        self.selection_day_var.set(f"Day: {day}")
        self.selection_shift_var.set("Shift(s): " + ("; ".join([self._fmt_assignment(s) for s in slots]) if slots else "None"))
        areas = sorted({str(getattr(s, "area", "")) for s in slots})
        self.selection_area_var.set(f"Area: {', '.join(areas) if areas else '--'}")
        self.selection_hours_var.set(f"Hours this week: {float(self._emp_hours.get(emp, 0.0) or 0.0):.1f}")

        self.issue_text.delete("1.0", tk.END)
        if slots:
            self.issue_text.insert(tk.END, "Selected assignment details loaded. Use Edit Selected to bridge into legacy manual editing when needed.")
        else:
            self.issue_text.insert(tk.END, "No assignment for this employee/day.")

    def _on_issue_select(self, _event):
        sel = self.issue_tree.selection()
        if not sel:
            return
        vals = self.issue_tree.item(sel[0], "values")
        msg = str(vals[1]) if len(vals) > 1 else ""
        self.issue_text.delete("1.0", tk.END)
        self.issue_text.insert(tk.END, msg)

    def _on_risk_select(self, _event):
        sel = self.risk_tree.selection()
        if not sel:
            return
        try:
            idx = int(str(sel[0]).split("-")[-1])
            risk = self._risk_windows[idx]
        except Exception:
            return
        self.issue_text.delete("1.0", tk.END)
        self.issue_text.insert(tk.END, risk.get("reason", ""))
        cb = self.callbacks.get("focus_risk")
        if cb:
            cb(risk)
