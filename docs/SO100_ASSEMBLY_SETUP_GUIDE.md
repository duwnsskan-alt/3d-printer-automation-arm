# SO-100 Leader & Follower Arm 조립 및 세팅 가이드

---

## 1. 필요한 부품 (BOM)

| 카테고리 | 항목 | 수량 | 비고 |
|----------|------|------|------|
| **서보 모터** | Feetech STS3215 (7.4V) | 14개 | Leader 7 + Follower 7 (6관절 + 1그리퍼) |
| **컨트롤러** | Waveshare Serial Bus Servo Driver Board | 2개 | Leader 1 + Follower 1 |
| **전원** | 5V PSU (7.4V 모터용) 또는 12V PSU (12V 모터용) | 2개 | Leader는 반드시 7.4V 모터 사용 |
| **케이블** | USB-C 케이블 | 2개 | PC - 컨트롤러 보드 |
| **3D 프린트** | SO-100 파트 세트 | 2세트 | Leader용 + Follower용 |
| **기타** | M2/M2.5 나사, 베어링 등 | - | GitHub BOM 참조 |

---

## 2. 3D 프린트 파트 출력

- STL 파일: https://github.com/TheRobotStudio/SO-ARM100 에서 다운로드
- Leader/Follower 파트가 하나의 파일에 올바른 방향(Z-up)으로 정렬되어 있음
- **권장 프린트 설정:**
  - 노즐: 0.4mm -> 레이어: 0.2mm
  - 노즐: 0.6mm -> 레이어: 0.4mm
  - 서포트 최소화된 배치

---

## 3. 조립 과정

### Step 1: 서보 모터 준비
- 모터를 하나씩 연결하여 ID 세팅 (아래 SW 세팅에서 진행)
- **팁:** 케이블을 3D 프린트 파트에 먼저 삽입한 후 조립하는 것이 훨씬 쉬움

### Step 2: Follower Arm 조립 (약 1시간)
1. **Base** -> Motor ID 1 (Shoulder Rotation) 장착
2. **Shoulder** -> Motor ID 2 장착
3. **Elbow** -> Motor ID 3 장착
4. **Forearm** -> Motor ID 4 장착
5. **Wrist** -> Motor ID 5, 6 장착
6. **Gripper** -> Motor ID 7 장착
7. 모터 간 데이지체인 케이블 연결

### Step 3: Leader Arm 조립 (약 45분, 두 번째라 빠름)
- Follower와 동일한 구조이나 텔레오퍼레이션용 (사람이 직접 움직임)
- **Leader는 반드시 7.4V 모터 사용 (12V 모터 연결 시 손상!)**

### Step 4: 배선
- 서보 모터 데이지체인 -> 컨트롤러 보드 -> USB로 PC 연결
- 전원 공급: PSU -> 컨트롤러 보드 (USB는 전원을 공급하지 않음, 반드시 PSU도 연결)

---

## 4. 필요한 소프트웨어

### 기본 환경 세팅

```bash
# 1. Conda 환경 생성
conda create -y -n lerobot python=3.10
conda activate lerobot

# 2. ffmpeg 설치
conda install -y -c conda-forge ffmpeg

# 3. LeRobot 설치 (Feetech SDK 포함)
git clone https://github.com/huggingface/lerobot.git
cd lerobot
pip install -e ".[feetech]"
```

### 필요한 SW 목록

| SW | 용도 | 설치 |
|----|------|------|
| **Python 3.10+** | 런타임 | conda |
| **LeRobot** | 로봇 제어/데이터수집/학습 프레임워크 | `pip install -e ".[feetech]"` |
| **scservo_sdk** | Feetech STS3215 서보 통신 SDK | LeRobot에 포함 |
| **ffmpeg** | 카메라 녹화/인코딩 | `conda install -c conda-forge ffmpeg` |
| **PyTorch** | VLA 학습/추론 | LeRobot 의존성으로 자동 설치 |
| **Hugging Face Hub** | 데이터셋/모델 업로드 | `pip install huggingface_hub` |

