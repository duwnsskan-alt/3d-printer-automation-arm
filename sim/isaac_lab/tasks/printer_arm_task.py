"""
sim/isaac_lab/tasks/printer_arm_task.py
-----------------------------------------
Isaac Lab task definition for the 3D printer automation scenario.

Tasks:
  - OpenDoorTask: Open the P2S front door
  - PickPrintTask: Pick a finished print from the build plate
  - PlacePrintTask: Place the print at the staging area
  - FullCycleTask: Complete open→pick→place→close cycle

Reward shaping, termination conditions, and randomizations are defined here.

Usage (train with IsaacLab RSL-RL runner):
  python -m isaaclab.app.run \
    --task PrinterArm-OpenDoor-v0 \
    --headless \
    --num_envs 256
"""

from __future__ import annotations

from dataclasses import MISSING
from typing import TYPE_CHECKING

import torch

# Isaac Lab imports
from isaaclab.envs import DirectRLEnv, DirectRLEnvCfg
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sim import SimulationCfg
from isaaclab.assets import ArticulationCfg, RigidObjectCfg
from isaaclab.sensors import CameraCfg
from isaaclab.utils import configclass
from isaaclab.managers import RewardTermCfg as RewTerm, TerminationTermCfg as DoneTerm
from isaaclab.utils.math import (
    subtract_frame_transforms,
    quat_from_euler_xyz,
    sample_uniform,
)

import isaaclab.sim as sim_utils

from .scene_cfg import P2SArmSceneCfg
from . import reward_terms, termination_terms


# ─── Task Config ─────────────────────────────────────────────────────────────

@configclass
class OpenDoorTaskCfg(DirectRLEnvCfg):
    """Configuration for the door-opening task."""

    # ── Simulation ──────────────────────────────────────────────────────────
    sim: SimulationCfg = SimulationCfg(
        dt=0.01,           # 100 Hz physics
        render_interval=2, # Render every 2 steps → 50 Hz render
    )

    # ── Scene ────────────────────────────────────────────────────────────────
    scene: P2SArmSceneCfg = P2SArmSceneCfg(num_envs=MISSING, env_spacing=2.5)

    # ── RL Settings ──────────────────────────────────────────────────────────
    decimation = 2          # Policy runs at 50 Hz
    episode_length_s = 10.0  # 10 second episodes

    # Observation space: joint positions (5) + door angle (1) + ee pos (3) = 9
    num_observations = 9
    # Action space: delta joint positions (5 arm joints)
    num_actions = 5

    # ── Rewards ──────────────────────────────────────────────────────────────
    rewards = {
        "door_angle_reward": RewTerm(
            func=reward_terms.door_angle_reward,
            weight=2.0,
        ),
        "ee_near_handle": RewTerm(
            func=reward_terms.ee_near_handle,
            weight=1.0,
        ),
        "action_smoothness": RewTerm(
            func=reward_terms.action_smoothness,
            weight=-0.01,
        ),
    }

    # ── Terminations ─────────────────────────────────────────────────────────
    terminations = {
        "door_open_success": DoneTerm(
            func=termination_terms.door_fully_open,
        ),
        "time_out": DoneTerm(
            func=termination_terms.time_out,
            time_out=True,
        ),
        "joint_limit": DoneTerm(
            func=termination_terms.joint_limit_violation,
        ),
    }


@configclass
class PickPrintTaskCfg(DirectRLEnvCfg):
    """Configuration for the pick-object task."""

    sim: SimulationCfg = SimulationCfg(dt=0.01, render_interval=2)
    scene: P2SArmSceneCfg = P2SArmSceneCfg(num_envs=MISSING, env_spacing=2.5)

    decimation = 2
    episode_length_s = 15.0
    num_observations = 15  # joints(5) + ee_pos(3) + obj_pos(3) + rel_pos(3) + gripper(1) = 15
    num_actions = 6  # 5 arm joints + gripper

    rewards = {
        "reach_object": RewTerm(func=reward_terms.reach_object, weight=1.0),
        "lift_object": RewTerm(func=reward_terms.lift_object, weight=3.0),
        "gripper_contact": RewTerm(func=reward_terms.gripper_contact, weight=0.5),
        "action_smoothness": RewTerm(func=reward_terms.action_smoothness, weight=-0.01),
    }

    terminations = {
        "object_picked": DoneTerm(func=termination_terms.object_lifted),
        "time_out": DoneTerm(func=termination_terms.time_out, time_out=True),
        "joint_limit": DoneTerm(func=termination_terms.joint_limit_violation),
        "object_dropped": DoneTerm(func=termination_terms.object_out_of_bounds),
    }


