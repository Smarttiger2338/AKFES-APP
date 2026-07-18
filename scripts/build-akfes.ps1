param(
    [ValidateSet("all", "web", "server", "installer")]
    [string]$Mode = "all",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $PSScriptRoot
Set-Location $rootDir

$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if ((Test-Path (Join-Path $cargoBin "cargo.exe")) -and ($env:Path -notlike "*$cargoBin*")) {
    $env:Path = "$cargoBin;$env:Path"
}

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Require-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. $InstallHint"
    }
}

function Invoke-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Get-JsonVersion([string]$Path) {
    return (Get-Content -Raw $Path | ConvertFrom-Json).version
}

Require-Command "npm" "Install Node.js LTS."
if ($Mode -ne "web" -or -not $SkipTests) {
    Require-Command "py" "Install Python 3.11 or newer."
}
if ($Mode -eq "all" -or $Mode -eq "installer") {
    Require-Command "cargo" "Install Rust and the Tauri Windows build tools."
    Require-Command "link" "Install Visual Studio Build Tools with the Desktop development with C++ workload."
}

$version = Get-JsonVersion (Join-Path $rootDir "package.json")
$serverDir = Join-Path $rootDir "server"
$venvDir = Join-Path $serverDir ".venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$releaseDir = Join-Path $rootDir "release-local"

if (($Mode -ne "web" -or -not $SkipTests) -and -not (Test-Path $pythonExe)) {
    Step "Creating Python virtual environment"
    Invoke-Checked { py -3.11 -m venv $venvDir }
}

if ($Mode -ne "web" -or -not $SkipTests) {
    Step "Installing server dependencies"
    Invoke-Checked { & $pythonExe -m pip install --disable-pip-version-check -q -e "$serverDir[dev]" pyinstaller }
}

if (-not (Test-Path (Join-Path $rootDir "node_modules"))) {
    Step "Installing desktop dependencies"
    Invoke-Checked { npm install --no-audit --no-fund }
} else {
    Step "Desktop dependencies already installed"
}

if (-not $SkipTests) {
    Step "Running server checks"
    Push-Location $serverDir
    try {
        $env:AKFES_ENVIRONMENT = "test"
        $env:AKFES_DATABASE_PATH = Join-Path $env:TEMP "akfes-build-check.sqlite3"
        $env:AKFES_LICENSE_HMAC_SECRET = "local-build-license-secret-000000000000000000000000"
        $env:AKFES_ADMIN_TOKEN = "local-build-admin-token-000000000000000000000000000"
        Invoke-Checked { & $pythonExe -m ruff check . }
        Invoke-Checked { & $pythonExe -m pytest }
    } finally {
        Pop-Location
    }
}

if ($Mode -eq "all" -or $Mode -eq "web" -or $Mode -eq "installer") {
    Step "Building React web apps"
    Invoke-Checked { npm --workspace apps/desktop run build }
    Invoke-Checked { npm --workspace apps/admin run build }
}

if ($Mode -eq "all" -or $Mode -eq "server" -or $Mode -eq "installer") {
    Step "Building FastAPI sidecar executable"
    Invoke-Checked { & $pythonExe -m PyInstaller --noconfirm --clean --onefile --name akfes-server --paths server server/sidecar.py }

    $serverExe = Join-Path $rootDir "dist\akfes-server.exe"
    if (-not (Test-Path $serverExe)) {
        throw "Server executable was not created: $serverExe"
    }

    foreach ($target in @(
        "apps\desktop\src-tauri\binaries\akfes-server.exe",
        "apps\admin\src-tauri\binaries\akfes-server.exe"
    )) {
        $targetPath = Join-Path $rootDir $target
        New-Item -ItemType Directory -Path (Split-Path -Parent $targetPath) -Force | Out-Null
        Copy-Item $serverExe $targetPath -Force
    }
}

if ($Mode -eq "all" -or $Mode -eq "installer") {
    Step "Checking Rust applications"
    Invoke-Checked { cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml }
    Invoke-Checked { cargo check --manifest-path apps/admin/src-tauri/Cargo.toml }

    Step "Building Windows installers"
    Invoke-Checked { npm run desktop:build }
    Invoke-Checked { npm run admin:build }

    Step "Collecting release files"
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

    $desktopInstaller = Get-ChildItem "apps\desktop\src-tauri\target\release\bundle\nsis\*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $adminInstaller = Get-ChildItem "apps\admin\src-tauri\target\release\bundle\nsis\*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $serverExe = Join-Path $rootDir "dist\akfes-server.exe"

    if (-not $desktopInstaller) { throw "Desktop installer was not found." }
    if (-not $adminInstaller) { throw "Admin installer was not found." }
    if (-not (Test-Path $serverExe)) { throw "Server executable was not found." }

    Copy-Item $desktopInstaller.FullName (Join-Path $releaseDir "AKFES-v$version-Windows-x64-Setup.exe") -Force
    Copy-Item $adminInstaller.FullName (Join-Path $releaseDir "AKFES-License-Manager-v$version-Windows-x64-Setup.exe") -Force
    Copy-Item $serverExe (Join-Path $releaseDir "akfes-server-v$version-Windows-x64.exe") -Force

    $checksumPath = Join-Path $releaseDir "SHA256SUMS.txt"
    Remove-Item $checksumPath -ErrorAction SilentlyContinue
    Get-ChildItem $releaseDir -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | ForEach-Object {
        $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
        "$hash  $($_.Name)" | Add-Content $checksumPath
    }
}

Step "Done"
Write-Host "Mode: $Mode"
if (Test-Path $releaseDir) {
    Write-Host "Release folder: $releaseDir"
}
