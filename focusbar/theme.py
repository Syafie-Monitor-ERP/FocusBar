"""Palette, sizing, glyphs, and the one mapping from task state to appearance.

Nothing here touches Tk. `state_dot` is the single definition of what each task
state looks like; both the strip and the list read it, so they cannot drift.
"""

from __future__ import annotations

from .util import lerp_color

# Palette. Kept muted so the bar reads as an overlay, not a window.
BG = "#0e1016"
FG = "#e9ecf3"
DIM = "#7d8496"
ACCENT = "#5b9dff"
ACCENT_LOW = "#2c4f80"     # dim end of the "running" breath
AMBER = "#f2a33c"          # the one colour that ever means "paused"
NUDGE = "#ff9152"
HOVER_BG = "#1e2431"
FLASH_BG = "#1f3352"       # brief highlight on a newly added row
BORDER = "#262a35"
PANEL_BG = "#0f1219"
RUNNING_BG = "#151d2c"     # whole-row wash on a ticking task
IDLE_FG = "#828998"        # text of a task that has never been started
IDLE_DIM = "#525969"       # its dot and its em-dash
ROW_TEXT = "#b9bfcd"       # unfocused row text in the list
STACK_TEXT = "#99a0b0"     # unfocused row text on the strip

BAR_HEIGHT = 30            # one row; the strip grows a row per running task
ROW_HEIGHT = 28            # height of each additional stacked row
RAIL_WIDTH = 3
MIN_WIDTH = 240
MAX_WIDTH = 760
PLACEHOLDER = "What are you working on?  (click to set)"

# Running vs stopped is signalled on several redundant channels at once, because
# a glyph swap alone is too easy to miss in peripheral vision:
#   1. the left rail  - breathing blue when running, solid amber when paused
#   2. the word       - the timer reads "paused · 25m" or "not started"
#   3. the task text  - full contrast when running, greyed otherwise
#   4. the row wash   - only running rows are tinted (list)
# Motion is the channel that survives peripheral vision, hence the breath.
BREATH_MS = 90
BREATH_STEPS = 18

# Segoe's icon fonts give real media glyphs; plain text is the fallback.
ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
ICON_PLAY, ICON_PAUSE, ICON_LINK = "", "", ""
TEXT_PLAY, TEXT_PAUSE, TEXT_LINK = "▶", "❚❚", "↗"

# Three states, three treatments - glyph, colour and the time column all differ,
# because a hollow-vs-filled dot alone is too quiet to read at 8pt:
#     running   ● blue, breathing   row washed blue   live time
#     paused    ▶ amber, still      plain row         banked time
#     unstarted ○ grey, hollow      plain row         em-dash
#
# `FocusBar.rest_control()` is the single definition; it lives on the bar because
# only the bar knows which icon font resolved.
DOT_RUNNING, DOT_IDLE = "●", "○"
DOT_FONT = ("Segoe UI", 8)
ICON_SIZE = 9


def breath_ramp() -> list[str]:
    """One full dim->bright->dim cycle for the running indicator."""
    half = [lerp_color(ACCENT_LOW, ACCENT, i / (BREATH_STEPS - 1)) for i in range(BREATH_STEPS)]
    return half + half[-2:0:-1]
