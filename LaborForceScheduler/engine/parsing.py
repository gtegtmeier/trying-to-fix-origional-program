"""Manual parsing adapters.

Manual edit parsing remains implemented on SchedulerApp; these helpers provide a module boundary
without changing behavior.
"""
from scheduler_app_v3_final import _normalize_user_time, SchedulerApp


def manual_parse_time_blocks(app: SchedulerApp, raw: str):
    return app._manual_parse_time_blocks(raw)


def manual_parse_pages_to_assignments(app: SchedulerApp):
    return app._manual_parse_pages_to_assignments()


def manual_validate_assignments(app: SchedulerApp, assigns):
    return app._manual_validate_assignments(assigns)


__all__ = [
    "_normalize_user_time",
    "manual_parse_time_blocks",
    "manual_parse_pages_to_assignments",
    "manual_validate_assignments",
]
