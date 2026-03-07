"""
src/robot/robot_api.py
----------------------
High-level, safe robot API that VLM-generated code calls.

All methods here are whitelisted in the safety layer. Each operation:
  1. Checks E-stop status
  2. Validates parameters
  3. Translates to low-level servo commands via FeetechDriver
  4. Verifies completion

Predefined poses (home, door_approach, etc.) are loaded from config.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from .feetech_driver import FeetechDriver
from src.safety.safety_layer import SafetyLayer

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class RobotAPI:
    """
    Safe, high-level robot control interface.

    All methods are designed to be called by VLM-generated code and are
    validated by the SafetyLayer before execution.

    Args:
        cfg: Full config dict
        safety: SafetyLayer instance
    """

    GRIPPER_OPEN_TICKS = 2500    # STS3215 encoder position for open
    GRIPPER_CLOSE_TICKS = 1600   # STS3215 encoder position for closed
    GRIPPER_PARTIAL_TICKS = 2000  # Partial close for delicate objects

    def __init__(self, cfg: dict, safety: SafetyLayer) -> None:
        self.cfg = cfg
        self.robot_cfg = cfg["robot"]
        self.safety = safety

        self.driver = FeetechDriver(
            port=self.robot_cfg["port"],
            baudrate=self.robot_cfg["baudrate"],
            joint_ids=self.robot_cfg["joint_ids"],
            gripper_id=self.robot_cfg["gripper_id"],
        )

        self._poses: dict[str, list[int]] = self.robot_cfg.get("poses", {})
        self._max_torque: int = self.robot_cfg.get("max_torque", 800)
        self._max_velocity: int = self.robot_cfg.get("max_velocity", 300)
        self._connected = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Open serial connection and initialize all servos."""
        self.driver.connect()
        self._configure_servos()
        self._connected = True
        # Register E-stop callback
        self.safety.register_estop_callback(self._emergency_stop)
        # Start overload monitor
        self.safety.start_overload_monitor(self)
        log.info("RobotAPI connected and overload monitor running.")

    def disconnect(self) -> None:
        """Safely disconnect: move to home then disable torque."""
        if self._connected:
            try:
                self.move_to_pose("home")
            except Exception as e:
                log.warning("Could not move to home on disconnect: %s", e)
            self.safety.stop_overload_monitor()
            self.driver.disable_torque_all()
            self.driver.disconnect()
            self._connected = False
            log.info("RobotAPI disconnected.")

    def _configure_servos(self) -> None:
        """Set torque and velocity limits on all servos."""
        for jid in self.robot_cfg["joint_ids"] + [self.robot_cfg["gripper_id"]]:
            self.driver.set_torque_limit(jid, self._max_torque)
            self.driver.set_velocity(jid, self._max_velocity)
        log.info("Servo parameters configured.")

    def _emergency_stop(self) -> None:
        """Immediately disable all motor torque (E-stop callback)."""
        log.critical("Emergency stop: disabling all torque NOW.")
        try:
            self.driver.disable_torque_all()
        except Exception as e:
            log.error("Error during emergency torque disable: %s", e)

    # ── Whitelisted API Methods ───────────────────────────────────────────────

    def open_door(self, speed: int = 200) -> bool:
        """
        Open the P2S front door using a predefined trajectory.

        Returns:
            True on success, False on failure
        """
        self.safety.assert_not_stopped()
        log.info("Opening door...")
        try:
            self.move_to_pose("door_approach", speed=speed)
            time.sleep(0.3)
            self.gripper_close()  # Grab door handle
            time.sleep(0.2)
            self.move_to_pose("door_grab", speed=150)
            time.sleep(0.2)
            self.move_to_pose("door_open", speed=100)  # Pull door open slowly
            time.sleep(0.5)
            self.gripper_open()
            log.info("Door opened successfully.")
            return True
        except Exception as e:
            log.error("open_door failed: %s", e)
            return False

    def close_door(self, speed: int = 150) -> bool:
        """
        Close the P2S front door.

        Returns:
            True on success, False on failure
        """
        self.safety.assert_not_stopped()
        log.info("Closing door...")
        try:
            self.move_to_pose("door_open", speed=speed)
            time.sleep(0.2)
            self.gripper_close()
            time.sleep(0.2)
            self.move_to_pose("door_grab", speed=100)
            time.sleep(0.2)
            self.move_to_pose("door_approach", speed=100)
            self.gripper_open()
            self.move_to_pose("home", speed=speed)
            log.info("Door closed successfully.")
            return True
        except Exception as e:
            log.error("close_door failed: %s", e)
            return False

    def pick_object(
        self,
        x_offset: float = 0.0,
        y_offset: float = 0.0,
        approach_speed: int = 150,
    ) -> bool:
        """
        Pick the printed object from the build plate.

        Args:
            x_offset: Fine adjustment in mm (from VLM vision output)
            y_offset: Fine adjustment in mm
            approach_speed: Servo speed during descent

        Returns:
            True on success
        """
        self.safety.assert_not_stopped()
        log.info("Picking object (offset=%.1f, %.1f mm)...", x_offset, y_offset)
        try:
            self.gripper_open()
            self.move_to_pose("pick_hover", speed=200)
            time.sleep(0.3)
            # Apply fine offset if VLM provided one
            if abs(x_offset) > 0.5 or abs(y_offset) > 0.5:
                self._apply_cartesian_offset(x_offset, y_offset)
            self.move_to_pose("pick_down", speed=approach_speed)
            time.sleep(0.4)
            self.gripper_close(partial=True)  # Gentle grip for FDM parts
            time.sleep(0.3)
            # Verify grip by checking gripper position
            if not self._verify_grip():
                log.warning("Grip verification failed — may have missed object.")
            self.move_to_pose("pick_hover", speed=100)  # Lift slowly
            log.info("Pick complete.")
            return True
        except Exception as e:
            log.error("pick_object failed: %s", e)
            return False

    def place_object(
        self,
        pose_name: str = "place_hover",
        speed: int = 150,
    ) -> bool:
        """
        Place the held object at the target location.

        Args:
            pose_name: Target pose from config (default: place_hover)
            speed: Movement speed

        Returns:
            True on success
        """
        self.safety.assert_not_stopped()
        log.info("Placing object at pose=%s...", pose_name)
        try:
            self.move_to_pose(pose_name, speed=speed)
            time.sleep(0.3)
            self.move_to_pose("place_down", speed=100)
            time.sleep(0.2)
            self.gripper_open()
            time.sleep(0.3)
            self.move_to_pose(pose_name, speed=speed)
            self.move_to_pose("home", speed=200)
            log.info("Place complete.")
            return True
        except Exception as e:
            log.error("place_object failed: %s", e)
            return False

    def move_to_pose(self, pose_name: str, speed: int | None = None) -> None:
        """
        Move arm to a named pose defined in config.

        Args:
            pose_name: Key from config.robot.poses
            speed: Override servo speed (STS units)

        Raises:
            KeyError: If pose_name not found
        """
        self.safety.assert_not_stopped()
        if pose_name not in self._poses:
            raise KeyError(f"Unknown pose: {pose_name!r}. Available: {list(self._poses)}")
        positions = self._poses[pose_name]
        spd = speed or self._max_velocity
        log.debug("Moving to pose %r: %s", pose_name, positions)
        self.driver.move_joints(positions, speed=spd)
        self._wait_for_motion(timeout=10.0)

    def move_joints_raw(self, positions: list[int], speed: int = 200) -> None:
        """
        Move all joints to raw encoder positions.

        Args:
            positions: List of encoder ticks per joint
            speed: Movement speed
        """
        self.safety.assert_not_stopped()
        if len(positions) != len(self.robot_cfg["joint_ids"]):
            raise ValueError(
                f"Expected {len(self.robot_cfg['joint_ids'])} joint positions, got {len(positions)}"
            )
        self.driver.move_joints(positions, speed=speed)

    def gripper_open(self) -> None:
        """Fully open the gripper."""
        self.safety.assert_not_stopped()
        self.driver.set_position(self.robot_cfg["gripper_id"], self.GRIPPER_OPEN_TICKS, speed=300)
        time.sleep(0.3)

    def gripper_close(self, partial: bool = False) -> None:
        """
        Close the gripper.

        Args:
            partial: If True, stop at partial close position (gentler grip)
        """
        self.safety.assert_not_stopped()
        ticks = self.GRIPPER_PARTIAL_TICKS if partial else self.GRIPPER_CLOSE_TICKS
        self.driver.set_position(self.robot_cfg["gripper_id"], ticks, speed=200)
        time.sleep(0.4)

    def get_joint_positions(self) -> list[int]:
        """Return current encoder positions for all joints."""
        return self.driver.read_positions()

    def read_torques(self) -> dict[int, int]:
        """
        Return current torque readings as {joint_id: torque_value}.
        Called by the overload monitor.
        """
        return self.driver.read_torques()

    def wait(self, seconds: float) -> None:
        """Sleep for specified duration (usable from VLM code)."""
        self.safety.assert_not_stopped()
        log.debug("Waiting %.2f seconds...", seconds)
        time.sleep(seconds)

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _wait_for_motion(self, timeout: float = 10.0, poll_interval: float = 0.05) -> None:
        """Block until all joints stop moving or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.safety.is_stopped:
                raise Exception("E-stop triggered during motion wait.")
            if self.driver.is_all_stopped():
                return
            time.sleep(poll_interval)
        log.warning("Motion timeout after %.1fs — proceeding anyway.", timeout)

    def _verify_grip(self) -> bool:
        """Check if gripper has gripped something (position between open and target)."""
        pos = self.driver.read_single_position(self.robot_cfg["gripper_id"])
        # If gripper stopped short of full close, something is in it
        return self.GRIPPER_CLOSE_TICKS < pos < self.GRIPPER_OPEN_TICKS - 100

    def _apply_cartesian_offset(self, x_mm: float, y_mm: float) -> None:
        """
        Apply a small Cartesian offset to the current position.
        Uses a simplified Jacobian for SO-100 near the pick pose.
        This is approximate; for production use full IK.
        """
        # Approx: at pick_hover, 1mm ≈ 3.5 ticks for joint 1 (base rotation)
        # and 2.0 ticks for joint 2 (shoulder)
        TICKS_PER_MM_BASE = 3.5
        TICKS_PER_MM_SHOULDER = 2.0

        current = self.driver.read_positions()
        current[0] = int(current[0] + x_mm * TICKS_PER_MM_BASE)
        current[1] = int(current[1] + y_mm * TICKS_PER_MM_SHOULDER)
        self.driver.move_joints(current, speed=100)
        self._wait_for_motion(timeout=5.0)

    # ── Context Manager ──────────────────────────────────────────────────────

    def __enter__(self) -> "RobotAPI":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()
