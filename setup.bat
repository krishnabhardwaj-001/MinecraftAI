@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   MinecraftAI - Beginner-Friendly Local Setup
echo ============================================================
echo.

:: 1. Check Python installation
echo [1/4] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not found in your PATH.
    echo Please install Python 3.10 or newer from https://www.python.org/
    echo During installation, be sure to check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo       Found Python %PY_VER%

:: 2. Set up virtual environment
echo.
echo [2/4] Setting up Python virtual environment (.venv)...
if not exist ".venv\Scripts\activate.bat" (
    echo       Creating virtual environment in .venv...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment in .venv.
        echo.
        pause
        exit /b 1
    )
) else (
    echo       Reusing existing virtual environment in .venv.
)

call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    echo.
    pause
    exit /b 1
)

echo       Installing/updating dependencies (pip install -e .)...
python -m pip install --upgrade pip --quiet
python -m pip install -e . --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install project dependencies.
    echo.
    pause
    exit /b 1
)
echo       Dependencies installed successfully.

:: 3. Check Ollama and cloud model
echo.
echo [3/4] Checking Ollama installation...
ollama --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Ollama is not installed or not found in PATH.
    echo ------------------------------------------------------------
    echo To use Ollama Cloud inference (zero local model weights):
    echo 1. Download and install Ollama from: https://ollama.com/download
    echo 2. After installing, open a new command prompt and run:
    echo      ollama signin
    echo 3. Register the cloud model pointer (384 bytes, no weights):
    echo      ollama pull gpt-oss:120b-cloud
    echo ------------------------------------------------------------
) else (
    for /f "tokens=*" %%o in ('ollama --version 2^>^&1') do set OLLAMA_VER=%%o
    echo       Found %OLLAMA_VER%
    echo       Checking cloud model pointer (gpt-oss:120b-cloud)...
    echo       (This only registers the cloud model manifest; no large model weights are stored locally)
    ollama pull gpt-oss:120b-cloud
    if %ERRORLEVEL% neq 0 (
        echo [NOTICE] If the cloud model pull failed, please ensure you are signed in:
        echo          ollama signin
    ) else (
        echo       Cloud model gpt-oss:120b-cloud is ready!
    )
)

:: 4. Local configuration (no API key required)
echo.
echo [4/4] Checking configuration...
if not exist ".env" (
    echo       Creating default local configuration (.env)...
    (
        echo # MinecraftAI Local Configuration
        echo ENVIRONMENT=development
        echo HOST=127.0.0.1
        echo PORT=8000
        echo LLM_PROVIDER=ollama
        echo OLLAMA_HOST=http://127.0.0.1:11434
        echo OLLAMA_MODEL=gpt-oss:120b-cloud
        echo # Notice: No API key needed! Ollama sign-in handles authentication.
    ) > .env
    echo       Created .env with local sign-in defaults (no API key required).
) else (
    echo       Preserving existing .env configuration.
)

echo.
echo ============================================================
echo   Setup completed successfully!
echo   Next steps:
echo   1. If you haven't signed in to Ollama yet, run:
echo        ollama signin
echo   2. Run 'start.bat' to launch the MinecraftAI website!
echo ============================================================
echo.
exit /b 0
