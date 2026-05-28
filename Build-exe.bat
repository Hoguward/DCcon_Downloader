@echo off
title Build DCcon-Downloader.exe
cd /d "%~dp0"

echo ===================================================
echo  Building DCcon-Downloader.exe with PyInstaller
echo ===================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [Error] Python is not installed.
    echo Install Python 3.10+ from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Checking dependencies...
python -c "import requests, bs4, PIL" 2>nul
if errorlevel 1 (
    echo Installing runtime dependencies...
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet requests beautifulsoup4 pillow
)

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install --quiet pyinstaller
    if errorlevel 1 (
        echo [Error] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo [2/3] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__

echo [3/3] Building... ^(this may take 1-3 minutes^)
python -m PyInstaller dccon_gui.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [Error] Build failed. See messages above.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo  Done! The .exe is at:
echo    %~dp0dist\DCcon-Downloader.exe
echo ===================================================
echo.

REM Clean intermediate build dir, keep dist/
if exist build rmdir /s /q build
if exist __pycache__ rmdir /s /q __pycache__

REM Offer to open dist folder
choice /c YN /m "Open the dist folder now"
if errorlevel 2 goto :end
explorer "%~dp0dist"

:end
pause
