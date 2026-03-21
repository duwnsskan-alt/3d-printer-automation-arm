#!/bin/bash
# ============================================================
# setup_edge.sh - Desktop Edge Environment Setup
# ============================================================
# One-command setup for the 3D Printer Automation Arm edge system.
# Run from project root: bash scripts/setup_edge.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
VENV_DIR="${PROJECT_DIR}/.venv"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

echo "============================================================"
echo " 3D Printer Automation Arm - Edge Setup"
echo "============================================================"
echo ""

# ─── 1. System Checks ──────────────────────────────────────────

info "Checking system requirements..."

# OS
if [[ ! -f /etc/os-release ]]; then
    error "Cannot detect OS. This script targets Ubuntu/Debian."
    exit 1
fi
source /etc/os-release
info "OS: ${PRETTY_NAME}"

# Python
if ! command -v python3 &>/dev/null; then
    error "python3 not found. Install with: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
PYTHON_VER=$(python3 --version 2>&1)
info "Python: ${PYTHON_VER}"

# NVIDIA driver
if command -v nvidia-smi &>/dev/null; then
    DRIVER_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    info "GPU: ${GPU_NAME} (driver ${DRIVER_VER})"
else
    warn "nvidia-smi not found. GPU acceleration will not be available."
fi

# CUDA
if command -v nvcc &>/dev/null; then
    CUDA_VER=$(nvcc --version | grep "release" | sed 's/.*release //' | sed 's/,.*//')
    info "CUDA: ${CUDA_VER}"
elif [[ -d /usr/local/cuda ]]; then
    CUDA_VER=$(cat /usr/local/cuda/version.json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['cuda']['version'])" 2>/dev/null || echo "detected")
    info "CUDA: ${CUDA_VER} (at /usr/local/cuda)"
else
    warn "CUDA toolkit not found. Install from: https://developer.nvidia.com/cuda-toolkit"
fi

echo ""

# ─── 2. Python Virtual Environment ────────────────────────────

if [[ -d "${VENV_DIR}" ]]; then
    info "Virtual environment already exists at ${VENV_DIR}"
else
    info "Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

info "Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

info "Upgrading pip..."
pip install --upgrade pip -q

echo ""

# ─── 3. PyTorch with CUDA ─────────────────────────────────────

info "Installing PyTorch with CUDA support..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 -q

echo ""

# ─── 4. Project Dependencies ──────────────────────────────────

info "Installing project dependencies..."
pip install -r "${PROJECT_DIR}/requirements.txt" -q

echo ""

# ─── 5. ZED SDK Check ─────────────────────────────────────────

if python3 -c "import pyzed.sl" 2>/dev/null; then
    ZED_VER=$(python3 -c "import pyzed.sl as sl; print(sl.Camera().get_sdk_version())")
    info "ZED SDK: v${ZED_VER} (already installed)"
else
    warn "ZED SDK (pyzed) not found."
    echo ""
    echo "  The ZED SDK must be installed manually:"
    echo "  1. Download from: https://www.stereolabs.com/developers/release"
    echo "  2. Run the installer: chmod +x ZED_SDK_*.run && ./ZED_SDK_*.run"
    echo "  3. When prompted, install the Python API for your active Python version"
    echo "  4. Re-run this script or: pip install pyzed (from the SDK install dir)"
    echo ""
fi

# ─── 6. udev Rules ────────────────────────────────────────────

UDEV_RULE="/etc/udev/rules.d/99-feetech-servo.rules"
RULE_CONTENT='SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="ttyFEETECH", MODE="0666"'

if [[ -f "${UDEV_RULE}" ]]; then
    info "udev rule for Feetech servo already exists."
else
    echo ""
    info "Setting up udev rule for Feetech USB-Serial adapter..."
    echo "  This creates a stable symlink at /dev/ttyFEETECH"
    echo "  Rule: ${RULE_CONTENT}"
    echo ""
    read -rp "  Install udev rule? (requires sudo) [y/N]: " answer
    if [[ "${answer,,}" == "y" ]]; then
        echo "${RULE_CONTENT}" | sudo tee "${UDEV_RULE}" > /dev/null
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        info "udev rule installed. Replug the USB adapter to create /dev/ttyFEETECH"
    else
        warn "Skipped udev rule. You may need to run: sudo chmod 666 /dev/ttyACM0"
    fi
fi

echo ""

# ─── 7. Environment File ──────────────────────────────────────

ENV_FILE="${PROJECT_DIR}/config/.env"
if [[ -f "${ENV_FILE}" ]]; then
    info ".env file already exists at ${ENV_FILE}"
else
    info "Creating .env from template..."
    cp "${PROJECT_DIR}/config/.env.example" "${ENV_FILE}"
    warn "Fill in your API keys and secrets in: ${ENV_FILE}"
fi

echo ""

# ─── 8. Verification ──────────────────────────────────────────

info "Running verification checks..."
echo ""

# PyTorch + CUDA
echo -n "  PyTorch CUDA: "
if python3 -c "import torch; assert torch.cuda.is_available(); print(f'OK ({torch.cuda.get_device_name(0)})')" 2>/dev/null; then
    :
else
    echo -e "${RED}FAIL${NC} (CUDA not available)"
fi

# ZED SDK
echo -n "  ZED SDK:      "
if python3 -c "import pyzed.sl; print('OK')" 2>/dev/null; then
    :
else
    echo -e "${YELLOW}NOT INSTALLED${NC} (optional - install ZED SDK separately)"
fi

# Feetech SDK
echo -n "  Feetech SDK:  "
if python3 -c "import scservo_sdk; print('OK')" 2>/dev/null; then
    :
else
    echo -e "${RED}FAIL${NC}"
fi

# LeRobot
echo -n "  LeRobot:      "
if python3 -c "import lerobot; print('OK')" 2>/dev/null; then
    :
else
    echo -e "${RED}FAIL${NC}"
fi

# Serial port
echo -n "  Serial port:  "
if [[ -e /dev/ttyACM0 ]] || [[ -e /dev/ttyFEETECH ]]; then
    echo -e "${GREEN}OK${NC} ($(ls /dev/ttyACM* /dev/ttyFEETECH 2>/dev/null | tr '\n' ' '))"
else
    echo -e "${YELLOW}NOT CONNECTED${NC} (plug in robot to check)"
fi

echo ""
echo "============================================================"
info "Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Fill in config/.env with your API keys"
echo "    2. Install ZED SDK if not done yet"
echo "    3. Connect robot and camera hardware"
echo "    4. Test: python main.py --dry-run"
echo "    5. Run:  bash scripts/run_edge.sh"
echo "============================================================"
