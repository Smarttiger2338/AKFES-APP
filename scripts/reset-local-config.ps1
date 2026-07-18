param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function New-Secret {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([Convert]::ToBase64String($bytes) -replace "\+", "-" -replace "/", "_" -replace "=", "")
}

function Protect-Payload([string]$Content) {
    Add-Type -AssemblyName System.Security
    $bytes = [Text.Encoding]::UTF8.GetBytes($Content)
    $cipher = [Security.Cryptography.ProtectedData]::Protect(
        $bytes,
        $null,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    return [Convert]::ToBase64String($cipher)
}

$baseDir = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { $env:APPDATA }
if (-not $baseDir) {
    throw "Windows app data path was not found."
}

$appDataDir = Join-Path $baseDir "AKFES"
$configPath = Join-Path $appDataDir "server-runtime.json"
$auditPath = Join-Path $appDataDir "admin-audit.jsonl"

New-Item -ItemType Directory -Path $appDataDir -Force | Out-Null

if (-not $Force) {
    Write-Host "This resets the local server config because it cannot be decrypted."
    Write-Host "The license database file will be kept, but old licenses may need to be reissued."
    $answer = Read-Host "Continue? Type YES"
    if ($answer -ne "YES") {
        throw "Local config reset was cancelled."
    }
}

if (Test-Path $configPath) {
    Step "Backing up old runtime config"
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupPath = Join-Path $appDataDir "server-runtime.undecryptable-$timestamp.json"
    Move-Item -LiteralPath $configPath -Destination $backupPath -Force
    Write-Host "Backup: $backupPath"
}

Step "Creating new protected runtime config"
$payload = [ordered]@{
    license_secret = New-Secret
    admin_token = New-Secret
    created_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()
    admin_pin_failed_attempts = 0
}

$payloadJson = $payload | ConvertTo-Json -Depth 32 -Compress
$envelope = [ordered]@{
    version = 2
    protected = $true
    protection = "windows-dpapi-current-user"
    payload = Protect-Payload $payloadJson
}

$encoding = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($configPath, ($envelope | ConvertTo-Json -Depth 32) + [Environment]::NewLine, $encoding)

$auditEntry = @{
    action = "local_config_reset"
    created_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()
    detail = "Local runtime config was reset by helper script after decryption failure."
} | ConvertTo-Json -Compress
Add-Content -Path $auditPath -Value $auditEntry

Step "Done"
Write-Host "Config: $configPath"
Write-Host "Open the License Manager and set a new administrator PIN."
