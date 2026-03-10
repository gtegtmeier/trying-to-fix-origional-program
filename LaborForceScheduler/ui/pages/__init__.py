import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Tuple


class DashboardPage(ttk.Frame):
    def __init__(self, master, actions: List[Tuple[str, Callable[[], None]]]):
        super().__init__(master)
        self.week_var = tk.StringVar(value="Current Week: N/A")
        self.status_var = tk.StringVar(value="Status: No schedule generated yet")
        self.warning_var = tk.StringVar(value="Warnings: 0")

        ttk.Label(self, text="Dashboard", style="SubHeader.TLabel").pack(anchor="w", pady=(4, 8))
        ttk.Label(self, textvariable=self.week_var).pack(anchor="w")
        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", pady=(2, 0))
        ttk.Label(self, textvariable=self.warning_var).pack(anchor="w", pady=(2, 10))

        quick = ttk.LabelFrame(self, text="Quick Actions")
        quick.pack(fill="x", pady=(0, 12))
        for txt, cb in actions:
            ttk.Button(quick, text=txt, command=cb).pack(side="left", padx=6, pady=8)

        risks = ttk.LabelFrame(self, text="Risk / Warning Summary")
        risks.pack(fill="x")
        ttk.Label(risks, text="Use Schedule Analysis for detailed diagnostics. This panel reserves dashboard KPI space.").pack(anchor="w", padx=8, pady=8)


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

        ttk.Label(self, text="Edit & Review Schedule", style="SubHeader.TLabel").pack(anchor="w", pady=(4, 6))
        self._build_toolbar()
        self._build_workflow_rail()
        self._build_summary_strip()
        self._build_workspace()
        self._build_issue_panel()
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
        self.grid_tree.bind("<<TreeviewSelect>>", self._on_grid_select)
        self.grid_tree.bind("<ButtonRelease-1>", self._on_grid_click)

        insp = ttk.LabelFrame(work, text="Inspector / Editor")
        insp.pack(side="left", fill="y")
        for var in [
            self.selection_emp_var,
            self.selection_day_var,
            self.selection_shift_var,
            self.selection_area_var,
            self.selection_hours_var,
        ]:
            ttk.Label(insp, textvariable=var, wraplength=290, justify="left").pack(anchor="w", padx=10, pady=4)

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

    def _invoke(self, key: str):
        cb = self.callbacks.get(key)
        if cb:
            cb()

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
