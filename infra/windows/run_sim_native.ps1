<#
.SYNOPSIS
    Windows 네이티브 venv에서 Isaac Lab 시뮬레이션을 실행하는 PowerShell 런처.

.DESCRIPTION
    .venv-isaac 가상환경을 활성화하고 python -m isaaclab.app.run 을 호출합니다.
    Docker / WSL2 / Linux 자산 없이 Windows 위에서 직접 동작합니다.

    선행 조건: .\install_isaac_native.ps1 을 한 번 실행해 두어야 합니다.

.PARAMETER Profile
    local (기본, 16 envs) | cloud (256 envs)

.PARAMETER Task
    open_door (기본) | pick_print

.PARAMETER Watch
    Isaac Sim 창을 열어 렌더링.

.PARAMETER NumEnvs
    환경 수 강제 지정.

.PARAMETER MaxIter
    학습 반복 횟수 (task별 기본: open_door=5000, pick_print=8000)

.EXAMPLE
    .\run_sim_native.ps1
    .\run_sim_native.ps1 -Task pick_print -Watch
    .\run_sim_native.ps1 -Profile cloud -MaxIter 5000
#>

[CmdletBinding()]
param(
    [ValidateSet('local', 'cloud')]
    [string]$Profile = 'local',

    [ValidateSet('open_door', 'pick_print')]
    [string]$Task = 'open_door',

    [switch]$Watch,

    [int]$NumEnvs = 0,

    [int]$MaxIter = 0
)

$ErrorActionPreference = 'Stop'

# ── Paths ─────────────────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$VenvDir = Join-Path $ProjectRoot '.venv-isaac'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$OutputDir = Join-Path $ProjectRoot 'output'

# ── Resolve task -> gym id ────────────────────────────────────────────────────
$GymId = switch ($Task) {
    'open_door'  { 'PrinterArm-OpenDoor-v0' }
    'pick_print' { 'PrinterArm-PickPrint-v0' }
}

$AgentCfg = switch ($Task) {
    'open_door'  { 'sim.isaac_lab.agents.rsl_rl_cfg:OpenDoorPPOCfg' }
    'pick_print' { 'sim.isaac_lab.agents.rsl_rl_cfg:PickPrintPPOCfg' }
}

# ── Resolve profile -> num_envs ───────────────────────────────────────────────
$EnvsFromProfile = switch ($Profile) {
    'local' { 16 }
    'cloud' { 256 }
}
if ($NumEnvs -le 0) { $NumEnvs = $EnvsFromProfile }

if ($MaxIter -le 0) {
    $MaxIter = switch ($Task) {
        'open_door'  { 5000 }
        'pick_print' { 8000 }
    }
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  Printer Arm Isaac Lab Simulation (Windows / Native)" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  Profile:   $Profile ($NumEnvs envs)"
Write-Host "  Task:      $Task ($GymId)"
Write-Host "  Watch:     $($Watch.IsPresent)"
Write-Host "  Max iter:  $MaxIter"
Write-Host "  Venv:      $VenvDir"
Write-Host "  Output:    $OutputDir"
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

# ── Pre-flight ────────────────────────────────────────────────────────────────
if (-not (Test-Path $VenvPython)) {
    Write-Error @"
가상환경이 없습니다: $VenvPython
먼저 다음을 실행하세요:
  .\install_isaac_native.ps1
"@
    exit 1
}

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Error "nvidia-smi 없음. NVIDIA 드라이버를 설치하세요."
    exit 1
}

Write-Host "[1/3] GPU 확인..." -ForegroundColor Yellow
& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
Write-Host ""

# ── Output dirs ───────────────────────────────────────────────────────────────
Write-Host "[2/3] 출력 디렉터리 준비..." -ForegroundColor Yellow
@('checkpoints', 'logs', 'videos') | ForEach-Object {
    $sub = Join-Path $OutputDir $_
    if (-not (Test-Path $sub)) { New-Item -ItemType Directory -Force -Path $sub | Out-Null }
}
Write-Host "  $OutputDir 준비 완료" -ForegroundColor Green
Write-Host ""

# ── Env vars ──────────────────────────────────────────────────────────────────
$env:PROJECT_ROOT = $ProjectRoot
$env:PYTHONPATH = $ProjectRoot
$env:OUTPUT_DIR = $OutputDir
$env:OMNI_KIT_ACCEPT_EULA = 'Y'
$env:OMNI_KIT_PRIVACY_CONSENT = 'Y'
$env:ACCEPT_EULA = 'Y'
$env:PRIVACY_CONSENT = 'Y'

# ── Build python args ─────────────────────────────────────────────────────────
$logDir = Join-Path $OutputDir 'logs'
$ckptDir = Join-Path $OutputDir 'checkpoints'

if ($Watch) {
    $pyArgs = @(
        '-m', 'isaaclab.app.run',
        '--task', $GymId,
        '--num_envs', "$NumEnvs",
        '--agent_cfg', $AgentCfg
    )
    Write-Host "[3/3] Isaac Sim 창을 띄우면서 학습 시작..." -ForegroundColor Yellow
} else {
    $pyArgs = @(
        '-m', 'isaaclab.app.run',
        '--headless',
        '--task', $GymId,
        '--num_envs', "$NumEnvs",
        '--max_iterations', "$MaxIter",
        '--log_dir', $logDir,
        '--checkpoint_dir', $ckptDir,
        '--agent_cfg', $AgentCfg
    )
    Write-Host "[3/3] Headless 학습 시작..." -ForegroundColor Yellow
}

Write-Host "  python $($pyArgs -join ' ')" -ForegroundColor DarkGray
Write-Host ""
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  중지하려면 Ctrl+C를 누르세요." -ForegroundColor DarkGray
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# ── Exec ──────────────────────────────────────────────────────────────────────
& $VenvPython @pyArgs
exit $LASTEXITCODE
