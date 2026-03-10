import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Tuple


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
    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Scheduling", style="SubHeader.TLabel").pack(anchor="w", pady=(4, 8))
        ttk.Label(self, text="Generate, review, and refine schedules in the embedded legacy workspace.", foreground="#555").pack(anchor="w", pady=(0, 8))
        self.content = ttk.Frame(self)
        self.content.pack(fill="both", expand=True)
