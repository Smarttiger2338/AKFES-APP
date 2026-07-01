﻿@echo off
setlocal
chcp 65001 >nul
title AKFES Server

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
    echo Example:
    echo set LICENSE_SECRET=your_long_random_secret
    pause
    exit /b 1
)

if "%SESSION_SECRET%"=="" (
    echo [ERROR] SESSION_SECRET is not set.
    echo Example:
    echo set SESSION_SECRET=your_long_random_secret_2
    pause
    exit /b 1
)

echo ==========================================
echo  AKFES - SERVER
echo ==========================================
echo.
echo [INFO] Python command: %PY%
%PY% --version

echo.
echo [INFO] Installing/checking server requirements...
%PY% -m pip install -r "%~dp0server/requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo [INFO] Starting AKFES Server...
%PY% "%~dp0server/server.py"

echo.
echo [INFO] Server stopped.
pause
