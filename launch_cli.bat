@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not found in your PATH.
    echo Please install Python 3.10+ from https://www.python.org/ and ensure Python is added to your PATH.
    exit /b 1
)

python run_pipeline.py %*
exit /b %ERRORLEVEL%
