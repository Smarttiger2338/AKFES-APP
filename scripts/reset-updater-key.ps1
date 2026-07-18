param()

$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $PSScriptRoot
Set-Location $rootDir

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Require-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. $InstallHint"
    }
}

function Update-TauriPublicKey([string]$ConfigPath, [string]$PublicKey) {
    $config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
    $config.plugins.updater.pubkey = $PublicKey
    $json = $config | ConvertTo-Json -Depth 32
    $encoding = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText((Resolve-Path $ConfigPath), $json + [Environment]::NewLine, $encoding)
}

Require-Command "npm.cmd" "Install Node.js LTS."

$keyDir = Join-Path $env:USERPROFILE ".tauri"
$keyPath = Join-Path $keyDir "akfes-updater.key"
$publicKeyPath = "$keyPath.pub"
$backupDir = Join-Path $keyDir "akfes-updater-key-backups"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

New-Item -ItemType Directory -Path $keyDir -Force | Out-Null
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

foreach ($path in @($keyPath, $publicKeyPath)) {
    if (Test-Path $path) {
        $backupPath = Join-Path $backupDir "$([IO.Path]::GetFileName($path)).$timestamp"
        Move-Item -LiteralPath $path -Destination $backupPath -Force
    }
}

Step "Generating a new Tauri updater signing key"
Write-Host "Choose a password you can remember. You will need it every time you build installers."
Invoke-Checked { npm.cmd --workspace apps/admin run tauri -- signer generate -w $keyPath }

if (-not (Test-Path $publicKeyPath)) {
    throw "Public key was not created: $publicKeyPath"
}

$publicKey = (Get-Content -Raw $publicKeyPath).Trim()

Step "Updating Tauri app configs with the new public key"
Update-TauriPublicKey (Join-Path $rootDir "apps\desktop\src-tauri\tauri.conf.json") $publicKey
Update-TauriPublicKey (Join-Path $rootDir "apps\admin\src-tauri\tauri.conf.json") $publicKey

Step "Done"
Write-Host "Private key: $keyPath"
Write-Host "Public key: $publicKeyPath"
Write-Host "Updated configs:"
Write-Host "- apps\desktop\src-tauri\tauri.conf.json"
Write-Host "- apps\admin\src-tauri\tauri.conf.json"
