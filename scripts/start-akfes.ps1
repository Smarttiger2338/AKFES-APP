$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Require-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name 명령을 찾을 수 없습니다. $InstallHint"
    }
}

Require-Command "py" "Python 3.11 이상을 설치하세요."
Require-Command "npm" "Node.js LTS를 설치하세요."
Require-Command "cargo" "Rust와 Tauri Windows 개발 도구를 설치하세요."

$serverDir = Join-Path $PWD "server"
$venvDir = Join-Path $serverDir ".venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "[1/4] Python 가상환경을 생성합니다..."
    & py -3.11 -m venv $venvDir
}

Write-Host "[2/4] 서버 의존성을 확인합니다..."
& $pythonExe -m pip install --disable-pip-version-check -q -e $serverDir

if (-not (Test-Path (Join-Path $PWD "node_modules"))) {
    Write-Host "[3/4] 데스크톱 의존성을 설치합니다..."
    & npm install --no-audit --no-fund
} else {
    Write-Host "[3/4] 데스크톱 의존성이 준비되어 있습니다."
}

$healthUrl = "http://127.0.0.1:8000/health"
$serverReady = $false
try {
    $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
    $serverReady = $response.StatusCode -eq 200
} catch {
    $serverReady = $false
}

if (-not $serverReady) {
    Write-Host "[4/4] FastAPI 서버를 시작합니다..."
    $serverProcess = Start-Process -FilePath $pythonExe -ArgumentList @(
        "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
    ) -WorkingDirectory $serverDir -PassThru -WindowStyle Minimized

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($serverProcess.HasExited) {
            throw "FastAPI 서버가 시작 중 종료되었습니다."
        }
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $serverReady = $true
                break
            }
        } catch {
            # 서버 준비 대기
        }
    }
}

if (-not $serverReady) {
    throw "FastAPI 서버가 제한 시간 안에 준비되지 않았습니다."
}

Write-Host "AKFES 데스크톱을 시작합니다. 창을 닫으면 이 실행기도 종료됩니다."
& npm run desktop:dev
exit $LASTEXITCODE
