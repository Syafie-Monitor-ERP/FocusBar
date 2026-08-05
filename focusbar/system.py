"""OS integrations: opening the session log and the Startup shortcut."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

from .paths import APP_NAME, ENTRY_SCRIPT, PROJECT_DIR
from .store import ensure_log

CREATE_NO_WINDOW = 0x08000000


def open_log() -> None:
    os.startfile(ensure_log())  # noqa: S606 - opening the user's own log file


def open_url(url: str) -> bool:
    """Open a web link in the default browser. Web schemes only.

    Refusing anything but http/https keeps a hand-edited or mistyped link from
    launching a local program.
    """
    if not url.startswith(("http://", "https://")):
        return False
    webbrowser.open(url)
    return True


def shortcut_path() -> str:
    startup = os.path.join(
        os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup"
    )
    return os.path.join(startup, f"{APP_NAME}.lnk")


def startup_enabled() -> bool:
    return os.path.exists(shortcut_path())


def toggle_startup() -> bool:
    """Add or remove the Startup shortcut. Returns the new state."""
    link = shortcut_path()
    if startup_enabled():
        try:
            os.remove(link)
        except OSError:
            pass
        return False

    if getattr(sys, "frozen", False):
        # A packaged build points the shortcut at the .exe itself, with no
        # arguments: ENTRY_SCRIPT then lives in a temp unpack directory that is
        # gone by the next login.
        exe = sys.executable
        arguments = ""
        cwd = os.path.dirname(sys.executable)
    else:
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(exe):
            exe = sys.executable
        arguments = "$s.Arguments = '\"{}\"';".format(ENTRY_SCRIPT)
        cwd = PROJECT_DIR

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        "$s.TargetPath = '{exe}';"
        "{arguments}"
        "$s.WorkingDirectory = '{cwd}';"
        "$s.Save()"
    ).format(link=link, exe=exe, arguments=arguments, cwd=cwd)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    return startup_enabled()
