"""
termination_terms.py — Termination conditions for all printer arm tasks.

Each function returns a boolean tensor [num_envs] indicating which envs should terminate.

Robot joint indices: rail(0), arm(1-5), gripper(6)
Printer joint indices: Z(0), Y(1), X(2), door_hinge(3)
"""

from __future__ import annotations

import torch
from isaaclab.envs import DirectRLEnv

DOOR_HINGE_IDX = 3


# ── Door conditions ──────────────────────────────────────────────────────────

def door_fully_open(env: DirectRLEnv) -> torch.Tensor:
    """True when door is opened past 1.2 rad (~69 deg)."""
    angle = env.printer.data.joint_pos[:, DOOR_HINGE_IDX]
    return angle >= 1.2


def door_closed(env: DirectRLEnv) -> torch.Tensor:
    """True when door is nearly closed (< 0.05 rad)."""
    angle = env.printer.data.joint_pos[:, DOOR_HINGE_IDX]
    return angle < 0.05


# ── Object conditions ────────────────────────────────────────────────────────

def object_lifted(env: DirectRLEnv) -> torch.Tensor:
    """True when object is lifted 5cm above the build plate."""
    obj_z = env.print_object.data.root_pos_w[:, 2]
    plate_z = env.build_plate.data.root_pos_w[:, 2] + 0.01
    return (obj_z - plate_z) > 0.05


def object_dropped(env: DirectRLEnv) -> torch.Tensor:
    """True when object falls below the workspace or far out of bounds."""
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    return (
        (obj_pos[:, 2] < -0.1)
        | (torch.abs(obj_pos[:, 0]) > 1.0)
        | (torch.abs(obj_pos[:, 1]) > 1.0)
    )


def object_on_staging(env: DirectRLEnv) -> torch.Tensor:
    """True when object is within 5cm XY of staging center and near surface height."""
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    staging_pos = env.staging_area.data.root_pos_w[:, :3]
    xy_dist = torch.norm(obj_pos[:, :2] - staging_pos[:, :2], dim=-1)
    z_near = torch.abs(obj_pos[:, 2] - (staging_pos[:, 2] + 0.01)) < 0.03
    return (xy_dist < 0.05) & z_near


# ── Common conditions ────────────────────────────────────────────────────────

def time_out(env: DirectRLEnv) -> torch.Tensor:
    """True when episode time limit is reached."""
    return env.episode_length_buf >= env.max_episode_length
