# ──────────────────────────────────────────────────────────────────────
#  JobCLI Global Uninstaller — Windows (PowerShell)
#
#  Usage:
#    irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/mahi_dev2/scripts/uninstall.ps1 | iex
# ──────────────────────────────────────────────────────────────────────

$InstallDir = Join-Path $env:USERPROFILE ".jobcli"
$Wrapper    = Join-Path $env:USERPROFILE ".local\bin\jobcli.cmd"

Write-Host ""
Write-Host "JobCLI — Uninstaller" -ForegroundColor Red
Write-Host ""

$confirm = Read-Host "This will delete $InstallDir and $Wrapper. Continue? [y/N]"
if ($confirm -notmatch "^[Yy]$") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# Remove wrapper
if (Test-Path $Wrapper) {
    Remove-Item -Force $Wrapper
    Write-Host "[✓] Removed $Wrapper" -ForegroundColor Green
} else {
    Write-Host "[—] Wrapper not found at $Wrapper" -ForegroundColor Yellow
}

# Remove install dir
if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
    Write-Host "[✓] Removed $InstallDir" -ForegroundColor Green
} else {
    Write-Host "[—] Install directory not found at $InstallDir" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "JobCLI has been uninstalled." -ForegroundColor Green
Write-Host "Note: The PATH entry was left intact — remove it manually from System Environment Variables if you wish." -ForegroundColor Yellow
Write-Host ""
