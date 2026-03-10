"""Primary app entry module.

Keeps launch behavior identical by delegating to the stable core module.
"""
from scheduler_app_v3_final import SchedulerApp, main

__all__ = ["SchedulerApp", "main"]

if __name__ == "__main__":
    main()
