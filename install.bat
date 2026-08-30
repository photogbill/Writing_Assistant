@echo off
REM ============================================================================
REM  Writing Workshop - standalone install.
REM
REM  You almost certainly do not need this. ATK installs the engine itself:
REM      get_engines.bat /writing        (from the ATK folder)
REM  which prefers this working tree over a clone and installs it into
REM  envs\atk_core, so ATK and the engine share one interpreter.
REM
REM  This script is for using the engine on its own - from a terminal, from
REM  another host, or to run its tests. It has ZERO runtime dependencies, so
REM  "install" is really just making the package importable.
REM ============================================================================
setlocal enableextensions
set "ROOT=%~dp0"
set "PY=python"
if not "%~1"=="" set "PY=%~1"

echo(
echo === Writing Workshop ===
call %PY% --version
if errorlevel 1 (
    echo [ERR] No Python on PATH. Pass one as the first argument:
    echo         install.bat "C:\path\to\python.exe"
    endlocal
    exit /b 1
)

echo(
echo Installing (editable, so a git pull is the whole update path)...
call %PY% -m pip install -e "%ROOT%." -q
if errorlevel 1 (
    echo(
    echo [--] pip declined. That happens on Python 3.10, where the manifest
    echo      declares requires-python ^>= 3.11 although the code runs fine.
    echo      The package has no dependencies, so a path entry IS the install:
    echo          set PYTHONPATH=%ROOT%
    echo      ATK does this for itself in atk\core\writing.py.
) else (
    echo   [OK] installed.
)

echo(
echo Running the suite (no model, no Qt, no network)...
pushd "%ROOT%"
call %PY% -m unittest discover -s tests -t tests
popd
echo(
endlocal
exit /b 0
