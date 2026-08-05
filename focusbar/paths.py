"""Where FocusBar keeps its data.

Resolved at import time, so anything redirecting %APPDATA% (the test harness does)
must do it before importing any other focusbar module.
"""

from __future__ import annotations

import os

APP_NAME = "FocusBar"

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "sessions.csv")

# The launcher a Startup shortcut has to point at: the .pyw beside this package.
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)
ENTRY_SCRIPT = os.path.join(PROJECT_DIR, "focusbar.pyw")
