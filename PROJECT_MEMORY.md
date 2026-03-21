# 3D Printer Automation Arm — Project Memory

## Overview
3D 프린터 자동화 로봇 팔. VLA/VLM 기반 두뇌 + LeRobot 프레임워크 제어.

## Architecture
- **System 2 (High-level):** VLM (Claude API / GPT) — 상황 판단, Code-as-Policy 생성
- **System 1 (Low-level):** VLA policy (SmolVLA 450M / OpenVLA-OFT 7B) — 10-50Hz 관절 제어
- **통신:** P1S 프린터 → MQTT, 로봇 → LeRobot, 카메라 → USB/RTSP
- **인프라:** `infra/terraform/`, `infra/docker/`, `infra/scripts/`

## Cloud
- Vast.ai → GPU 시뮬레이션 (AWS 대비 가성비 좋음)
- AWS $100 크레딧 보유 (다른 용도로 사용 가능)
- 시뮬 렌더링: Xvfb + noVNC (SSH 터널 → localhost:6080/vnc.html)

## Isaac Lab Simulation (2026-03-14 구축)
- **One-button launcher:** `./run_sim.sh` (Docker 기반)
- **P2S 프린터:** 단일 URDF articulation (`p2s_printer.urdf`, xacro에서 전처리)
  - door_hinge = joint index 3 (Z=0, Y=1, X=2, door=3)
  - Gantry axes locked (stiffness 10000)
- **Primitives:** build plate = CuboidCfg, print object = CylinderCfg (USD 불필요)
- **Tasks:** OpenDoor (5 actions, 9 obs), PickPrint (6 actions, 15 obs)
- **Scale:** local=16 envs, cloud=256, vast.ai 4xGPU=1024, 8xGPU=~10k
- **다음 단계:** Linux GPU 머신에서 `./run_sim.sh --max-iter 500` 테스트 → Vast.ai 배포

## Status
- 하드웨어 미입고 (BOM 단계)
- `config.yaml`의 `printer.serial`, `printer.access_code`는 CHANGE_ME 상태
- VLM 모델: config에 `claude-opus-4-5` → 실사용 시 최신 모델로 업데이트 필요

## Agent Memory
- 전용 에이전트 메모리: `.claude/agent-memory/3d-printer-robotics-architect/`
