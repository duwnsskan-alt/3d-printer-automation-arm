<#
.SYNOPSIS
    Windows에서 Docker(WSL2) 기반 Isaac Lab 시뮬레이션을 실행하는 PowerShell 런처.
    Linux의 run_sim.sh를 그대로 포팅했습니다.

.DESCRIPTION
    Docker 이미지를 (필요 시) 빌드하고, GPU 패스스루를 활성화한 컨테이너에서
    Isaac Lab을 실행합니다. -Watch 옵션 사용 시 noVNC 포트를 노출하고
    브라우저로 http://localhost:6080/vnc.html 에서 시뮬레이션 화면을 볼 수 있습니다.

.PARAMETER Profile
    local (기본, 16 envs) | cloud (256 envs)

.PARAMETER Task
    open_door (기본) | pick_print

.PARAMETER Watch
    VNC 렌더링 모드. http://localhost:6080/vnc.html 로 접속.

.PARAMETER NumEnvs
    환경 수 강제 지정 (Profile 기본값을 덮어씀)

.PARAMETER MaxIter
    학습 반복 횟수 (task별 기본: open_door=5000, pick_print=8000)

.PARAMETER Rebuild
    Docker 이미지 강제 재빌드.

.EXAMPLE
    .\run_sim.ps1
    .\run_sim.ps1 -Task pick_print -Watch
    .\run_sim.ps1 -Profile cloud -MaxIter 5000
#>

[CmdletBinding()]
param(
    [ValidateSet('local', 'cloud')]
    [string]$Profile = 'local',

    [ValidateSet('open_door', 'pick_print')]
    [string]$Task = 'open_door',

    [switch]$Watch,

    [int]$NumEnvs = 0,

    [int]$MaxIter = 0,

    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'

# ── Paths ─────────────────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$DockerDir = Join-Path $ProjectRoot 'infra\docker'
$OutputDir = Join-Path $ProjectRoot 'output'

# ── Constants ─────────────────────────────────────────────────────────────────
$ImageName = 'printer-arm-isaacsim'
$ImageTag = 'latest'
$FullImage = "${ImageName}:${ImageTag}"
$ContainerName = 'printer-arm-sim'

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

# ── Default MaxIter per task ──────────────────────────────────────────────────
if ($MaxIter -le 0) {
    $MaxIter = switch ($Task) {
        'open_door'  { 5000 }
        'pick_print' { 8000 }
    }
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  Printer Arm Isaac Lab Simulation (Windows / Docker)" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  Profile:   $Profile ($NumEnvs envs)"
Write-Host "  Task:      $Task ($GymId)"
Write-Host "  Watch:     $($Watch.IsPresent)"
Write-Host "  Max iter:  $MaxIter"
Write-Host "  Project:   $ProjectRoot"
Write-Host "  Output:    $OutputDir"
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

# ── Prerequisite checks ───────────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker가 설치돼 있지 않습니다. Docker Desktop 설치 후 다시 시도하세요. (사전 점검: .\check_prereqs.ps1)"
    exit 1
}

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Error "nvidia-smi가 보이지 않습니다. NVIDIA 드라이버가 필요합니다. (사전 점검: .\check_prereqs.ps1)"
    exit 1
}

Write-Host "[1/4] GPU 확인..." -ForegroundColor Yellow
& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
Write-Host ""

# Docker daemon
try {
    $null = & docker info 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker daemon이 응답하지 않습니다. Docker Desktop을 실행해 주세요."
        exit 1
    }
} catch {
    Write-Error "Docker 명령 실행 실패: $($_.Exception.Message)"
    exit 1
}

# ── Build image ───────────────────────────────────────────────────────────────
$null = & docker image inspect $FullImage 2>$null
$imageExists = ($LASTEXITCODE -eq 0)

