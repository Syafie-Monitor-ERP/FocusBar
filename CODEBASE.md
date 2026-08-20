# FocusBar — codebase guide

Developer-facing companion to `README.md` (which is the user manual). This one is about
**navigating and changing the code**: where things live, what the invariants are, and which
parts will bite you.

---

## 1. Files

| File | Lines | What it is |
| --- | ---: | --- |
| `focusbar.pyw` | 30 | Entry point. Puts the project dir on `sys.path`, then `FocusBar().run()`. |
| `focusbar/__init__.py` | 37 | Docstring module map, `GITHUB_URL`, lazily-resolved `__version__`. |
| `focusbar/paths.py` | 20 | Where data lives on disk. Resolved at import time. |
| `focusbar/version.py` | 57 | The version number: build stamp if packaged, else `git describe`. |
| `focusbar/util.py` | 68 | Pure helpers: `format_elapsed`, `truncate`, `lerp_color`, and the id rules `initials` / `clean_id` / `unique_id`. |
| `focusbar/theme.py` | 78 | Palette, sizing, glyphs, `state_dot`, `breath_ramp`. |
| `focusbar/tooltip.py` | 54 | Delayed hover hint in its own window. |
| `focusbar/system.py` | 80 | Session-log opening, Startup shortcut (points at the .exe when packaged). |
| `focusbar/winapi.py` | 121 | ctypes bindings, window-style helpers, `HotkeyListener`. |
| `focusbar/row.py` | 160 | `BarRow` — one row of the strip. |
| `focusbar/store.py` | 380 | Config, session log, and **`TaskStore`** — the timing, id and rank model. |
| `focusbar/panel.py` | 629 | `TaskListPanel` — the drop-down list; also ranks, id editing and drag-to-reorder. |
| `focusbar/bar.py` | 725 | `FocusBar` — the window, layout, input and wiring. |
| `tests/test_focusbar.py` | 992 | The whole suite. `python tests/test_focusbar.py`. |
| `tools/make_version_file.py` | 91 | Generates the Windows VERSIONINFO resource PyInstaller embeds. |
| `FocusBar.cmd` | | Launcher: `start pythonw focusbar.pyw`, no console. |
| `install-startup.ps1` | | Creates/removes the Startup shortcut (`-Remove` to undo). |
| `.github/workflows/release.yml` | | Tag → version-stamped `.exe` + generated release notes. |
| `RELEASE.md` | | Standing preamble for release notes: download and first-run steps. |

**No runtime dependencies and no build step to run the app** — `compileall` over `focusbar/`
is the whole "build", and `python focusbar.pyw` needs nothing installed. Packaging for
distribution is separate and lives entirely in CI (see §11). The `.pyw` extension is what
makes `pythonw` run the entry point without a console — and `.pyw` is not an importable
suffix, so the file and the `focusbar/` package can share a name without clashing.

Runtime data lives outside the repo, in `%APPDATA%\FocusBar\`:

| Path | Contents |
| --- | --- |
| `config.json` | Task list **in rank order**, each with id, per-task total and run flags; focus, window position, opacity, nudge interval. |
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
  "text":      str,
  "id":        str,    # the short label the user sees; unique, never empty
  "id_locked": bool,   # the user typed it, so a rename must not overwrite it
  "seconds":   float,  # banked total, NOT including the stretch currently running
  "running":   bool,
  "auto":      bool,   # started merely because focus landed here (see §4)
  "_since":    float | None,    # time.monotonic() when the current stretch began
  "_from":     datetime | None  # wall clock for the same, used for the CSV row
}
```

**Keys beginning with `_` are runtime-only.** `TaskStore.to_config()` rebuilds a clean dict per
task, so a new runtime field is excluded automatically as long as you prefix it.

Elapsed time is always `seconds + (now - _since)`, via `TaskStore.elapsed(task)`. Nothing
mutates `seconds` except `TaskStore.stop()`.

> **Index-as-identity is the sharpest edge in this codebase.** `remove()` fixes up `active` by
> hand, and any widget callback that captured an index is stale after a removal or a
> **reorder**. Rows are always rebuilt after a mutation, which is what keeps this safe — don't
> add a path that mutates `tasks` without a `_refresh()`.

### `id` is a label, not an identity

`id` exists for the user to refer to a task by; the code still addresses tasks by index. Do
not be tempted to route wiring through it — `move()` reorders the list under every captured
index, which is exactly the hazard above, and an id can be changed by the user at any moment.

Two invariants hold, both enforced in `TaskStore` and re-established in `load_config()` so a
hand-edited file cannot break them:

1. **Every task has one.** Blank means "generate it", never "no id".
2. **No two match**, compared case-insensitively — `unique_id()` appends a digit. Two tasks
   labelled `rte` and `RTE` would be indistinguishable at a glance, which defeats the point.

`id_locked` is the whole reason the field is not derivable. A generated id is a *view of the
name* and is regenerated by `rename()`; one the user typed is a *reference they may have
written down elsewhere* and survives any number of renames. Setting it to blank via `set_id()`
clears the flag and hands it back to the generator. Note the name: `auto` is already taken and
means something unrelated (§4) — do not add a second field called `id_auto`.

