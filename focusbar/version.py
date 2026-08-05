"""The version number, derived rather than typed.

A git tag is the only place a version is authored. Two facts follow from that: a
packaged .exe has no git and no repository to interrogate, and a working checkout
has no tag of its own until one is cut. So there are two sources, tried in order.

`STAMPED` is rewritten by `.github/workflows/release.yml` from the tag that
triggered the build, just before PyInstaller runs. It stays empty in the
repository on purpose — committing a number here would recreate the very thing
the tag is meant to replace, a second place to keep it up to date.
"""

from __future__ import annotations

import subprocess
import sys

from .paths import PROJECT_DIR

# Rewritten at package time. Do not edit by hand; tag a release instead.
STAMPED = ""

_CREATE_NO_WINDOW = 0x08000000


def _from_git() -> str:
    """`git describe` on the checkout, or `""` if that can't be answered.

    Yields `0.0.1` on a tagged commit and `0.0.1-4-gc3dfa40` four commits later,
    which is enough to identify a dev build from a screenshot. Every failure mode
    — git absent, not a checkout, subprocess hanging — collapses to `""` so a
    missing version can never stop the app from starting.
    """
    try:
        done = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            creationflags=_CREATE_NO_WINDOW,  # no console flash under pythonw
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip().lstrip("v")


def resolve() -> str:
    """The version to show the user."""
    if STAMPED:
        return STAMPED
    if getattr(sys, "frozen", False):
        # A packaged build that somehow missed its stamp. Say so rather than
        # invent a number, and don't shell out to git from an install directory.
        return "unknown"
    return _from_git() or "dev"
