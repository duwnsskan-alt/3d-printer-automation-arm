"""
sim/isaac_lab/tasks/termination_terms.py
------------------------------------------
Termination conditions for printer arm tasks.

The P2S printer is loaded as a single articulation. The door_hinge
joint is at index 3 (after Z-axis, Y-axis, X-axis).
"""

from __future__ import annotations

import torch
from isaaclab.envs import DirectRLEnv


def door_fully_open(env: DirectRLEnv) -> torch.Tensor:
    """Return True for environments where door is fully open (>= 70 deg)."""
    door_angle = env.printer.data.joint_pos[:, 3]
    return door_angle >= 1.2  # ~70 degrees


def object_lifted(env: DirectRLEnv) -> torch.Tensor:
    """Return True when object is lifted 5cm above build plate."""
    obj_z = env.print_object.data.root_pos_w[:, 2]
    plate_z = env.build_plate.data.root_pos_w[:, 2] + 0.01
    return (obj_z - plate_z) > 0.05


def object_out_of_bounds(env: DirectRLEnv) -> torch.Tensor:
    """Return True when object falls outside workspace."""
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    return (
        (torch.abs(obj_pos[:, 0]) > 0.8)
        | (torch.abs(obj_pos[:, 1]) > 0.8)
        | (obj_pos[:, 2] < -0.1)
    )


def joint_limit_violation(env: DirectRLEnv) -> torch.Tensor:
    """Return True if any joint exceeds its limits."""
    joint_pos = env.robot.data.joint_pos[:, :6]
    lower = env.robot.data.joint_pos_limits[:, :6, 0]
    upper = env.robot.data.joint_pos_limits[:, :6, 1]
    violation = (joint_pos < lower + 0.05) | (joint_pos > upper - 0.05)
    return violation.any(dim=-1)


def time_out(env: DirectRLEnv) -> torch.Tensor:
    """Return True when episode time limit is reached."""
    return env.episode_length_buf >= env.max_episode_length
