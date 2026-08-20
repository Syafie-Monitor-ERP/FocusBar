"""In-process checks for FocusBar.

Run it directly:  python tests/test_focusbar.py
Exits non-zero on failure. No pytest, matching the rest of the project.

Two constraints shape this file (see CODEBASE.md section 8):
  * %APPDATA% is redirected to a temp dir BEFORE importing anything from the
    package, because paths.py resolves DATA_DIR at import time.
  * FocusBar is built with __new__ and hand-initialised, so the real __init__
    never starts the global-hotkey thread and hijacks Ctrl+Alt+* system-wide.
"""
import json
import os
import pathlib
import sys
import tempfile
import tkinter as tk
from datetime import datetime, timedelta

PROJECT = pathlib.Path(__file__).resolve().parent.parent
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="focusbar_test_")   # before import
sys.path.insert(0, str(PROJECT))


class _NB:
    """Flat view over the package, so the checks below read unchanged."""

    def __init__(self):
        from focusbar import bar, panel, paths, store, theme, util
        for module in (paths, theme, util, store, panel, bar):
            for name in dir(module):
                if not name.startswith("_"):
                    setattr(self, name, getattr(module, name))


nb = _NB()

fails = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        fails.append(name)


# --- the clock ------------------------------------------------------------
# Timers must not bank time the machine spent asleep, so they run on the
# unbiased counter rather than time.monotonic() - see focusbar/clock.py.
import time as _time                                            # noqa: E402

from focusbar import bar as _bar, clock as _clock, store as _store   # noqa: E402

check("clock: unbiased counter available on Windows",
      (os.name != "nt") or not _clock.COUNTS_SLEEP)
check("clock: never counts more than the biased clock",
      _clock.awake() <= _time.monotonic() + 1.0)
check("clock: advances", _clock.awake() > 0)
check("clock: task clocks use it", _store.awake is _clock.awake)
check("clock: the nudge timer uses it too", _bar.awake is _clock.awake)


# --- pure helpers ---------------------------------------------------------
check("elapsed <1h", nb.format_elapsed(14 * 60) == "14m")
check("elapsed >1h", nb.format_elapsed(3 * 3600 + 7 * 60) == "3h07")
check("truncate", nb.truncate("abcdefghij", 5) == "abcd…", nb.truncate("abcdefghij", 5))

check("initials: first letters", nb.initials("Refactor the export path") == "RTE",
      nb.initials("Refactor the export path"))
check("initials: counts short words too", nb.initials("Write release notes") == "WRN")
check("initials: pads from the last word", nb.initials("Fix CSV") == "FCS",
      nb.initials("Fix CSV"))
check("initials: pads a lone word", nb.initials("Email") == "EMA", nb.initials("Email"))
check("initials: ignores punctuation", nb.initials("re-do (the) thing") == "RDT",
      nb.initials("re-do (the) thing"))
check("initials: fallback when nothing usable", nb.initials("--- ...") == nb.ID_FALLBACK)
check("unique_id: free base kept", nb.unique_id("RTE", ["ABC"]) == "RTE")
check("unique_id: suffixes past collisions", nb.unique_id("RTE", ["RTE", "rte2"]) == "RTE3",
      nb.unique_id("RTE", ["RTE", "rte2"]))
check("unique_id: stays within the length cap",
      len(nb.unique_id("M" * nb.ID_MAX, ["M" * nb.ID_MAX])) == nb.ID_MAX)
check("clean_id: strips whitespace and clamps",
      nb.clean_id("  MON 4821  ") == "MON4821" and len(nb.clean_id("x" * 40)) == nb.ID_MAX)

start = datetime(2026, 8, 5, 9, 0)
nb.append_log("Real task", start, start + timedelta(minutes=42), 42 * 60)
nb.append_log("Typo", start, start + timedelta(seconds=4), 4)
rows = open(nb.LOG_PATH, encoding="utf-8").read().strip().splitlines()
check("log: header + 1 row", len(rows) == 2, f"{len(rows)}")
check("log: short task skipped", "Typo" not in "".join(rows))

# --- config loading must survive junk on disk -----------------------------
os.makedirs(nb.DATA_DIR, exist_ok=True)
with open(nb.CONFIG_PATH, "w", encoding="utf-8") as fh:
    json.dump({
        "opacity": 0.5,
        "unknown_key": "ignored",
        "active": 99,                                  # out of range
        "tasks": [
            {"text": "  Real  ", "seconds": "12"},     # str seconds, needs strip
            {"text": "   "},                           # blank -> dropped
            "not a dict",                              # junk -> dropped
        ],
    }, fh)
loaded = nb.load_config()
check("config: keeps known keys", loaded["opacity"] == 0.5)
check("config: drops unknown keys", "unknown_key" not in loaded)
check("config: cleans the task list",
      [t["text"] for t in loaded["tasks"]] == ["Real"], str(loaded["tasks"]))
check("config: coerces seconds", loaded["tasks"][0]["seconds"] == 12.0)
check("config: fills run flags",
      loaded["tasks"][0]["running"] is False and loaded["tasks"][0]["auto"] is False)
check("config: clamps out-of-range active", loaded["active"] == 0, str(loaded["active"]))
check("config: generates a missing id", loaded["tasks"][0]["id"] == "REA",
      loaded["tasks"][0]["id"])
check("config: unset id is not locked", loaded["tasks"][0]["id_locked"] is False)

# ids written by hand may repeat or be missing; both are settled at load so the
# rest of the code can assume every task has one and no two share it.
with open(nb.CONFIG_PATH, "w", encoding="utf-8") as fh:
    json.dump({"tasks": [
        {"text": "Alpha one", "id": "AAA", "id_locked": True},
        {"text": "Alpha two", "id": "aaa", "id_locked": True},   # same, bar the case
        {"text": "Ship the thing"},                              # legacy, no id
        {"text": "Ship the thumb"},                              # would collide -> STT2
    ]}, fh)
