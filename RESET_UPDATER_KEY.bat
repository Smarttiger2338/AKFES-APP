@echo off
setlocal
chcp 65001 >nul
title AKFES Updater Key Reset
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\reset-updater-key.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [OK] AKFES updater key reset finished successfully.
  echo [NEXT] Run BUILD_AKFES.bat again and enter the new password.
) else (
  echo [ERROR] AKFES updater key reset failed. Exit code: %EXIT_CODE%
)

pause
exit /b %EXIT_CODE%
