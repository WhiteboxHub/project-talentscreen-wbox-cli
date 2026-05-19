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
)

REM Run the CLI directly from source
echo Launching JobCLI...
set PYTHONPATH=src
python src\jobcli\cli\entry.py
pause
