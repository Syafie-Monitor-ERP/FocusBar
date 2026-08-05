"""The strip: one row per running task, stacked.

This module is the view and the wiring. Every rule about clocks and focus lives
in `store.TaskStore`; the methods here delegate to it and then redraw.
"""

from __future__ import annotations

import queue
import time
import tkinter as tk
import tkinter.font as tkfont

from .panel import TaskListPanel
from .paths import APP_NAME
from .row import BarRow
from .store import TaskStore, load_config, save_config
from .system import open_log, startup_enabled, toggle_startup
from .theme import (ACCENT, AMBER, BAR_HEIGHT, BG, BORDER, BREATH_MS, DOT_FONT,
                    DOT_IDLE, DOT_RUNNING, FG, ICON_FONTS, ICON_LINK, ICON_PAUSE,
                    ICON_PLAY, ICON_SIZE, IDLE_DIM, MAX_WIDTH, MIN_WIDTH, NUDGE,
                    PLACEHOLDER, ROW_HEIGHT, TEXT_LINK, TEXT_PAUSE, TEXT_PLAY,
                    breath_ramp)
from .util import format_elapsed, truncate
from .version import resolve as app_version
from .winapi import (MOD_ALT, MOD_CONTROL, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
                     WS_EX_TRANSPARENT, HotkeyListener, bring_to_front, root_hwnd,
                     round_corners, set_ex_style, virtual_screen)

TICK_MS = 500
PULSE_MS = 280
PULSE_FRAMES = 6