ids = [t["id"] for t in nb.load_config()["tasks"]]
check("config: de-duplicates ids", ids == ["AAA", "aaa2", "STT", "STT2"], str(ids))
check("config: keeps id_locked", nb.load_config()["tasks"][0]["id_locked"] is True)

with open(nb.CONFIG_PATH, "w", encoding="utf-8") as fh:
    fh.write("{ this is not json")
check("config: survives corrupt json", nb.load_config()["tasks"] == [])
os.remove(nb.CONFIG_PATH)
check("config: no file -> defaults", nb.load_config()["active"] == -1)

# --- the widget -----------------------------------------------------------
bar = nb.FocusBar.__new__(nb.FocusBar)          # skip __init__ so no hotkey thread
bar.config = dict(nb.DEFAULTS)
bar.config["tasks"], bar.config["active"] = [], -1
bar.store = nb.TaskStore(bar.config)
bar.opacity, bar.nudge_minutes, bar.click_through = 0.72, 15, False
bar.hidden = bar.editing = False
bar.last_nudge = 0
bar._drag_origin = None
bar._drag_moved = False
bar._pulse_left = 0
bar._restore_click_through = False
bar.panel = nb.TaskListPanel(bar)
bar._build_window()
bar.root.update()

before = (bar.root.winfo_x(), bar.root.winfo_y())


def row_texts():
    return [r.label.cget("text") for r in bar.rows]


def row_of(i):
    return bar._row_for(i)


check("empty: no rows", bar.rows == [] and bar.visible_tasks() == [])
check("empty: single-row height", bar._bar_height() == nb.BAR_HEIGHT)

# --- colour helpers -------------------------------------------------------
check("lerp ends", nb.lerp_color("#000000", "#ffffff", 0.0) == "#000000"
      and nb.lerp_color("#000000", "#ffffff", 1.0) == "#ffffff")
check("lerp midpoint", nb.lerp_color("#000000", "#ffffff", 0.5) == "#808080",
      nb.lerp_color("#000000", "#ffffff", 0.5))
ramp = nb.breath_ramp()
check("breath ramp loops", ramp[0] == nb.ACCENT_LOW and nb.ACCENT in ramp
      and ramp[-1] != ramp[0], f"{len(ramp)} steps")

# First task activates (nothing was running); later ones must NOT steal the clock.
bar.create_task("Review PR 412")
bar.root.update()
check("first task auto-activates", bar.active == 0, str(bar.active))
bar.create_task("Migration script")
bar.create_task("Update API docs")
bar.root.update()
check("3 tasks", len(bar.tasks) == 3)
check("adding does not switch", bar.active == 0 and bar.current["text"] == "Review PR 412",
      f"active={bar.active}")
check("only the running one shows", row_texts() == ["Review PR 412"], str(row_texts()))
check("position held", (bar.root.winfo_x(), bar.root.winfo_y()) == before)

# adding must not disturb the running task
bar.set_active(0)
bar.tasks[0]["seconds"] = 900.0
banked = bar.total_elapsed()
seg_start = bar.tasks[0]["_from"]
bar.create_task("Something later")
bar.root.update()
check("adding keeps the clock", bar.total_elapsed() >= banked, str(bar.total_elapsed()))
check("adding keeps the segment", bar.tasks[0]["_from"] == seg_start)
check("adding keeps the row", row_texts() == ["Review PR 412"], str(row_texts()))
check("added task is not running", not bar.tasks[-1]["running"])
check("explicit activate works", bar.create_task("Start me", activate=True) == bar.active)
bar.remove_task(bar.active)
bar.remove_task(3)
bar.set_active(0)
bar.root.update()
check("back to 3 tasks", len(bar.tasks) == 3, str([t["text"] for t in bar.tasks]))

# --- the play/pause button ------------------------------------------------
class E:  # stand-in for a tk event; release handlers only read drag state
    pass

r0 = row_of(0)
check("running: button shows state dot at rest", r0.button.cget("text") == nb.DOT_RUNNING,
      r0.button.cget("text"))
r0.hover(True)
check("running: hover reveals pause action", r0.button.cget("text") == bar.icon_pause,
      r0.button.cget("text"))
r0.hover(False)
check("running: unhover restores the dot", r0.button.cget("text") == nb.DOT_RUNNING)
check("running: full-contrast text", r0.label.cget("fg") == nb.FG)
check("running: no 'paused' word", "paused" not in r0.timer.cget("text"))
check("running: rail is blue-ish", r0.rail.cget("bg") in (nb.ACCENT, *nb.breath_ramp()),
      r0.rail.cget("bg"))

# the rail must actually move while running
seen = set()
for _ in range(6):
    bar._breathe_step()
    seen.add(row_of(0).rail.cget("bg"))
check("running: rail animates", len(seen) > 1, f"{len(seen)} distinct colours")

bar._drag_moved = False
bar._on_release_button(0)
bar.root.update()
check("button click pauses", bar.paused)
# it was the only running task, so the strip keeps showing it in paused form
check("last running task stays visible", row_texts() == ["Review PR 412"], str(row_texts()))
r0 = row_of(0)
# A STOPPED row shows the play triangle at rest - unambiguous beside an amber
# rail and a "paused" readout, and it invites the click.
check("paused: shows a play button at rest",
      r0.button.cget("text") == bar.icon_play and r0.button.cget("fg") == nb.AMBER,
      f"{r0.button.cget('text')!r} {r0.button.cget('fg')}")
check("paused: play button is not the state dot",
      r0.button.cget("text") not in (nb.DOT_RUNNING, nb.DOT_IDLE))
r0.hover(True)
check("paused: hover keeps the play action", r0.button.cget("text") == bar.icon_play,
      r0.button.cget("text"))
