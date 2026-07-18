param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
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

function Unprotect-Payload([string]$Payload) {
    Add-Type -AssemblyName System.Security
    $bytes = [Convert]::FromBase64String($Payload)
    $plain = [Security.Cryptography.ProtectedData]::Unprotect(
        $bytes,
        $null,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    return [Text.Encoding]::UTF8.GetString($plain)
}

function Remove-PropertyIfPresent($Object, [string]$Name) {
    if ($Object.PSObject.Properties.Name -contains $Name) {
        $Object.PSObject.Properties.Remove($Name)
    }
}

$baseDir = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { $env:APPDATA }
if (-not $baseDir) {
    throw "Windows app data path was not found."
}

$appDataDir = Join-Path $baseDir "AKFES"
$configPath = Join-Path $appDataDir "server-runtime.json"
$auditPath = Join-Path $appDataDir "admin-audit.jsonl"

if (-not (Test-Path $configPath)) {
    throw "AKFES runtime config was not found: $configPath"
}

if (-not $Force) {
    Write-Host "This resets only the local administrator PIN."
    Write-Host "Admin token, license secret, and license database will be kept."
    $answer = Read-Host "Continue? Type YES"
    if ($answer -ne "YES") {
        throw "PIN reset was cancelled."
    }
}

Step "Backing up runtime config"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $appDataDir "server-runtime.before-pin-reset-$timestamp.json"
Copy-Item -LiteralPath $configPath -Destination $backupPath -Force

Step "Reading protected config"
$stored = Get-Content -Raw $configPath | ConvertFrom-Json
$protected = $false

if (
    $stored.version -eq 2 -and
    $stored.protected -eq $true -and
    $stored.payload
) {
    $config = Unprotect-Payload $stored.payload | ConvertFrom-Json
    $protected = $true
} else {
    $config = $stored
}

if (-not $config.license_secret -or -not $config.admin_token) {
    throw "AKFES runtime config is invalid."
}

Step "Clearing administrator PIN"
Remove-PropertyIfPresent $config "admin_pin_salt"
Remove-PropertyIfPresent $config "admin_pin_hash"
Remove-PropertyIfPresent $config "admin_pin_locked_until"

if ($config.PSObject.Properties.Name -contains "admin_pin_failed_attempts") {
    $config.admin_pin_failed_attempts = 0
} else {
    $config | Add-Member -NotePropertyName "admin_pin_failed_attempts" -NotePropertyValue 0
}

$configJson = $config | ConvertTo-Json -Depth 32 -Compress
if ($protected) {
    $output = [ordered]@{
        version = 2
        protected = $true
        protection = "windows-dpapi-current-user"
        payload = Protect-Payload $configJson
    }
    $content = $output | ConvertTo-Json -Depth 32
} else {
    $content = $config | ConvertTo-Json -Depth 32
}

$temporaryPath = "$configPath.tmp"
$encoding = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($temporaryPath, $content + [Environment]::NewLine, $encoding)
Move-Item -LiteralPath $temporaryPath -Destination $configPath -Force

$auditEntry = @{
    action = "admin_pin_reset_local"
    created_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()
    detail = "Administrator PIN was reset by local helper script."
} | ConvertTo-Json -Compress
Add-Content -Path $auditPath -Value $auditEntry

Step "Done"
Write-Host "Backup: $backupPath"
Write-Host "Open the License Manager and set a new administrator PIN."
