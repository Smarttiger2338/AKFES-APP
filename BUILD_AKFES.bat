@echo off
setlocal
chcp 65001 >nul
title AKFES v2 Build Helper
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-akfes.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [OK] AKFES build helper finished successfully.
) else (
  echo [ERROR] AKFES build helper failed. Exit code: %EXIT_CODE%
)

pause
exit /b %EXIT_CODE%
