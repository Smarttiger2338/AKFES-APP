﻿@echo off
setlocal
chcp 65001 >nul
title AKFES License Key Generator

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
    echo It must be the same as the server LICENSE_SECRET.
    pause
    exit /b 1
)

echo ==========================================
echo  AKFES License Key Generator
echo ==========================================
echo Lifetime examples: 3h, 1d, 2w, 3m, 1y
echo.

set /p LIFE=Enter lifetime:
set /p NAME=Enter user name:

if "%LIFE%"=="" (
    echo [ERROR] Lifetime is empty.
    pause
    exit /b 1
)

if "%NAME%"=="" (
    set "NAME=user"
)

%PY% "%~dp0tools/generate_license_key.py" "%LIFE%" "%NAME%"
pause
