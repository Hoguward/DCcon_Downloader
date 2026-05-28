@echo off
title DCcon Downloader - Fix Commit Author
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ===================================================
echo  Re-author all commits and force push
echo ===================================================
echo.
echo This script will:
echo   1) Set local git user.name / user.email to your target account
echo   2) Rewrite ALL commits in this repo to use that author
echo   3) Force-push to GitHub (overwrites remote history)
echo.
echo WARNING: Force push rewrites history on GitHub.
echo Safe only if you are the sole contributor to this repo.
echo.
pause

REM ---- Check prerequisites ----
where git >nul 2>nul
if errorlevel 1 (
    echo [Error] git is not installed or not on PATH.
    pause & exit /b 1
)

if not exist .git (
    echo [Error] No git repo found in this folder.
    echo Run setup-repo.bat first.
    pause & exit /b 1
)

REM ---- Show current author ----
echo Current author info on the latest commit:
git log -1 --format="  Name : %%an%%n  Email: %%ae"
echo.

REM ---- Get target name + email ----
set /p NEW_NAME="Enter the correct git user.name (display name): "
if "!NEW_NAME!"=="" (
    echo [Error] Name cannot be empty.
    pause & exit /b 1
)

set /p NEW_EMAIL="Enter the correct git user.email (must be registered on GitHub): "
if "!NEW_EMAIL!"=="" (
    echo [Error] Email cannot be empty.
    pause & exit /b 1
)

echo.
echo You entered:
echo   Name : !NEW_NAME!
echo   Email: !NEW_EMAIL!
echo.
choice /c YN /n /m "Proceed [Y/N]? "
if errorlevel 2 (
    echo Cancelled.
    pause & exit /b 0
)

REM ---- Set local config ----
echo.
echo [1/3] Setting local git config...
git config user.name "!NEW_NAME!"
git config user.email "!NEW_EMAIL!"

REM ---- Rewrite history ----
echo.
echo [2/3] Rewriting commit history...
echo This uses git filter-branch (legacy but built-in).

REM Save name/email to environment for filter-branch
set "GIT_AUTHOR_NAME=!NEW_NAME!"
set "GIT_AUTHOR_EMAIL=!NEW_EMAIL!"
set "GIT_COMMITTER_NAME=!NEW_NAME!"
set "GIT_COMMITTER_EMAIL=!NEW_EMAIL!"

git filter-branch -f --env-filter "GIT_AUTHOR_NAME='!NEW_NAME!'; GIT_AUTHOR_EMAIL='!NEW_EMAIL!'; GIT_COMMITTER_NAME='!NEW_NAME!'; GIT_COMMITTER_EMAIL='!NEW_EMAIL!';" --tag-name-filter cat -- --branches --tags
if errorlevel 1 (
    echo.
    echo [Error] filter-branch failed.
    pause & exit /b 1
)

echo.
echo Verifying rewrite:
git log -1 --format="  Name : %%an%%n  Email: %%ae"
echo.

REM ---- Force push ----
echo [3/3] Force pushing to GitHub...
git remote -v
echo.
choice /c YN /n /m "Force push to origin now [Y/N]? "
if errorlevel 2 (
    echo Skipped push. You can push manually later with:
    echo   git push --force-with-lease --all
    echo   git push --force-with-lease --tags
    pause & exit /b 0
)

git push --force-with-lease --all
if errorlevel 1 (
    echo [Error] push --all failed.
    pause & exit /b 1
)
git push --force-with-lease --tags 2>nul

echo.
echo ===================================================
echo  Done!
echo ===================================================
echo.
echo Refresh the GitHub repo page - the old contributor
echo should disappear within a few seconds, and the
echo Contributors list should now only show your target
echo account.
echo.
echo If the old account is still listed:
echo   - Wait ~1 minute for GitHub to update
echo   - Make sure the email you entered is registered
echo     on the TARGET GitHub account (Settings -> Emails)
echo.
gh repo view --web 2>nul
pause
