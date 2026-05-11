# ──────────────────────────────────────────────────────────────────────
#  WboxCLI Global Installer — Windows (PowerShell)
#
#  Usage:
#    irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.ps1 | iex
#
#  What it does:
#    1. Clones (or updates) the repo into %USERPROFILE%\.jobcli\src
#    2. Creates a Python venv at %USERPROFILE%\.jobcli\venv
#    3. Installs the package + Playwright Chromium
#    4. Drops wboxcli.cmd + jobcli.cmd at %USERPROFILE%\.local\bin\
#    5. Adds %USERPROFILE%\.local\bin to the user PATH (if not already there)
#    6. Launches the interactive TUI
#
#  Uninstall:
#    irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/uninstall.ps1 | iex
# ──────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

# ── Config ───────────────────────────────────────────────────────────
$InstallDir    = Join-Path $env:USERPROFILE ".jobcli"
$SrcDir        = Join-Path $InstallDir "src"
$VenvDir       = Join-Path $InstallDir "venv"
$BinDir        = Join-Path $env:USERPROFILE ".local\bin"
$Wrapper       = Join-Path $BinDir "wboxcli.cmd"
$WrapperJobcli = Join-Path $BinDir "jobcli.cmd"
$RepoUrl       = "https://github.com/WhiteboxHub/wbox-cli.git"
$Branch        = if ($env:JOBCLI_BRANCH) { $env:JOBCLI_BRANCH } else { "dev" }

function Write-Step   { param($msg) Write-Host "[info]  $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host "[✓]    $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "[warn]  $msg" -ForegroundColor Yellow }
function Write-Fail   { param($msg) Write-Host "[✗]    $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     WboxCLI — Global Installer       ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Prerequisites ────────────────────────────────────────────
Write-Step "Checking prerequisites..."

# Python 3.10+
try {
    $pyVersion = & python --version 2>&1
    if ($pyVersion -match "Python (\d+)\.(\d+)") {
        $pyMajor = [int]$Matches[1]
        $pyMinor = [int]$Matches[2]
        if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
            Write-Fail "Python 3.10+ is required (found $pyVersion)."
        }
        Write-Ok "Python $($Matches[1]).$($Matches[2])"
    } else {
        Write-Fail "Could not determine Python version."
    }
} catch {
    Write-Fail "python is not installed. Install Python 3.10+ from https://python.org"
}

# Git
try {
    $null = & git --version 2>&1
    Write-Ok "git found"
} catch {
    Write-Fail "git is not installed. Install from https://git-scm.com"
}

# ── Step 2: Clone or update repo ─────────────────────────────────────
Write-Step "Setting up source at $SrcDir..."

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

if (Test-Path (Join-Path $SrcDir ".git")) {
    Write-Step "Existing installation found — pulling latest..."
    & git -C $SrcDir fetch origin $Branch --quiet 2>$null
    & git -C $SrcDir checkout $Branch --quiet 2>$null
    & git -C $SrcDir reset --hard "origin/$Branch" --quiet 2>$null
    Write-Ok "Updated to latest $Branch"
} else {
    & git clone --branch $Branch --depth 1 $RepoUrl $SrcDir --quiet 2>$null
    Write-Ok "Cloned $Branch branch"
}

# ── Step 3: Create venv and install ──────────────────────────────────
Write-Step "Setting up Python virtual environment..."

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
    & python -m venv $VenvDir
    Write-Ok "Created venv at $VenvDir"
} else {
    Write-Ok "Venv already exists"
}

Write-Step "Installing wboxcli and dependencies (this may take a minute)..."

& $VenvPip install --upgrade pip --quiet 2>$null
& $VenvPip install -e $SrcDir --quiet 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Warn "pip install had issues — retrying with verbose output..."
    & $VenvPip install -e $SrcDir
}

Write-Ok "wboxcli installed"

# ── Step 4: Install Playwright browsers ──────────────────────────────
Write-Step "Installing Playwright Chromium browser..."

try {
    & $VenvPython -m playwright install chromium 2>$null
    Write-Ok "Playwright Chromium ready"
} catch {
    Write-Warn "Playwright browser install had issues — run 'wboxcli doctor' to verify."
}

# ── Step 5: Create global wrapper scripts ─────────────────────────────
Write-Step "Creating global commands at $BinDir..."

if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

# Primary command: wboxcli (interactive TUI when bare, CLI with args)
$WboxcliContent = @"
@echo off
REM WboxCLI global wrapper — calls the managed venv transparently.
set "JOBCLI_VENV=%USERPROFILE%\.jobcli\venv"

if not exist "%JOBCLI_VENV%\Scripts\python.exe" (
    echo Error: WboxCLI installation not found at %JOBCLI_VENV%
    echo Re-install with: irm https://raw.githubusercontent.com/WhiteboxHub/wbox-cli/dev/scripts/install.ps1 ^| iex
    exit /b 1
)

"%JOBCLI_VENV%\Scripts\wboxcli.exe" %*
"@
Set-Content -Path $Wrapper -Value $WboxcliContent -Encoding ASCII

# Alias: jobcli (direct Typer CLI for scripting)
$JobcliContent = @"
@echo off
set "JOBCLI_VENV=%USERPROFILE%\.jobcli\venv"
"%JOBCLI_VENV%\Scripts\jobcli.exe" %*
"@
Set-Content -Path $WrapperJobcli -Value $JobcliContent -Encoding ASCII

Write-Ok "Commands created: wboxcli (interactive) + jobcli (direct CLI)"

# ── Step 6: Ensure ~/.local/bin is on user PATH ───────────────────────
Write-Step "Checking PATH..."

$CurrentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($CurrentUserPath -notlike "*$BinDir*") {
    Write-Step "Adding $BinDir to user PATH..."
    $NewPath = "$BinDir;$CurrentUserPath"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    # Also update the current session
    $env:Path = "$BinDir;$env:Path"
    Write-Ok "Added to user PATH"
    $NeedsRestart = $true
} else {
    Write-Ok "$BinDir already on PATH"
    $NeedsRestart = $false
}

# ── Step 7: Copy .env template if no .env exists ─────────────────────
$EnvFile     = Join-Path $InstallDir ".env"
$EnvTemplate = Join-Path $SrcDir ".env.template"

if (-not (Test-Path $EnvFile) -and (Test-Path $EnvTemplate)) {
    Copy-Item $EnvTemplate $EnvFile
    Write-Step "Created default config at $EnvFile — edit it with your API keys."
}

# ── Done! ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║       Installation Complete! 🎉      ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Install dir  : $InstallDir" -ForegroundColor Cyan
Write-Host "  Command      : wboxcli" -ForegroundColor Cyan
Write-Host ""

if ($NeedsRestart) {
    Write-Host "  → Restart your terminal for PATH changes to take effect." -ForegroundColor Yellow
    Write-Host ""
}

# ── Auto-launch interactive TUI ──────────────────────────────────────
Write-Host "  Launching WboxCLI..." -ForegroundColor White
Write-Host ""

$VenvWboxcli = Join-Path $VenvDir "Scripts\wboxcli.exe"
if (Test-Path $VenvWboxcli) {
    & $VenvWboxcli
} else {
    Write-Host "  Next steps:" -ForegroundColor White
    Write-Host "    1. Restart your terminal" -ForegroundColor Cyan
    Write-Host "    2. Type: wboxcli" -ForegroundColor Cyan
    Write-Host ""
}
