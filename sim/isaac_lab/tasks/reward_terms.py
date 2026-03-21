"""
sim/isaac_lab/tasks/reward_terms.py
-------------------------------------
Reward function components for the printer arm tasks.

Each function takes the environment as first argument and returns
a per-environment tensor of reward values.

The P2S printer is loaded as a single articulation. The door_hinge
joint is at index 3 (after Z-axis, Y-axis, X-axis).
"""

from __future__ import annotations

import torch
from isaaclab.envs import DirectRLEnv


def door_angle_reward(env: DirectRLEnv) -> torch.Tensor:
    """Reward proportional to door opening angle."""
    # door_hinge is joint index 3 in the printer articulation
    door_angle = env.printer.data.joint_pos[:, 3]
    target_angle = 1.2  # ~70 degrees (fully open)
    return torch.clamp(door_angle / target_angle, 0.0, 1.0)


def ee_near_handle(env: DirectRLEnv) -> torch.Tensor:
    """Reward for end-effector being close to the door handle."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    # Handle position is approximate relative to printer root
    printer_pos = env.printer.data.root_pos_w[:, :3]
    handle_pos = printer_pos + torch.tensor(
        [0.0, 0.15, 0.15], device=env.device
    )
    dist = torch.norm(ee_pos - handle_pos, dim=-1)
    return torch.exp(-10.0 * dist)


def reach_object(env: DirectRLEnv) -> torch.Tensor:
    """Reward for approaching the print object."""
    ee_pos = env.ee.data.target_pos_w[:, 0, :3]
    obj_pos = env.print_object.data.root_pos_w[:, :3]
    dist = torch.norm(ee_pos - obj_pos, dim=-1)
    return torch.exp(-5.0 * dist)


def lift_object(env: DirectRLEnv) -> torch.Tensor:
    """Reward for lifting the object above the build plate."""
    obj_z = env.print_object.data.root_pos_w[:, 2]
    plate_z = env.build_plate.data.root_pos_w[:, 2] + 0.01
    lift_height = torch.clamp(obj_z - plate_z, 0.0, 0.1)
    return lift_height / 0.1


def gripper_contact(env: DirectRLEnv) -> torch.Tensor:
    """Reward for gripper contact forces on the object (from contact sensor)."""
    # This requires a contact sensor on the gripper -- simplified here
    gripper_pos = env.robot.data.joint_pos[:, 5:6]
    # Tighter gripper = higher contact reward
    return 1.0 - torch.clamp(gripper_pos / 0.04, 0.0, 1.0).squeeze(-1)


def action_smoothness(env: DirectRLEnv) -> torch.Tensor:
    """Penalty for jerky actions (L2 norm of action)."""
    if hasattr(env, "_last_actions") and env._last_actions is not None:
        delta = env.action_manager.action - env._last_actions
        return -torch.sum(delta ** 2, dim=-1)
    return torch.zeros(env.num_envs, device=env.device)
