﻿@echo off
setlocal
chcp 65001 >nul
title AKFES Protected Server

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo [ERROR] Python was not found.
        echo Install Python and check "Add Python to PATH".
        pause
        exit /b 1
    )
)

if "%LICENSE_SECRET%"=="" (
    echo [ERROR] LICENSE_SECRET is not set.
    pause
    exit /b 1
)

if "%SESSION_SECRET%"=="" (
    echo [ERROR] SESSION_SECRET is not set.
    pause
    exit /b 1
)

if "%SERVER_HOST%"=="" set "SERVER_HOST=127.0.0.1"
if "%SERVER_PORT%"=="" set "SERVER_PORT=5000"
if "%SERVER_THREADS%"=="" set "SERVER_THREADS=4"

echo ==========================================
echo  AKFES - PROTECTED SERVER
echo ==========================================
echo.
echo [INFO] Installing/checking server requirements...
%PY% -m pip install -r "%~dp0server/requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo [INFO] Closed API surface enabled.
echo [INFO] Device-bound signed requests enabled.
echo [INFO] Production WSGI server enabled.
echo [INFO] Listening on %SERVER_HOST%:%SERVER_PORT%
echo.
%PY% "%~dp0server/production_server.py"

echo.
echo [INFO] Server stopped.
pause