if ($Rebuild -or -not $imageExists) {
    Write-Host "[2/4] Docker 이미지 빌드: $FullImage..." -ForegroundColor Yellow
    Write-Host "  (최초 빌드는 ~20GB Isaac Lab 베이스 이미지 다운로드. 수십 분 소요)" -ForegroundColor DarkGray
    Write-Host ""

    & docker build -t $FullImage -f (Join-Path $DockerDir 'Dockerfile') $DockerDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker 이미지 빌드 실패."
        exit 1
    }
    Write-Host "  이미지 빌드 완료." -ForegroundColor Green
} else {
    Write-Host "[2/4] Docker 이미지 존재: $FullImage (재빌드는 -Rebuild)" -ForegroundColor Yellow
}
Write-Host ""

# ── Output dirs ───────────────────────────────────────────────────────────────
Write-Host "[3/4] 출력 디렉터리 준비..." -ForegroundColor Yellow
@('checkpoints', 'logs', 'videos') | ForEach-Object {
    $sub = Join-Path $OutputDir $_
    if (-not (Test-Path $sub)) { New-Item -ItemType Directory -Force -Path $sub | Out-Null }
}
Write-Host "  $OutputDir 준비 완료" -ForegroundColor Green
Write-Host ""

# ── Stop existing container ───────────────────────────────────────────────────
$existing = & docker ps -a --filter "name=^${ContainerName}$" --format '{{.ID}}' 2>$null
if ($existing) {
    Write-Host "  기존 컨테이너 정리 중: $ContainerName" -ForegroundColor DarkGray
    & docker rm -f $ContainerName | Out-Null
}

# ── Build docker run command ──────────────────────────────────────────────────
Write-Host "[4/4] 컨테이너 시작..." -ForegroundColor Yellow
Write-Host ""

function ConvertTo-DockerPath($winPath) {
    return ($winPath -replace '\\', '/')
}

$projectMount = ConvertTo-DockerPath $ProjectRoot
$outputMount = ConvertTo-DockerPath $OutputDir

$dockerArgs = @(
    'run', '--rm',
    '--name', $ContainerName,
    '--gpus', 'all',
    '--ipc=host',
    '--ulimit', 'memlock=-1',
    '--ulimit', 'stack=67108864',
    '-v', "${projectMount}:/workspace/project:ro",
    '-v', "${outputMount}:/workspace/output",
    '-e', 'PROJECT_ROOT=/workspace/project',
    '-e', 'OUTPUT_DIR=/workspace/output',
    '-e', 'PYTHONPATH=/workspace/project'
)

if ($Watch) {
    $dockerArgs += @(
        '-e', 'SIM_MODE=watch',
        '-p', '6080:6080',
        '-p', '5900:5900'
    )
    $simArgs = @(
        '--task', $GymId,
        '--num_envs', "$NumEnvs"
    )
    Write-Host "  VNC 렌더링 모드 활성화" -ForegroundColor Green
    Write-Host "  컨테이너 부팅 후 브라우저에서 열기: http://localhost:6080/vnc.html" -ForegroundColor Green
} else {
    $dockerArgs += @('-e', 'SIM_MODE=train')
    $simArgs = @(
        '--task', $GymId,
        '--num_envs', "$NumEnvs",
        '--max_iterations', "$MaxIter",
        '--log_dir', '/workspace/output/logs',
        '--checkpoint_dir', '/workspace/output/checkpoints'
    )
}

$simArgs += @('--agent_cfg', $AgentCfg)

Write-Host ""
Write-Host "  컨테이너: $ContainerName" -ForegroundColor DarkGray
Write-Host "  이미지:   $FullImage" -ForegroundColor DarkGray
Write-Host "  Sim args: $($simArgs -join ' ')" -ForegroundColor DarkGray
Write-Host ""
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  중지하려면 Ctrl+C를 누르세요." -ForegroundColor DarkGray
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# ── Exec ──────────────────────────────────────────────────────────────────────
& docker @dockerArgs $FullImage @simArgs
exit $LASTEXITCODE