r0.hover(False)
check("paused: unhover keeps the play button", r0.button.cget("text") == bar.icon_play)
check("paused: rail amber", r0.rail.cget("bg") == nb.AMBER)
check("paused: says the word", r0.timer.cget("text").startswith("paused · "),
      r0.timer.cget("text"))
check("paused: timer amber", r0.timer.cget("fg") == nb.AMBER)

still = set()
for _ in range(6):
    bar._breathe_step()
    still.add(row_of(0).rail.cget("bg"))
check("paused: rail frozen", still == {nb.AMBER}, str(still))

frozen = bar.total_elapsed()
bar.root.after(120, bar.root.quit); bar.root.mainloop()
check("clock frozen", abs(bar.total_elapsed() - frozen) < 0.01)
bar._drag_moved = False
bar._on_release_button(0)
bar.root.update()
check("button click resumes", not bar.paused
      and row_of(0).button.cget("fg") == nb.ACCENT)
check("resumed: word gone", "paused" not in row_of(0).timer.cget("text"))
check("button hint tracks state", "Stop" in bar.button_hint(0), bar.button_hint(0))
bar.toggle_pause()
check("hint flips when paused", "Start" in bar.button_hint(0), bar.button_hint(0))
bar.toggle_pause()

# the dot must actually move while running, and the hover swap must survive it
r0 = row_of(0)
dots = set()
for _ in range(6):
    bar._breathe_step()
    dots.add(r0.button.cget("fg"))
check("running: button dot breathes", len(dots) > 1, f"{len(dots)} colours")
r0.hover(True)
bar._breathe_step()
check("breath does not clobber hover", r0.button.cget("text") == bar.icon_pause,
      r0.button.cget("text"))
r0.hover(False)
check("unhover returns to a breathing dot", r0.button.cget("text") == nb.DOT_RUNNING)

bar._drag_moved = True            # a drag must not toggle pause
was = bar.paused
bar._on_release_button(0)
check("drag on button does not pause", bar.paused == was)

# --- navigation -----------------------------------------------------------
bar.set_active(0)
bar.root.update()
check("set_active(0)", bar.active == 0 and row_texts() == ["Review PR 412"])
bar.cycle(1)
check("cycle next", bar.active == 1)
bar.cycle(-1)
check("cycle prev", bar.active == 0)
bar.cycle(-1)
check("cycle wraps backwards", bar.active == 2, str(bar.active))
bar.cycle(1)
check("cycle wraps forwards", bar.active == 0, str(bar.active))

# time banks per task instead of resetting
bar.set_active(1)
bar.tasks[1]["seconds"] = 600.0
bar.set_active(2)
bar.set_active(1)
bar.root.update()
check("per-task time kept", bar.total_elapsed() >= 600.0, str(bar.total_elapsed()))
check("timer text", row_of(1).timer.cget("text") in ("10m", "11m"),
      row_of(1).timer.cget("text"))

# --- the panel ------------------------------------------------------------
bar.panel.open()
bar.root.update()
check("panel opens", bar.panel.is_open)
check("panel row per task", len(bar.panel.rows) == 3, str(len(bar.panel.rows)))
bar.panel.cursor = 0
bar.panel._move_cursor(1)
check("panel cursor moves", bar.panel.cursor == 1)
bar.panel._move_cursor(-1)
bar.panel._move_cursor(-1)
check("panel cursor wraps", bar.panel.cursor == 2, str(bar.panel.cursor))
bar.panel.cursor = 0
bar.panel._activate_cursor()
bar.root.update()
check("panel Enter activates", bar.active == 0 and not bar.panel.is_open)

bar.panel.open(); bar.root.update()
bar.panel.cursor = 2
bar.panel._delete_cursor()
bar.root.update()
check("panel Delete removes", len(bar.tasks) == 2, str([t["text"] for t in bar.tasks]))
check("active still valid", 0 <= bar.active < len(bar.tasks), str(bar.active))
bar.panel.close()
check("panel closes", not bar.panel.is_open)

# --- adding happens inside the list, not in the bar -----------------------
bar.set_active(0)
running_task = bar.current["text"]
n_before = len(bar.tasks)
bar.add_task()
bar.root.update()
check("add opens the list", bar.panel.is_open and bar.panel.adding)
check("add does not edit the bar", not bar.editing)
check("bar still shows running task", row_texts() == [running_task], str(row_texts()))
check("add row has an entry", isinstance(getattr(bar.panel, "add_entry", None), tk.Entry))

bar.panel.add_var.set("Typed in the list")
bar.panel._commit_add(start=False)
bar.root.update()
check("Enter appends", len(bar.tasks) == n_before + 1
      and bar.tasks[-1]["text"] == "Typed in the list")
check("Enter keeps list open", bar.panel.is_open)
check("Enter stays in add mode", bar.panel.adding)
check("Enter clears the field", bar.panel.add_var.get() == "")
check("Enter does not switch", bar.current["text"] == running_task, bar.current["text"])
check("new row is selected", bar.panel.cursor == len(bar.tasks) - 1)
check("new row flashed", bar.panel.rows[-1].cget("bg") == nb.FLASH_BG,
      bar.panel.rows[-1].cget("bg"))

bar.panel.add_var.set("Start this now")
bar.panel._commit_add(start=True)
bar.root.update()
check("Ctrl+Enter switches", bar.current["text"] == "Start this now")
check("Ctrl+Enter closes list", not bar.panel.is_open)

bar.add_task()
bar.panel.add_var.set("   ")
bar.panel._commit_add(start=False)
bar.root.update()
check("blank input adds nothing", bar.tasks[-1]["text"] == "Start this now")
check("blank input leaves add mode", not bar.panel.adding)
bar.panel.begin_add()
bar.panel.cancel_add()
check("Esc leaves add mode", not bar.panel.adding and bar.panel.is_open)
bar.panel.close()

while len(bar.tasks) > 2:
    bar.remove_task(len(bar.tasks) - 1)
bar.set_active(0)
bar.root.update()

