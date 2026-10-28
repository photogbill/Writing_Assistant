@echo off
REM ============================================================================
REM  untrack_generated.bat - run ONCE, from this folder.
REM
REM  The review of 2026-10-28 found 115 .pyc files and the egg-info folder
REM  tracked in git, with no .gitignore. This takes them OUT OF THE INDEX
REM  only: nothing on disk is deleted, and .gitignore keeps them out from
REM  now on. It commits nothing - look at "git status", then commit and push
REM  the way you always do.
REM ============================================================================
setlocal enableextensions
cd /d "%~dp0"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERR] This folder is not a git working tree.
    endlocal
    exit /b 1
)

echo(
echo === Untracking generated files ===
for /f "delims=" %%F in ('git ls-files -- "*.pyc" "*.pyo"') do (
    git rm --cached --quiet -- "%%F"
)
for /f "delims=" %%D in ('git ls-files -- "*.egg-info/*"') do (
    git rm --cached --quiet -- "%%D"
)
echo(
echo Done. Still on disk, no longer tracked. Now:
echo     git status
echo     git add .gitignore
echo and commit when it looks right.
endlocal
exit /b 0
