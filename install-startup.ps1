<#
.SYNOPSIS
    Adds (or removes, with -Remove) a Startup shortcut so FocusBar launches at login.
#>
param([switch]$Remove)

$ErrorActionPreference = 'Stop'

$script = Join-Path $PSScriptRoot 'focusbar.pyw'
$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'FocusBar.lnk'

if ($Remove) {
    if (Test-Path $link) { Remove-Item $link -Force; "Removed $link" } else { 'Not installed.' }
    return
}

if (-not (Test-Path $script)) { throw "Cannot find $script" }

$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command python.exe).Source -replace 'python\.exe$', 'pythonw.exe'
}
if (-not (Test-Path $python)) { throw 'Could not locate pythonw.exe' }

$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
$shortcut.TargetPath = $python
$shortcut.Arguments = "`"$script`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'FocusBar - current task overlay'
$shortcut.Save()

"Installed $link -> $python `"$script`""
