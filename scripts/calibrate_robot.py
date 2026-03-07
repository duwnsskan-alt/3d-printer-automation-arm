"""
scripts/calibrate_robot.py
---------------------------
Interactive robot calibration script.

Steps:
  1. Home all joints (move to hardstop)
  2. Record min/max encoder ticks for each joint
  3. Measure and set zero offsets
  4. Update config/config.yaml with calibrated values

Usage:
  python scripts/calibrate_robot.py --config config/config.yaml
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import load_config
from src.robot.feetech_driver import FeetechDriver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--joint", type=int, default=None, help="Calibrate only this joint ID")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    robot_cfg = cfg["robot"]

    driver = FeetechDriver(
        port=robot_cfg["port"],
        baudrate=robot_cfg["baudrate"],
        joint_ids=robot_cfg["joint_ids"],
        gripper_id=robot_cfg["gripper_id"],
    )
    driver.connect()

    print("\n" + "="*60)
    print("SO-100 Robot Calibration Tool")
    print("="*60)
    print("\nWARNING: Ensure the workspace is clear before proceeding.")
    print("The arm will move to its hardstop limits.")
    input("\nPress Enter to continue, or Ctrl+C to abort...\n")

    joint_ids = [args.joint] if args.joint else robot_cfg["joint_ids"]
    calibration_data = {}

    for jid in joint_ids:
        print(f"\n─── Calibrating Joint {jid} ────────────────────────")
        print(f"Manually move joint {jid} to its MINIMUM position.")
        input("Press Enter when ready...")
        min_pos = driver.read_single_position(jid)
        print(f"  Min position recorded: {min_pos}")

        print(f"Manually move joint {jid} to its MAXIMUM position.")
        input("Press Enter when ready...")
        max_pos = driver.read_single_position(jid)
        print(f"  Max position recorded: {max_pos}")

        print(f"Manually move joint {jid} to its HOME (zero) position.")
        input("Press Enter when ready...")
        home_pos = driver.read_single_position(jid)
        print(f"  Home position recorded: {home_pos}")

        calibration_data[jid] = {
            "min": min_pos,
            "max": max_pos,
            "home": home_pos,
            "range_deg": abs(max_pos - min_pos) * (360.0 / 4096),
        }
        print(f"  Joint {jid}: range = {calibration_data[jid]['range_deg']:.1f}°")

    driver.disable_torque_all()
    driver.disconnect()

    print("\n" + "="*60)
    print("Calibration Results:")
    print("="*60)
    for jid, data in calibration_data.items():
        print(f"  Joint {jid}: min={data['min']}, max={data['max']}, home={data['home']}")

    # Write to YAML
    import yaml
    cfg_path = Path(args.config)
    with open(cfg_path) as f:
        full_cfg = yaml.safe_load(f)

    homes = [calibration_data.get(jid, {}).get("home", 2048) for jid in robot_cfg["joint_ids"]]
    full_cfg["robot"]["home_position"] = homes

    with open(cfg_path, "w") as f:
        yaml.dump(full_cfg, f, default_flow_style=False, sort_keys=False)

    print(f"\n✅ Calibration saved to {cfg_path}")
    print("   Updated: robot.home_position")


if __name__ == "__main__":
    main()
