"""Small pure helpers. No Tk, no Win32, no state."""

from __future__ import annotations

import re

ID_LENGTH = 3       # characters in a generated id
ID_MAX = 12         # characters a hand-typed one may keep
ID_FALLBACK = "TSK"


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    if total < 3600:
        return f"{total // 60}m"
    return f"{total // 3600}h{(total % 3600) // 60:02d}"


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def initials(text: str) -> str:
    """A mnemonic id for a task: the first letters of its first words.

    "Refactor the export path" -> "RTE". Every word counts, including short ones,
    because dropping "the" would make the code harder to derive by eye than to
    look up - and the point of an initials id is that you can guess it.

    Names with fewer than `ID_LENGTH` words are padded from the tail of the last
    word ("Fix CSV" -> "FCS", "Email" -> "EMA") so codes stay a uniform width.
    """
    words = [w for w in re.split(r"[^0-9A-Za-z]+", text) if w]
    if not words:
        return ID_FALLBACK
    code = "".join(word[0] for word in words[:ID_LENGTH])
    if len(code) < ID_LENGTH:
        code += words[-1][1 : 1 + ID_LENGTH - len(code)]
    return code.upper()


def clean_id(text: str) -> str:
    """Normalise a hand-typed id: no whitespace, bounded length."""
    return "".join(str(text).split())[:ID_MAX]


def unique_id(base: str, taken) -> str:
    """`base` if free, else the first of `base2`, `base3`, ... that is.

    Comparison is case-insensitive: two tasks labelled "rte" and "RTE" would be
    indistinguishable at a glance, which is the whole thing an id exists to avoid.
    """
    seen = {t.casefold() for t in taken}
    if base.casefold() not in seen:
        return base
    for n in range(2, 1000):
        suffix = str(n)
        candidate = base[: ID_MAX - len(suffix)] + suffix
        if candidate.casefold() not in seen:
            return candidate
    return base


def lerp_color(start: str, end: str, t: float) -> str:
    """Blend two #rrggbb colours; t=0 gives start, t=1 gives end."""
    a = [int(start[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(end[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))
