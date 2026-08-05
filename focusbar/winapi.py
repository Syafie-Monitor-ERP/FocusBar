"""ctypes bindings and the window tricks the overlay depends on.

Every helper here exists because of a specific Win32 behaviour; see CODEBASE.md
"Win32 gotchas" before changing any of it.
"""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes

import tkinter as tk

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GA_ROOT = 2
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

# Virtual-screen metrics, for clamping the strip onto a real monitor.
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

user32.GetWindowLongPtrW.restype = ctypes.c_longlong
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_longlong
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]


def root_hwnd(widget: tk.Misc) -> int:
    """Real top-level HWND for a tkinter widget.

    winfo_id() is not always the top level, so go through GetAncestor.
    """
    return user32.GetAncestor(wintypes.HWND(widget.winfo_id()), GA_ROOT)


def set_ex_style(hwnd: int, flag: int, enabled: bool) -> None:
    style = user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE)
    style = (style | flag) if enabled else (style & ~flag)
    user32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)


def round_corners(hwnd: int) -> None:
    """Windows 11 rounded corners. Silently no-ops on Windows 10."""
    try:
        pref = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )
    except OSError:
        pass


def bring_to_front(widget: tk.Misc) -> None:
    """Best-effort foreground. Windows refuses this to background processes."""
    user32.SetForegroundWindow(wintypes.HWND(root_hwnd(widget)))


def virtual_screen() -> tuple[int, int, int, int]:
    """(x, y, width, height) spanning every monitor."""
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


class HotkeyListener(threading.Thread):
    """Registers global hotkeys and pumps their messages on its own thread.

    RegisterHotKey delivers WM_HOTKEY to the registering thread's queue, so the
    message loop has to live here rather than in tkinter's mainloop. Results
    reach Tk through the queue - never call Tk from this thread.
    """

    def __init__(self, bindings: dict[int, tuple[int, int]], sink: queue.Queue):
        super().__init__(daemon=True)
        self.bindings = bindings
        self.sink = sink
        self.thread_id: int | None = None
        self.failed: list[int] = []

    def run(self) -> None:
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        for hotkey_id, (mods, vk) in self.bindings.items():
            if not user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk):
                self.failed.append(hotkey_id)

        msg = wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                self.sink.put(int(msg.wParam))

        for hotkey_id in self.bindings:
            user32.UnregisterHotKey(None, hotkey_id)

    def stop(self) -> None:
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
