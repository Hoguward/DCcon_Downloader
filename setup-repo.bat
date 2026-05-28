@echo off
title DCcon Downloader - GitHub Repo Setup
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ===================================================
echo  DCcon Downloader - GitHub Repo Setup
echo ===================================================
echo.
echo This script will:
echo   1) Initialize a local git repository here
echo   2) Create a new GitHub repo via gh CLI
echo   3) Push the initial commit
echo.
echo Make sure you've run "gh auth login" at least once.
echo.
pause

REM ---- Check prerequisites ----
where git >nul 2>nul
if errorlevel 1 (
    echo [Error] git is not installed or not on PATH.
    pause & exit /b 1
)

where gh >nul 2>nul
if errorlevel 1 (
    echo [Error] gh CLI is not installed or not on PATH.
    echo Install from: https://cli.github.com/
    pause & exit /b 1
)

REM ---- Verify gh auth ----
echo.
echo Checking GitHub authentication...
gh auth status >nul 2>nul
if errorlevel 1 (
    echo You need to authenticate with GitHub first.
    echo Running: gh auth login
    echo.
    gh auth login
    if errorlevel 1 (
        echo [Error] gh auth login failed.
        pause & exit /b 1
    )
)

REM ---- Initialize git repo if needed ----
echo.
if exist .git (
    echo Existing git repo detected - skipping init.
) else (
    echo [1/4] Initializing git repository...
    git init -b main
    if errorlevel 1 (
        echo [Error] git init failed.
        pause & exit /b 1
    )
)

REM ---- Configure user if not set ----
git config user.name >nul 2>nul || (
    set /p GIT_NAME="Enter your name for git commits: "
    git config user.name "!GIT_NAME!"
)
git config user.email >nul 2>nul || (
    set /p GIT_EMAIL="Enter your GitHub email for git commits: "
    git config user.email "!GIT_EMAIL!"
)

REM ---- Stage and commit ----
echo.
echo [2/4] Staging files...
git add .
git status --short

echo.
echo [3/4] Creating initial commit...
git diff --cached --quiet
if not errorlevel 1 (
    echo Nothing to commit. Already committed?
) else (
    git commit -m "Initial commit: DCcon Downloader Python GUI"
    if errorlevel 1 (
        echo [Error] commit failed.
        pause & exit /b 1
    )
)

REM ---- Ask repo name ----
echo.
set "DEFAULT_NAME=dccon-downloader-py"
set /p REPO_NAME="GitHub repo name [default: %DEFAULT_NAME%]: "
if "!REPO_NAME!"=="" set "REPO_NAME=%DEFAULT_NAME%"

REM ---- Ask visibility ----
echo.
echo Choose repo visibility:
echo   1) Public  (recommended for open source)
echo   2) Private
choice /c 12 /n /m "Select [1-2]: "
if errorlevel 2 (set "VIS=--private") else (set "VIS=--public")

REM ---- Create + push ----
echo.
echo [4/4] Creating GitHub repo and pushing...
gh repo create "!REPO_NAME!" !VIS! --source=. --remote=origin --push
if errorlevel 1 (
    echo.
    echo [Error] gh repo create failed.
    echo If the repo already exists, you can manually add the remote:
    echo     git remote add origin https://github.com/^<your-username^>/!REPO_NAME!.git
    echo     git push -u origin main
    pause & exit /b 1
)

echo.
echo ===================================================
echo  Success!
echo ===================================================
echo.
gh repo view --web
echo.
pause
