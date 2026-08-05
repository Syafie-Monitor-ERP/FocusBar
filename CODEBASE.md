# FocusBar — codebase guide

Developer-facing companion to `README.md` (which is the user manual). This one is about
**navigating and changing the code**: where things live, what the invariants are, and which
parts will bite you.

---

## 1. Files

| File | Lines | What it is |
| --- | ---: | --- |
| `focusbar.pyw` | 30 | Entry point. Puts the project dir on `sys.path`, then `FocusBar().run()`. |
| `focusbar/__init__.py` | 25 | Docstring module map, `__version__`, `GITHUB_URL`. |
| `focusbar/paths.py` | 20 | Where data lives on disk. Resolved at import time. |
| `focusbar/util.py` | 21 | Pure formatters: `format_elapsed`, `truncate`, `lerp_color`. |
| `focusbar/theme.py` | 73 | Palette, sizing, glyphs, `state_dot`, `breath_ramp`. |
| `focusbar/tooltip.py` | 54 | Delayed hover hint in its own window. |
| `focusbar/system.py` | 56 | Session-log opening, Startup shortcut. |
| `focusbar/winapi.py` | 121 | ctypes bindings, window-style helpers, `HotkeyListener`. |
| `focusbar/row.py` | 160 | `BarRow` — one row of the strip. |
| `focusbar/store.py` | 323 | Config, session log, and **`TaskStore`** — the timing model. |
| `focusbar/panel.py` | 368 | `TaskListPanel` — the drop-down list. |
| `focusbar/bar.py` | 645 | `FocusBar` — the window, layout, input and wiring. |
| `tests/test_focusbar.py` | 560 | The whole suite. `python tests/test_focusbar.py`. |
| `FocusBar.cmd` | | Launcher: `start pythonw focusbar.pyw`, no console. |
| `install-startup.ps1` | | Creates/removes the Startup shortcut (`-Remove` to undo). |

**No dependencies, no build step, no package metadata.** `compileall` over `focusbar/` is the
whole "build". The `.pyw` extension is what makes `pythonw` run the entry point without a
console — and `.pyw` is not an importable suffix, so the file and the `focusbar/` package can
share a name without clashing.

Runtime data lives outside the repo, in `%APPDATA%\FocusBar\`:

| Path | Contents |
| --- | --- |
| `config.json` | Task list with per-task totals and run flags, focus, window position, opacity, nudge interval. |
| `sessions.csv` | Append-only log: `date,start,end,minutes,task`. |

---

## 2. How the pieces fit

```
focusbar.pyw
   └── bar.FocusBar ................ the window: layout, input, hotkeys, redraw
         ├── store.TaskStore ..... ALL rules about clocks and focus (no Tk)
         ├── row.BarRow × n ...... one strip row each
         ├── panel.TaskListPanel . the drop-down list
         └── system / winapi ..... OS edges
```

The important line is between **`TaskStore`** and everything else. The store has no Tk import
at all: it owns the task list, the clocks, focus, persistence shape and the session log. The
view layer asks it questions and then redraws. `FocusBar` exposes thin proxies (`tasks`,
`active`, `current`, `paused`, `elapsed`, `running_tasks`, `visible_tasks`) so rows, the panel
and the tests can keep talking to the bar, but the rules live in one Tk-free place.

Mutating methods on `FocusBar` follow one shape:

```python
def set_active(self, index):
    self.store.set_active(index)     # model decides
    self.last_nudge = time.monotonic()
    self._changed()                  # == self._refresh(); self._persist()
