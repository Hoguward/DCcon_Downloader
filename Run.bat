@echo off
title DCcon Downloader
cd /d "%~dp0desktop"

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

python -c "import requests, bs4, fastapi, uvicorn, webview, win32clipboard" 2>nul
if errorlevel 1 (
    echo Installing required packages... ^(first time only^)
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [Error] Package installation failed.
        echo Run manually:  pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

python main.py
if errorlevel 1 pause
