## Download

**[FocusBar.exe](https://github.com/Syafie-Monitor-ERP/FocusBar/releases/latest/download/FocusBar.exe)** — one file. Nothing to install, no admin rights needed.

## First run

1. Save the file somewhere you'll keep it — `Documents\FocusBar` is fine.
2. Double-click it.
3. **Windows will say "Windows protected your PC".** Click **More info**, then
   **Run anyway**. This appears because the file isn't code-signed yet, not
   because anything is wrong with it.
4. A thin strip appears at the top of your screen. Drag it wherever you like —
   it remembers the position.

## The three things worth knowing

- **Ctrl+Alt+A** — add a task
- **Ctrl+Alt+L** — open the task list
- **Right-click the strip → Start with Windows** — so it's there every morning

Click a task's dot to stop its timer, click its text to rename it. The full list
of hotkeys is in the [README](https://github.com/Syafie-Monitor-ERP/FocusBar#hotkeys-global--work-from-any-app).

## Where your data lives

- `%APPDATA%\FocusBar\config.json` — your tasks and settings
- `%APPDATA%\FocusBar\sessions.csv` — a log of every stretch of work, openable in Excel

## Uninstall

Delete `FocusBar.exe`. Also delete the `%APPDATA%\FocusBar` folder if you don't
want to keep the time log.

## Verifying the download (optional)

`FocusBar.exe.sha256` holds the checksum. To confirm your copy matches, run this
in PowerShell from the folder you saved it in:

```powershell
Get-FileHash FocusBar.exe -Algorithm SHA256
```
