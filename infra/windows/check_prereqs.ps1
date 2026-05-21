<#
.SYNOPSIS
    Windows 환경에서 Isaac Lab 시뮬레이션을 돌리기 위한 사전 조건 점검.

.DESCRIPTION
    WSL2 + Docker Desktop + NVIDIA GPU 경로(-Mode docker, 기본값)와
    네이티브 Python 경로(-Mode native) 양쪽 모두를 점검할 수 있습니다.
    누락된 항목은 OK/WARN/FAIL 표로 출력하고, 비종결적 종료 코드를 반환합니다.

.PARAMETER Mode
    docker (기본) | native | all

.EXAMPLE
    .\check_prereqs.ps1
    .\check_prereqs.ps1 -Mode native
    .\check_prereqs.ps1 -Mode all
#>

[CmdletBinding()]
param(
    [ValidateSet('docker', 'native', 'all')]
    [string]$Mode = 'docker'
)

$ErrorActionPreference = 'Continue'
$script:Failures = 0
$script:Warnings = 0

function Write-Section($title) {
    Write-Host ""
    Write-Host "===========================================================" -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host "===========================================================" -ForegroundColor Cyan
}

function Report-OK($name, $detail = '') {
    Write-Host ("  [OK]    {0,-30} {1}" -f $name, $detail) -ForegroundColor Green
}

function Report-Warn($name, $detail = '') {
    Write-Host ("  [WARN]  {0,-30} {1}" -f $name, $detail) -ForegroundColor Yellow
    $script:Warnings++
}

function Report-Fail($name, $detail = '') {
    Write-Host ("  [FAIL]  {0,-30} {1}" -f $name, $detail) -ForegroundColor Red
    $script:Failures++
}

# ── Common checks ─────────────────────────────────────────────────────────────
Write-Section "공통 사전 조건"

# Windows build
$build = [int](Get-CimInstance Win32_OperatingSystem).BuildNumber
if ($build -ge 22000) {
    Report-OK "Windows build" "$build (Win11 OK)"
} elseif ($build -ge 19045) {
    Report-Warn "Windows build" "$build (Win10 22H2). WSL2 동작은 가능하나 Win11 권장."
} else {
    Report-Fail "Windows build" "$build (너무 낮음 — Windows 업데이트 필요)"
}

# NVIDIA driver
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    try {
        $driverInfo = & nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>$null
        if ($LASTEXITCODE -eq 0 -and $driverInfo) {
            $first = ($driverInfo | Select-Object -First 1).Trim()
            $parts = $first -split ','
            $driverVer = ($parts[1]).Trim()
            $verNum = [version]($driverVer -replace '[^\d\.].*$', '')
            if ($verNum -ge [version]"537.0") {
                Report-OK "NVIDIA driver" "$driverVer / $($parts[0].Trim())"
            } else {
                Report-Warn "NVIDIA driver" "$driverVer (< 537 — Isaac Sim 5.x는 537 이상 권장)"
            }
        } else {
            Report-Fail "NVIDIA driver" "nvidia-smi 실행 실패"
        }
    } catch {
        Report-Fail "NVIDIA driver" $_.Exception.Message
    }
} else {
    Report-Fail "NVIDIA driver" "nvidia-smi 없음 — https://www.nvidia.com/drivers 에서 설치"
}