```

If you add a mutation, go through the store and finish with `_changed()`.

---

## 3. The data model

One task is a plain `dict` — no class, because it goes straight to JSON.

```python
{
  "text":    str,
  "seconds": float,  # banked total, NOT including the stretch currently running
  "running": bool,
  "auto":    bool,   # started merely because focus landed here (see §4)
  "_since":  float | None,    # time.monotonic() when the current stretch began
  "_from":   datetime | None  # wall clock for the same, used for the CSV row
}
```

**Keys beginning with `_` are runtime-only.** `TaskStore.to_config()` rebuilds a clean dict per
task, so a new runtime field is excluded automatically as long as you prefix it.

Elapsed time is always `seconds + (now - _since)`, via `TaskStore.elapsed(task)`. Nothing
mutates `seconds` except `TaskStore.stop()`.

> **Index-as-identity is the sharpest edge in this codebase.** There are no task IDs, so
> `remove()` fixes up `active` by hand, and any widget callback that captured an index is
> stale after a removal. Rows are always rebuilt after a mutation, which is what keeps this
> safe — don't add a path that mutates `tasks` without a `_refresh()`.

---

## 4. The two invariants that shape everything

### Focus vs running

Independent, and conflating them will break the UI.

- **running** decides what appears on the strip (`TaskStore.visible()`).
- **focus** (`store.active`) decides what the keyboard acts on.

`TaskStore.normalize_focus()` enforces: *if anything is running, `active` points at a running
task*, so the focused row is always on screen. `FocusBar._rebuild_rows()` calls it first.

`visible()` never returns empty while tasks exist — with nothing running it falls back to the
focused task, shown paused. A strip with no rows would have nothing to click and no way back.

### The `auto` flag

Set when a task starts **only because focus landed on it** (`set_active` → `start(auto=True)`).
Cleared when started deliberately (`set_running` → `start(auto=False)`).

`set_active` stops the previous task **only if it was `auto`**. That is what lets you cycle
through tasks without either accumulating a pile of running clocks or killing a background
timer you started on purpose. `start()` on an already-running task does
`task["auto"] = task["auto"] and auto`, so explicit always outranks automatic.

If you touch `set_active`, `start` or `stop`, re-read this — the `multi: *auto*` tests exist
specifically to pin it down.

---

## 5. Rendering model

The strip is **rebuilt, not mutated**: `_refresh()` → `_rebuild_rows()` destroys every `BarRow`
and recreates it from current state. Cheap, and it removes a whole class of stale-view bugs.

Two deliberate exceptions:

1. **`_refresh()` skips the rebuild while `self.editing`** — an open `Entry` would be destroyed
   mid-keystroke. `_end_edit()` refreshes once editing finishes.
2. **`_update_times()` mutates in place**, every 500 ms from `_tick`. It also calls
   `row.sync_state(task)` when a row's cached `running` no longer matches, which repairs the
   rows that exception 1 left stale.

`TaskListPanel` has the same split: `refresh()` rebuilds, `update_times()` pokes labels.

### `BarRow`

`[rail] [state dot / action button] task text .... timer [chevron]`. The row owns its widgets,
its tooltip, its hover swap and its state sync. The chevron exists on **every** row with a
fixed `width=5` but only the first carries text and bindings — that fixed slot is what keeps
the timer column aligned down the stack.

The bar keeps only layout (`_resize`, `_bar_height`), hit-handling (`_on_release_*`) and the
model proxies.

---

## 6. The state-signalling rule

> **State and action never share a channel at the same moment.** State is carried by the rail
> colour and motion, the dot, the wording of the timer, and the text contrast. The action
> appears on hover.

**`FocusBar.rest_control(task)` is the single definition** of what the start/stop control looks
like at rest, returning `(glyph, colour, font)`. It lives on the bar rather than in `theme`
because only the bar knows which icon font resolved. Both `BarRow` and
`TaskListPanel._row_style()` call it, so the two surfaces cannot drift.

The asymmetry in it is deliberate — don't collapse it into one rule:

- **Running → a breathing dot.** Paused rows are hidden from the strip, so an action-only icon
  there would be permanently ❚❚: a control that never changes reads as broken. The action
  appears on hover instead.
- **Stopped → the play triangle, at rest.** Next to an amber rail and a `paused · 13m` readout
  there is nothing to misread, and a button invites the click where a dot does not.

### Three task states, four channels

`TaskListPanel._row_style()` maps a task to `(glyph, colour, font, time text, time colour,
text colour)`; `_row_bg()` handles the row wash. Both feed row construction, `update_times()`
and `_highlight()`, so there is one definition per state.

| | Running | Paused (banked > 0) | Never started |
| --- | --- | --- | --- |
| Control | `●` `ACCENT`, breathing | `▶` `AMBER`, still | `○` `IDLE_DIM` |
| Row bg | `RUNNING_BG` | `PANEL_BG` | `PANEL_BG` |
| Time | live, `ACCENT`, always printed | banked, `DIM` | `—`, `IDLE_DIM` |
| Text | `FG` | `ROW_TEXT` | `IDLE_FG` |

If you add a state, make it differ on **more than one** channel — a glyph swap alone is not
legible at this size.

### Derive from live state, never from build-time state

`FocusBar.action_icon(index)` and `FocusBar.button_hint(index)` both read the task's current
`running` **at hover time**. They are a pair and must stay one; same for
`TaskListPanel._dot_hint()`.

Caching either onto the widget breaks the pairing: a row that skipped a rebuild (see §5) would
show one thing and say another.

`_breathe_step()` animates the running rows' rails and dots, but `BarRow.breathe()` skips a row
whose `hovering` is set, so the breath never clobbers the hover swap. It also drives
`TaskListPanel.breathe()` so the list pulses in step.

---

## 7. Win32 constraints

Each of these dictates a piece of the code. Don't "simplify" one away without testing it.

| Constraint | Where | Why |
| --- | --- | --- |
| **Geometry drift** | `bar._resize` | On an `overrideredirect` window, `geometry("WxH")` without coordinates makes Tk re-add a title-bar offset, so the strip walks down the screen on every resize. Always restate `+x+y`. |
| **`SetForegroundWindow` is refused** to background processes | `panel._close_if_unfocused` | The click-away watchdog is armed only after a real `<FocusIn>` (`_had_focus`); otherwise the panel closes the instant it opens. |
| **`RegisterHotKey` delivers to the registering thread** | `winapi.HotkeyListener` | So the `GetMessageW` loop lives on that thread and results reach Tk through a `queue.Queue` drained by `_tick`. Never call Tk from that thread. |
| **Topmost gets stolen** | `bar._tick` | Installers and some full-screen apps take the topmost slot; `-topmost` is re-asserted twice a second. |
| **HWND of a Tk widget** | `winapi.root_hwnd` | `winfo_id()` is not always the top level; go through `GetAncestor(..., GA_ROOT)`. |
| **Click-through eats keystrokes** | `bar.begin_edit` | `WS_EX_TRANSPARENT` is dropped for the duration of an edit and restored in `_end_edit` via `_restore_click_through`. |
| **Icon font may be absent** | `bar._build_window` | Falls back from Segoe Fluent Icons / MDL2 to plain `▶` / `❚❚`. The glyphs are private-use `\ue768` / `\ue769` — easy to mangle when editing `theme.py`; verify with `hex(ord(...))` after touching that line. |

`WS_EX_TOOLWINDOW` keeps the strip and the panel out of the taskbar and Alt-Tab.
`round_corners` is a no-op on Windows 10.

---

## 8. Tests

```
python tests/test_focusbar.py
```

154 in-process checks, no pytest, no dependencies; exits non-zero on failure. It opens real
Tk windows briefly, so it needs a desktop session — it will not run headless.

Two constraints shape the harness:

```python
os.environ["APPDATA"] = tempfile.mkdtemp()   # BEFORE the import: paths.py resolves
sys.path.insert(0, str(PROJECT))             # DATA_DIR at import time

