"""
main.py
--------
Unified edge entry point for the 3D Printer Automation Arm system.

Validates hardware, initializes all components, starts the state machine,
and handles graceful shutdown.

Usage:
  python main.py                          # Full system
  python main.py --dry-run                # Validate hardware only
  python main.py --no-robot --no-printer  # Camera + VLA dev mode
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.config_loader import load_config, mask_sensitive

log = logging.getLogger("automation")


# ─── Argument Parsing ────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="3D Printer Automation Arm - Edge Runtime",
    )
    parser.add_argument(
        "--config", type=Path, default=Path("config/config.yaml"),
        help="Path to config YAML (default: config/config.yaml)",
    )
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None, help="Override log level from config",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate hardware and config, then exit",
    )
    parser.add_argument(
        "--no-robot", action="store_true",
        help="Skip robot connection (camera/VLM dev mode)",
    )
    parser.add_argument(
        "--no-printer", action="store_true",
        help="Skip MQTT printer connection",
    )
    parser.add_argument(
        "--next-job", type=Path, default=None,
        help="Path to .3mf file for the next print job",
    )
    return parser.parse_args()


# ─── Logging Setup ───────────────────────────────────────────────────────────

def setup_logging(cfg: dict, level_override: str | None = None) -> None:
    log_cfg = cfg.get("logging", {})
    level = level_override or log_cfg.get("level", "INFO")
    log_dir = Path(log_cfg.get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)

    # File handler with rotation
    file_h = RotatingFileHandler(
        log_dir / "automation.log",
        maxBytes=log_cfg.get("max_bytes", 50 * 1024 * 1024),
        backupCount=log_cfg.get("backup_count", 5),
    )
    file_h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))
    root.addHandler(console)
    root.addHandler(file_h)


# ─── Hardware Validation ─────────────────────────────────────────────────────

def validate_hardware(cfg: dict, args: argparse.Namespace) -> dict[str, bool]:
    """Check availability of each hardware component. Returns {name: ok}."""
    results = {}

    # GPU
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_mem / (1024 ** 3)
            log.info("GPU: %s (%.1f GB VRAM)", props.name, vram_gb)
            results["gpu"] = True
            if vram_gb < 6:
                log.warning("GPU VRAM < 6GB: SmolVLA + ZED may be tight")
        else:
            log.warning("CUDA not available. VLA inference will use CPU (slow).")
            results["gpu"] = False
    except ImportError:
        log.warning("PyTorch not installed.")
        results["gpu"] = False

    # Serial port (robot)
    if not args.no_robot:
        port = cfg.get("robot", {}).get("port", "/dev/ttyACM0")
        exists = os.path.exists(port)
        results["serial"] = exists
        if exists:
            log.info("Serial port: %s (found)", port)
        else:
            log.warning("Serial port %s not found. Is the robot connected?", port)
    else:
        results["serial"] = None
        log.info("Serial port: skipped (--no-robot)")

    # Cameras
    cameras_cfg = cfg.get("cameras", {})
    for label, cam_cfg in cameras_cfg.items():
        cam_type = cam_cfg.get("type", "usb")
        if cam_type == "zed":
            try:
                import pyzed.sl as sl_test
                log.info("Camera %r (ZED): SDK v%s found", label, sl_test.Camera().get_sdk_version())
                results[f"camera_{label}"] = True
            except ImportError:
                log.warning("Camera %r: ZED SDK not installed", label)
                results[f"camera_{label}"] = False
        else:
            device = cam_cfg.get("device", "")
            exists = os.path.exists(device)
            results[f"camera_{label}"] = exists
            if exists:
                log.info("Camera %r (USB): %s found", label, device)
            else:
                log.warning("Camera %r: device %s not found", label, device)

    # Printer MQTT
    if not args.no_printer:
        host = cfg.get("printer", {}).get("host", "")
        port = cfg.get("printer", {}).get("mqtt_port", 8883)
        try:
            sock = socket.create_connection((host, port), timeout=3)
            sock.close()
            log.info("Printer MQTT: %s:%d reachable", host, port)
            results["printer"] = True
        except (socket.error, OSError) as e:
            log.warning("Printer MQTT: %s:%d unreachable (%s)", host, port, e)
            results["printer"] = False
    else:
        results["printer"] = None
        log.info("Printer MQTT: skipped (--no-printer)")

    return results


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    setup_logging(cfg, args.log_level)

    log.info("=" * 60)
    log.info("3D Printer Automation Arm - Edge Runtime")
    log.info("=" * 60)
    log.info("Config: %s", args.config)
    log.debug("Config (masked): %s", mask_sensitive(cfg))

    # ── Hardware validation ──
    hw = validate_hardware(cfg, args)
    log.info("Hardware check: %s", {k: v for k, v in hw.items() if v is not None})

    if args.dry_run:
        failed = [k for k, v in hw.items() if v is False]
        if failed:
            log.warning("Dry-run: components not available: %s", failed)
        else:
            log.info("Dry-run: all components OK")
        return

    # ── Initialize components in dependency order ──
    from src.safety.safety_layer import SafetyLayer
    from src.vision.camera_manager import CameraManager

    safety = SafetyLayer(cfg)
    cameras = CameraManager(cfg["cameras"])

    robot = None
    if not args.no_robot:
        from src.robot.robot_api import RobotAPI
        robot = RobotAPI(cfg, safety)

    printer = None
    if not args.no_printer:
        from src.printer.bambu_client import BambuClient
        printer = BambuClient(cfg["printer"])

    from src.vision.vlm_orchestrator import VLMOrchestrator
    from src.vla.vla_engine import VLAEngine
    from src.orchestrator.state_machine import AutomationStateMachine

    vlm = VLMOrchestrator(cfg, safety, robot)
    vla = VLAEngine(cfg, robot, cameras, safety)

    # ── Connect hardware ──
    cameras.open_all()
    log.info("Cameras opened.")

    if robot:
        robot.connect()
        log.info("Robot connected.")

    if printer:
        printer.connect()
        log.info("Printer connected.")

    # ── Load VLA model ──
    vla.load_model()
    log.info("VLA model loaded.")

    # ── Start state machine ──
    state_machine = AutomationStateMachine(
        cfg=cfg,
        printer=printer,
        robot=robot,
        vlm=vlm,
        cameras=cameras,
        safety=safety,
        next_job_path=args.next_job,
    )

    shutdown_event = threading.Event()

    def shutdown_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        log.info("Received %s, shutting down...", sig_name)
        shutdown_event.set()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    state_machine.start()
    log.info("System ready. Waiting for print completion...")

    # ── Block until shutdown signal ──
    shutdown_event.wait()

    # ── Graceful shutdown ──
    log.info("Shutting down components...")
    state_machine.stop()
    vla.stop()
    cameras.close_all()
    if robot:
        robot.disconnect()
    if printer:
        printer.disconnect()

    log.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Fatal error in main")
        sys.exit(1)
