"""FocusBar - a thin, translucent, always-on-top strip showing what you're doing.

Pure standard library (tkinter + ctypes). No pip installs.

Module map (see CODEBASE.md for the full guide):

    paths    where data lives on disk
    version  the version number, from the build stamp or from git
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

# Opened by the link icon in the task-list footer. Change this one line to
# point it wherever you like; set it to "" to hide the icon entirely.
GITHUB_URL = "https://github.com/Syafie-Monitor-ERP/FocusBar"


def __getattr__(name: str) -> str:
    """Resolve `__version__` on first access.

    Off a checkout, resolving it costs a `git describe` subprocess (see
    `version.resolve`) — not something every importer of this package should pay
    for at import time.
    """
    if name == "__version__":
        from .version import resolve

        return resolve()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
