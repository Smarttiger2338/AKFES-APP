﻿@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if "%LICENSE_SECRET%"=="" (
    echo [ERROR] LICENSE_SECRET is not set.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Usage:
    echo   GENERATE_KEY_QUICK.bat 2w user1
    echo   GENERATE_KEY_QUICK.bat 1y dohyun
    pause
    exit /b 1
)

if "%~2"=="" (
    set "NAME=user"
) else (
    set "NAME=%~2"
)

%PY% "%~dp0tools/generate_license_key.py" "%~1" "%NAME%"
pause
