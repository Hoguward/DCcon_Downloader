@echo off
title DCcon Downloader - Publish Release
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ===================================================
echo  Publish DCcon-Downloader.exe to GitHub Releases
echo ===================================================
echo.

REM ---- Check prerequisites ----
where gh >nul 2>nul
if errorlevel 1 (
    echo [Error] gh CLI is not installed or not on PATH.
    echo Install from: https://cli.github.com/
    pause & exit /b 1
)

gh auth status >nul 2>nul
if errorlevel 1 (
    echo You need to authenticate with GitHub first.
    gh auth login
    if errorlevel 1 (
        echo [Error] gh auth login failed.
        pause & exit /b 1
    )
)

REM ---- Check that we are inside a gh-tracked repo ----
gh repo view >nul 2>nul
if errorlevel 1 (
    echo [Error] This folder is not a GitHub repo yet.
    echo Run setup-repo.bat first.
    pause & exit /b 1
)

REM ---- Check that the .exe exists ----
set "EXE_PATH=%~dp0dist\DCcon-Downloader.exe"
if not exist "!EXE_PATH!" (
    echo [Error] Built .exe not found at:
    echo   !EXE_PATH!
    echo.
    echo Run Build-exe.bat first to build the executable.
    pause & exit /b 1
)

REM ---- Show file info ----
echo Found:
for %%I in ("!EXE_PATH!") do (
    echo   File: %%~nxI
    echo   Size: %%~zI bytes
)
echo.

REM ---- Ask for version tag ----
set "DEFAULT_TAG=v1.0.0"
REM Suggest the next version based on the latest existing tag
for /f "tokens=*" %%T in ('gh release list --limit 1 --json tagName -q ".[0].tagName" 2^>nul') do (
    set "LATEST=%%T"
)
if defined LATEST (
    echo Latest release tag: !LATEST!
    set "DEFAULT_TAG=!LATEST!"
)
set /p TAG="Enter release tag [default: !DEFAULT_TAG!]: "
if "!TAG!"=="" set "TAG=!DEFAULT_TAG!"

REM ---- Ask for release title ----
set "DEFAULT_TITLE=DCcon Downloader !TAG!"
set /p TITLE="Release title [default: !DEFAULT_TITLE!]: "
if "!TITLE!"=="" set "TITLE=!DEFAULT_TITLE!"

REM ---- Ask for release notes ----
echo.
echo Release notes (optional). Press Enter to skip, or type one line:
set /p NOTES="> "
if "!NOTES!"=="" set "NOTES=See README for details."

REM ---- Check if tag already exists ----
gh release view "!TAG!" >nul 2>nul
if not errorlevel 1 (
    echo.
    echo Release "!TAG!" already exists.
    choice /c YN /n /m "Upload .exe to existing release instead [Y/N]? "
    if errorlevel 2 (
        echo Cancelled. To create a new release, choose a different tag.
        pause & exit /b 0
    )
    echo Uploading to existing release...
    gh release upload "!TAG!" "!EXE_PATH!" --clobber
    if errorlevel 1 (
        echo [Error] Upload failed.
        pause & exit /b 1
    )
    goto :show_result
)

REM ---- Create new release ----
echo.
echo Creating release "!TAG!" and uploading .exe...
gh release create "!TAG!" "!EXE_PATH!" --title "!TITLE!" --notes "!NOTES!"
if errorlevel 1 (
    echo [Error] gh release create failed.
    pause & exit /b 1
)

:show_result
echo.
echo ===================================================
echo  Done!
echo ===================================================
echo.
gh release view "!TAG!" --web
echo.
pause
