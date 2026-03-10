import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional


class AppShell(ttk.Frame):
    def __init__(self, master, nav_items: Dict[str, str], on_nav: Callable[[str], None], actions: Dict[str, Callable[[], None]]):
        super().__init__(master)
        self.pack(fill="both", expand=True)

        self.header_store_var = tk.StringVar(value="Store: Unset")
        self.header_week_var = tk.StringVar(value="Week: Not selected")
        self.header_state_var = tk.StringVar(value="State: Draft")
        self.header_warning_var = tk.StringVar(value="Warnings: 0")

        self.status_save_var = tk.StringVar(value="Saved")
        self.status_operation_var = tk.StringVar(value="Ready")
        self.status_schedule_var = tk.StringVar(value="Draft")

        self._build_header(actions)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        self.nav = ttk.Frame(body)
        self.nav.pack(side="left", fill="y", padx=(10, 0), pady=8)

        self._nav_buttons: Dict[str, ttk.Button] = {}
        for key, label in nav_items.items():
            btn = ttk.Button(self.nav, text=label, command=lambda k=key: on_nav(k), width=24)
            btn.pack(fill="x", pady=3)
            self._nav_buttons[key] = btn

        self.workspace = ttk.Frame(body)
        self.workspace.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        self._build_status_bar()

    def _build_header(self, actions: Dict[str, Callable[[], None]]):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=(10, 4))

        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="LaborForceScheduler", style="Header.TLabel").pack(anchor="w")
        ttk.Label(left, textvariable=self.header_store_var).pack(anchor="w")
        ttk.Label(left, textvariable=self.header_week_var).pack(anchor="w")

        right = ttk.Frame(header)
        right.pack(side="right")
        ttk.Button(right, text="Generate", command=actions.get("generate", lambda: None)).pack(side="left", padx=4)
        ttk.Button(right, text="Improve", command=actions.get("improve", lambda: None)).pack(side="left", padx=4)
        ttk.Button(right, text="Publish", command=actions.get("publish", lambda: None)).pack(side="left", padx=4)
        ttk.Button(right, text="Save", command=actions.get("save", lambda: None)).pack(side="left", padx=4)
        ttk.Button(right, text="Open", command=actions.get("open", lambda: None)).pack(side="left", padx=4)
        ttk.Button(right, text="New", command=actions.get("new", lambda: None)).pack(side="left", padx=4)

        summary = ttk.Frame(self)
        summary.pack(fill="x", padx=10)
        ttk.Label(summary, textvariable=self.header_state_var).pack(side="left", padx=(0, 12))
        ttk.Label(summary, textvariable=self.header_warning_var).pack(side="left")

    def _build_status_bar(self):
        status = ttk.Frame(self)
        status.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Separator(status, orient="horizontal").pack(fill="x", pady=(2, 4))
        row = ttk.Frame(status)
        row.pack(fill="x")
        ttk.Label(row, text="Save:").pack(side="left")
        ttk.Label(row, textvariable=self.status_save_var).pack(side="left", padx=(3, 14))
        ttk.Label(row, text="Operation:").pack(side="left")
        ttk.Label(row, textvariable=self.status_operation_var).pack(side="left", padx=(3, 14))
        ttk.Label(row, text="Schedule:").pack(side="left")
        ttk.Label(row, textvariable=self.status_schedule_var).pack(side="left", padx=(3, 14))

    def set_active_nav(self, key: str):
        for nav_key, btn in self._nav_buttons.items():
            btn.state(["!disabled"])
            if nav_key == key:
                btn.state(["disabled"])
