@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv || exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || exit /b 1
pip install -r requirements.txt pillow nuitka ordered-set zstandard || exit /b 1

python generate_icon.py || exit /b 1

set "RELEASE_KEY_DIR=%LOCALAPPDATA%\AKFES-Builder"
set "RELEASE_PRIVATE_KEY=%RELEASE_KEY_DIR%\release_private.pem"
if not exist "%RELEASE_KEY_DIR%" mkdir "%RELEASE_KEY_DIR%"
python release_signing.py prepare --private "%RELEASE_PRIVATE_KEY%" --public-module release_public_key.py || exit /b 1

python -m nuitka ^
  --standalone ^
  --onefile ^
  --enable-plugin=pyside6 ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\akfes.ico ^
  --company-name=Smarttiger2338 ^
  --product-name=AKFES ^
  --file-description="Arduino Keypad File Encryption System" ^
  --file-version=2.0.0.0 ^
  --product-version=2.0.0.0 ^
  --lto=yes ^
  --python-flag=no_docstrings ^
  --nofollow-import-to=tkinter,unittest,test,pydoc ^
  --output-dir=dist-hardened ^
  --output-filename=AKFES.exe ^
  secure_main.py || exit /b 1

if defined AKFES_SIGN_CERT (
  where signtool >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] AKFES_SIGN_CERT is set but signtool was not found.
    exit /b 1
  )
  signtool sign /fd SHA256 /f "%AKFES_SIGN_CERT%" /p "%AKFES_SIGN_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "dist-hardened\AKFES.exe" || exit /b 1
)

python release_signing.py sign --private "%RELEASE_PRIVATE_KEY%" --exe "dist-hardened\AKFES.exe" --manifest "dist-hardened\AKFES.manifest.json" || exit /b 1

if not exist "dist-hardened\AKFES.exe" exit /b 1
if not exist "dist-hardened\AKFES.manifest.json" exit /b 1

echo.
echo Hardened build complete:
echo   dist-hardened\AKFES.exe
echo   dist-hardened\AKFES.manifest.json
echo.
echo Keep both files together. The signing private key is stored outside the repository:
echo   %RELEASE_PRIVATE_KEY%
pause
endlocal