# ─── Task Environments ───────────────────────────────────────────────────────

class OpenDoorEnv(DirectRLEnv):
    """
    Isaac Lab environment for training the door-open skill.

    Randomizations:
      - Initial arm pose (small joint noise)
      - Door hinge stiffness ±10%
      - Lighting (point lights random intensity)
    """

    cfg: OpenDoorTaskCfg

    def __init__(self, cfg: OpenDoorTaskCfg, render_mode: str | None = None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)
        self._door_open_threshold = 0.7  # Radians (~40°)

    def _setup_scene(self):
        """Called by base class to set up the Isaac Sim scene."""
        # Assets are defined in scene_cfg; just get references here
        self.robot = self.scene["robot"]
        self.door = self.scene["printer_door"]
        self.ee = self.scene["ee_frame"]

    def _pre_physics_step(self, actions: torch.Tensor) -> None:
        """Apply actions to the robot joints."""
        # actions: [num_envs, 5] delta joint positions (5 arm joints, no gripper)
        current_pos = self.robot.data.joint_pos[:, :5]
        target_pos = current_pos + actions * 0.05  # Scale action magnitude
        self.robot.set_joint_position_target(target_pos)

    def _get_observations(self) -> dict:
        """Collect observations for the policy."""
        joint_pos = self.robot.data.joint_pos[:, :5]  # [N, 5] arm joints only
        door_angle = self.door.data.joint_pos[:, :1]   # [N, 1]
        ee_pos = self.ee.data.target_pos_w[:, 0, :3]  # [N, 3]

        obs = torch.cat([joint_pos, door_angle, ee_pos], dim=-1)
        return {"policy": obs}

    def _get_rewards(self) -> torch.Tensor:
        """Compute per-environment rewards."""
        door_angle = self.door.data.joint_pos[:, 0]
        # Reward proportional to door opening
        reward = door_angle / self._door_open_threshold
        reward = torch.clamp(reward, 0.0, 1.0)
        return reward

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        """Return (terminated, truncated) tensors."""
        door_angle = self.door.data.joint_pos[:, 0]
        terminated = door_angle > self._door_open_threshold
        truncated = self.episode_length_buf >= self.max_episode_length
        return terminated, truncated

    def _reset_idx(self, env_ids: torch.Tensor) -> None:
        """Reset specified environments."""
        if len(env_ids) == 0:
            return

        super()._reset_idx(env_ids)

        # Randomize initial joint positions (small noise around home)
        # Order: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll
        joint_pos_home = torch.tensor(
            [0.0, -0.5, 1.0, 0.0, 0.5],
            device=self.device,
        ).unsqueeze(0).expand(len(env_ids), -1)
        noise = torch.randn_like(joint_pos_home) * 0.05
        self.robot.write_joint_state_to_sim(
            joint_pos_home + noise,
            torch.zeros_like(joint_pos_home),
            env_ids=env_ids,
        )

        # Reset door to closed position
        self.door.write_joint_state_to_sim(
            torch.zeros(len(env_ids), 1, device=self.device),
            torch.zeros(len(env_ids), 1, device=self.device),
            env_ids=env_ids,
        )


