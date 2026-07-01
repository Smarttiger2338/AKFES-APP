﻿@echo off
setlocal
chcp 65001 >nul
title AKFES One-Click Launcher

cd /d "%~dp0"

echo ==========================================
echo  AKFES One-Click Launcher
echo ==========================================
echo.

if "%LICENSE_SECRET%"=="" (
    echo [ERROR] LICENSE_SECRET is not set.
    echo Example:
    echo set LICENSE_SECRET=your_long_random_license_secret
    pause
    exit /b 1
)

if "%SESSION_SECRET%"=="" (
    echo [ERROR] SESSION_SECRET is not set.
    echo Example:
    echo set SESSION_SECRET=your_long_random_session_secret
    pause
    exit /b 1
)

if "%AKFES_SERVER_URL%"=="" (
    set "AKFES_SERVER_URL=http://127.0.0.1:5000"
)

if "%ALLOWED_ORIGINS%"=="" (
    set "ALLOWED_ORIGINS=null,http://127.0.0.1:8080,http://localhost:8080"
)

if "%SERVER_HOST%"=="" (
    set "SERVER_HOST=127.0.0.1"
)

if "%SERVER_PORT%"=="" (
    set "SERVER_PORT=5000"
)

if not exist "%~dp0AKFES-Server\server\server.py" (
    echo [ERROR] AKFES-Server\server\server.py was not found.
    echo Extract the ZIP first, then run this file.
    pause
    exit /b 1
)

if not exist "%~dp0AKFES-Client\electron\main.js" (
    echo [ERROR] AKFES-Client\electron\main.js was not found.
    echo Extract the ZIP first, then run this file.
    pause
    exit /b 1
)

echo [INFO] Starting AKFES Server...
start "AKFES Server" /D "%~dp0AKFES-Server" cmd /k call START_SERVER.bat

echo [INFO] Waiting for server startup...
timeout /t 5 /nobreak >nul

echo [INFO] Starting AKFES Electron Client...
start "AKFES Client" /D "%~dp0AKFES-Client" cmd /k call START_ELECTRON_DEV.bat

echo.
echo [INFO] AKFES launch commands sent.
pause
