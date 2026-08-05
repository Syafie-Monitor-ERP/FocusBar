"""Delayed hover hint, in its own borderless window."""

from __future__ import annotations

import tkinter as tk

from .theme import BORDER, FG


class Tooltip:
    """Hint window shown under a widget on hover."""

    DELAY_MS = 500
    BG = "#161a24"

    def __init__(self, widget: tk.Widget):
        self.widget = widget
        self.window: tk.Toplevel | None = None
        self.after_id: str | None = None

    def show(self, text: str) -> None:
        self.hide()
        self.after_id = self.widget.after(self.DELAY_MS, lambda: self._render(text))

    def _render(self, text: str) -> None:
        self.after_id = None
        try:
            self.window = tk.Toplevel(self.widget)
            self.window.overrideredirect(True)
            self.window.attributes("-topmost", True)
            self.window.configure(bg=BORDER)
            tk.Label(
                self.window, text=text, bg=self.BG, fg=FG,
                font=("Segoe UI", 8), padx=7, pady=3,
            ).pack(padx=1, pady=1)
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.window.geometry(f"+{x}+{y}")
        except tk.TclError:
            self.window = None

    def hide(self) -> None:
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
