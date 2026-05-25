# 3D Printer Automation Arm — Claude Code Guide

## 프로젝트 컨텍스트
- Bambu Lab P2S 출력물 자동 수거 로봇팔
- VLM (System 2) + VLA (System 1) 2-tier 아키텍처
- Isaac Lab 2.3.2 시뮬레이션 → Sim-to-Real → SO-100 실기 배포
- 자세한 스펙은 [PROJECT_MEMORY.md](PROJECT_MEMORY.md), 메모리 인덱스는 `~/.claude/projects/-home-yeojun-3d-printer-automation-arm/memory/MEMORY.md`

## ECC (Everything Claude Code) 활용 가이드

ECC 플러그인 설치됨 (60 agents, 232 skills, 75 commands). 로보틱스 작업에 자주 쓸 항목:

### Agents — `Agent` tool로 호출 (subagent_type 또는 description으로)
| 상황 | Agent |
|---|---|
| Isaac Lab 환경/태스크 코드 리뷰 | `python-reviewer` |
| CUDA OOM, tensor shape, RL training 에러 | `pytorch-build-resolver` |
| 데이터 컨트랙트/학습 재현성/평가 파이프라인 | `mle-reviewer` |
| RL pipeline TDD | `tdd-guide` |
| VLA/VLM 시스템 설계 | `code-architect` |
| Isaac Lab API/낯선 코드 탐색 | `code-explorer` |
| 복잡한 sim-to-real 작업 분해 | `planner` |
| MQTT/secrets/통신 보안 | `security-reviewer` |
| RL reward/env 조용한 실패 | `silent-failure-hunter` |

### Slash Commands
```
/ecc:python-review      # 변경 사항 PEP8/타입힌트/security
/ecc:plan               # 작업 plan 후 user confirm 대기
/ecc:tdd-guide          # 테스트 먼저
/ecc:code-review        # 로컬 또는 PR
/ecc:harness-audit      # 현재 ECC 설정 점수표
/ecc:security-scan      # .claude/ 보안 스캔
/ecc:learn              # 세션에서 재사용 패턴 추출
/ecc:project-init       # 프로젝트 onboarding plan dry-run
```

### Skills (자동 트리거 — 명시 호출 가능)
- `python-patterns`, `python-testing`, `pytorch-patterns` — 핵심 Python/PyTorch
- `mle-workflow` — production ML loop (data → train → eval → deploy)
- `docker-patterns` — Isaac Lab Docker (shader cache, multi-stage)
- `tdd-workflow` — 80%+ coverage 강제
- `agentic-engineering` — eval-first, cost-aware model routing (VLM 호출 시)
- `agent-harness-construction` — VLA action space 설계
- `agent-introspection-debugging` — 정책 실패 디버깅
- `codebase-onboarding` — 새 에이전트 컨텍스트 주입

## MCP Servers (설정됨, 첫 사용 시 npx로 자동 설치)
- **context7** — Isaac Lab/PyTorch/Gymnasium docs 실시간 (`@upstash/context7-mcp`)
- **sequential-thinking** — RL/제어 알고리즘 chain-of-thought
- **github** — PR/Issue 자동화 (`GITHUB_PERSONAL_ACCESS_TOKEN` 환경변수 필요)

설정 위치: `~/.claude.json` 의 `mcpServers`. GitHub MCP 활성화는 PAT 발급 후:
```bash
# ~/.claude.json 의 mcpServers.github.env.GITHUB_PERSONAL_ACCESS_TOKEN 값 교체
```

## 런타임
- Node.js 25.8.2 (`~/miniconda3/bin/node`) — conda-forge로 설치, ECC hooks/npx MCP용
- uv 0.11.16 (`~/miniconda3/bin/uvx`) — uvx 기반 MCP용
- Python 3.x miniconda base — Isaac Lab은 별도 docker 컨테이너

## 워크플로우 컨벤션
- Isaac Lab 실행은 `./run_sim.sh` (Docker 기반, shader cache 마운트)
- 시뮬 클라우드는 Vast.ai (AWS 대비 가성비)
- VNC 접근: SSH 터널 → `localhost:6080/vnc.html`
- 4-task RL pipeline: OpenDoor / PickPrint / ... (sim/isaac_lab/tasks/)
- joint indices: Z=0, Y=1, X=2, door=3 (gantry axes locked, stiffness 10000)
