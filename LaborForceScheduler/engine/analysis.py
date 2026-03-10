"""Analysis adapters.

Analysis/heatmap/call-off implementations remain on SchedulerApp; these wrappers preserve behavior.
"""
from scheduler_app_v3_final import (
    schedule_score_breakdown,
    explain_assignment,
    explain_shortage_window,
    explain_employee_hours,
    SchedulerApp,
)


def refresh_schedule_analysis(app: SchedulerApp):
    return app._refresh_schedule_analysis()


def refresh_heatmap(app: SchedulerApp):
    return app._refresh_heatmap()


def simulate_calloff(app: SchedulerApp):
    return app._simulate_calloff()


__all__ = [
    "schedule_score_breakdown",
    "explain_assignment",
    "explain_shortage_window",
    "explain_employee_hours",
    "refresh_schedule_analysis",
    "refresh_heatmap",
    "simulate_calloff",
]
