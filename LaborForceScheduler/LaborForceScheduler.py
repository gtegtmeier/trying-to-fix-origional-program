"""Compatibility launcher.

This project uses scheduler_app_v3_final.py as the canonical entrypoint.
This file remains for backward compatibility with older shortcuts/batch files.
"""

from scheduler_app_v3_final import main

if __name__ == "__main__":
    main()
