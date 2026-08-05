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

    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        "$s.TargetPath = '{exe}';"
        "$s.Arguments = '\"{target}\"';"
        "$s.WorkingDirectory = '{cwd}';"
        "$s.Save()"
    ).format(link=link, exe=pythonw, target=ENTRY_SCRIPT, cwd=PROJECT_DIR)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    return startup_enabled()
