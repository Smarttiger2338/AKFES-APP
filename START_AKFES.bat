@echo off
setlocal
chcp 65001 >nul
title AKFES v2 One-Click Launcher
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-akfes.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] AKFES 실행에 실패했습니다. 오류 코드: %EXIT_CODE%
  pause
)

exit /b %EXIT_CODE%
