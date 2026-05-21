# 3D Printer Automation Arm — Windows 실행 패키지

Windows 머신에서 Isaac Lab 시뮬레이션을 돌리기 위한 자산 묶음입니다.
원본 `run_sim.sh` (Linux/Bash 전용)를 두 가지 윈도우 친화적 경로로 재구현했습니다.

## 두 가지 실행 방식

| 방식 | 진입점 | 요구 사항 | 권장 시점 |
|------|--------|----------|----------|
| **A. WSL2 + Docker Desktop** | `run_sim.ps1` | Windows 11 + WSL2 + Docker Desktop + NVIDIA Container Toolkit | 기존 Docker 자산 그대로 재사용. CI/클라우드와 동일 환경 |
| **B. 네이티브 Windows (pip Isaac Sim)** | `run_sim_native.ps1` | Windows 10/11 + Python 3.10/3.11 + 30GB pip 캐시 + NVIDIA 드라이버 | Docker 설정 없이 빠르게 켜고 끄기. GUI 디버깅 편함 |

둘 다 **NVIDIA GPU (RTX 20 시리즈 이상, 드라이버 ≥ 537)** 가 필요합니다.
Isaac Sim/Lab은 macOS / AMD GPU / Intel iGPU에서 지원되지 않습니다.

---

## A. WSL2 + Docker Desktop 경로 (권장)

### 1) 사전 준비 (최초 1회)

PowerShell을 **관리자 권한**으로 열고:

```powershell
cd <패키지 위치>\infra\windows
.\check_prereqs.ps1
```

스크립트가 다음을 점검하고 누락되면 안내합니다:
- Windows 빌드 (≥ 22000 권장)
- WSL2 활성화
- Docker Desktop 설치/실행
- NVIDIA 드라이버 (`nvidia-smi`)
- WSL 내부 NVIDIA Container Toolkit

수동 설치가 필요한 경우:

1. **WSL2** — `wsl --install` 후 재부팅
2. **Docker Desktop** — <https://www.docker.com/products/docker-desktop/>
   - Settings → Resources → WSL Integration → 활성화
   - Settings → General → "Use the WSL 2 based engine" 체크
3. **NVIDIA 드라이버** — <https://www.nvidia.com/drivers> (Windows 호스트 측만 설치, WSL 안은 자동 패스스루)
4. **NVIDIA Container Toolkit** (WSL Ubuntu 내부):
   ```bash
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   ```

### 2) 실행

```powershell
# 학습 (기본: open_door 태스크, local 프로파일 = 16 envs)
.\run_sim.ps1

# 다른 태스크 / 클라우드 스케일
.\run_sim.ps1 -Task pick_print
.\run_sim.ps1 -Profile cloud -Task open_door

# VNC로 화면 보면서 실행
.\run_sim.ps1 -Watch
# → 브라우저에서 http://localhost:6080/vnc.html 열기

# 빠른 점검 (적은 반복)
.\run_sim.ps1 -MaxIter 50 -NumEnvs 4

# 이미지 강제 재빌드
.\run_sim.ps1 -Rebuild
```

산출물 (체크포인트, 로그, 비디오)은 프로젝트 루트 `output\` 폴더에 저장됩니다.

---

## B. 네이티브 Windows 경로

WSL/Docker 없이 Windows 호스트에서 직접 Python/Isaac Sim을 돌립니다.

### 1) 사전 준비 (최초 1회)

```powershell
cd <패키지 위치>\infra\windows
.\install_isaac_native.ps1
```

스크립트가 다음을 수행합니다 (각 단계 사용자 확인):

1. Python 3.10 가상환경 생성 → `.venv-isaac\`
2. `pip install --upgrade pip wheel`
3. `pip install 'isaacsim[all,extscache]==5.0.0' --extra-index-url https://pypi.nvidia.com`
4. `pip install isaaclab==2.3.2 isaaclab-assets==2.3.2 isaaclab-rl==2.3.2`
5. `pip install -r ..\..\requirements.txt` (프로젝트 의존성)
6. 첫 실행 시 NGC EULA 동의 자동 환경 변수 설정

추가 수동 설치 항목:
- **Python 3.10 또는 3.11** (3.12 미지원) — <https://www.python.org/downloads/> "Add to PATH" 체크
- **Microsoft Visual C++ Build Tools** — <https://visualstudio.microsoft.com/visual-cpp-build-tools/>
  (USD 휠 일부에 필요)
- **NVIDIA 드라이버 ≥ 537**

### 2) 실행

```powershell
.\run_sim_native.ps1
.\run_sim_native.ps1 -Task pick_print -Watch
.\run_sim_native.ps1 -Profile cloud -MaxIter 5000
```

네이티브 모드의 `-Watch`는 Isaac Sim 자체 창을 띄웁니다 (VNC 불필요).

---

## 옵션 공통

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `-Profile <local\|cloud>` | `local` | local=16 envs, cloud=256 envs |
| `-Task <open_door\|pick_print>` | `open_door` | 태스크 선택 |
| `-Watch` | off | 렌더링 활성화 (학습 속도 ↓) |
| `-NumEnvs <N>` | profile 값 | 환경 수 강제 지정 |
| `-MaxIter <N>` | task별 기본값 | 학습 반복 횟수 |
| `-Rebuild` (Docker만) | off | Docker 이미지 강제 재빌드 |

태스크 → Gym ID 매핑:
- `open_door` → `PrinterArm-OpenDoor-v0` (5 actions / 9 obs)
- `pick_print` → `PrinterArm-PickPrint-v0` (6 actions / 15 obs)

---

## 문제 해결

| 증상 | 원인 / 해결 |
|------|------------|
| `nvidia-smi`가 안 보임 | NVIDIA 스튜디오/게임레디 드라이버 설치 필요. AMD/Intel GPU 환경에서는 동작 불가. |
| `docker: could not select device driver "" with capabilities: [[gpu]]` | NVIDIA Container Toolkit 미설치/미설정. WSL Ubuntu에서 `nvidia-container-cli info`로 확인. |
| `ModuleNotFoundError: No module named 'isaaclab'` | 네이티브 모드에서 `.venv-isaac\Scripts\Activate.ps1` 활성화 누락. |
| `pip install isaacsim[all]` 실패 | Python 3.12 사용 중. 3.10/3.11로 다운그레이드. |
| WSL2에서 `Permission denied` (Docker 소켓) | Docker Desktop → Settings → Resources → WSL Integration에서 사용 중인 배포판 ON. |
| Watch 모드인데 VNC가 까만 화면 | 컨테이너 부팅 30초 대기 후 새로고침. 그래도 안 보이면 `docker logs printer-arm-sim` 확인. |

---

## 디렉터리 구조

```
infra/windows/
├── README_WINDOWS.md          (이 파일)
├── check_prereqs.ps1          사전 조건 점검 (WSL/Docker/NVIDIA)
├── install_isaac_native.ps1   네이티브 Isaac Sim/Lab pip 설치
├── run_sim.ps1                Docker(WSL2) 방식 학습 런처
├── run_sim_native.ps1         네이티브 방식 학습 런처
├── connect_vnc.ps1            VNC 브라우저 오픈 헬퍼
└── stop_sim.ps1               실행 중 컨테이너 정리
```

작성: 2026-05-21