# removing the active task keeps the bar coherent
bar.set_active(0)
bar.remove_task(0)
bar.root.update()
check("remove active", len(bar.tasks) == 1 and bar.active == 0, str(bar.active))
bar.remove_task(0)
bar.root.update()
check("remove last -> empty", bar.tasks == [] and bar.active == -1)
check("empty clears the strip", bar.rows == [], str(row_texts()))
check("empty clears timer", bar.total_elapsed() == 0.0)
bar._drag_moved = False
bar._on_release_button(0)     # with no tasks this routes to the add flow
check("button safe when empty", bar.rows == [])
check("empty button opens add", bar.panel.is_open and bar.panel.adding)
bar.panel.close()
bar._cancel_edit()

# --- simultaneous timers --------------------------------------------------
for t in list(bar.tasks):
    bar.store.stop(t)
bar.store.tasks.clear(); bar.store.active = -1
bar.create_task("Build running in CI")
bar.create_task("Review PR 412")
bar.create_task("Write the docs")
bar.set_active(0)
bar.root.update()
check("multi: one running to start", len(bar.running_tasks()) == 1)
check("multi: one row", row_texts() == ["Build running in CI"], str(row_texts()))
check("multi: single-row height", bar._bar_height() == nb.BAR_HEIGHT)

bar.set_running(1, True)                     # explicit start, alongside
bar.root.update()
check("multi: two running", len(bar.running_tasks()) == 2,
      str([t["text"] for t in bar.running_tasks()]))
check("multi: focus unchanged", bar.active == 0)
check("multi: two rows on the strip",
      row_texts() == ["Build running in CI", "Review PR 412"], str(row_texts()))
check("multi: strip grew", bar._bar_height() == nb.ROW_HEIGHT * 2, str(bar._bar_height()))

bar.set_running(2, True)
bar.root.update()
check("multi: three running", len(bar.running_tasks()) == 3)
check("multi: three rows", len(bar.rows) == 3, str(row_texts()))
check("multi: every row running", all(r.running for r in bar.rows))
check("multi: chevron only on row 0",
      bar.counter_text() == "3 ▾", bar.counter_text())

# clocks must advance independently
bar.tasks[0]["seconds"] = 100.0
bar.tasks[1]["seconds"] = 200.0
e0, e1 = bar.elapsed(bar.tasks[0]), bar.elapsed(bar.tasks[1])
check("multi: separate totals", 100.0 <= e0 < 101 and 200.0 <= e1 < 201, f"{e0:.1f}/{e1:.1f}")

# focus moves off an auto-started task -> it stops; explicit ones keep running
check("multi: focused task is auto", bar.tasks[0]["auto"])
check("multi: explicit not auto", not bar.tasks[1]["auto"] and not bar.tasks[2]["auto"])
bar.set_active(2)
bar.root.update()
check("multi: auto task stopped on leave", not bar.tasks[0]["running"])
check("multi: explicit task survives", bar.tasks[1]["running"])
check("multi: newly focused runs", bar.tasks[2]["running"])
check("multi: leaving banked the time", bar.tasks[0]["seconds"] >= 100.0)

# navigating back onto an explicitly-running task must not demote it
bar.set_active(1)
bar.root.update()
check("multi: explicit stays explicit", not bar.tasks[1]["auto"])
bar.set_active(0)
bar.root.update()
check("multi: explicit survives leaving again", bar.tasks[1]["running"])

# pausing the focused task leaves the others alone AND hides its row
bar.toggle_pause()
bar.root.update()
check("multi: pause focused only", not bar.tasks[0]["running"] and bar.tasks[1]["running"])
check("multi: paused row is hidden", "Build running in CI" not in row_texts(),
      str(row_texts()))
check("multi: others still shown", len(bar.rows) == 2, str(row_texts()))
check("multi: focus moved to a visible row", bar.tasks[bar.active]["running"])
check("multi: paused task listed in chevron hint",
      "Build running in CI" in bar.counter_hint(), bar.counter_hint())

# the list reports each task's own state
bar.panel.open(); bar.root.update()
# task 0 was just paused; 1 and 2 were both started explicitly and must persist.
# A paused task with banked time gets an amber PLAY button, not a dot.
states = [(r.dot.cget("text"), r.dot.cget("fg")) for r in bar.panel.rows]
check("multi: list dots match",
      states == [(bar.icon_play, nb.AMBER)] + [(nb.DOT_RUNNING, nb.ACCENT)] * 2,
      str(states))
focused_row = bar.active
bar.panel.cursor = 0
bar.panel._toggle_cursor()
bar.root.update()
check("multi: Space starts a row", bar.tasks[0]["running"])
check("multi: Space did not move focus", bar.active == focused_row)
check("multi: restarted row reappears", "Build running in CI" in row_texts(), str(row_texts()))
bar.panel.cursor = 0          # re-assert: a real pointer over a row moves it
bar.panel._toggle_cursor()
bar.root.update()
check("multi: Space stops it again", not bar.tasks[0]["running"])
check("multi: stopped row hidden again", "Build running in CI" not in row_texts(),
      str(row_texts()))
bar.panel.close()

bar.stop_all()
bar.root.update()
check("multi: stop all", bar.running_tasks() == [])
# with nothing running the strip must not go blank - it falls back to the focused task
check("multi: falls back to one row", len(bar.rows) == 1, str(row_texts()))
check("multi: fallback row is paused", row_of(bar.active).timer.cget("text").startswith("paused"))

# persisted shape must be JSON-clean (no runtime keys)
bar.set_running(1, True)
bar._persist()
saved = json.load(open(nb.CONFIG_PATH, encoding="utf-8"))
check("multi: config has running flags", saved["tasks"][1]["running"] is True)
check("multi: no runtime keys saved",
      all(not k.startswith("_") for t in saved["tasks"] for k in t),
      str(list(saved["tasks"][0])))