bar = FocusBar.__new__(FocusBar)                 # skip __init__ ...
bar.config = dict(DEFAULTS)
bar.config["tasks"], bar.config["active"] = [], -1
bar.store = TaskStore(bar.config)            # ... build the model by hand
bar.opacity, bar.nudge_minutes, bar.click_through = 0.72, 15, False
bar.hidden = bar.editing = False
bar.last_nudge = 0
bar._drag_origin = None; bar._drag_moved = False
bar._pulse_left = 0; bar._restore_click_through = False
bar.panel = TaskListPanel(bar)               # BEFORE _build_window: rows read it
bar._build_window()
```

Why `__new__`: the real `__init__` starts the global-hotkey thread, which would hijack
`Ctrl+Alt+*` system-wide for the duration of the run.

`TaskStore` needs no display at all, so model-level tests can skip every line above.

Rules learned the hard way:

- **Never drive the app with `SendKeys`.** Synthetic keystrokes go to whatever window has
  focus, not necessarily this one. Call handlers directly (`bar._on_release_button(0)`,
  `row.hover(True)`, `bar.panel._commit_add(start=False)`).
- **Re-assert `panel.cursor` before each `_toggle_cursor()`.** The panel is a real window; a
  pointer resting over a row fires its `<Enter>` and moves the cursor, making tests flaky.
- **Watch for leftover panel state.** Clicking a row button with no tasks opens the add flow,
  and a later `panel.open()` is a no-op if it is already open, so `adding` stays `True`.

For screenshots, launch a throwaway instance with a sandboxed `APPDATA` and a seeded
`config.json` rather than touching real data.

`TaskStore` needs no display at all, so model-level tests can skip the widget setup entirely —
that is the main practical payoff of keeping it Tk-free.

---

## 9. Recipes

**Add a global hotkey** — add an ID to the `HOTKEY_*` line on `FocusBar`, register it in
`_start_hotkeys`, map it in the `actions` dict in `_tick`, and document it in `focusbar.pyw`'s
docstring and `README.md`.

**Add a persisted setting** — add the key to `store.DEFAULTS`, normalise it in `load_config`
(which only copies keys present in `DEFAULTS`), read it in `FocusBar.__init__`, and write it
wherever it changes.

**Add a right-click menu item** — add it in `_build_menu` and, if its label is dynamic, capture
the index right after (`self.X_INDEX = self.menu.index("end")`) and update it in `_show_menu`.
Never hard-code menu indices.

**Change what the strip shows** — `TaskStore.visible()` is the single source of truth. Keep the
"never empty while tasks exist" fallback.

**Add something to a strip row** — `row.BarRow.__init__` plus a method on `BarRow`; then extend
`bar._resize`'s width calculation if it takes horizontal space.

**Add a model rule** — put it in `TaskStore` and give `FocusBar` a one-line delegating wrapper
that ends in `_changed()`. Resist the urge to put timing logic in the view.

**Change the footer link** — `GITHUB_URL` in `focusbar/__init__.py`; `""` hides the icon.
`system.open_url()` accepts `http`/`https` only, so a mistyped value cannot launch a local
program.

---

## 10. Known limitations

- **Single instance is not enforced.** Two copies fight over `config.json` (last write wins)
  and both try to register the same hotkeys; the second silently fails
  (`HotkeyListener.failed` records which, but nothing surfaces it).
- **`MAX_TASKS` (40) trims from the front** and stops those timers first — silently.
- **No timezone/DST handling** in the CSV — wall-clock strings only.
- **Log stretches under 30 s are dropped** (`MIN_LOGGED_SECONDS`), so rapid hopping
  under-reports.
- **`TaskListPanel` rows monkey-patch attributes** onto their `tk.Frame` rather than having a
  class of their own like `BarRow`. Worth extracting if that file grows.
- **DPI**: sizes are in Tk pixels; on a mixed-DPI multi-monitor setup the strip may look
  slightly off after being dragged to a differently-scaled display.