class PickPrintEnv(DirectRLEnv):
    """
    Isaac Lab environment for pick skill.
    Door is assumed already open.
    Object position is randomized on the build plate.
    """

    cfg: PickPrintTaskCfg

    def __init__(self, cfg: PickPrintTaskCfg, render_mode: str | None = None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)
        self._lift_threshold = 0.05  # 5cm above build plate = lifted

    def _setup_scene(self):
        self.robot = self.scene["robot"]
        self.print_object = self.scene["print_object"]
        self.ee = self.scene["ee_frame"]
        self.build_plate = self.scene["build_plate"]

    def _pre_physics_step(self, actions: torch.Tensor) -> None:
        # actions: [num_envs, 6] — 5 arm joints + 1 gripper
        joint_actions = actions[:, :5]
        gripper_action = actions[:, 5:6]

        current_pos = self.robot.data.joint_pos[:, :5]
        target_pos = current_pos + joint_actions * 0.05
        self.robot.set_joint_position_target(target_pos)

        # Gripper: binary (single joint in SO-100 URDF)
        gripper_pos = torch.where(
            gripper_action > 0,
            torch.tensor([0.5], device=self.device),   # closed
            torch.tensor([-0.5], device=self.device),  # open
        )
        self.robot.set_joint_position_target(gripper_pos, joint_ids=[5])

    def _get_observations(self) -> dict:
        joint_pos = self.robot.data.joint_pos[:, :5]   # 5 arm joints
        ee_pos = self.ee.data.target_pos_w[:, 0, :3]
        obj_pos = self.print_object.data.root_pos_w[:, :3]
        rel_pos = obj_pos - ee_pos
        gripper = self.robot.data.joint_pos[:, 5:6]    # gripper joint
        obs = torch.cat([joint_pos, ee_pos, obj_pos, rel_pos, gripper], dim=-1)
        return {"policy": obs}

    def _get_rewards(self) -> torch.Tensor:
        ee_pos = self.ee.data.target_pos_w[:, 0, :3]
        obj_pos = self.print_object.data.root_pos_w[:, :3]
        dist = torch.norm(obj_pos - ee_pos, dim=-1)
        reach_reward = torch.exp(-5.0 * dist)
        obj_height = obj_pos[:, 2] - self._build_plate_z()
        lift_reward = torch.clamp(obj_height / self._lift_threshold, 0.0, 1.0) * 3.0
        return reach_reward + lift_reward

    def _build_plate_z(self) -> float:
        """Z height of build plate surface (world frame)."""
        return self.build_plate.data.root_pos_w[0, 2].item() + 0.01

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        obj_pos = self.print_object.data.root_pos_w[:, :3]
        lifted = (obj_pos[:, 2] - self._build_plate_z()) > self._lift_threshold
        truncated = self.episode_length_buf >= self.max_episode_length
        out_of_bounds = (torch.abs(obj_pos[:, 0]) > 0.5) | (torch.abs(obj_pos[:, 1]) > 0.5)
        return lifted | out_of_bounds, truncated

    def _reset_idx(self, env_ids: torch.Tensor) -> None:
        if len(env_ids) == 0:
            return
        super()._reset_idx(env_ids)

        # Randomize object position on build plate (±5cm)
        base_pos = torch.tensor([0.35, 0.0, self._build_plate_z()], device=self.device)
        noise = torch.zeros(len(env_ids), 3, device=self.device)
        noise[:, :2] = sample_uniform(-0.05, 0.05, (len(env_ids), 2), device=self.device)
        obj_pos = base_pos.unsqueeze(0) + noise
        obj_quat = quat_from_euler_xyz(
            torch.zeros(len(env_ids), device=self.device),
            torch.zeros(len(env_ids), device=self.device),
            sample_uniform(-3.14, 3.14, (len(env_ids),), device=self.device),
        )
        self.print_object.write_root_pose_to_sim(
            torch.cat([obj_pos, obj_quat], dim=-1),
            env_ids=env_ids,
        )


# ─── Task Registration ───────────────────────────────────────────────────────

# These are registered with Isaac Lab's task registry in __init__.py
# gym.register(id="PrinterArm-OpenDoor-v0", entry_point=OpenDoorEnv, ...)