reloaded = nb.load_config()
check("multi: running survives reload", reloaded["tasks"][1]["running"] is True)
bar.stop_all()

# --- unstarted vs paused vs running must be unmistakable -------------------
for t in list(bar.tasks):
    bar.store.stop(t)
bar.store.tasks.clear(); bar.store.active = -1
bar.create_task("Ticking away")
bar.create_task("Stopped with time")
bar.create_task("Never started")
bar.tasks[1]["seconds"] = 780.0
bar.set_active(0)
bar.root.update()
check("3states: only one running", [t["running"] for t in bar.tasks] == [True, False, False])

bar.panel.open(); bar.root.update()
run_row, paused_row, fresh_row = bar.panel.rows
bar.panel.cursor = -1            # neutralise hover so backgrounds are comparable
bar.panel._highlight()

check("3states: running dot filled+blue",
      run_row.dot.cget("text") == nb.DOT_RUNNING and run_row.dot.cget("fg") == nb.ACCENT)
check("3states: paused shows a play button",
      paused_row.dot.cget("text") == bar.icon_play and paused_row.dot.cget("fg") == nb.AMBER,
      f"{paused_row.dot.cget('text')!r} {paused_row.dot.cget('fg')}")
check("3states: unstarted dot hollow+grey",
      fresh_row.dot.cget("text") == nb.DOT_IDLE and fresh_row.dot.cget("fg") == nb.IDLE_DIM)

check("3states: running row washed", run_row.cget("bg") == nb.RUNNING_BG, run_row.cget("bg"))
check("3states: paused row plain", paused_row.cget("bg") == nb.PANEL_BG)
check("3states: unstarted row plain", fresh_row.cget("bg") == nb.PANEL_BG)

check("3states: running shows live time",
      run_row.time_label.cget("text") == "0m", run_row.time_label.cget("text"))
check("3states: paused shows banked time",
      paused_row.time_label.cget("text") == "13m", paused_row.time_label.cget("text"))
check("3states: unstarted shows dash",
      fresh_row.time_label.cget("text") == "—", fresh_row.time_label.cget("text"))
check("3states: three distinct time colours",
      len({run_row.time_label.cget("fg"), paused_row.time_label.cget("fg"),
           fresh_row.time_label.cget("fg")}) == 3)

# every one of the three channels differs between running and unstarted
diffs = sum([
    run_row.dot.cget("text") != fresh_row.dot.cget("text"),
    run_row.dot.cget("fg") != fresh_row.dot.cget("fg"),
    run_row.cget("bg") != fresh_row.cget("bg"),
    run_row.time_label.cget("text") != fresh_row.time_label.cget("text"),
])
check("3states: running vs unstarted differs on 4 channels", diffs == 4, f"{diffs}/4")

# the running dot breathes; the other two never move
before = (paused_row.dot.cget("fg"), fresh_row.dot.cget("fg"))
moved = set()
for _ in range(6):
    bar._breathe_step()
    moved.add(run_row.dot.cget("fg"))
check("3states: running dot breathes", len(moved) > 1, f"{len(moved)} colours")
check("3states: others stay put",
      (paused_row.dot.cget("fg"), fresh_row.dot.cget("fg")) == before)
bar.panel.close()

# the strip says which kind of stopped it is
bar.set_active(2)               # focus the never-started one, then stop everything
bar.stop_all(); bar.root.update()
check("3states: strip says 'not started'",
      row_of(bar.active).timer.cget("text") == "not started",
      row_of(bar.active).timer.cget("text"))
bar.set_active(1)
bar.toggle_pause(); bar.stop_all(); bar.root.update()
check("3states: strip says 'paused' when time banked",
      row_of(bar.active).timer.cget("text").startswith("paused · "),
      row_of(bar.active).timer.cget("text"))

# --- icon and tooltip must never contradict each other ---------------------
def agrees(index, tag):
    """The hover icon and the hover tooltip must describe the same action."""
    row = row_of(index)
    row.hover(True)
    icon_says_stop = row.button.cget("text") == bar.icon_pause
    tip_says_stop = "Stop" in bar.button_hint(index)
    row.hover(False)
    check(f"agree: {tag}", icon_says_stop == tip_says_stop,
          f"icon={'stop' if icon_says_stop else 'start'} tip={'stop' if tip_says_stop else 'start'}")


for t in list(bar.tasks):
    bar.store.stop(t)
bar.store.tasks.clear(); bar.store.active = -1
bar.create_task("Solo task")
bar.set_active(0); bar.root.update()
agrees(0, "while running")
bar.toggle_pause(); bar.root.update()
agrees(0, "after pausing")
bar.toggle_pause(); bar.root.update()
agrees(0, "after resuming")

# the regression: state changed while the inline editor suppressed the rebuild
bar.tasks[0]["seconds"] = 300.0      # so stopping lands in "paused", not "unstarted"
bar.begin_edit(0)
bar.toggle_pause()
bar.root.update()
check("stale row: state really changed", not bar.tasks[0]["running"])
agrees(0, "stopped while editing")
bar._update_times()                       # the 500 ms tick must resync the row
check("stale row: control resynced after tick",
      row_of(0).button.cget("text") == bar.icon_play
      and row_of(0).button.cget("fg") == nb.AMBER,
      f"{row_of(0).button.cget('text')!r} {row_of(0).button.cget('fg')}")
check("stale row: rail resynced", row_of(0).rail.cget("bg") == nb.AMBER)
bar._cancel_edit(); bar.root.update()
agrees(0, "after the editor closes")

# and the same invariant with several rows in mixed states
bar.create_task("Second"); bar.create_task("Third")
bar.set_running(1, True); bar.set_running(2, True)
bar.set_active(1); bar.root.update()
for i, _ in enumerate(bar.tasks):
    if row_of(i) is not None:
        agrees(i, f"mixed row {i}")
bar.stop_all(); bar.root.update()

# --- task ids ---------------------------------------------------------------
for t in list(bar.tasks):
    bar.store.stop(t)
