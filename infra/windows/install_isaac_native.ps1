<#
.SYNOPSIS
    Windows 호스트에 Isaac Sim / Isaac Lab을 pip로 설치하는 셋업 스크립트.

.DESCRIPTION
    프로젝트 루트에 .venv-isaac 가상환경을 만들고, NVIDIA의 PyPI에서
    isaacsim[all] + isaaclab + isaaclab-rl + isaaclab-assets를 설치합니다.
    이후 requirements.txt의 프로젝트 의존성을 같은 venv에 설치합니다.

    1회만 실행하면 됩니다. 이후로는 run_sim_native.ps1만 사용.

.PARAMETER PythonExe
    사용할 Python 인터프리터 경로. 기본은 `python` (PATH).
    3.10 또는 3.11이어야 합니다.

.PARAMETER IsaacSimVersion
    설치할 isaacsim 버전 (기본: 5.0.0).

.PARAMETER IsaacLabVersion
    설치할 isaaclab 버전 (기본: 2.3.2). Dockerfile의 NGC 이미지 태그와 동일 메이저.

.PARAMETER SkipConfirm
    각 단계 확인 프롬프트 생략.

.EXAMPLE
    .\install_isaac_native.ps1
    .\install_isaac_native.ps1 -PythonExe "C:\Python311\python.exe"
#>

[CmdletBinding()]
param(
    [string]$PythonExe = 'python',
    [string]$IsaacSimVersion = '5.0.0',
    [string]$IsaacLabVersion = '2.3.2',
    [switch]$SkipConfirm
)

$ErrorActionPreference = 'Stop'

# ── Paths ─────────────────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$VenvDir = Join-Path $ProjectRoot '.venv-isaac'
$RequirementsFile = Join-Path $ProjectRoot 'requirements.txt'

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  Isaac Sim / Isaac Lab - Windows Native Installer" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  Python:       $PythonExe"
Write-Host "  Isaac Sim:    $IsaacSimVersion"
Write-Host "  Isaac Lab:    $IsaacLabVersion"
Write-Host "  Venv:         $VenvDir"
Write-Host "  Project:      $ProjectRoot"
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

function Confirm-Step($msg) {
    if ($SkipConfirm) { return $true }
    $response = Read-Host "$msg [Y/n]"
    return ($response -eq '' -or $response -match '^[Yy]')
}

function Step($num, $title) {
    Write-Host ""
    Write-Host "[$num] $title" -ForegroundColor Yellow
    Write-Host "---------------------------------------------------------------" -ForegroundColor DarkGray
}

# ── Step 1: Python version check ──────────────────────────────────────────────
Step '1/6' 'Python 버전 확인'

try {
    $pyVerOutput = & $PythonExe --version 2>&1
} catch {
    Write-Error "Python 실행 실패: $PythonExe. PATH 확인 또는 -PythonExe 옵션으로 경로 지정."
    exit 1
}

Write-Host "  감지: $pyVerOutput"
if ($pyVerOutput -notmatch 'Python\s+3\.(10|11)\.') {
    Write-Error "Python 3.10 또는 3.11이 필요합니다. Isaac Sim 5.x는 3.12를 지원하지 않습니다."
    Write-Host "  다운로드: https://www.python.org/downloads/release/python-31011/" -ForegroundColor White
    exit 1
}
Write-Host "  OK" -ForegroundColor Green

# ── Step 2: NVIDIA driver check ───────────────────────────────────────────────
Step '2/6' 'NVIDIA GPU 드라이버 확인'

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Error "nvidia-smi 없음. NVIDIA 드라이버 설치 필요: https://www.nvidia.com/drivers"
    exit 1
}

& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
Write-Host "  OK" -ForegroundColor Green

# ── Step 3: Create venv ───────────────────────────────────────────────────────
Step '3/6' "가상환경 생성: $VenvDir"

