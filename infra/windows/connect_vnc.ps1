<#
.SYNOPSIS
    Watch 모드로 실행 중인 컨테이너의 noVNC URL을 기본 브라우저로 엽니다.

.DESCRIPTION
    run_sim.ps1 -Watch 로 켜진 컨테이너는 호스트 :6080 포트를 노출합니다.
    이 스크립트는 컨테이너 상태를 확인한 후 브라우저를 자동 실행합니다.

.PARAMETER Port
    호스트 측 noVNC 포트 (기본 6080).

.PARAMETER NoOpen
    URL만 출력하고 브라우저는 열지 않습니다.

.EXAMPLE
    .\connect_vnc.ps1
    .\connect_vnc.ps1 -Port 6081
#>

[CmdletBinding()]
param(
    [int]$Port = 6080,
    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'
$ContainerName = 'printer-arm-sim'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker 없음. Docker Desktop 실행/설치 확인."
    exit 1
}

$running = & docker ps --filter "name=^${ContainerName}$" --format '{{.ID}}' 2>$null
if (-not $running) {
    Write-Warning "실행 중인 컨테이너($ContainerName)가 없습니다."
    Write-Host "  먼저 다음을 실행: .\run_sim.ps1 -Watch" -ForegroundColor White
    exit 1
}

$url = "http://localhost:${Port}/vnc.html"
Write-Host "  noVNC URL: $url" -ForegroundColor Green

if (-not $NoOpen) {
    Start-Process $url
}
