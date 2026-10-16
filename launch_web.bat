@echo off
setlocal
cd /d "%~dp0"

if exist "start.bat" (
    call start.bat %*
    exit /b %ERRORLEVEL%
)

python run_web.py %*
exit /b %ERRORLEVEL%
