@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   MinecraftAI - Starting Local Website
echo ============================================================
echo.

:: 1. Verify environment
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment (.venv) was not found.
    echo Please run 'setup.bat' first to install project dependencies.
    echo.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

:: 2. Check port availability to avoid duplicate instances
set SERVER_PORT=8000
if defined PORT set SERVER_PORT=%PORT%
set SERVER_HOST=127.0.0.1
if defined HOST set SERVER_HOST=%HOST%

python -c "import socket; s = socket.socket(); s.bind(('%SERVER_HOST%', %SERVER_PORT%)); s.close()" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Port %SERVER_PORT% is already in use on %SERVER_HOST%.
    echo MinecraftAI is likely already running, or another program is using port %SERVER_PORT%.
    echo Please close the existing server or specify a different port:
    echo   python run_web.py --port 8001 --open-browser
    echo.
    pause
    exit /b 1
)

:: 3. Check Ollama daemon status
python -c "import httpx; httpx.get('http://127.0.0.1:11434/api/tags', timeout=1.0)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [NOTICE] Ollama local service does not seem to be running on http://127.0.0.1:11434.
    echo Attempting to start Ollama in the background...
    start "" ollama serve >nul 2>&1
    timeout /t 2 /nobreak >nul 2>&1
)

echo Starting MinecraftAI web server at http://%SERVER_HOST%:%SERVER_PORT%
echo The website will automatically open in your default browser once ready.
echo Press Ctrl+C in this command window to stop the server.
echo.

python run_web.py --host %SERVER_HOST% --port %SERVER_PORT% --open-browser
exit /b %ERRORLEVEL%
