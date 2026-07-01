﻿@echo off
setlocal
chcp 65001 >nul
title AKFES Demo Launcher

cd /d "%~dp0"

echo ==========================================
echo  AKFES Demo Launcher
echo ==========================================
echo [WARNING] This launcher uses demo secrets.
echo [WARNING] Do not use this for real deployment.
echo.

set "LICENSE_SECRET=AKFES_DEMO_LICENSE_SECRET_CHANGE_ME_2026"
set "SESSION_SECRET=AKFES_DEMO_SESSION_SECRET_CHANGE_ME_2026"
set "AKFES_SERVER_URL=http://127.0.0.1:5000"
set "ALLOWED_ORIGINS=null,http://127.0.0.1:8080,http://localhost:8080"
set "SERVER_HOST=127.0.0.1"
set "SERVER_PORT=5000"

start "AKFES Server" /D "%~dp0AKFES-Server" cmd /k call START_SERVER.bat
timeout /t 5 /nobreak >nul
start "AKFES Client" /D "%~dp0AKFES-Client" cmd /k call START_ELECTRON_DEV.bat

echo.
echo Demo key:
echo   Run GENERATE_DEMO_KEY.bat
echo.
pause