`initials()` and `unique_id()` are pure and live in `util.py`, so the generation rules can be
tested without a store.

### Rank is position

There is **no rank field**. `TaskStore.rank(index)` returns `index + 1` and that is the entire
definition, so priority and list order cannot drift apart. `move()` is the single mutation;
`shift()` is `move()` by ±1 and deliberately does not wrap.

`move()` re-points `active` by identity (`t is focused`), not by arithmetic on the old slot —
focus belongs to a task, not to a position. Everything else about the task is untouched: the
clock keeps running, `_since` is not reset, the id does not change.

Adding a call site? Go through `FocusBar.move_task()` / `shift_task()`, which end in
`_changed()` like every other mutation.

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

`[rail] [state dot / action button] id  task text .... timer [chevron]`. The row owns its
widgets, its tooltip, its hover swap and its state sync. The chevron exists on **every** row
with a fixed `width=5` but only the first carries text and bindings — that fixed slot is what
keeps the timer column aligned down the stack.

The bar keeps only layout (`_resize`, `_bar_height`), hit-handling (`_on_release_*`) and the
model proxies.

### Column alignment: pad the text, never fix the width

Both the id column here and the id/rank columns in the panel are **space-padded to the widest
value currently on screen** and set in a fixed-width face (`ID_FONT`). The obvious alternative
— a Tk `width=` on the label — clips anything longer, which a 12-character hand-typed id
immediately is.

`FocusBar.id_slot()` measures across the **visible** tasks only, so one long id on a paused
task cannot indent the whole strip; `TaskListPanel._id_slot()` measures across all of them,
because the list shows all of them. Rows are rebuilt on every mutation (above), so neither
needs invalidating.

If you add a column that takes horizontal space, extend `bar._resize`'s width sum too — it
adds `id_font.measure("0" * id_slot())` for this one.

### `TaskListPanel` row

`[focus edge] [rank] [dot] [id] task text .... [▴ ▾] [✕] [timer]`.

`row.parts` is the tuple `_highlight()` and `_flash()` repaint, so **anything you add to a row
must go into it** or it will keep the previous background. `row.remove` and `row.movers` are
kept as separate references because those three hide by matching the row background rather
than by being unpacked.

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

### The id and the rank stay out of it

Both are **metadata, not state**, and each gets exactly one colour (`ID_FG`, `RANK_FG`) on
every row regardless of what the task is doing. Do not give rank a colour ramp: `ACCENT`
already means running and `AMBER` already means paused, so a blue rank 1 reads as a ticking
clock. The number and the position are the whole signal.

The one exception is the id's own hover — it brightens to `FG` because it is clickable, which
is the same hover-reveals-action rule the controls follow.

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

### Two Tk constraints that shape the panel

**A pressed widget owns the pointer until release.** This is why drag-to-reorder in
`TaskListPanel` does *not* reorder as you drag: `refresh()` would destroy the very widget
holding the implicit grab and the gesture would simply stop mid-drag. The list holds still and
only `drop_line` — a `place`d 2px frame — moves; the single `move()` happens on release. If
you ever make the rows reorder live, you have to move the bindings off the rows first.

**A binding on a Toplevel fires for events in its children**, because the toplevel's name is
in every descendant's bindtags. The panel binds bare `<Return>`, `<space>`, `<Delete>` and
`<Up>`/`<Down>` on the window, so a keystroke meant for a text field also runs the list
shortcut. There are two defences and **which one to use depends on the key**:

| | Use | Why |
| --- | --- | --- |
| `<Up>` `<Down>` `<Alt-Up>` `<Alt-Down>` | `_seal()` — a widget-tag `"break"` | The Entry does nothing with them, so swallowing them costs nothing |
| `<Return>` `<Escape>` | `_closing()` — the handler itself returns `"break"` | See below |
| **`<space>` `<Delete>`** | **the `typing` guard only — never `"break"`** | The `Entry` *class* binding is what inserts the character |

That last row was a real bug: bindtags run **widget → class → toplevel**, so a `"break"` on
the widget tag aborts the whole chain *including the class binding*, and the space never
reaches the entry. Sealing `<space>` silently made the add field refuse spaces. If a key edits
text, let it through and stop the window handler at the handler instead — that is all
`TaskListPanel.typing` is for.

`_closing()` exists because `entry.bind(seq, ..., add="+")` is **not** a reliable way to append
a `"break"`. Committing destroys the entry, and a destroyed widget never reaches the rest of
its own binding script, so the appended `"break"` is skipped and the key sails on to the
window. The `"break"` has to be returned by the same handler that does the work.

Test these by generating the keystroke, never by calling the handler — a call cannot observe a
swallowed keypress. Note `event_generate("<4>")` is a **button** event: spell digits out as
`event_generate("<Key>", keysym="4")`. And flush with `root.update()` after opening an editor,
or the entry is not yet mapped and the keys go nowhere.

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
  `widget.event_generate("<Return>")` *is* allowed and is used to prove the `"break"` above —
  it is delivered to one named widget rather than to whatever the OS thinks is focused.