if (Test-Path $VenvDir) {
    Write-Host "  이미 존재합니다."
    if (-not (Confirm-Step "  기존 venv를 삭제하고 새로 만들까요?")) {
        Write-Host "  기존 venv를 재사용합니다." -ForegroundColor DarkGray
    } else {
        Remove-Item -Recurse -Force $VenvDir
        & $PythonExe -m venv $VenvDir
    }
} else {
    & $PythonExe -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$VenvPip = Join-Path $VenvDir 'Scripts\pip.exe'

if (-not (Test-Path $VenvPython)) {
    Write-Error "Venv 생성 실패: $VenvPython 없음."
    exit 1
}
Write-Host "  OK" -ForegroundColor Green

# ── Step 4: Upgrade pip / wheel ───────────────────────────────────────────────
Step '4/6' 'pip / wheel 업그레이드'
& $VenvPython -m pip install --upgrade pip wheel setuptools
if ($LASTEXITCODE -ne 0) { Write-Error "pip 업그레이드 실패"; exit 1 }
Write-Host "  OK" -ForegroundColor Green

# ── Step 5: Install Isaac Sim + Isaac Lab ─────────────────────────────────────
Step '5/6' "Isaac Sim ($IsaacSimVersion) + Isaac Lab ($IsaacLabVersion) 설치"
Write-Host "  대용량 다운로드입니다 (~20GB). 회선/디스크 확인 후 진행하세요." -ForegroundColor DarkGray

if (-not (Confirm-Step "  계속 진행할까요?")) {
    Write-Host "  사용자가 중단했습니다." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "  >>> isaacsim[all,extscache]==$IsaacSimVersion ..." -ForegroundColor Cyan
& $VenvPip install --extra-index-url https://pypi.nvidia.com "isaacsim[all,extscache]==$IsaacSimVersion"
if ($LASTEXITCODE -ne 0) {
    Write-Error "isaacsim 설치 실패. NVIDIA NGC PyPI 접근 또는 디스크 공간 확인."
    exit 1
}

Write-Host ""
Write-Host "  >>> isaaclab + isaaclab-assets + isaaclab-rl == $IsaacLabVersion ..." -ForegroundColor Cyan
& $VenvPip install `
    "isaaclab==$IsaacLabVersion" `
    "isaaclab-assets==$IsaacLabVersion" `
    "isaaclab-rl==$IsaacLabVersion"
if ($LASTEXITCODE -ne 0) {
    Write-Error "isaaclab 설치 실패."
    exit 1
}
Write-Host "  OK" -ForegroundColor Green

# ── Step 6: Project requirements ──────────────────────────────────────────────
Step '6/6' "프로젝트 requirements.txt 설치"

if (Test-Path $RequirementsFile) {
    & $VenvPip install -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error "프로젝트 requirements 설치 실패."
        exit 1
    }
    Write-Host "  OK" -ForegroundColor Green
} else {
    Write-Host "  requirements.txt 없음. 건너뜀." -ForegroundColor DarkGray
}

# ── Activate helper ───────────────────────────────────────────────────────────
$ActivateHelper = Join-Path $ScriptDir 'activate_venv.ps1'
@"
# Helper: 현재 PowerShell 세션에서 Isaac venv 활성화
# 사용: PS> . .\activate_venv.ps1
. '$VenvDir\Scripts\Activate.ps1'
`$env:PROJECT_ROOT = '$ProjectRoot'
`$env:PYTHONPATH = '$ProjectRoot'
`$env:OMNI_KIT_ACCEPT_EULA = 'Y'
`$env:OMNI_KIT_PRIVACY_CONSENT = 'Y'
`$env:ACCEPT_EULA = 'Y'
`$env:PRIVACY_CONSENT = 'Y'
Write-Host "  venv 활성화 완료. Python: `$((Get-Command python).Source)" -ForegroundColor Green
"@ | Set-Content -Encoding UTF8 -Path $ActivateHelper

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host "  설치 완료" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "다음 단계:" -ForegroundColor White
Write-Host "  학습 실행:     .\run_sim_native.ps1" -ForegroundColor White
Write-Host "  세션에서 활성:  . .\activate_venv.ps1" -ForegroundColor White
Write-Host ""
