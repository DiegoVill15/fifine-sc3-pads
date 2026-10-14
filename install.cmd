@echo off
cd /d "%~dp0"
echo Creating the Python environment in .venv ...
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m venv .venv) else (python -m venv .venv)
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Python 3.10 or newer is required: https://www.python.org/downloads/
    echo During setup, check "Add python.exe to PATH".
    pause
    exit /b 1
)
echo Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo Installing dependencies failed.
    pause
    exit /b 1
)
echo.
echo Done. Open "SC3 Pads.cmd" to start.
pause
