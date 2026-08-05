"""Small pure helpers. No Tk, no Win32, no state."""

from __future__ import annotations


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    if total < 3600:
        return f"{total // 60}m"
    return f"{total // 3600}h{(total % 3600) // 60:02d}"


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def lerp_color(start: str, end: str, t: float) -> str:
    """Blend two #rrggbb colours; t=0 gives start, t=1 gives end."""
    a = [int(start[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(end[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))