bar.store.tasks.clear(); bar.store.active = -1
bar.create_task("Refactor the export path")
bar.create_task("Write release notes")
bar.create_task("Refactor the export pipeline")     # same initials as the first
bar.root.update()
check("id: generated from the name", bar.tasks[0]["id"] == "RTE", bar.tasks[0]["id"])
check("id: collision gets a suffix", bar.tasks[2]["id"] == "RTE2", bar.tasks[2]["id"])
check("id: generated ones are not locked",
      [t["id_locked"] for t in bar.tasks] == [False] * 3)

# a generated id is a view of the name, so it follows a rename
bar.rename_task(1, "Cut a release")
bar.root.update()
check("id: follows a rename while automatic", bar.tasks[1]["id"] == "CAR",
      bar.tasks[1]["id"])

bar.set_task_id(1, " mon 4821 ")
bar.root.update()
check("id: hand-typed one is cleaned", bar.tasks[1]["id"] == "mon4821", bar.tasks[1]["id"])
check("id: typing locks it", bar.tasks[1]["id_locked"] is True)
bar.rename_task(1, "Cut the release instead")
bar.root.update()
check("id: a locked one survives a rename", bar.tasks[1]["id"] == "mon4821",
      bar.tasks[1]["id"])
bar.set_task_id(1, "RTE")           # task 0 holds RTE, task 2 already holds RTE2
check("id: typed collisions are suffixed too", bar.tasks[1]["id"] == "RTE3",
      bar.tasks[1]["id"])
bar.set_task_id(1, "")
bar.root.update()
check("id: blank hands it back to the generator", bar.tasks[1]["id"] == "CTR",
      bar.tasks[1]["id"])
check("id: blank unlocks it", bar.tasks[1]["id_locked"] is False)
check("id: setting one keeps the others",
      [t["id"] for t in bar.tasks] == ["RTE", "CTR", "RTE2"],
      str([t["id"] for t in bar.tasks]))

# the strip shows it, padded to the widest id on screen
bar.set_task_id(0, "MON-1")
bar.set_running(2, True)
bar.set_active(0)
bar.root.update()
check("id: on the strip", row_of(0).id_label.cget("text").strip() == "MON-1",
      row_of(0).id_label.cget("text"))
check("id: column padded to the widest showing", bar.id_slot() == 5, str(bar.id_slot()))
check("id: shorter ids padded to match",
      row_of(2).id_label.cget("text") == "RTE2 ", repr(row_of(2).id_label.cget("text")))
bar.set_task_id(0, "")
bar.root.update()

# ids must survive a save/load round trip, runtime keys must not sneak in
bar._persist()
saved = json.load(open(nb.CONFIG_PATH, encoding="utf-8"))
check("id: persisted", saved["tasks"][0]["id"] == "RTE", str(saved["tasks"][0]))
check("id: id_locked persisted", "id_locked" in saved["tasks"][0])
check("id: reload keeps ids", [t["id"] for t in nb.load_config()["tasks"]]
      == [t["id"] for t in bar.tasks])

# --- rank is position, and rearranging is the only way it changes -----------
check("rank: one-based position", [bar.store.rank(i) for i in range(3)] == [1, 2, 3])

names = lambda: [t["text"] for t in bar.tasks]                        # noqa: E731
bar.set_active(0)
before_ids = [t["id"] for t in bar.tasks]
check("rank: move returns the new slot", bar.move_task(0, 2) == 2)
bar.root.update()
check("rank: the list reordered",
      names() == ["Cut the release instead", "Refactor the export pipeline",
                  "Refactor the export path"], str(names()))
check("rank: focus followed the task itself",
      bar.current["text"] == "Refactor the export path", bar.current["text"])
check("rank: moving changes nothing but the order",
      sorted(t["id"] for t in bar.tasks) == sorted(before_ids))
check("rank: renumbered after the move", bar.store.rank(bar.active) == 3,
      str(bar.store.rank(bar.active)))

check("rank: shift up", bar.shift_task(2, -1) == 1)
bar.root.update()
check("rank: shift moved one slot", names()[1] == "Refactor the export path", str(names()))
check("rank: shift does not wrap off the top", bar.shift_task(0, -1) == 0)
check("rank: shift does not wrap off the bottom", bar.shift_task(2, 1) == 2)
check("rank: order held at the ends",
      names() == ["Cut the release instead", "Refactor the export path",
                  "Refactor the export pipeline"], str(names()))
check("rank: a move out of range is a no-op", bar.move_task(9, 0) == 9 and len(bar.tasks) == 3)

# a clock must not notice being re-ranked
bar.set_running(0, True)
bar.tasks[0]["seconds"] = 400.0
running_name = bar.tasks[0]["text"]
bar.move_task(0, 2)
bar.root.update()
moved = next(t for t in bar.tasks if t["text"] == running_name)
check("rank: the clock survives a move", moved["running"] and moved["seconds"] >= 400.0,
      f"{moved['running']} {moved['seconds']}")
bar.stop_all(); bar.root.update()

# --- the list: ranks, ids, and the two ways to rearrange -------------------
bar.set_active(0)
bar.panel.open(); bar.root.update()
ranks = [r.parts[0].cget("text").strip() for r in bar.panel.rows]
check("panel: ranks count from 1", ranks == ["1", "2", "3"], str(ranks))
check("panel: id shown per row",
      [r.parts[2].cget("text").strip() for r in bar.panel.rows]
      == [t["id"] for t in bar.tasks],
      str([r.parts[2].cget("text") for r in bar.panel.rows]))

bar.panel.cursor = 1
bar.panel._highlight()
mid_up, mid_down = bar.panel.rows[1].movers
top_up, _ = bar.panel.rows[0].movers
check("panel: arrows appear on the cursor row",
      mid_up.cget("fg") == nb.DIM and mid_down.cget("fg") == nb.DIM,
      f"{mid_up.cget('fg')} {mid_down.cget('fg')}")
