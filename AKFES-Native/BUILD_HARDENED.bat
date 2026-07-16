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

python -m nuitka ^
  --standalone ^
  --onefile ^
  --enable-plugin=pyside6 ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\akfes.ico ^
  --company-name=Smarttiger2338 ^
  --product-name=AKFES ^
  --file-description="Arduino Keypad File Encryption System" ^
  --file-version=1.0.0.0 ^
  --product-version=1.0.0.0 ^
  --lto=yes ^
  --python-flag=no_docstrings ^
  --output-dir=dist-hardened ^
  --output-filename=AKFES.exe ^
  secure_main.py || exit /b 1

if defined AKFES_SIGN_CERT (
  where signtool >nul 2>nul
  if not errorlevel 1 (
    signtool sign /fd SHA256 /f "%AKFES_SIGN_CERT%" /p "%AKFES_SIGN_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "dist-hardened\AKFES.exe"
  )
)

echo.
echo Hardened build complete: dist-hardened\AKFES.exe
pause
endlocal
