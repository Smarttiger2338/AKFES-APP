﻿@echo off
setlocal
chcp 65001 >nul
title AKFES Electron Client

cd /d "%~dp0"

if "%AKFES_SERVER_URL%"=="" (
    echo [INFO] AKFES_SERVER_URL is not set.
    echo [INFO] Using local API server: http://127.0.0.1:5000
    set "AKFES_SERVER_URL=http://127.0.0.1:5000"
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm was not found.
    echo Install Node.js first.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo [INFO] Installing npm packages...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

echo [INFO] Starting AKFES Electron Client...
echo [INFO] API server URL: %AKFES_SERVER_URL%
npm start

pause
