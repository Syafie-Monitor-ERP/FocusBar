"""FocusBar - a thin, translucent, always-on-top strip showing what you're doing.

Pure standard library (tkinter + ctypes). No pip installs.

Module map (see CODEBASE.md for the full guide):

    paths    where data lives on disk
    theme    palette, sizing, glyphs, the state->appearance mapping
    util     small pure formatters
    winapi   ctypes bindings, window-style helpers, the global-hotkey thread
    store    config load/save, the session log, and TaskStore (the timing model)
    tooltip  hover hint window
    panel    TaskListPanel - the drop-down list
    bar      FocusBar - the strip itself
    system   session log + "start with Windows" shortcut

The entry point is `focusbar.pyw` in the parent directory.
"""

__version__ = "2.0"

# Opened by the link icon in the task-list footer. Change this one line to
# point it wherever you like; set it to "" to hide the icon entirely.
GITHUB_URL = "https://example.com"
