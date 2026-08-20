# FocusBar

A thin, translucent, always-on-top strip that shows the one thing you're supposed to be
doing right now — so when you drift, a glance at the top of the screen pulls you back.

**Every running task gets its own row.** Paused ones are hidden.

```
┌──────────────────────────────────────────────────────────────┐
│ ●  FOT       Fixing the OIDC token refresh      25m   4 ▾    │
│ ●  MON-4821  Nightly build on CI                40m          │
│ ●  RP4       Review PR 412 - customer import     5m          │
└──────────────────────────────────────────────────────────────┘
    ↑ breathing blue dot = running; hover it to get ❚❚
   ┌────────────────────────────────────────────────────┐
   │  1 ● FOT       Fixing the OIDC token refresh   25m │  ← running (blue, washed)
   │  2 ● MON-4821  Nightly build on CI             40m │  ← running
   │  3 ▶ RP4       Review PR 412 - customer  ▴▾✕    5m │  ← paused (amber play)
   │  4 ○ UTA       Update the API documentation      — │  ← never started
   │ ───────────────────────────────────────────────    │
   │ ＋  Add task                                       │
   └────────────────────────────────────────────────────┘
      ↑ rank = priority; drag a row or press Alt+↑/↓ to re-rank
```

Pure Python standard library (tkinter + ctypes). Nothing to install. The code is a small
package (`focusbar/`) behind a one-file launcher.

> Working on the code rather than using it? See **[CODEBASE.md](CODEBASE.md)** — module map,
> data model, invariants, Win32 gotchas, and how to test it.

## Run it

Requires Python 3.10+ with tkinter (the standard Windows installer includes it). Windows only
— it uses Win32 APIs for the always-on-top overlay and the global hotkeys.

Double-click `FocusBar.cmd`, or:

```powershell
pythonw path\to\FocusBar\focusbar.pyw
```

Tests: `python tests/test_focusbar.py` (needs a desktop session; it opens real windows).

## Hotkeys (global — work from any app)

| Keys | Action |
| --- | --- |
| `Ctrl+Alt+T` | Rename the current task |
| `Ctrl+Alt+A` | Add a task to the list (keeps the clock running) |
| `Ctrl+Alt+L` | Open / close the task list |
| `Ctrl+Alt+N` | Next task |
| `Ctrl+Alt+B` | Previous task (back) |
| `Ctrl+Alt+P` | Pause or resume the timer |
| `Ctrl+Alt+H` | Hide or show the bar |

## On the bar

Each row acts on **its own** task:

| Action | Result |
| --- | --- |
| Hover a row's dot | It becomes ❚❚ (or ▶) — the action a click will perform |
| Click a row's dot | Stop that timer — the row then disappears from the strip |
| Click a row's text | Edit that task (`Enter` saves, `Esc` cancels) |
| Click **n ▾** (first row) | Open the task list; hover to see what's paused and hidden |
| Drag anywhere | Move it — the position is remembered |
| Mouse wheel | Adjust opacity |
| Right-click | Menu: add, list, next/previous, move up/down, remove, stop all, opacity, nudge, click-through, log, startup, quit |

## Task states

A task is always in exactly one of three states, told apart on several channels at once so
you can read it from the corner of your eye:

| | Running | Paused | Never started |
| --- | --- | --- | --- |
| **Control** | `●` blue dot, **breathing** | `▶` amber play button | `○` hollow grey |
| **Left rail** | blue, breathing | amber, still | — |
| **Time** | live, blue — always shown, even `0m` | `paused · 13m`, grey | `—` / `not started` |
| **Text** | full contrast | mid | dimmed |
| **On the strip** | one row | hidden | hidden |

A stopped task shows a **play button you can press**. A running one shows a breathing dot
instead, and reveals ❚❚ when you hover it — so hovering any control always tells you what a
click will do.

Motion carries furthest in peripheral vision, which is why the rail and dot breathe while a
clock runs and freeze solid when it stops. Amber appears nowhere else, so it only ever means
paused. And a running row always prints a figure in the time column, so an empty-looking one
is never live.

## Task list

`Ctrl+Alt+L` (or click the `n ▾` counter) drops the list under the bar.

| In the list | Result |
| --- | --- |
| `↑` `↓` | Move the selection |
| `Alt+↑` `Alt+↓` or click `▴` `▾` | Re-rank: move that task up or down the list |
| Drag a row | Re-rank it anywhere — a blue line shows where it will land |
| Click the id | Type your own (`Enter` saves, `Esc` cancels, empty restores the automatic one) |
| `Enter` or click the text | Switch to that task |
| `Space` or click the dot | Start / stop **just that** timer — runs alongside the rest |
| `Delete` or click `✕` | Remove that task |
| `Esc` or click away | Close |

The footer's bottom-right corner carries a small link icon that opens `GITHUB_URL` from
`focusbar/__init__.py` in your browser. Change that one line to point it anywhere; set it to
`""` to hide the icon.

`Ctrl+Alt+N` / `Ctrl+Alt+B` cycle through tasks without opening the list at all —
that's the fastest way to bounce between two things.

## Task ids

Every task carries a short id, shown on the strip and in the list just left of its name.
It's generated from the name — the first letters of its first words:

| Task | Id |
| --- | --- |
| Refactor the export path | `RTE` |
| Write release notes | `WRN` |
| Fix CSV | `FCS` (padded from the last word so codes stay a uniform width) |
| Review PR 412 | `RP4` |

Two tasks that would collide get a digit: the second `RTE` becomes `RTE2`.

**Click the id in the list to type your own** — a ticket key like `MON-4821`, or anything up
to 12 characters. Whitespace is stripped; if the id you type is already in use it gets a digit
the same way.