check("panel: arrows hidden on other rows",
      top_up.cget("fg") == bar.panel.rows[0].cget("bg"), top_up.cget("fg"))
bar.panel.cursor = 0
bar.panel._highlight()
check("panel: no up arrow at rank 1",
      bar.panel.rows[0].movers[0].cget("fg") == bar.panel.rows[0].cget("bg"))
check("panel: down arrow present at rank 1",
      bar.panel.rows[0].movers[1].cget("fg") == nb.DIM)
bar.panel.cursor = 2
bar.panel._highlight()
check("panel: no down arrow at the last rank",
      bar.panel.rows[2].movers[1].cget("fg") == bar.panel.rows[2].cget("bg"))

# Alt+Up / Alt+Down carry the cursor with the row they move
bar.panel.cursor = 2
top_before = names()[2]
bar.panel._shift_cursor(-1)
bar.root.update()
check("panel: Alt+Up moves the row", names()[1] == top_before, str(names()))
check("panel: the cursor rides along", bar.panel.cursor == 1, str(bar.panel.cursor))
bar.panel._shift_cursor(1)
bar.root.update()
check("panel: Alt+Down puts it back", names()[2] == top_before, str(names()))

# --- drag and drop ----------------------------------------------------------
class Drag:  # stand-in for a tk event; the drag handlers only read y_root
    def __init__(self, y_root):
        self.y_root = y_root


def row_mid(i):
    row = bar.panel.rows[i]
    return row.winfo_rooty() + row.winfo_height() // 2


bar.root.update()
first = names()[0]
bar.panel._press(0, Drag(row_mid(0)))
bar.panel._motion(Drag(row_mid(0) + 1))          # inside the slop: still a click
check("drag: a nudge is not a drag", not bar.panel.drag["moved"])
bar.panel._motion(Drag(row_mid(2) + 4))          # past the last row's midpoint
bar.root.update()                                # place() lands on the idle queue
check("drag: past the slop it drags", bar.panel.drag["moved"])
check("drag: slot is the gap below the last row", bar.panel.drag["slot"] == 3,
      str(bar.panel.drag["slot"]))
check("drag: a drop line is shown", bar.panel.drop_line is not None
      and bar.panel.drop_line.winfo_ismapped())
bar.panel._release(0, Drag(row_mid(2) + 4))
bar.root.update()
check("drag: dropped at the bottom", names()[2] == first, str(names()))
check("drag: cursor follows the drop", bar.panel.cursor == 2, str(bar.panel.cursor))
check("drag: drop line put away", not bar.panel.drop_line.winfo_ismapped()
      if bar.panel.drop_line else True)
check("drag: state cleared", bar.panel.drag is None)
check("drag: the list stays open", bar.panel.is_open)

# Dropping into the gap directly below yourself is where the off-by-one lives:
# it is the same gap you were already in, so it must mean "stay put".
order = names()
below_self = (row_mid(1) + row_mid(2)) // 2       # between the two midpoints
bar.panel._press(1, Drag(row_mid(1)))
bar.panel._motion(Drag(below_self))
check("drag: the gap below self is slot index+1", bar.panel.drag["slot"] == 2,
      str(bar.panel.drag["slot"]))
bar.panel._release(1, Drag(below_self))
bar.root.update()
check("drag: dropping there changes nothing", names() == order, str(names()))

# one gap further down is a real one-slot move
bar.panel._press(1, Drag(row_mid(1)))
bar.panel._motion(Drag(row_mid(2) + 4))
bar.panel._release(1, Drag(row_mid(2) + 4))
bar.root.update()
check("drag: the next gap down moves it one slot",
      names() == [order[0], order[2], order[1]], str(names()))

# a press that never moves is still a click
bar.panel.close(); bar.panel.open(); bar.root.update()
bar.panel._press(1, Drag(row_mid(1)))
bar.panel._release(1, Drag(row_mid(1)))
bar.root.update()
check("drag: a still press activates the row", not bar.panel.is_open and bar.active == 1,
      str(bar.active))

# --- editing an id in the list ---------------------------------------------
bar.panel.open(); bar.root.update()
bar.panel.begin_edit_id(0)
bar.root.update()
check("id edit: an entry replaces the label",
      isinstance(getattr(bar.panel, "id_entry", None), tk.Entry))
check("id edit: prefilled with the current id",
      bar.panel.id_var.get() == bar.tasks[0]["id"], bar.panel.id_var.get())
check("id edit: counts as typing", bar.panel.typing)
bar.panel.id_var.set("MON-99")
bar.panel._commit_id()
bar.root.update()
check("id edit: commits", bar.tasks[0]["id"] == "MON-99", bar.tasks[0]["id"])
check("id edit: leaves edit mode", bar.panel.editing_id == -1 and not bar.panel.typing)
check("id edit: the row shows it",
      bar.panel.rows[0].parts[2].cget("text").strip() == "MON-99",
      bar.panel.rows[0].parts[2].cget("text"))
was = bar.tasks[0]["id"]
bar.panel.begin_edit_id(0)
bar.panel.id_var.set("scrapped")
bar.panel.cancel_id()
bar.root.update()
check("id edit: Escape discards", bar.tasks[0]["id"] == was, bar.tasks[0]["id"])
check("id edit: a second commit is inert", bar.panel._commit_id() is None
      and bar.tasks[0]["id"] == was)

# while a text field is open the list's single-key shortcuts must stand down
n_before = len(bar.tasks)
bar.panel.begin_edit_id(0)
bar.panel._delete_cursor()
bar.panel._toggle_cursor()
bar.panel._move_cursor(1)
check("typing: Delete does not remove a task", len(bar.tasks) == n_before)
check("typing: Space does not toggle a clock", not bar.tasks[0]["running"])
check("typing: Up/Down do not move the cursor", bar.panel.cursor == 0)
bar.panel.cancel_id()

