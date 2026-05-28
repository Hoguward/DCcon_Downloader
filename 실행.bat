@echo off
title DCcon Downloader (Python GUI)
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [Error] Python is not installed.
    echo Install Python 3.10+ from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python -c "import requests, bs4, PIL" 2>nul
if errorlevel 1 (
    echo Installing required packages... ^(first time only^)
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet requests beautifulsoup4 pillow
    if errorlevel 1 (
        echo.
        echo [Error] Package installation failed.
        echo Run manually:  pip install requests beautifulsoup4 pillow
        echo.
        pause
        exit /b 1
    )
)

python "%~dp0dccon_gui.py"
if errorlevel 1 pause