- **Never call `_show_menu`.** `tk_popup` grabs the pointer and does not return until the menu
  is dismissed, so a test that calls it hangs forever. The dynamic labels and states live in
  `_sync_menu()`, which is what the checks call; `_show_menu` is that plus the popup.
- **Flush the idle queue before asserting on geometry.** `place()` and `pack()` are deferred,
  so `winfo_ismapped()` on the freshly-placed `drop_line` is False until `root.update()`.
- **Mouse-gesture handlers take a stand-in event.** `_press`/`_motion`/`_release` read only
  `y_root`, so a two-line class stands in; the row midpoints come from `winfo_rooty()`.
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

**Add a column to a list row** — build it in `_build_row`, add it to `row.parts` (else
`_highlight` leaves it on the old background), and pad its text via a `_slot()` helper rather
than setting `width=`. If it takes horizontal space on the *strip* too, extend `bar._resize`.

**Add a hover-only control** — pack it right of the text, give it `fg=bg` at rest, and paint
it in `_highlight` only when the row is selected. Paint it out entirely rather than greying it
when it would do nothing (as the `▴` on rank 1 does), and add it to the `_flash` fg loop so it
does not blink into view on a newly added row.

**Change the footer link** — `GITHUB_URL` in `focusbar/__init__.py`; `""` hides the icon.
`system.open_url()` accepts `http`/`https` only, so a mistyped value cannot launch a local
program.

---

## 10. Known limitations

- **Single instance is not enforced.** Two copies fight over `config.json` (last write wins)
  and both try to register the same hotkeys; the second silently fails
  (`HotkeyListener.failed` records which, but nothing surfaces it).
- **`MAX_TASKS` (40) trims from the front** and stops those timers first — silently. Since
  rank is position, that means it drops the *highest-priority* tasks.
- **Ids are not in the session log.** `sessions.csv` still records the task text only, so a
  renamed task is two different labels in the log even though it kept its id.
- **`unique_id` gives up after 999 collisions** and returns the base, which would allow a
  duplicate. Reaching it needs 999 tasks sharing one id and `MAX_TASKS` is 40.
- **Drag-to-reorder has no auto-scroll**, because the panel never scrolls — with 40 tasks the
  list is simply taller than it is comfortable to drag across. Alt+↑/↓ has no such limit.
- **No timezone/DST handling** in the CSV — wall-clock strings only.
- **Log stretches under 30 s are dropped** (`MIN_LOGGED_SECONDS`), so rapid hopping
  under-reports.
- **`TaskListPanel` rows monkey-patch attributes** onto their `tk.Frame` rather than having a
  class of their own like `BarRow`. Worth extracting if that file grows.
- **DPI**: sizes are in Tk pixels; on a mixed-DPI multi-monitor setup the strip may look
  slightly off after being dragged to a differently-scaled display.

---

## 11. Versioning and releases

**A git tag is the only place a version number is authored.** Nothing in the repository
records one, so cutting a release edits no files:

```powershell
git tag v0.0.2
git push --tags
```

`.github/workflows/release.yml` does the rest on a Windows runner: stamps the version,
builds a one-file `.exe`, generates the notes, and publishes the release.

### Where the number comes from

`version.resolve()` has two sources, tried in order:

| Situation | Source | Example |
| --- | --- | --- |
| Packaged `.exe` | `version.STAMPED`, rewritten by CI from the tag | `0.0.2` |
| Working checkout | `git describe --tags --always --dirty` | `0.0.2-4-gc3dfa40-dirty` |
| Neither works | literal fallback | `dev`, or `unknown` if frozen |

`STAMPED` is `""` in the repository **on purpose** — committing a number there would recreate
the second source of truth the tag exists to remove. The stamping step fails the build if its
regex no longer matches, so renaming that constant breaks CI loudly rather than silently
shipping `unknown`.

`__version__` is resolved through a module-level `__getattr__` rather than at import: off a
checkout it costs a subprocess, which no importer should pay for unasked. It surfaces to users
as a disabled entry above **Quit** in the right-click menu, and in the exe's
Properties → Details (from the VERSIONINFO resource that `tools/make_version_file.py` writes).

### The changelog

Generated from `git log <previous tag>..<this tag>`, appended to `RELEASE.md`. No commit
message convention is required — every non-merge commit is listed as written. On a first
release `git describe` on the tag's parent fails, which is read as "log everything".

### Gotchas

- **A tag suffix means prerelease.** `v1.0.0-beta.1` is published with `--prerelease`, so
  `/releases/latest` keeps pointing at the last stable build.
- **Re-running a tag's workflow updates the existing release** rather than failing, so a
  botched build can be fixed by re-running the job.
- **`workflow_dispatch` is a dry run**: it builds and version-stamps identically but publishes
  nothing, leaving the exe as a run artifact. Use it to test packaging changes.
- **The build is unsigned**, so users get a SmartScreen warning. `RELEASE.md` tells them how
  to get past it. Fixing it properly needs a code-signing certificate, not a CI change.
- **The line counts in §1 drift.** Several were already stale before the release tooling
  landed; treat them as rough.
