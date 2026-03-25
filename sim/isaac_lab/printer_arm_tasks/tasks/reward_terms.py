"""
reward_terms.py — Reward function components for all printer arm tasks.

Each function takes the environment and returns a per-env reward tensor.

Robot joint indices: rail(0), arm(1-5), gripper(6)
Printer joint indices: Z(0), Y(1), X(2), door_hinge(3)
"""

from __future__ import annotations

import torch
from isaaclab.envs import DirectRLEnv

GRIPPER_IDX = 6
DOOR_HINGE_IDX = 3


# ── OpenDoor rewards ─────────────────────────────────────────────────────────

def approach_ee_handle(env: DirectRLEnv) -> torch.Tensor:
    """Exponential reward for EE approaching the door handle."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    handle_pos = env.door_handle.data.target_pos_w[:, 0, :3]
    dist = torch.norm(ee_pos - handle_pos, dim=-1)
    return torch.exp(-10.0 * dist)


def grasp_handle(env: DirectRLEnv) -> torch.Tensor:
    """Reward for closing the gripper when near the door handle."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    handle_pos = env.door_handle.data.target_pos_w[:, 0, :3]
    dist = torch.norm(ee_pos - handle_pos, dim=-1)
    near = (dist < 0.05).float()
    gripper = env.robot.data.joint_pos[:, GRIPPER_IDX]
    grip_reward = torch.clamp(gripper / 1.5, 0.0, 1.0)
    return near * grip_reward


def open_door_angle(env: DirectRLEnv) -> torch.Tensor:
    """Reward proportional to how far the door is opened."""
    angle = env.printer.data.joint_pos[:, DOOR_HINGE_IDX]
    return torch.clamp(angle / 1.2, 0.0, 1.0)


def multi_stage_door_bonus(env: DirectRLEnv) -> torch.Tensor:
    """Discrete bonuses at 0.3, 0.7, and 1.2 rad milestones."""
    angle = env.printer.data.joint_pos[:, DOOR_HINGE_IDX]
    bonus = torch.zeros_like(angle)
    bonus += (angle > 0.3).float() * 0.5
    bonus += (angle > 0.7).float() * 0.75
    bonus += (angle > 1.2).float() * 1.0
    return bonus


# ── PickPrint rewards ─────────────────────────────────────────────────────────

def reach_object(env: DirectRLEnv) -> torch.Tensor:
    """Exponential reward for EE approaching the print object."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    dist = torch.norm(ee_pos - obj_pos, dim=-1)
    return torch.exp(-5.0 * dist)


def gripper_alignment(env: DirectRLEnv) -> torch.Tensor:
    """Reward for approaching the object from above."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    height_diff = ee_pos[:, 2] - obj_pos[:, 2]
    xy_dist = torch.norm(ee_pos[:, :2] - obj_pos[:, :2], dim=-1)
    above = (height_diff > 0.02) & (xy_dist < 0.05)
    return above.float()


def grasp_object(env: DirectRLEnv) -> torch.Tensor:
    """Reward for closing gripper when near the object."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    dist = torch.norm(ee_pos - obj_pos, dim=-1)
    near = (dist < 0.04).float()
    gripper = env.robot.data.joint_pos[:, GRIPPER_IDX]
    grip_reward = torch.clamp(gripper / 1.5, 0.0, 1.0)
    return near * grip_reward


def lift_object(env: DirectRLEnv) -> torch.Tensor:
    """Reward for lifting the object above the build plate."""
    obj_z = env.print_object.data.root_pos_w[:, 2]
    plate_z = env.build_plate.data.root_pos_w[:, 2] + 0.01
    lift = torch.clamp(obj_z - plate_z, 0.0, 0.1) / 0.1
    return lift


def object_held(env: DirectRLEnv) -> torch.Tensor:
    """Continuous reward for maintaining grip on the object."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    dist = torch.norm(ee_pos - obj_pos, dim=-1)
    gripper = env.robot.data.joint_pos[:, GRIPPER_IDX]
    held = (dist < 0.06) & (gripper > 0.3)
    return held.float()


# ── PlacePrint rewards ────────────────────────────────────────────────────────

def approach_staging(env: DirectRLEnv) -> torch.Tensor:
    """Exponential reward for moving the object toward the staging area."""
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    staging_pos = env.staging_area.data.root_pos_w[:, :3]
    dist = torch.norm(obj_pos - staging_pos, dim=-1)
    return torch.exp(-5.0 * dist)


def place_height(env: DirectRLEnv) -> torch.Tensor:
    """Reward for lowering object to staging surface height."""
    obj_z = env.print_object.data.root_pos_w[:, 2]
    staging_z = env.staging_area.data.root_pos_w[:, 2] + 0.01
    height_error = torch.abs(obj_z - staging_z)
    return torch.exp(-20.0 * height_error)


def release_at_target(env: DirectRLEnv) -> torch.Tensor:
    """Reward for opening gripper when object is over the staging area."""
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    staging_pos = env.staging_area.data.root_pos_w[:, :3]
    xy_dist = torch.norm(obj_pos[:, :2] - staging_pos[:, :2], dim=-1)
    near_target = xy_dist < 0.05
    gripper = env.robot.data.joint_pos[:, GRIPPER_IDX]
    gripper_open = gripper < 0.1
    return (near_target & gripper_open).float()


# ── CloseDoor rewards ─────────────────────────────────────────────────────────

def approach_door(env: DirectRLEnv) -> torch.Tensor:
    """Exponential reward for EE approaching the door (to push it)."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    handle_pos = env.door_handle.data.target_pos_w[:, 0, :3]
    dist = torch.norm(ee_pos - handle_pos, dim=-1)
    return torch.exp(-10.0 * dist)


def close_door_angle(env: DirectRLEnv) -> torch.Tensor:
    """Reward proportional to how much the door has been closed."""
    angle = env.printer.data.joint_pos[:, DOOR_HINGE_IDX]
    max_angle = 2.094
    return (max_angle - angle) / max_angle


def door_closed_bonus(env: DirectRLEnv) -> torch.Tensor:
    """Large bonus when door is fully closed."""
    angle = env.printer.data.joint_pos[:, DOOR_HINGE_IDX]
    return (angle < 0.05).float()


# ── Common rewards ────────────────────────────────────────────────────────────

def action_rate_l2(env: DirectRLEnv) -> torch.Tensor:
    """Penalty proportional to action magnitude (encourages smooth motion)."""
    if hasattr(env, "_prev_actions") and env._prev_actions is not None:
        return -torch.sum(env._prev_actions ** 2, dim=-1)
    return torch.zeros(env.num_envs, device=env.device)
