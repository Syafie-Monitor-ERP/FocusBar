"""One row of the strip.

A row owns its widgets, its hover swap and its state sync. The bar keeps only
layout, hit-handling and the model.
"""

from __future__ import annotations

import tkinter as tk

from .theme import (ACCENT, AMBER, BG, BORDER, DIM, FG, HOVER_BG, ICON_SIZE,
                    NUDGE, RAIL_WIDTH, STACK_TEXT)
from .tooltip import Tooltip


class BarRow:
    """`[rail] [state dot / play button] task text .... timer [chevron]`"""

    CHEVRON_SLOT = 5      # in characters; identical on every row so timers align

    def __init__(self, bar, parent: tk.Misc, index: int, position: int, height: int):
        self.bar = bar
        self.index = index
        self.first = position == 0
        task = bar.tasks[index]
        self.running = task["running"]
        self.hovering = False

        self.frame = tk.Frame(parent, bg=BG, height=height)
        self.frame.pack(fill="x")
        self.frame.pack_propagate(False)
        if position:
            tk.Frame(parent, bg=BORDER, height=1).place(
                in_=self.frame, x=0, y=0, relwidth=1.0, anchor="nw")

        self.rail = tk.Frame(self.frame, bg=ACCENT if self.running else AMBER,
                             width=RAIL_WIDTH)
        self.rail.pack(side="left", fill="y")
        self.rail.pack_propagate(False)

        # Running -> a breathing dot; stopped -> a play triangle you can press.
        # Hovering always shows the action. See FocusBar.rest_control().
        glyph, colour, font = bar.rest_control(task)
        self._rest_text, self._rest_fg, self._rest_font = glyph, colour, font
        self.button = tk.Label(self.frame, text=glyph, bg=BG, fg=colour,
                               font=font, padx=7, cursor="hand2")
        self.button.pack(side="left", padx=(4, 2))

        # A same-width slot on every row keeps the timers vertically aligned even
        # though only the first row carries the task-list chevron.
        self.chevron = tk.Label(
            self.frame, text=bar.counter_text() if self.first else "", bg=BG, fg=DIM,
            font=bar.counter_font, padx=6, width=self.CHEVRON_SLOT,
            cursor="hand2" if self.first else "arrow")
        self.chevron.pack(side="right")

        self.timer = tk.Label(self.frame, text=bar.timer_text(task), bg=BG,
                              fg=DIM if self.running else AMBER,
                              font=("Segoe UI", 9 if self.running else 8))
        self.timer.pack(side="right", padx=(6, 2))

        self.label = tk.Label(self.frame, text=task["text"], bg=BG,
                              fg=FG if index == bar.active else STACK_TEXT,
                              font=bar.task_font, anchor="w")
        self.label.pack(side="left", fill="x", expand=True)

        self.tip = Tooltip(self.button)
        self.chevron_tip = Tooltip(self.chevron)
        self._bind()

    # -- wiring -------------------------------------------------------------

    def _bind(self) -> None:
        bar, index = self.bar, self.index
        for widget in (self.frame, self.label, self.timer, self.button,
                       self.chevron, self.rail):
            widget.bind("<ButtonPress-1>", bar._on_press)
            widget.bind("<B1-Motion>", bar._on_drag)
            widget.bind("<Button-3>", bar._show_menu)
            widget.bind("<MouseWheel>", bar._on_wheel)
        # Everything hangs off release so a drag from any part moves the window.
        self.button.bind("<ButtonRelease-1>", lambda _e: bar._on_release_button(index))
        for widget in (self.frame, self.label, self.timer, self.rail):
            widget.bind("<ButtonRelease-1>", lambda _e: bar._on_release_text(index))
        self.button.bind("<Enter>", lambda _e: self.hover(True))
        self.button.bind("<Leave>", lambda _e: self.hover(False))
        if self.first:
            self.chevron.bind("<ButtonRelease-1>", bar._on_release_counter)
            self.chevron.bind("<Enter>", lambda _e: self.hover_chevron(True))
            self.chevron.bind("<Leave>", lambda _e: self.hover_chevron(False))

    # -- hover --------------------------------------------------------------

    def hover(self, entering: bool) -> None:
        """Show the action icon under the cursor.

        Both the icon and the tooltip are derived from live state here, never
        cached onto the widget, so they cannot disagree.
        """
        self.hovering = entering
        self.button.configure(bg=HOVER_BG if entering else BG)
        if entering:
            self.button.configure(text=self.bar.action_icon(self.index),
                                  font=(self.bar.icon_family, ICON_SIZE), fg=FG)
            self.tip.show(self.bar.button_hint(self.index))
        else:
            self.button.configure(text=self._rest_text, font=self._rest_font,
                                  fg=self._rest_fg)
            self.tip.hide()

    def hover_chevron(self, entering: bool) -> None:
        self.chevron.configure(bg=HOVER_BG if entering else BG)
        self.chevron_tip.show(self.bar.counter_hint()) if entering else self.chevron_tip.hide()

    # -- live updates -------------------------------------------------------

    def set_time(self, text: str) -> None:
        self.timer.configure(text=text)

    def sync_state(self, task: dict) -> None:
        """Adopt a running/stopped change that happened without a rebuild."""
        self.running = task["running"]
        glyph, colour, font = self.bar.rest_control(task)
        self._rest_text, self._rest_fg, self._rest_font = glyph, colour, font
        self.rail.configure(bg=ACCENT if self.running else AMBER)
        if self.hovering:
            self.button.configure(text=self.bar.action_icon(self.index),
                                  font=(self.bar.icon_family, ICON_SIZE))
        else:
            self.button.configure(text=glyph, font=font, fg=colour)

    def breathe(self, colour: str) -> None:
        if not self.running:
            return
        self.rail.configure(bg=colour)
        if not self.hovering:          # never fight the hover swap
            self.button.configure(fg=colour)
            self._rest_fg = colour

    def pulse(self, on: bool) -> None:
        if not self.running:
            return
        self.label.configure(fg=NUDGE if on else FG)
        self.rail.configure(bg=NUDGE if on else ACCENT)

    # -- editing / teardown --------------------------------------------------

    def hide_label(self) -> None:
        self.label.pack_forget()

    def destroy(self) -> None:
        self.tip.hide()
        self.chevron_tip.hide()
        self.frame.destroy()
