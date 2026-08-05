"""The drop-down task list anchored under the strip.

Rows are keyboard-navigable (Up/Down/Enter/Space/Delete) as well as clickable, so
switching or starting a task never requires leaving the keyboard.
"""

from __future__ import annotations

import tkinter as tk

from . import GITHUB_URL
from .system import open_url
from .theme import (ACCENT, BORDER, DIM, FG, FLASH_BG, HOVER_BG, IDLE_DIM, IDLE_FG,
                    NUDGE, PANEL_BG, RAIL_WIDTH, ROW_TEXT, RUNNING_BG)
from .tooltip import Tooltip
from .util import format_elapsed, truncate
from .winapi import (WS_EX_TOOLWINDOW, bring_to_front, root_hwnd, round_corners,
                     set_ex_style)


class TaskListPanel:
    ROW_FONT = ("Segoe UI", 9)
    FLASH_MS = 650
    ALPHA_BOOST = 0.18          # the list sits slightly more solid than the strip

    def __init__(self, bar):
        self.bar = bar
        self.window: tk.Toplevel | None = None
        self.cursor = 0
        self.rows: list[tk.Frame] = []
        self.adding = False
        self.add_var: tk.StringVar | None = None
        self._had_focus = False

    @property
    def store(self):
        return self.bar.store

    @property
    def is_open(self) -> bool:
        return self.window is not None

    # -- window -------------------------------------------------------------

    def toggle(self) -> None:
        self.close() if self.is_open else self.open()

    def focus_window(self) -> None:
        if self.window:
            bring_to_front(self.window)
            self.window.focus_force()

    def open(self) -> None:
        if self.is_open:
            return
        self.cursor = max(0, self.store.active)
        self.adding = False
        self._had_focus = False
        self.add_var = tk.StringVar(master=self.bar.root, value="")
        self.window = tk.Toplevel(self.bar.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", min(1.0, self.bar.opacity + self.ALPHA_BOOST))
        self.window.configure(bg=BORDER)

        self.body = tk.Frame(self.window, bg=PANEL_BG)
        self.body.pack(padx=1, pady=1, fill="both", expand=True)

        self.window.bind("<Escape>", lambda _e: self.close())
        self.window.bind("<Up>", lambda _e: self._move_cursor(-1))
        self.window.bind("<Down>", lambda _e: self._move_cursor(1))
        self.window.bind("<Return>", lambda _e: self._activate_cursor())
        self.window.bind("<space>", lambda _e: self._toggle_cursor())
        self.window.bind("<Delete>", lambda _e: self._delete_cursor())
        self.window.bind("<FocusIn>", self._on_focus_in)
        self.window.bind("<FocusOut>", self._on_focus_out)

        self.refresh()
        self._place()
        set_ex_style(root_hwnd(self.window), WS_EX_TOOLWINDOW, True)
        round_corners(root_hwnd(self.window))
        self.focus_window()

    def close(self) -> None:
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
            self.rows = []
            self.adding = False

    def _on_focus_in(self, _event: tk.Event) -> None:
        self._had_focus = True

    def _on_focus_out(self, _event: tk.Event) -> None:
        # Ignore focus bouncing between the panel and its own child rows.
        self.window.after(80, self._close_if_unfocused) if self.window else None

    def _close_if_unfocused(self) -> None:
        # Only arm the click-away watchdog once the panel has actually held
        # focus. Windows refuses SetForegroundWindow to background processes,
        # and without this guard the panel closed the instant it opened.
        if self._had_focus and self.window and not self.window.focus_displayof():
            self.close()

    def _place(self) -> None:
        if not self.window:
            return
        self.window.update_idletasks()
        root = self.bar.root
        width = max(root.winfo_width(), self.window.winfo_reqwidth())
        height = self.window.winfo_reqheight()
        x, y = root.winfo_x(), root.winfo_y() + root.winfo_height() + 4
        if y + height > root.winfo_screenheight():      # flip above the bar
            y = max(0, root.winfo_y() - height - 4)
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    # -- contents -----------------------------------------------------------

    def refresh(self) -> None:
        if not self.window:
            return
        for child in self.body.winfo_children():
            child.destroy()
        self.rows = []

        if not self.store.tasks:
            tk.Label(
                self.body, text="No tasks yet", bg=PANEL_BG, fg=DIM,
                font=self.ROW_FONT, padx=12, pady=8, anchor="w",
            ).pack(fill="x")

        for index, task in enumerate(self.store.tasks):
            self.rows.append(self._build_row(index, task))

        tk.Frame(self.body, bg=BORDER, height=1).pack(fill="x", pady=(3, 0))
        self._build_add_area()

        self._highlight()
        self._place()

    def _row_style(self, task: dict, focused: bool):
        """(glyph, colour, font, time text, time colour, text colour) per state."""
        total = self.store.elapsed(task)
        glyph, colour, font = self.bar.rest_control(task)   # one shared definition
        if task["running"]:
            # Always print the time, even "0m": an occupied time column is itself
            # a signal that this row is live, where an empty one reads as inert.
            return glyph, colour, font, format_elapsed(total), ACCENT, FG
        if total >= 1:
            return (glyph, colour, font, format_elapsed(total), DIM,
                    FG if focused else ROW_TEXT)
        return glyph, colour, font, "—", IDLE_DIM, FG if focused else IDLE_FG

    def _row_bg(self, index: int, running: bool) -> str:
        if index == self.cursor:
            return HOVER_BG
        return RUNNING_BG if running else PANEL_BG

    def _build_row(self, index: int, task: dict) -> tk.Frame:
        focused = index == self.store.active
        running = task["running"]
        row = tk.Frame(self.body, bg=PANEL_BG, cursor="hand2")
        row.pack(fill="x")

        # A thin accent edge marks which row the bar is showing. It is a separate
        # signal from the dot, because focus and running are separate things: the
        # bar can display a stopped task while other tasks tick away.
        focus_edge = tk.Frame(row, bg=ACCENT if focused else PANEL_BG, width=RAIL_WIDTH)
        focus_edge.pack(side="left", fill="y")
        focus_edge.pack_propagate(False)
        row.focus_edge = focus_edge if not focused else None  # type: ignore[attr-defined]

        glyph, dot_fg, dot_font, time_text, time_fg, text_fg = self._row_style(task, focused)
        bg = self._row_bg(index, running)

        dot = tk.Label(row, text=glyph, bg=bg, fg=dot_fg, font=dot_font,
                       padx=9, pady=5, cursor="hand2")
        dot.pack(side="left")
        time_label = tk.Label(row, text=time_text, bg=bg, fg=time_fg,
                              font=("Segoe UI", 8), padx=8)
        time_label.pack(side="right")
        remove = tk.Label(row, text="✕", bg=bg, fg=bg, font=("Segoe UI", 8),
                          padx=8, cursor="hand2")
        remove.pack(side="right")
        text = tk.Label(row, text=truncate(task["text"], 52), bg=bg, fg=text_fg,
                        font=self.ROW_FONT, anchor="w")
        text.pack(side="left", fill="x", expand=True)
        row.configure(bg=bg)
        focus_edge.configure(bg=ACCENT if focused else bg)

        row.parts = (dot, text, time_label, remove)  # type: ignore[attr-defined]
        row.time_label = time_label                  # type: ignore[attr-defined]
        row.dot = dot                                # type: ignore[attr-defined]
        row.index = index                            # type: ignore[attr-defined]
        row.running = running                        # type: ignore[attr-defined]

        def enter(_e=None):
            self.cursor = index
            self._highlight()

        for widget in (row, text, time_label):
            widget.bind("<Enter>", enter)
            widget.bind("<Button-1>", lambda _e, i=index: self._activate(i))
        # The dot is its own control: it starts or stops just this task, leaving
        # focus and every other task alone. That is how several run at once.
        dot.tip = Tooltip(dot)                       # type: ignore[attr-defined]
        dot.bind("<Enter>", lambda _e, i=index: (enter(), dot.tip.show(self._dot_hint(i))))
        dot.bind("<Leave>", lambda _e: dot.tip.hide())
        dot.bind("<Button-1>", lambda _e, i=index: self._toggle_run(i))
        remove.bind("<Enter>", lambda _e: (enter(), remove.configure(fg=NUDGE)))
        remove.bind("<Leave>", lambda _e: remove.configure(fg=DIM))
        remove.bind("<Button-1>", lambda _e, i=index: self._delete(i))
        return row

    def _dot_hint(self, index: int) -> str:
        """Read live state, so the hint can never disagree with the dot."""
        if self.store.is_running(index):
            return "Stop this timer"
        return "Start this timer  ·  runs alongside"

    def _build_add_area(self) -> None:
        """The add affordance stays inside the list.

        Typing in place - list still on screen, running timers untouched - reads
        as an addition. Closing the panel and blanking the bar would read as a
        reset instead.
        """
        if not self.adding:
            footer = tk.Frame(self.body, bg=PANEL_BG)
            footer.pack(fill="x")
            add = tk.Label(
                footer, text="＋  Add task", bg=PANEL_BG, fg=DIM,
                font=self.ROW_FONT, padx=12, pady=6, anchor="w", cursor="hand2",
            )
            add.pack(side="left", fill="x", expand=True)

            def add_hover(entering):
                bg = HOVER_BG if entering else PANEL_BG
                footer.configure(bg=bg)
                add.configure(bg=bg, fg=FG if entering else DIM)

            add.bind("<Enter>", lambda _e: add_hover(True))
            add.bind("<Leave>", lambda _e: add_hover(False))
            add.bind("<Button-1>", lambda _e: self.begin_add())
            self._build_link(footer, add_hover)
            return

        row = tk.Frame(self.body, bg=HOVER_BG)
        row.pack(fill="x")
        tk.Label(row, text="＋", bg=HOVER_BG, fg=ACCENT, font=("Segoe UI", 8),
                 padx=10, pady=6).pack(side="left")
        tk.Label(row, text="Enter adds  ·  Ctrl+Enter adds and starts", bg=HOVER_BG,
                 fg=DIM, font=("Segoe UI", 7), padx=10).pack(side="right")
        entry = tk.Entry(
            row, textvariable=self.add_var, bg=HOVER_BG, fg=FG, font=self.ROW_FONT,
            relief="flat", insertbackground=ACCENT, highlightthickness=0, borderwidth=0,
        )
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self._commit_add(start=False))
        entry.bind("<Control-Return>", lambda _e: self._commit_add(start=True))
        entry.bind("<Escape>", lambda _e: self.cancel_add())
        entry.focus_set()
        entry.icursor("end")
        self.add_entry = entry

    def _build_link(self, footer: tk.Frame, add_hover) -> None:
        """Small link icon in the footer corner. Hidden when no URL is set."""
        if not GITHUB_URL:
            self.link = None
            return
        link = tk.Label(
            footer, text=self.bar.icon_link, bg=PANEL_BG, fg=IDLE_DIM,
            font=(self.bar.icon_family, 9), padx=12, cursor="hand2",
        )
        link.pack(side="right")
        link.tip = Tooltip(link)                     # type: ignore[attr-defined]

        def hover(entering):
            # Cancel the footer's own hover so the two do not fight over the row.
            add_hover(False)
            link.configure(bg=HOVER_BG if entering else PANEL_BG,
                           fg=ACCENT if entering else IDLE_DIM)
            link.tip.show(GITHUB_URL) if entering else link.tip.hide()

        link.bind("<Enter>", lambda _e: hover(True))
        link.bind("<Leave>", lambda _e: hover(False))
        link.bind("<Button-1>", lambda _e: open_url(GITHUB_URL))
        self.link = link

    # -- adding -------------------------------------------------------------

    def begin_add(self) -> None:
        if not self.is_open:
            self.open()
        self.adding = True
        if self.add_var is not None:
            self.add_var.set("")
        self.refresh()
        self.focus_window()
        if getattr(self, "add_entry", None):
            self.add_entry.focus_set()

    def cancel_add(self) -> None:
        self.adding = False
        if self.add_var is not None:
            self.add_var.set("")
        self.refresh()

    def _commit_add(self, start: bool) -> None:
        text = (self.add_var.get() if self.add_var else "").strip()
        if not text:
            self.cancel_add()
            return
        index = self.bar.create_task(text, activate=start)
        self.add_var.set("")
        if start:
            self.close()
            return
        # Stay in add mode so several tasks can be typed in one go.
        self.cursor = index
        self.refresh()
        self._flash(index)

    # -- live updates -------------------------------------------------------

    def breathe(self, colour: str) -> None:
        """Pulse the running dots in step with the strip's rails."""
        for row in self.rows:
            if row.running:                              # type: ignore[attr-defined]
                row.dot.configure(fg=colour)             # type: ignore[attr-defined]

    def update_times(self) -> None:
        """Tick the per-row clocks without rebuilding the panel."""
        if not self.window:
            return
        for row in self.rows:
            index = row.index                        # type: ignore[attr-defined]
            if not (0 <= index < len(self.store.tasks)):
                continue
            task = self.store.tasks[index]
            *_, time_text, time_fg, _ = self._row_style(task, index == self.store.active)
            row.time_label.configure(text=time_text, fg=time_fg)  # type: ignore[attr-defined]

    def _highlight(self) -> None:
        for row in self.rows:
            index = row.index                            # type: ignore[attr-defined]
            selected = index == self.cursor
            bg = self._row_bg(index, row.running)        # type: ignore[attr-defined]
            row.configure(bg=bg)
            dot, text, time_label, remove = row.parts    # type: ignore[attr-defined]
            for widget in (dot, text, time_label, remove):
                widget.configure(bg=bg)
            # The focused row's accent edge stays put; unfocused edges blend in.
            if row.focus_edge is not None:               # type: ignore[attr-defined]
                row.focus_edge.configure(bg=bg)          # type: ignore[attr-defined]
            remove.configure(fg=DIM if selected else bg)

    def _flash(self, index: int) -> None:
        """Briefly light up a freshly added row so the addition is visible."""
        if not self.window or not (0 <= index < len(self.rows)):
            return
        row = self.rows[index]
        for widget in (row, *row.parts):                 # type: ignore[attr-defined]
            widget.configure(bg=FLASH_BG)
        self.window.after(self.FLASH_MS, self._highlight)

    # -- actions ------------------------------------------------------------

    def _move_cursor(self, delta: int) -> None:
        if not self.rows:
            return
        self.cursor = (self.cursor + delta) % len(self.rows)
        self._highlight()

    def _toggle_run(self, index: int) -> None:
        self.bar.toggle_running(index)
        self.refresh()

    def _toggle_cursor(self) -> None:
        if self.rows and not self.adding:
            self._toggle_run(self.cursor)

    def _activate_cursor(self) -> None:
        if self.rows:
            self._activate(self.cursor)

    def _delete_cursor(self) -> None:
        if self.rows:
            self._delete(self.cursor)

    def _activate(self, index: int) -> None:
        self.close()
        self.bar.set_active(index)

    def _delete(self, index: int) -> None:
        self.bar.remove_task(index)
        if not self.store.tasks:
            self.close()
            return
        self.cursor = min(self.cursor, len(self.store.tasks) - 1)
        self.refresh()
