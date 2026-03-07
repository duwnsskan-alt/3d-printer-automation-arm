"""
src/robot/feetech_driver.py
---------------------------
Low-level driver for Feetech STS3215 servo chain via SCServo SDK.

Wraps the scservo_sdk (Feetech's official Python library) into a clean interface.
All register addresses and protocol constants are for STS3215 / SCS series.

Install: pip install scservo_sdk
"""

from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# Register addresses (STS3215)
ADDR_STS_TORQUE_ENABLE   = 40
ADDR_STS_GOAL_POSITION   = 42
ADDR_STS_GOAL_VELOCITY   = 46   # Also used as max speed
ADDR_STS_TORQUE_LIMIT    = 48
ADDR_STS_PRESENT_POSITION = 56
ADDR_STS_PRESENT_LOAD    = 60
ADDR_STS_MOVING          = 66

PROTOCOL_END = 0  # STS/SMS protocol


class FeetechDriver:
    """
    Serial driver for a chain of Feetech STS3215 servos.

    Args:
        port: Serial device path (e.g. /dev/ttyUSB0)
        baudrate: Communication baudrate (typically 1000000)
        joint_ids: List of servo IDs in kinematic order (base→wrist)
        gripper_id: Servo ID of the gripper
    """

    def __init__(
        self,
        port: str,
        baudrate: int,
        joint_ids: list[int],
        gripper_id: int,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.joint_ids = joint_ids
        self.gripper_id = gripper_id
        self.all_ids = joint_ids + [gripper_id]

        self._port_handler = None
        self._packet_handler = None
        self._group_sync_write_pos = None
        self._group_sync_read_pos = None
        self._group_sync_read_load = None

    def connect(self) -> None:
        """Open serial port and initialize SDK handlers."""
        try:
            from scservo_sdk import (
                PortHandler,
                PacketHandler,
                GroupSyncWrite,
                GroupSyncRead,
                COMM_SUCCESS,
            )
        except ImportError as e:
            raise ImportError(
                "scservo_sdk not found. Install with: pip install scservo_sdk"
            ) from e

        self._ph = PortHandler(self.port)
        self._pk = PacketHandler(PROTOCOL_END)

        if not self._ph.openPort():
            raise IOError(f"Failed to open port {self.port}")
        if not self._ph.setBaudRate(self.baudrate):
            raise IOError(f"Failed to set baudrate {self.baudrate}")

        # GroupSyncWrite for goal position (2 bytes) + velocity (2 bytes) = 4 bytes
        self._gsw_pos = GroupSyncWrite(self._ph, self._pk, ADDR_STS_GOAL_POSITION, 4)
        # GroupSyncRead for present position
        self._gsr_pos = GroupSyncRead(self._ph, self._pk, ADDR_STS_PRESENT_POSITION, 2)
        # GroupSyncRead for present load (torque)
        self._gsr_load = GroupSyncRead(self._ph, self._pk, ADDR_STS_PRESENT_LOAD, 2)

        for sid in self.all_ids:
            self._gsr_pos.addParam(sid)
            self._gsr_load.addParam(sid)

        # Enable torque on all servos
        self.enable_torque_all()
        log.info("Feetech driver connected on %s @ %d bps", self.port, self.baudrate)

    def disconnect(self) -> None:
        """Close serial port."""
        if self._ph:
            self.disable_torque_all()
            self._ph.closePort()
            log.info("Feetech driver disconnected.")

    # ── Motion ───────────────────────────────────────────────────────────────

    def move_joints(self, positions: list[int], speed: int = 300) -> None:
        """
        Move all arm joints to target positions simultaneously.

        Args:
            positions: List of goal positions (ticks) matching joint_ids order
            speed: Goal velocity for all joints (STS units, 0-32767)
        """
        if len(positions) != len(self.joint_ids):
            raise ValueError(
                f"Expected {len(self.joint_ids)} positions, got {len(positions)}"
            )
        self._gsw_pos.clearParam()

        for sid, pos in zip(self.joint_ids, positions):
            # Pack: position (2 bytes LE) + velocity (2 bytes LE)
            data = [
                pos & 0xFF,
                (pos >> 8) & 0xFF,
                speed & 0xFF,
                (speed >> 8) & 0xFF,
            ]
            if not self._gsw_pos.addParam(sid, data):
                log.warning("Failed to add param for servo %d", sid)

        result = self._gsw_pos.txPacket()
        if result != 0:  # COMM_SUCCESS = 0
            log.warning("SyncWrite txPacket returned %d", result)

    def set_position(self, servo_id: int, position: int, speed: int = 200) -> None:
        """Move a single servo to position."""
        dxl_comm_result, dxl_error = self._pk.write4ByteTxRx(
            self._ph, servo_id, ADDR_STS_GOAL_POSITION,
            (position & 0xFFFF) | ((speed & 0xFFFF) << 16),
        )
        if dxl_comm_result != 0:
            log.warning("set_position servo %d: comm_result=%d", servo_id, dxl_comm_result)

    def set_torque_limit(self, servo_id: int, limit: int) -> None:
        """Set maximum torque for a servo (0-1023)."""
        self._pk.write2ByteTxRx(self._ph, servo_id, ADDR_STS_TORQUE_LIMIT, limit)

    def set_velocity(self, servo_id: int, velocity: int) -> None:
        """Set goal velocity (max speed) for a servo."""
        self._pk.write2ByteTxRx(self._ph, servo_id, ADDR_STS_GOAL_VELOCITY, velocity)

    # ── Sensing ──────────────────────────────────────────────────────────────

    def read_positions(self) -> list[int]:
        """Read current positions of all arm joints."""
        result = self._gsr_pos.txRxPacket()
        positions = []
        for sid in self.joint_ids:
            if self._gsr_pos.isAvailable(sid, ADDR_STS_PRESENT_POSITION, 2):
                pos = self._gsr_pos.getData(sid, ADDR_STS_PRESENT_POSITION, 2)
                positions.append(pos)
            else:
                positions.append(0)
                log.warning("Position read failed for servo %d", sid)
        return positions

    def read_single_position(self, servo_id: int) -> int:
        """Read position of a single servo."""
        pos, result, error = self._pk.read2ByteTxRx(
            self._ph, servo_id, ADDR_STS_PRESENT_POSITION
        )
        if result != 0:
            log.warning("read_single_position servo %d: result=%d", servo_id, result)
        return pos

    def read_torques(self) -> dict[int, int]:
        """Read present load (torque) for all servos. Returns {id: load}."""
        result = self._gsr_load.txRxPacket()
        torques = {}
        for sid in self.all_ids:
            if self._gsr_load.isAvailable(sid, ADDR_STS_PRESENT_LOAD, 2):
                load = self._gsr_load.getData(sid, ADDR_STS_PRESENT_LOAD, 2)
                # STS3215: sign bit is bit 10; convert to signed
                if load > 1023:
                    load = -(load & 0x3FF)
                torques[sid] = load
            else:
                torques[sid] = 0
        return torques

    def is_all_stopped(self) -> bool:
        """Return True if no joints are currently moving."""
        for sid in self.joint_ids:
            moving, result, _ = self._pk.read1ByteTxRx(
                self._ph, sid, ADDR_STS_MOVING
            )
            if result == 0 and moving != 0:
                return False
        return True

    # ── Torque Enable/Disable ─────────────────────────────────────────────────

    def enable_torque_all(self) -> None:
        """Enable torque on all servos."""
        for sid in self.all_ids:
            self._pk.write1ByteTxRx(self._ph, sid, ADDR_STS_TORQUE_ENABLE, 1)

    def disable_torque_all(self) -> None:
        """Disable torque on all servos (safe power-off state)."""
        for sid in self.all_ids:
            try:
                self._pk.write1ByteTxRx(self._ph, sid, ADDR_STS_TORQUE_ENABLE, 0)
            except Exception as e:
                log.error("Error disabling torque on servo %d: %s", sid, e)
