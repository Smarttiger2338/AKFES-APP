@echo off
setlocal
chcp 65001 >nul
title AKFES Local Config Reset
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\reset-local-config.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [OK] AKFES local server config was reset.
  echo [NEXT] Open the License Manager and set a new admin PIN.
) else (
  echo [ERROR] AKFES local server config reset failed. Exit code: %EXIT_CODE%
)

pause
exit /b %EXIT_CODE%