---

## 5. 모터 세팅 (ID & Baudrate)

USB 포트를 먼저 확인:

```bash
# macOS
ls /dev/tty.usbmodem*

# Linux (Jetson 등)
ls /dev/ttyUSB* /dev/ttyACM*
```

**모터를 하나씩** 컨트롤러에 연결하고 ID를 설정:

```bash
# Follower Arm 모터 세팅
lerobot-setup-motors \
  --robot.type=so100_follower \
  --robot.port=/dev/ttyUSB0

# Leader Arm 모터 세팅
lerobot-setup-motors \
  --robot.type=so100_leader \
  --robot.port=/dev/ttyUSB1
```

- 스크립트가 안내에 따라 모터를 **하나씩** 연결하면 자동으로 ID(1~7)와 baudrate(1000000)를 설정
- 모든 모터 세팅 후 데이지체인으로 연결

---

## 6. 캘리브레이션

```bash
# Follower Arm 캘리브레이션
lerobot-calibrate \
  --robot.type=so100_follower \
  --robot.port=/dev/ttyUSB0 \
  --robot.id=my_follower_arm

# Leader Arm 캘리브레이션
lerobot-calibrate \
  --teleop.type=so100_leader \
  --teleop.port=/dev/ttyUSB1 \
  --teleop.id=my_leader_arm
```

**캘리브레이션 프로세스:**
1. 모든 관절을 **가동 범위의 중간 위치**로 이동 -> Enter
2. 모든 관절을 **전체 가동 범위로** 움직임 (min <-> max) -> Enter
3. 캘리브레이션 데이터가 `~/.cache/huggingface/lerobot/calibration/` 에 저장됨

> STS3215는 0~4096 (한 바퀴) 범위이며, 2048이 중앙. +-2048 스텝 = +-180도

---

## 7. 텔레오퍼레이션 테스트

조립과 캘리브레이션이 완료되면 Leader -> Follower 연동 테스트:

```bash
lerobot-teleoperate \
  --robot.type=so100_follower \
  --robot.port=/dev/ttyUSB0 \
  --teleop.type=so100_leader \
  --teleop.port=/dev/ttyUSB1
```

Leader arm을 손으로 움직이면 Follower arm이 실시간으로 따라 움직여야 합니다.

---

## 8. 데이터 수집 (다음 단계)

텔레오퍼레이션이 정상 작동하면 학습용 데이터 수집:

```bash
lerobot-record \
  --robot.type=so100_follower \
  --robot.port=/dev/ttyUSB0 \
  --teleop.type=so100_leader \
  --teleop.port=/dev/ttyUSB1 \
  --fps=20 \
  --episode-time-s=30 \
  --reset-time-s=10 \
  --num-episodes=50 \
  --repo-id=duwnsskan-alt/3d-printer-arm-dataset
```

---

## 주의사항

- **전압 확인 필수** — Leader arm은 항상 7.4V 모터. 12V PSU 연결 시 모터 파손
- USB만으로는 전원 공급 안 됨. PSU + USB **둘 다** 연결 필요
- 모터 세팅 시 반드시 **하나씩** 연결 (데이지체인 상태에서 하지 말 것)
- 프로젝트의 `config/config.yaml`에서 `robot.port`, `robot.baudrate`, `robot.joint_ids`가 실제 하드웨어와 일치하는지 확인

---

## 참고 자료

- SO-100 Official LeRobot Docs: https://huggingface.co/docs/lerobot/en/so100
- TheRobotStudio/SO-ARM100 GitHub: https://github.com/TheRobotStudio/SO-ARM100
- Seeed Studio SO-100 Wiki: https://wiki.seeedstudio.com/lerobot_so100m_new/
- LeRobot Calibration Guide: https://deepwiki.com/huggingface/lerobot/6.4-calibration-and-setup
