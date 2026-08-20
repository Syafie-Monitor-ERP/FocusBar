"""FocusBar launcher.

A thin, translucent, always-on-top strip showing what you're currently doing.
One row per running task; paused tasks live in the drop-down list.

Each task carries a short id, generated from its name and editable in the list.
Its position in the list is its priority: drag a row, or press Alt+Up/Alt+Down.

Hotkeys (work anywhere in Windows):
    Ctrl+Alt+T   rename the focused task
    Ctrl+Alt+A   add a task to the list
    Ctrl+Alt+L   open / close the task list
    Ctrl+Alt+N   next task          Ctrl+Alt+B   previous task
    Ctrl+Alt+P   pause / resume the focused task
    Ctrl+Alt+H   hide or show the strip

On the strip, each row acts on its own task: hover its dot for the action,
click the dot to start/stop, click the text to rename, drag to move, wheel for
opacity, right-click for the menu (which includes Move up / Move down).

The implementation lives in the `focusbar` package beside this file; see
CODEBASE.md for a guide to it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from focusbar.bar import FocusBar  # noqa: E402  (path set up above)

if __name__ == "__main__":
    FocusBar().run()
