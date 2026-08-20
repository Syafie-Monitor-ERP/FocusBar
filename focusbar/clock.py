"""The clock every timer in FocusBar runs on. No Tk, no state.

`time.monotonic()` is the obvious choice and the wrong one here. On Windows it
is *biased*: it keeps advancing while the machine is suspended, so leaving a
task running overnight banks the sleep as eight hours of work. (Python 3.13+
maps it to QueryPerformanceCounter and older versions to GetTickCount64 - both
count suspended time, so the version makes no difference.)

Windows exposes the unbiased counter for exactly this case, and time-on-task is
exactly what it is for: sleep and hibernate stop the clock, a locked screen does
not. Its resolution is the system timer tick (~15.6 ms), which is ample for a
readout that counts in minutes.

Elsewhere the counter is unavailable, `time.monotonic()` is the fallback - on
Linux and macOS it already excludes suspend, so the semantics match.
"""

from __future__ import annotations

import ctypes
import time

_query_unbiased = None
try:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.QueryUnbiasedInterruptTime.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
    _kernel32.QueryUnbiasedInterruptTime.restype = ctypes.c_int
    # Probe rather than trust the lookup: a stub that fails at call time would
    # otherwise turn every elapsed() into a garbage figure.
    _probe = ctypes.c_ulonglong()
    if _kernel32.QueryUnbiasedInterruptTime(ctypes.byref(_probe)) and _probe.value:
        _query_unbiased = _kernel32.QueryUnbiasedInterruptTime
except (AttributeError, OSError):
    _query_unbiased = None


def awake() -> float:
    """Monotonic seconds of machine-awake time. Suspended time is not counted.

    Only differences between two readings mean anything; the origin is boot.
    """
    if _query_unbiased is None:
        return time.monotonic()
    value = ctypes.c_ulonglong()
    _query_unbiased(ctypes.byref(value))
    return value.value / 1e7          # 100-nanosecond units


COUNTS_SLEEP = _query_unbiased is None
"""True when the fallback is in use, i.e. suspended time may be counted."""
