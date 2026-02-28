# 3D Print Farm Automation — Robotics VLA Architecture (2026)

## Project Overview
Bambu Lab P1S 3D 프린터의 출력물을 자동으로 제거하고 다음 작업을 시작하는 로봇팔 자동화 시스템. 2026년 최신 로보틱스 트런드인 **Sim-to-Real (Isaac Lab)** 및 **VLA (Vision-Language-Action)** 아키텍처를 기반으로 설계됨.

### Core Objectives
- **End-to-End Automation:** P1S 출력 완료 감지 → 도어 개봉 → 출력물 수거 → 도어 폐쇄 → 다음 작업 시작.
- **Zero-Marker Vision:** QR/ArUco 마커 없이 VLM/VLA를 통한 시각적 판단 및 제어.
- **Sim-to-Real Efficiency:** NVIDIA Isaac Lab 시뮬레이션 데이터를 활용하여 실제 시연 데이터 수집량 최소화.

---

## System Architecture

### 1. System 2: VLM Orchestrator (High-Level Planner)
- **Model:** Claude 4 API / GPT-5 (Primary), Qwen 3.0 VL (Local Fallback)
- **Role:** 상황 판단, Code-as-Policy 생성, 실패 복구 전략 수립.
- **Input:** RTSP/USB Camera Stream + P1S MQTT Status.

### 2. System 1: VLA Policy (Low-Level Control)
- **Model:** SmolVLA (450M) / OpenVLA-OFT (7B)
- **Framework:** Hugging Face LeRobot
- **Role:** 10Hz~50Hz 실시간 관절 제어 (Action Chunking).
- **Training:** Isaac Lab (Synthetic) + Teleop (Real-world) Hybrid Dataset.

---

## Hardware BOM (2026 Optimized)

| Category | Item | Specification |
| :--- | :--- | :--- |
| **Compute (Train)** | Workstation | NVIDIA RTX 5080/5090 (Isaac Lab Acceleration) |
| **Compute (Edge)** | Jetson Orin Nano | 8GB VRAM (Real-time VLA Inference) |
| **Robot Arm** | SO-100 Follower | 6-DoF + Gripper (Feetech STS3215 x7) |
| **Teleop Gear** | SO-100 Leader | For Sim-to-Real Calibration & Real-world Demo |
| **Vision** | USB Camera x2 | Global Shutter (Front + Wrist) |
| **Printer** | Bambu Lab P1S | LAN Mode (MQTT/FTPS) enabled |

---

## Automation Cycle
1. **[IDLE]** P1S MQTT `FINISH` 신호 대기 및 베드 냉각 확인.
2. **[TASK 1]** VLM이 `robot.open_door()` 실행 결정 → VLA 정책 구동.
3. **[TASK 2]** VLM이 출력물 위치/크기 판단 → `robot.pick_object()` 실행.
4. **[TASK 3]** 수납 트레이 배치 및 `robot.close_door()` 실행.
5. **[NEXT]** P1S MQTT로 다음 G-code 전송 및 출력 시작.

---

## Tech Stack (2026)
- **Simulation:** NVIDIA Isaac Lab / Isaac Sim
- **Robotics:** Hugging Face LeRobot, PyRobotics
- **AI Models:** SmolVLA, Claude 4, Foundation Pose 2.0
- **Communication:** MQTT, FTPS, RTSP

---

## Safety & Watchdog
- **Force Limit:** 도어 개방 및 픽업 시 과부하 감지 (STS3215 Feedback).
- **VLM Safety Guard:** 생성된 코드가 허용된 API 범위를 벗어나는지 사전 검증.
- **Physical E-Stop:** 비상 시 로봇 전원 즉시 차단.