The difference between the two matters in one place:

- **A generated id follows the name.** Rename the task and the id is regenerated, because
  it's just a short view of the name.
- **An id you typed is yours and stays put** through any number of renames — it's a reference
  you may have written down somewhere else.

Clearing the field hands the id back to the generator.

Ids are padded so the task names line up in a column. On the strip that padding is measured
across the rows actually showing, so one long id on a paused task can't indent everything.

## Rank and priority

**Position in the list is the priority** — rank 1 is the top task. There's no separate
priority field to keep in sync: rearranging the list *is* re-prioritising, and the numbers
down the left edge of the list renumber as you go.

| To re-rank | |
| --- | --- |
| **Drag** a row in the list | A blue line shows the gap it will drop into |
| `Alt+↑` / `Alt+↓` | Moves the selected row one place; the selection rides along with it |
| Hover a row and click `▴` `▾` | The same, for the mouse — the arrows appear only on the row under the cursor |
| Right-click the bar → **Move up / Move down** | Re-ranks the focused task without opening the list |

Neither end wraps: `Alt+↑` on rank 1 does nothing, and the arrow that has nowhere to go isn't
drawn at all. Re-ranking never touches anything else about a task — its clock keeps running,
its id doesn't change, and the bar keeps showing whatever it was showing, because focus
follows the *task*, not the slot it came from.

The ranks live in the list rather than on the strip, because the strip only shows what's
running — `1, 4, 7` down the side of it would be unreadable as a priority order. The strip
does stack its rows in rank order.

## Several timers at once

Every task owns its own clock, so any number can run together — a build ticking away while
you review a PR, for instance. **The strip shows one row per running task and grows
downward**; paused tasks drop off it entirely and live only in the list.

**Start an extra one** by clicking its `●`/`○` dot in the list, or selecting it and pressing
`Space`. That starts *only* that task: nothing else stops, and a new row appears.

**Stop one** by clicking that row's icon on the strip — the row disappears. Everything else
keeps going.

Two ideas are deliberately kept apart:

- **Running** — per task. Determines what appears on the strip.
- **Focus** — which single row the keyboard acts on (`Ctrl+Alt+P` pause, `Ctrl+Alt+T` rename).
  Shown by full-contrast text; the other rows are slightly dimmer. Moved with
  `Ctrl+Alt+N`/`B`, or by clicking a row.

**Moving focus doesn't pile up timers.** When focus leaves a task that started *just because
focus landed on it*, that task stops. Tasks you started deliberately (via the dot or `Space`)
keep running until you stop them — so cycling through your list never leaves a trail of
running clocks, and never kills a background timer either.

**The strip never goes blank.** If you stop everything, it falls back to showing the focused
task in its paused form, so there's always something to click. That's the one case where a
paused task stays visible.

**Paused work stays findable.** The `n ▾` counter shows the full task count, and hovering it
lists every paused task that the strip is hiding. Right-click → **Stop all timers** (with a
count) ends everything at once.

Each task logs its own stretches independently, so overlapping work produces overlapping rows
in the CSV — the per-task totals stay correct even though the wall-clock spans overlap.

## Adding a task

Adding happens **in place, inside the list** — click `＋ Add task` or press `Ctrl+Alt+A`
and the row turns into a text field where it sits.

| In the add field | Result |
| --- | --- |
| `Enter` | Add it to the list and stay in the field, ready for the next one |
| `Ctrl+Enter` | Add it **and** switch to it right away |
| `Esc` | Back out |

**Adding never touches the clock.** Whatever you're timing keeps running and keeps counting —
only the task count ticks up, and the new row flashes briefly so you can see what landed.
Switching is a separate, deliberate act (`Ctrl+Enter`, a click, or `Ctrl+Alt+N`).

**Time banks per task.** Each task keeps its own running total, so switching away
and back resumes where it left off rather than resetting to zero. The list shows
each task's total next to it.

## Nudge

Every 15 minutes (configurable, or off) the strip pulses orange for a couple of seconds.
It never steals focus or pops a dialog — it just moves in your peripheral vision, which is
enough to notice without breaking what you're doing.

## Session log

Every stretch of work is appended to `%APPDATA%\FocusBar\sessions.csv` when you switch away
from it or quit, with date, start, end, minutes and the task text. Bouncing between two
tasks writes one row per stretch, so the CSV reads as a real chronology of the day.
Stretches under 30 seconds are skipped so typos don't pollute the log. Open it from the
right-click menu, or in Excel:

```
%APPDATA%\FocusBar\sessions.csv
```

## Start with Windows

Right-click the bar → **Start with Windows** (toggles a shortcut in your Startup folder).
Or run `install-startup.ps1`.

## Click-through

Right-click → **Click-through** makes the bar ignore the mouse entirely, so it can sit over
a work area without ever intercepting a click. You can still reach it with `Ctrl+Alt+T` —
editing temporarily re-enables the mouse, then restores click-through when you're done.

## Settings

`%APPDATA%\FocusBar\config.json` holds the task list — in rank order, each with its id,
per-task total and run state — which one is focused, plus position, opacity and nudge
interval. It's written automatically; edit it by hand only while the app is closed.

Hand-edited files are repaired on load rather than rejected: a task with no id gets one
generated, and if two end up sharing an id the later one is given a digit.

Timers that were running at exit resume on the next launch. The closed period is never
counted — every clock is banked to the log on quit.

**Sleep doesn't count; a locked screen does.** Timers run on Windows' unbiased counter, so
suspending or hibernating the machine stops every clock where it stood and resumes it on wake
— leaving a task running overnight won't come back with eight hours against it. Locking your
screen (or walking away) is *not* treated as a stop: the clock keeps ticking, because only you
know whether you were still on the task.