bar.panel.begin_add()
bar.root.update()
bar.panel._delete_cursor()
check("typing: Delete is inert in the add field too", len(bar.tasks) == n_before)

# Sealing a key runs on the widget tag, ahead of the Entry CLASS tag that types
# the character - so anything that edits text must NOT be sealed. Drive these as
# real keystrokes; calling the handlers cannot catch a swallowed keypress.
bar.panel.add_var.set("")
bar.panel.add_entry.focus_set()
for keysym in ("a", "space", "b"):
    bar.panel.add_entry.event_generate(f"<{keysym}>")
bar.root.update()
check("keys: space types a space in the add field",
      bar.panel.add_var.get() == "a b", repr(bar.panel.add_var.get()))
check("keys: space did not toggle a clock", not bar.tasks[bar.panel.cursor]["running"])
bar.panel.add_entry.icursor(1)
bar.panel.add_entry.event_generate("<Delete>")
bar.root.update()
check("keys: Delete edits text in the add field",
      bar.panel.add_var.get() == "ab", repr(bar.panel.add_var.get()))
check("keys: Delete removed no task", len(bar.tasks) == n_before)
bar.panel.cancel_add()

# the same for the id field, plus Enter there must not fall through and activate
bar.panel.begin_edit_id(0)
bar.root.update()
bar.panel.id_var.set("")
bar.panel.id_entry.focus_set()
for keysym in ("X", "space", "Y"):
    bar.panel.id_entry.event_generate(f"<{keysym}>")
bar.root.update()
check("keys: space types in the id field", bar.panel.id_var.get() == "X Y",
      repr(bar.panel.id_var.get()))
was_active = bar.active
bar.panel.id_entry.event_generate("<Return>")
bar.root.update()
check("keys: Enter commits the id", bar.tasks[0]["id"] == "XY", bar.tasks[0]["id"])
check("keys: Enter does not close the list", bar.panel.is_open)
check("keys: Enter does not switch task", bar.active == was_active, str(bar.active))
bar.set_task_id(0, "")

# Enter inside the add field must not also reach the window's "activate row"
# binding, which would close the list and switch tasks.
bar.panel.begin_add()          # every refresh above rebuilt add_entry; re-enter
bar.root.update()
bar.panel.add_var.set("Added by keystroke")
bar.panel.add_entry.event_generate("<Return>")
bar.root.update()
check("typing: Enter adds", bar.tasks[-1]["text"] == "Added by keystroke",
      bar.tasks[-1]["text"])
check("typing: Enter does not close the list", bar.panel.is_open)
check("typing: Enter stays in add mode", bar.panel.adding)
bar.panel.cancel_add()
bar.remove_task(len(bar.tasks) - 1)
bar.panel.close()
bar.root.update()

# --- the menu's move entries track the ends of the list ---------------------
bar._build_menu()


def menu_state(index):
    return str(bar.menu.entrycget(index, "state"))


# _sync_menu, never _show_menu: tk_popup grabs the pointer and does not return.
bar.set_active(0)
bar._sync_menu()
check("menu: Move up disabled at rank 1", menu_state(bar.MOVE_UP_INDEX) == "disabled",
      menu_state(bar.MOVE_UP_INDEX))
check("menu: Move down live at rank 1", menu_state(bar.MOVE_DOWN_INDEX) == "normal")
check("menu: Move up says the rank",
      "rank 1" in bar.menu.entrycget(bar.MOVE_UP_INDEX, "label"),
      bar.menu.entrycget(bar.MOVE_UP_INDEX, "label"))
bar.set_active(len(bar.tasks) - 1)
bar._sync_menu()
check("menu: Move down disabled at the last rank",
      menu_state(bar.MOVE_DOWN_INDEX) == "disabled", menu_state(bar.MOVE_DOWN_INDEX))
last = bar.current["text"]
bar.shift_current(-1)
bar.root.update()
check("menu: Move up shifts the focused task", names()[len(bar.tasks) - 2] == last,
      str(names()))

# --- the footer link -------------------------------------------------------
import focusbar                                   # noqa: E402

bar.panel.open(); bar.root.update()
if focusbar.GITHUB_URL:
    check("link: icon present in the footer", bar.panel.link is not None)
    check("link: uses the link glyph",
          bar.panel.link.cget("text") == bar.icon_link, bar.panel.link.cget("text"))
    check("link: tooltip is the url", focusbar.GITHUB_URL.startswith("http"))
else:
    check("link: hidden when no url is set", bar.panel.link is None)
bar.panel.close()

# only web schemes may be launched
check("link: rejects a local path", nb.open_url(r"C:\Windows\System32\calc.exe") is False)
check("link: rejects a custom scheme", nb.open_url("file:///C:/") is False)
check("link: rejects an empty url", nb.open_url("") is False)

# --- appearance -----------------------------------------------------------
bar.set_opacity(5.0)
check("opacity clamped", bar.opacity == 1.0)
bar.set_opacity(0.4)
check("opacity applied", abs(float(bar.root.attributes("-alpha")) - 0.4) < 0.01)
bar.toggle_click_through(); bar.toggle_click_through()
check("click-through round-trips", not bar.click_through)
bar.toggle_hidden(); bar.root.update()
check("hides", bar.root.state() == "withdrawn")
bar.toggle_hidden(); bar.root.update()
check("shows", bar.root.state() == "normal")

bar._build_menu()
check("PAUSE_INDEX", "Pause" in bar.menu.entrycget(bar.PAUSE_INDEX, "label"))
check("CLICK_THROUGH_INDEX", "Click-through" in bar.menu.entrycget(bar.CLICK_THROUGH_INDEX, "label"))
check("STARTUP_INDEX", "Start with Windows" in bar.menu.entrycget(bar.STARTUP_INDEX, "label"))

bar.root.destroy()
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}"))
sys.exit(1 if fails else 0)