class FocusBar:
    HOTKEY_EDIT, HOTKEY_HIDE, HOTKEY_PAUSE = 1, 2, 3
    HOTKEY_NEXT, HOTKEY_PREV, HOTKEY_LIST, HOTKEY_ADD = 4, 5, 6, 7

    def __init__(self) -> None:
        self.config = load_config()
        self.store = TaskStore(self.config)
        self.opacity: float = float(self.config["opacity"])
        self.nudge_minutes: int = int(self.config["nudge_minutes"])
        self.click_through: bool = bool(self.config["click_through"])

        self.hidden = False
        self.last_nudge = time.monotonic()
        self.editing = False
        self._drag_origin: tuple[int, int] | None = None
        self._drag_moved = False
        self._pulse_left = 0
        self._restore_click_through = False

        self.hotkey_events: queue.Queue[int] = queue.Queue()
        self.panel = TaskListPanel(self)   # before _build_window: rows read it
        self._build_window()
        self._start_hotkeys()
        self.root.after(200, self._tick)
        self.root.after(BREATH_MS, self._breathe)

    # -- model proxies ------------------------------------------------------
    # The panel, the rows and the tests all speak to the bar; these keep that
    # surface intact while the rules themselves live in TaskStore.

    @property
    def tasks(self) -> list[dict]:
        return self.store.tasks

    @property
    def active(self) -> int:
        return self.store.active

    @active.setter
    def active(self, index: int) -> None:
        self.store.active = index

    @property
    def current(self) -> dict | None:
        return self.store.current

    @property
    def paused(self) -> bool:
        return self.store.paused

    def elapsed(self, task: dict) -> float:
        return self.store.elapsed(task)

    def total_elapsed(self) -> float:
        return self.store.total_elapsed()

    def running_tasks(self) -> list[dict]:
        return self.store.running_tasks()

    def visible_tasks(self) -> list[int]:
        return self.store.visible()

    # -- mutations: delegate, then redraw and save --------------------------

    def _changed(self) -> None:
        self._refresh()
        self._persist()

    def set_running(self, index: int, running: bool) -> None:
        self.store.set_running(index, running)
        self.last_nudge = time.monotonic()
        self._changed()

    def toggle_running(self, index: int) -> None:
        if 0 <= index < len(self.tasks):
            self.set_running(index, not self.tasks[index]["running"])

    def toggle_pause(self) -> None:
        """Pause / resume the focused task. Other running tasks are untouched."""
        if self.current:
            self.toggle_running(self.active)

    def stop_all(self) -> None:
        self.store.stop_all()
        self._changed()

    def create_task(self, text: str, activate: bool | None = None) -> int:
        index = self.store.create(text, activate)
        self._changed()
        return index

    def rename_task(self, index: int, text: str) -> None:
        self.store.rename(index, text)
        self._changed()

    def set_active(self, index: int) -> None:
        self.store.set_active(index)
        self.last_nudge = time.monotonic()
        self._changed()

    def cycle(self, delta: int) -> None:
        self.store.cycle(delta)
        self.last_nudge = time.monotonic()
        self._changed()

    def remove_task(self, index: int) -> None:
        self.store.remove(index)
        self._changed()

    def remove_current(self) -> None:
        self.remove_task(self.active)

    # -- construction -------------------------------------------------------

    def _build_window(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.opacity)
        self.root.configure(bg=BG)

        self.frame = tk.Frame(self.root, bg=BG, highlightthickness=1,
                              highlightbackground=BORDER)
        self.frame.pack(fill="both", expand=True)
        self.stack = tk.Frame(self.frame, bg=BG)
        self.stack.pack(fill="both", expand=True)

        self.breath = breath_ramp()
        self._breath_step = 0

        icon_family = next((f for f in ICON_FONTS if f in set(tkfont.families())), None)
        self.icon_family = icon_family or "Segoe UI"
        self.icon_play = ICON_PLAY if icon_family else TEXT_PLAY
        self.icon_pause = ICON_PAUSE if icon_family else TEXT_PAUSE
        self.icon_link = ICON_LINK if icon_family else TEXT_LINK

        self.task_font = tkfont.Font(family="Segoe UI", size=10)
        self.counter_font = tkfont.Font(family="Segoe UI", size=8)

        self.rows: list[tk.Frame] = []
        self.entry_var = tk.StringVar()
        self.entry: tk.Entry | None = None
        self.editing_index = -1

        self._build_menu()
        self._rebuild_rows()

        self.root.update_idletasks()
        self._resize()
        self._place_window()
        self.root.deiconify()
        self.root.update_idletasks()

        hwnd = root_hwnd(self.root)
        set_ex_style(hwnd, WS_EX_TOOLWINDOW, True)
        round_corners(hwnd)
        self._apply_click_through()

        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    def _build_menu(self) -> None:
        self.menu = tk.Menu(self.root, tearoff=0)
        opacity_menu = tk.Menu(self.menu, tearoff=0)
        for pct in (40, 55, 70, 85, 100):
            opacity_menu.add_command(label=f"{pct}%",
                                     command=lambda p=pct: self.set_opacity(p / 100))
        nudge_menu = tk.Menu(self.menu, tearoff=0)
        for minutes in (5, 10, 15, 30, 60, 0):
            nudge_menu.add_command(
                label="Off" if minutes == 0 else f"Every {minutes} min",
                command=lambda m=minutes: self.set_nudge(m),
            )

        # Indices are captured rather than hard-coded so reordering stays safe.
        self.menu.add_command(label="Edit task\tCtrl+Alt+T", command=self.begin_edit)
        self.menu.add_command(label="Add task\tCtrl+Alt+A", command=self.add_task)
        self.menu.add_command(label="Task list\tCtrl+Alt+L", command=self.panel.toggle)
        self.menu.add_separator()
        self.menu.add_command(label="Next task\tCtrl+Alt+N", command=lambda: self.cycle(1))
        self.menu.add_command(label="Previous task\tCtrl+Alt+B", command=lambda: self.cycle(-1))
        self.menu.add_command(label="Remove current task", command=self.remove_current)
        self.menu.add_separator()
        self.menu.add_command(label="Pause\tCtrl+Alt+P", command=self.toggle_pause)
        self.PAUSE_INDEX = self.menu.index("end")
        self.menu.add_command(label="Stop all timers", command=self.stop_all)
        self.STOP_ALL_INDEX = self.menu.index("end")
        self.menu.add_command(label="Hide\tCtrl+Alt+H", command=self.toggle_hidden)
        self.menu.add_separator()
        self.menu.add_cascade(label="Opacity", menu=opacity_menu)
        self.menu.add_cascade(label="Nudge", menu=nudge_menu)
        self.menu.add_command(label="Click-through", command=self.toggle_click_through)
        self.CLICK_THROUGH_INDEX = self.menu.index("end")
        self.menu.add_separator()
        self.menu.add_command(label="Open session log", command=open_log)
        self.menu.add_command(label="Start with Windows", command=toggle_startup)
        self.STARTUP_INDEX = self.menu.index("end")
        self.menu.add_separator()
        self.menu.add_command(label=f"{APP_NAME} {app_version()}", state="disabled")
        self.menu.add_command(label="Quit", command=self.quit)

    def _start_hotkeys(self) -> None:
        mod = MOD_CONTROL | MOD_ALT
        self.hotkeys = HotkeyListener(
            {
                self.HOTKEY_EDIT: (mod, ord("T")),
                self.HOTKEY_HIDE: (mod, ord("H")),
                self.HOTKEY_PAUSE: (mod, ord("P")),
                self.HOTKEY_NEXT: (mod, ord("N")),
                self.HOTKEY_PREV: (mod, ord("B")),
                self.HOTKEY_LIST: (mod, ord("L")),
                self.HOTKEY_ADD: (mod, ord("A")),
            },
            self.hotkey_events,
        )
        self.hotkeys.start()

    # -- the stacked rows ---------------------------------------------------

    def _rebuild_rows(self) -> None:
        self.store.normalize_focus()
        for row in self.rows:
            row.destroy()
        height = self._row_height()
        self.rows = [
            BarRow(self, self.stack, index, position, height)
            for position, index in enumerate(self.visible_tasks())
        ]
        self._resize()

    def _row_height(self) -> int:
        return BAR_HEIGHT if len(self.visible_tasks()) == 1 else ROW_HEIGHT

    def _row_for(self, index: int) -> BarRow | None:
        return next((r for r in self.rows if r.index == index), None)

    # -- geometry -----------------------------------------------------------

    def counter_text(self) -> str:
        return f"{len(self.tasks)} ▾" if self.tasks else ""

    def _bar_height(self) -> int:
        rows = len(self.visible_tasks())
        return BAR_HEIGHT if rows <= 1 else ROW_HEIGHT * rows

    def _resize(self) -> None:
        visible = self.visible_tasks()
        texts = [self.tasks[i]["text"] for i in visible] or [PLACEHOLDER]
        widest = max(self.task_font.measure(t) for t in texts)
        timers = [self.timer_text(self.tasks[i]) for i in visible] or [""]
        widest += max(self.counter_font.measure(t) for t in timers)
        widest += self.counter_font.measure(self.counter_text()) + 108
        width = max(MIN_WIDTH, min(MAX_WIDTH, widest))
        height = self._bar_height()
        if self.root.winfo_ismapped():
            # Always restate the position: a bare "WxH" on an overrideredirect
            # window lets Tk drift it down by the title-bar height on each resize.
            self.root.geometry(
                f"{width}x{height}+{self.root.winfo_x()}+{self.root.winfo_y()}")
        else:
            self.root.geometry(f"{width}x{height}")

    def _place_window(self) -> None:
        self.root.update_idletasks()
        x, y = self.config.get("x"), self.config.get("y")
        if x is None or y is None:
            x = (self.root.winfo_screenwidth() - self.root.winfo_width()) // 2
            y = 8
        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _clamp_to_screen(self, x: int, y: int) -> tuple[int, int]:
        vx, vy, vw, vh = virtual_screen()
        width, height = self.root.winfo_width(), self._bar_height()
        return (max(vx, min(x, vx + vw - width)), max(vy, min(y, vy + vh - height)))

    # -- mouse --------------------------------------------------------------

    def _on_press(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(),
                             event.y_root - self.root.winfo_y())
        self._drag_moved = False

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag_origin:
            return
        dx, dy = self._drag_origin
        x, y = self._clamp_to_screen(event.x_root - dx, event.y_root - dy)
        if abs(x - self.root.winfo_x()) > 2 or abs(y - self.root.winfo_y()) > 2:
            self._drag_moved = True
        self.root.geometry(f"+{x}+{y}")
        if self.panel.is_open:
            self.panel._place()

    def _save_position_if_dragged(self) -> bool:
        self._drag_origin = None
        if not self._drag_moved:
            return False
        self.config["x"] = self.root.winfo_x()
        self.config["y"] = self.root.winfo_y()
        self._persist()
        return True

    def _on_release_text(self, index: int) -> None:
        """Clicking a row's text focuses that task and opens its editor."""
        if self._save_position_if_dragged():
            return
        if not self.tasks:
            self.add_task()
            return
        self.active = index
        self.begin_edit(index)

    def _on_release_button(self, index: int) -> None:
        """Each row's dot starts or stops that row's own timer."""
        if self._save_position_if_dragged():
            return
        if not self.tasks:
            self.add_task()
            return
        self.active = index
        self.toggle_running(index)

    def _on_release_counter(self, _event: tk.Event) -> None:
        if not self._save_position_if_dragged():
            self.panel.toggle()

    def _on_wheel(self, event: tk.Event) -> None:
        self.set_opacity(self.opacity + (0.05 if event.delta > 0 else -0.05))

    # -- live strings the rows ask for --------------------------------------
    # Read at the moment they are shown, never cached onto a widget: the icon
    # and the tooltip have to agree even if the row was not rebuilt.

    def rest_control(self, task: dict) -> tuple[str, str, tuple]:
        """(glyph, colour, font) for a task's start/stop control at rest.

        The single definition, shared by the strip and the list.

        A stopped task shows the play triangle: unambiguous next to an amber rail
        and a "paused" readout, and more inviting than a dot. A running task
        shows a breathing dot instead - paused rows are hidden from the strip, so
        an action-only icon there would be permanently the pause glyph and would
        never change. Hovering always reveals the action; see `action_icon`.
        """
        total = self.elapsed(task)
        if task["running"]:
            return DOT_RUNNING, ACCENT, DOT_FONT
        if total >= 1:
            return self.icon_play, AMBER, (self.icon_family, ICON_SIZE)
        return DOT_IDLE, IDLE_DIM, DOT_FONT

    def action_icon(self, index: int) -> str:
        """The icon for what a click does right now. Pairs with button_hint."""
        return self.icon_pause if self.store.is_running(index) else self.icon_play

    def button_hint(self, index: int) -> str:
        if not (0 <= index < len(self.tasks)):
            return "Add a task  (Ctrl+Alt+A)"
        running = self.store.is_running(index)
        others = len(self.running_tasks()) - (1 if running else 0)
        if running:
            return "Stop this timer" + ("  ·  hides this row" if others else "")
        return "Start this timer"

    def counter_hint(self) -> str:
        """Surface what the strip is NOT showing, so paused work stays findable."""
        hidden = [t["text"] for t in self.tasks if not t["running"]]
        base = f"Task list  ({len(self.tasks)})  ·  Ctrl+Alt+L"
        if not hidden or not self.running_tasks():
            return base
        listed = "\n".join(f"   ○ {truncate(n, 40)}" for n in hidden[:8])
        more = f"\n   … and {len(hidden) - 8} more" if len(hidden) > 8 else ""
        plural = "task" if len(hidden) == 1 else "tasks"
        return f"{base}\n{len(hidden)} paused {plural}, not shown:\n{listed}{more}"

    def _show_menu(self, event: tk.Event) -> None:
        running = len(self.running_tasks())
        self.menu.entryconfigure(
            self.PAUSE_INDEX,
            label="Resume\tCtrl+Alt+P" if self.paused else "Pause\tCtrl+Alt+P")
        self.menu.entryconfigure(
            self.STOP_ALL_INDEX,
            label=f"Stop all timers ({running})" if running else "Stop all timers",
            state="normal" if running else "disabled")
        self.menu.entryconfigure(
            self.CLICK_THROUGH_INDEX,
            label=("✓ " if self.click_through else "") + "Click-through")
        self.menu.entryconfigure(
            self.STARTUP_INDEX,
            label=("✓ " if startup_enabled() else "") + "Start with Windows")
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # -- editing ------------------------------------------------------------

    def add_task(self) -> None:
        """Adding always happens inside the task list, never in the bar."""
        if self.hidden:
            self.toggle_hidden()
        if self.editing:
            self._cancel_edit()
        self.panel.begin_add()

    def begin_edit(self, index: int | None = None) -> None:
        if self.editing:
            return
        if self.hidden:
            self.toggle_hidden()
        if not self.current:
            # Nothing to rename yet - send this to the add flow instead.
            self.add_task()
            return
        index = self.active if index is None else index
        row = self._row_for(index)
        if row is None:                     # focused task is hidden; show it first
            self._rebuild_rows()
            row = self._row_for(index)
            if row is None:
                return
        self.panel.close()

        # Click-through would swallow the keystrokes; drop it for the edit.
        if self.click_through:
            self.click_through = False
            self._apply_click_through()
            self._restore_click_through = True

        self.editing = True
        self.editing_index = index
        row.hide_label()
        self.entry = tk.Entry(
            row.frame, textvariable=self.entry_var, bg=BG, fg=FG, font=self.task_font,
            relief="flat", insertbackground=ACCENT, highlightthickness=0, borderwidth=0)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._commit_edit)
        self.entry.bind("<Escape>", self._cancel_edit)
        self.entry.bind("<FocusOut>", self._commit_edit)
        self.entry_var.set(self.tasks[index]["text"])

        bring_to_front(self.root)
        self.root.focus_force()
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        self.entry.icursor("end")

    def _end_edit(self) -> int:
        index, self.editing_index = self.editing_index, -1
        self.editing = False
        if self.entry is not None:
            self.entry.destroy()
            self.entry = None
        self._refresh()
        if self._restore_click_through:
            self._restore_click_through = False
            self.click_through = True
            self._apply_click_through()
        return index

    def _commit_edit(self, _event: tk.Event | None = None) -> None:
        if not self.editing:
            return
        text = self.entry_var.get().strip()
        index = self._end_edit()
        # The bar's inline editor only ever renames; adding lives in the list.
        if text and 0 <= index < len(self.tasks) and text != self.tasks[index]["text"]:
            self.rename_task(index, text)

    def _cancel_edit(self, _event: tk.Event | None = None) -> None:
        if self.editing:
            self._end_edit()

    # -- appearance / window state ------------------------------------------

    def toggle_hidden(self) -> None:
        self.hidden = not self.hidden
        if self.hidden:
            self.panel.close()
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.attributes("-topmost", True)

    def set_opacity(self, value: float) -> None:
        self.opacity = max(0.2, min(1.0, round(value, 2)))
        self.root.attributes("-alpha", self.opacity)
        if self.panel.is_open:
            self.panel.window.attributes(
                "-alpha", min(1.0, self.opacity + self.panel.ALPHA_BOOST))
        self.config["opacity"] = self.opacity
        self._persist()

    def set_nudge(self, minutes: int) -> None:
        self.nudge_minutes = minutes
        self.last_nudge = time.monotonic()
        self.config["nudge_minutes"] = minutes
        self._persist()

    def toggle_click_through(self) -> None:
        self.click_through = not self.click_through
        self._apply_click_through()
        self.config["click_through"] = self.click_through
        self._persist()

    def _apply_click_through(self) -> None:
        hwnd = root_hwnd(self.root)
        set_ex_style(hwnd, WS_EX_TRANSPARENT, self.click_through)
        set_ex_style(hwnd, WS_EX_NOACTIVATE, self.click_through)

    # -- redraw -------------------------------------------------------------

    def timer_text(self, task: dict | None = None) -> str:
        task = self.current if task is None else task
        if not task:
            return ""
        total = self.elapsed(task)
        if task["running"]:
            return format_elapsed(total)
        # The word is the channel that cannot be misread, so a stopped clock
        # spells out which kind of stopped it is.
        return f"paused · {format_elapsed(total)}" if total >= 1 else "not started"

    def _refresh(self) -> None:
        # Rebuilding while an entry is open would destroy it mid-keystroke.
        if not self.editing:
            self._rebuild_rows()
        if self.panel.is_open:
            self.panel.refresh()
        self._update_times()

    def _update_times(self) -> None:
        for row in self.rows:
            if not (0 <= row.index < len(self.tasks)):
                continue
            task = self.tasks[row.index]
            row.set_time(self.timer_text(task))
            # State can move without a rebuild (the editor suppresses those);
            # resync rather than let a row contradict its own tooltip.
            if task["running"] != row.running:
                row.sync_state(task)

    def _persist(self) -> None:
        self.config.update(self.store.to_config())
        try:
            save_config(self.config)
        except OSError:
            pass

    # -- loop ---------------------------------------------------------------

    def _tick(self) -> None:
        actions = {
            self.HOTKEY_EDIT: self.begin_edit,
            self.HOTKEY_HIDE: self.toggle_hidden,
            self.HOTKEY_PAUSE: self.toggle_pause,
            self.HOTKEY_NEXT: lambda: self.cycle(1),
            self.HOTKEY_PREV: lambda: self.cycle(-1),
            self.HOTKEY_LIST: self.panel.toggle,
            self.HOTKEY_ADD: self.add_task,
        }
        while True:
            try:
                hotkey_id = self.hotkey_events.get_nowait()
            except queue.Empty:
                break
            actions.get(hotkey_id, lambda: None)()

        self._update_times()
        self.panel.update_times()

        # Keep the strip above windows that steal the topmost slot (installers,
        # UAC-adjacent apps, some full-screen tools).
        if not self.hidden and not self.editing:
            self.root.attributes("-topmost", True)

        if (
            self.nudge_minutes
            and self.running_tasks()      # any clock ticking is worth a nudge
            and not self.hidden
            and self._pulse_left == 0
            and time.monotonic() - self.last_nudge >= self.nudge_minutes * 60
        ):
            self.last_nudge = time.monotonic()
            self._pulse_left = PULSE_FRAMES
            self._pulse()

        self.root.after(TICK_MS, self._tick)

    def _pulse(self) -> None:
        """Flash the strip so it pulls your eye back without stealing focus."""
        if self._pulse_left <= 0:
            self.frame.configure(highlightbackground=BORDER)
            self._refresh()
            return
        on = self._pulse_left % 2 == 0
        for row in self.rows:
            row.pulse(on)
        self.frame.configure(highlightbackground=NUDGE if on else BORDER)
        self._pulse_left -= 1
        self.root.after(PULSE_MS, self._pulse)

    def _breathe_step(self) -> None:
        """Advance the glow by one frame on every running row.

        Motion is the one signal that survives peripheral vision, so a running
        timer is never mistaken for a stopped one. Stopped rows stay still - and
        normally are not on the strip at all.
        """
        if self._pulse_left or self.hidden:
            return
        self._breath_step = (self._breath_step + 1) % len(self.breath)
        colour = self.breath[self._breath_step]
        for row in self.rows:
            row.breathe(colour)
        self.panel.breathe(colour)                       # keep the list in step

    def _breathe(self) -> None:
        self._breathe_step()
        self.root.after(BREATH_MS, self._breathe)

    # -- lifecycle ----------------------------------------------------------

    def quit(self) -> None:
        self.store.bank_for_exit()
        self._persist()
        self.panel.close()
        self.hotkeys.stop()
        self.root.destroy()

    def run(self) -> None:
        self._refresh()
        self.root.mainloop()
