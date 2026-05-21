<#
.SYNOPSIS
    실행 중인 printer-arm-sim 컨테이너를 강제 중지/정리합니다.

.EXAMPLE
    .\stop_sim.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ContainerName = 'printer-arm-sim'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker 없음."
    exit 1
}

$existing = & docker ps -a --filter "name=^${ContainerName}$" --format '{{.ID}}' 2>$null
if (-not $existing) {
    Write-Host "  실행 중인 컨테이너 없음." -ForegroundColor DarkGray
    exit 0
}

Write-Host "  $ContainerName 컨테이너 정리..." -ForegroundColor Yellow
& docker rm -f $ContainerName | Out-Null
Write-Host "  완료." -ForegroundColor Green
