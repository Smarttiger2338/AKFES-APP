@echo off
setlocal
chcp 65001 >nul
title AKFES Admin PIN Reset
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\reset-admin-pin.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [OK] AKFES administrator PIN was reset.
  echo [NEXT] Open the License Manager and set a new PIN.
) else (
  echo [ERROR] AKFES administrator PIN reset failed. Exit code: %EXIT_CODE%
)

pause
exit /b %EXIT_CODE%
