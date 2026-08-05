"""Persistence and the task-timing model. No Tk anywhere in this module.

`TaskStore` owns every rule about clocks and focus. Keeping it free of widgets
means the subtle parts - the auto/explicit distinction, banking time on stop,
what the strip is allowed to show - can be reasoned about and tested on their
own, and the view layer only has to redraw.
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime

from .paths import CONFIG_PATH, DATA_DIR, LOG_PATH

MAX_TASKS = 40
MIN_LOGGED_SECONDS = 30      # shorter stretches are typos, not work

DEFAULTS = {
    # Each task carries its own clock, so any number of them can run at once.
    # "auto" marks a task that started merely because focus landed on it - those
    # stop when focus leaves, while ones you started deliberately keep running.
    "tasks": [],          # [{"text": str, "seconds": float, "running": bool, "auto": bool}]
    "active": -1,         # which task the bar displays; independent of running
    "x": None,
    "y": None,
    "opacity": 0.72,
    "nudge_minutes": 15,
    "click_through": False,
}

LOG_HEADER = ["date", "start", "end", "minutes", "task"]


# ---------------------------------------------------------------------------
# Config file
# ---------------------------------------------------------------------------


def load_config() -> dict:
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return config

    # Unknown keys are dropped; every field below is re-validated, so a corrupt
    # or hand-edited file degrades to defaults rather than crashing at startup.
    config.update({k: v for k, v in stored.items() if k in DEFAULTS})
    config["tasks"] = [
        {
            "text": str(t.get("text", "")).strip(),
            "seconds": float(t.get("seconds", 0) or 0),
            "running": bool(t.get("running", False)),
            "auto": bool(t.get("auto", False)),
        }
        for t in config.get("tasks", [])
        if isinstance(t, dict) and str(t.get("text", "")).strip()
    ][:MAX_TASKS]
    active = int(config.get("active", -1))
    config["active"] = active if 0 <= active < len(config["tasks"]) else (0 if config["tasks"] else -1)
    return config


def save_config(config: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    os.replace(tmp, CONFIG_PATH)


# ---------------------------------------------------------------------------
# Session log
# ---------------------------------------------------------------------------


def ensure_log() -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(LOG_HEADER)
    return LOG_PATH


def append_log(task: str, started: datetime, ended: datetime, seconds: float) -> None:
    if not task.strip() or seconds < MIN_LOGGED_SECONDS:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    new_file = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(LOG_HEADER)
        writer.writerow([
            started.strftime("%Y-%m-%d"),
            started.strftime("%H:%M"),
            ended.strftime("%H:%M"),
            f"{seconds / 60:.1f}",
            task.strip(),
        ])


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


def new_task(text: str) -> dict:
    return {"text": text, "seconds": 0.0, "running": False, "auto": False,
            "_since": None, "_from": None}


class TaskStore:
    """The task list plus every rule about clocks and focus.

    Two independent ideas live here and must not be conflated:

      running  - per task; decides what the strip shows.
      active   - which single task the keyboard acts on ("focus").

    Keys beginning with "_" are runtime-only and never persisted.
    """

    def __init__(self, config: dict):
        self.tasks: list[dict] = config["tasks"]
        self.active: int = config["active"]
        # Resume whatever was running when we last exited. The closed period is
        # never counted: bank_for_exit() stops every clock before shutdown.
        for task in self.tasks:
            task.setdefault("_since", None)
            task.setdefault("_from", None)
            if task["running"]:
                task["_since"] = time.monotonic()
                task["_from"] = datetime.now()

    # -- queries ------------------------------------------------------------

    @property
    def current(self) -> dict | None:
        return self.tasks[self.active] if 0 <= self.active < len(self.tasks) else None

    @property
    def paused(self) -> bool:
        """True when the task the bar is showing is not ticking."""
        task = self.current
        return task is not None and not task["running"]

    @staticmethod
    def elapsed(task: dict) -> float:
        total = task["seconds"]
        if task["running"] and task.get("_since") is not None:
            total += time.monotonic() - task["_since"]
        return total

    def total_elapsed(self) -> float:
        return self.elapsed(self.current) if self.current else 0.0

    def running_tasks(self) -> list[dict]:
        return [t for t in self.tasks if t["running"]]

    def running_indices(self) -> list[int]:
        return [i for i, t in enumerate(self.tasks) if t["running"]]

    def is_running(self, index: int) -> bool:
        return 0 <= index < len(self.tasks) and self.tasks[index]["running"]

    def visible(self) -> list[int]:
        """Indices the strip shows: everything running.

        Paused tasks are hidden - unless nothing at all is running, in which case
        the focused task is shown in its paused form. A strip with no rows would
        have nothing to click and no way back, so it never goes empty.
        """
        running = self.running_indices()
        if running:
            return running
        return [self.active] if self.current else []

    def normalize_focus(self) -> None:
        """Keep the focused task on screen whenever anything is running."""
        running = self.running_indices()
        if running and self.active not in running:
            self.active = running[0]

    # -- clocks -------------------------------------------------------------

    def start(self, task: dict, auto: bool = False) -> None:
        """Begin (or continue) this task's clock. Never touches other tasks."""
        if task["running"]:
            # Already ticking: an explicit start outranks an automatic one, so
            # focus moving away later will not stop it.
            task["auto"] = task["auto"] and auto
            return
        task["running"] = True
        task["auto"] = auto
        task["_since"] = time.monotonic()
        task["_from"] = datetime.now()

    def stop(self, task: dict) -> None:
        """Bank this task's clock and write its stretch to the session log."""
        if not task["running"]:
            return
        seconds = self.elapsed(task) - task["seconds"]
        task["seconds"] += seconds
        if task.get("_from"):
            append_log(task["text"], task["_from"], datetime.now(), seconds)
        task["running"] = False
        task["auto"] = False
        task["_since"] = task["_from"] = None

    def set_running(self, index: int, running: bool) -> None:
        """Explicitly toggle one task, independent of focus and of the others."""
        if not (0 <= index < len(self.tasks)):
            return
        task = self.tasks[index]
        self.start(task, auto=False) if running else self.stop(task)

    def toggle_running(self, index: int) -> None:
        if 0 <= index < len(self.tasks):
            self.set_running(index, not self.tasks[index]["running"])

    def stop_all(self) -> None:
        for task in self.tasks:
            self.stop(task)

    # -- list mutation ------------------------------------------------------

    def create(self, text: str, activate: bool | None = None) -> int:
        """Append a task. Returns its index.

        By default a new task does NOT steal focus or start a clock: interrupting
        what you are timing is what made adding feel like a reset. It only takes
        over when asked, or when there was nothing to interrupt.
        """
        if activate is None:
            activate = self.current is None
        task = new_task(text)
        self.tasks.append(task)
        while len(self.tasks) > MAX_TASKS:
            self.stop(self.tasks[0])
            self.tasks.pop(0)
            self.active = max(-1, self.active - 1)
        index = self.tasks.index(task)
        if activate:
            self.set_active(index)
        return index

    def rename(self, index: int, text: str) -> None:
        if not (0 <= index < len(self.tasks)):
            return
        task = self.tasks[index]
        # Close the old name's stretch so the log never attributes time to the
        # wrong label, then carry on under the new one.
        was_running, was_auto = task["running"], task["auto"]
        self.stop(task)
        task["text"] = text
        if was_running:
            self.start(task, auto=was_auto)

    def set_active(self, index: int) -> None:
        """Move focus to a task and start it.

        The task focus is leaving stops only if it started automatically. Tasks
        you deliberately set running keep going in the background - that is what
        makes several timers at once possible without them piling up by accident.
        """
        if not (0 <= index < len(self.tasks)):
            return
        previous = self.current
        if previous is not None and index != self.active and previous["auto"]:
            self.stop(previous)
        self.active = index
        self.start(self.tasks[index], auto=True)

    def cycle(self, delta: int) -> None:
        if len(self.tasks) >= 2:
            self.set_active((self.active + delta) % len(self.tasks))

    def remove(self, index: int) -> None:
        if not (0 <= index < len(self.tasks)):
            return
        self.stop(self.tasks[index])
        self.tasks.pop(index)
        if not self.tasks:
            self.active = -1
        elif index < self.active or self.active >= len(self.tasks):
            self.active = max(0, min(self.active - 1, len(self.tasks) - 1))

    # -- persistence --------------------------------------------------------

    def to_config(self) -> dict:
        """The JSON-safe shape. Runtime "_" keys are dropped here."""
        return {
            "tasks": [
                {"text": t["text"], "seconds": round(t["seconds"], 1),
                 "running": t["running"], "auto": t["auto"]}
                for t in self.tasks
            ],
            "active": self.active,
        }

    def bank_for_exit(self) -> None:
        """Stop every clock (so the log is complete) but remember to resume."""
        resume = self.running_indices()
        for task in list(self.tasks):
            self.stop(task)
        for index in resume:
            self.tasks[index]["running"] = True
