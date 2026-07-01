﻿@echo off
setlocal
chcp 65001 >nul
title AKFES Demo Key Generator

cd /d "%~dp0AKFES-Server"

set "LICENSE_SECRET=AKFES_DEMO_LICENSE_SECRET_CHANGE_ME_2026"

call GENERATE_KEY_QUICK.bat 1d demo