# ── Docker path ───────────────────────────────────────────────────────────────
if ($Mode -in @('docker', 'all')) {
    Write-Section "WSL2 + Docker Desktop 경로"

    # WSL
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($wsl) {
        try {
            $wslStatus = & wsl.exe --status 2>&1 | Out-String
            if ($wslStatus -match 'Default Version:\s*2') {
                Report-OK "WSL2" "기본 버전 2"
            } elseif ($wslStatus -match 'Default Version:\s*1') {
                Report-Warn "WSL2" "기본 버전 1 (wsl --set-default-version 2 실행)"
            } else {
                Report-Warn "WSL2" "상태 확인 불가 — 'wsl --install' 필요할 수 있음"
            }
        } catch {
            Report-Warn "WSL2" "확인 실패: $($_.Exception.Message)"
        }
    } else {
        Report-Fail "WSL2" "wsl.exe 없음. 관리자 PowerShell에서 'wsl --install' 실행 후 재부팅"
    }

    # Docker Desktop
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) {
        try {
            $dockerVer = & docker --version 2>$null
            Report-OK "Docker CLI" $dockerVer
            $dockerInfo = & docker info 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0) {
                Report-OK "Docker daemon" "실행 중"
                if ($dockerInfo -match 'nvidia') {
                    Report-OK "NVIDIA runtime" "Docker에서 인식됨"
                } else {
                    Report-Warn "NVIDIA runtime" "Docker info에서 미감지. WSL에 nvidia-container-toolkit 설치 필요"
                }
            } else {
                Report-Fail "Docker daemon" "응답 없음 — Docker Desktop을 실행해 주세요"
            }
        } catch {
            Report-Fail "Docker CLI" $_.Exception.Message
        }
    } else {
        Report-Fail "Docker CLI" "Docker Desktop 미설치 — https://www.docker.com/products/docker-desktop/"
    }

    if ($docker) {
        Write-Host ""
        Write-Host "  Docker GPU 패스스루 스모크 테스트는 다음 명령으로 확인:" -ForegroundColor DarkGray
        Write-Host "    docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi" -ForegroundColor DarkGray
    }
}

# ── Native path ───────────────────────────────────────────────────────────────
if ($Mode -in @('native', 'all')) {
    Write-Section "네이티브 Python 경로"

    # Python version
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $pyVer = & python --version 2>&1
            if ($pyVer -match 'Python\s+3\.(10|11)\.') {
                Report-OK "Python" "$pyVer"
            } elseif ($pyVer -match 'Python\s+3\.12') {
                Report-Fail "Python" "$pyVer — Isaac Sim 5.x는 3.10/3.11 필요"
            } else {
                Report-Warn "Python" "$pyVer (3.10/3.11 권장)"
            }
        } catch {
            Report-Fail "Python" $_.Exception.Message
        }
    } else {
        Report-Fail "Python" "python.exe 없음 — https://www.python.org/downloads/release/python-31011/"
    }

    # MSVC Build Tools (rough check)
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        try {
            $installs = & $vswhere -products '*' -requires 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64' -property installationPath 2>$null
            if ($installs) {
                Report-OK "MSVC Build Tools" "감지됨"
            } else {
                Report-Warn "MSVC Build Tools" "VC 도구 미감지 — 일부 USD 휠 빌드에 필요할 수 있음"
            }
        } catch {
            Report-Warn "MSVC Build Tools" "확인 실패"
        }
    } else {
        Report-Warn "MSVC Build Tools" "vswhere 없음 — Build Tools 미설치 가능성"
    }

    # Free disk
    $userQual = (Split-Path $env:USERPROFILE -Qualifier).TrimEnd(':')
    $sys = Get-PSDrive -Name $userQual -ErrorAction SilentlyContinue
    if ($sys) {
        $freeGB = [math]::Round($sys.Free / 1GB, 1)
        if ($freeGB -ge 50) {
            Report-OK "디스크 여유 공간" "$freeGB GB"
        } elseif ($freeGB -ge 30) {
            Report-Warn "디스크 여유 공간" "$freeGB GB — Isaac Sim 5.x 휠+캐시 약 30GB 사용"
        } else {
            Report-Fail "디스크 여유 공간" "$freeGB GB — 부족 (30GB 이상 필요)"
        }
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Section "결과 요약"
if ($Failures -eq 0 -and $Warnings -eq 0) {
    Write-Host "  모든 점검 통과. 다음 단계로 진행 가능합니다." -ForegroundColor Green
} elseif ($Failures -eq 0) {
    Write-Host "  경고 $Warnings 건. 진행은 가능하나 README의 안내를 참고하세요." -ForegroundColor Yellow
} else {
    Write-Host "  실패 $Failures 건 / 경고 $Warnings 건. 위 항목을 먼저 해결해야 합니다." -ForegroundColor Red
}

Write-Host ""
Write-Host "다음 단계:" -ForegroundColor White
if ($Mode -in @('docker', 'all')) {
    Write-Host "  Docker 경로   ->  .\run_sim.ps1" -ForegroundColor White
}
if ($Mode -in @('native', 'all')) {
    Write-Host "  네이티브 경로 ->  .\install_isaac_native.ps1  ->  .\run_sim_native.ps1" -ForegroundColor White
}
Write-Host ""

if ($Failures -gt 0) { exit 2 }
elseif ($Warnings -gt 0) { exit 1 }
else { exit 0 }
