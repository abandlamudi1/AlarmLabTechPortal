@echo off
REM Windows wrapper for start_day.py
REM Auto-detects Python installation

where python >nul 2>&1
if %errorlevel% equ 0 (
    python "%~dp0start_day.py" %*
) else (
    where python3 >nul 2>&1
    if %errorlevel% equ 0 (
        python3 "%~dp0start_day.py" %*
    ) else (
        echo Error: Python is not installed or not in PATH
        echo Please install Python from https://www.python.org/
        exit /b 1
    )
)
