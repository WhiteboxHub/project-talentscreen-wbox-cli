# Repair wboxcli PATH and wrapper without wiping login (jobcli.db).
# Usage: irm .../repair-wboxcli-path.ps1 | iex
#    or: powershell -File repair-wboxcli-path.ps1

$ErrorActionPreference = "Stop"
$InstallDir = Join-Path $env:USERPROFILE ".jobcli"
$VenvPython = Join-Path $InstallDir "venv\Scripts\python.exe"
$BinDir = Join-Path $env:USERPROFILE ".local\bin"
$Wrapper = Join-Path $BinDir "wboxcli.cmd"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[FAIL] WboxCLI venv not found. Run the full installer first." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
@'
@echo off
set "JOBCLI_PY=%USERPROFILE%\.jobcli\venv\Scripts\python.exe"
if not exist "%JOBCLI_PY%" (
    echo Error: WboxCLI not found. Re-run the installer.
    exit /b 1
)
"%JOBCLI_PY%" -m jobcli.cli.entry %*
'@ | Set-Content -Path $Wrapper -Encoding ASCII

& $VenvPython -c "from jobcli.cli.launcher import remove_stale_global_shims; remove_stale_global_shims()" 2>$null | Out-Null

$current = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = @($current -split ';' | Where-Object { $_ -and ($_ -ne $BinDir) })
$newPath = "$BinDir;" + ($parts -join ';')
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")
$env:Path = "$BinDir;$env:Path"

Write-Host "[OK] wboxcli repaired at $Wrapper" -ForegroundColor Green
Write-Host "     Restart PowerShell, then run:  wboxcli" -ForegroundColor Cyan
