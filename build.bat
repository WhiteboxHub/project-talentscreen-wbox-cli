@echo off
REM Quick launch script for JobCLI development (Windows)

REM Ensure we are in the project root
cd %~dp0

REM Activate the virtual environment
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo Warning: No virtual environment found!
    goto run_cli
)

REM Playwright Chromium required for apply (matches this venv's playwright version)
echo Checking Playwright Chromium...
python -m playwright install chromium
if errorlevel 1 (
    echo.
    echo [WARN] playwright install chromium failed. Run manually after fixing network/SSL:
    echo   python -m playwright install chromium
    echo.
)

:run_cli
REM Run the CLI directly from source
echo Launching JobCLI...
set PYTHONPATH=src
python src\jobcli\cli\entry.py
pause
