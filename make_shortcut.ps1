# Creates a Start Menu shortcut for Lattice.
# Run from a PowerShell prompt in the project folder:
#     powershell -ExecutionPolicy Bypass -File .\make_shortcut.ps1

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw  = Join-Path $root 'Lattice.pyw'

# Windowless interpreter so no extra console flashes; the .pyw opens its own.
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { $pythonw = (Get-Command python.exe).Source }

$programs = [Environment]::GetFolderPath('Programs')   # ...\Start Menu\Programs
$lnk = Join-Path $programs 'Lattice.lnk'

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath       = $pythonw
$shortcut.Arguments        = '"' + $pyw + '"'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation     = $pythonw
$shortcut.Description       = 'Lattice - a quiet little grid keeper'
$shortcut.Save()

Write-Host "Shortcut created:" $lnk
