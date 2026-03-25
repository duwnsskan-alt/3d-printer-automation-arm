"""
printer_arm_task.py — Isaac Lab task environments for 3D printer automation.

Tasks:
  - OpenDoorEnv:   Open the P2S front door via handle
  - PickPrintEnv:  Pick a finished print from the build plate
  - PlacePrintEnv: Carry print to staging area and release
  - CloseDoorEnv:  Push the door closed

Joint index mapping (robot — SO-100 on linear rail):
  0: rail_slide  (prismatic, Y-axis)
  1: shoulder_pan
  2: shoulder_lift
  3: elbow_flex
  4: wrist_flex
  5: wrist_roll
  6: gripper

Joint index mapping (printer — P2S):
  0: Z_axis
  1: Y_axis
  2: X_axis
  3: door_hinge
"""

from __future__ import annotations

from dataclasses import MISSING

import torch

from isaaclab.envs import DirectRLEnv, DirectRLEnvCfg
from isaaclab.sim import SimulationCfg
import isaaclab.sim as sim_utils
from isaaclab.utils import configclass
from isaaclab.utils.math import quat_from_euler_xyz, sample_uniform

from .scene_cfg import P2SArmSceneCfg
from . import reward_terms as R
from . import termination_terms as T

# ─── Joint Index Constants ────────────────────────────────────────────────────

RAIL_IDX = 0
ARM_SLICE = slice(1, 6)       # indices 1..5 (5 arm joints)
GRIPPER_IDX = 6
DOOR_HINGE_IDX = 3            # within printer articulation


# ─── Task Configs ─────────────────────────────────────────────────────────────

@configclass
class OpenDoorTaskCfg(DirectRLEnvCfg):
    """Open the P2S front door. obs=13, act=7."""
    sim: SimulationCfg = SimulationCfg(dt=0.01, render_interval=2)
    scene: P2SArmSceneCfg = P2SArmSceneCfg(num_envs=MISSING, env_spacing=2.5)
    decimation = 2
    episode_length_s = 10.0
    observation_space = 13   # rail(1)+arm(5)+ee(3)+handle(3)+door_angle(1)
    action_space = 7         # rail(1)+arm(5)+gripper(1)
    state_space = 0


@configclass
class PickPrintTaskCfg(DirectRLEnvCfg):
    """Pick a print from the build plate (door pre-opened). obs=16, act=7."""
    sim: SimulationCfg = SimulationCfg(dt=0.01, render_interval=2)
    scene: P2SArmSceneCfg = P2SArmSceneCfg(num_envs=MISSING, env_spacing=2.5)
    decimation = 2
    episode_length_s = 15.0
    observation_space = 16   # rail(1)+arm(5)+ee(3)+obj(3)+rel(3)+gripper(1)
    action_space = 7
    state_space = 0


@configclass
class PlacePrintTaskCfg(DirectRLEnvCfg):
    """Place the held print on the staging area. obs=16, act=7."""
    sim: SimulationCfg = SimulationCfg(dt=0.01, render_interval=2)
    scene: P2SArmSceneCfg = P2SArmSceneCfg(num_envs=MISSING, env_spacing=2.5)
    decimation = 2
    episode_length_s = 15.0
    observation_space = 16   # rail(1)+arm(5)+ee(3)+obj(3)+staging(3)+gripper(1)
    action_space = 7
    state_space = 0


@configclass
class CloseDoorTaskCfg(DirectRLEnvCfg):
    """Push the open door closed. obs=13, act=6 (no gripper)."""
    sim: SimulationCfg = SimulationCfg(dt=0.01, render_interval=2)
    scene: P2SArmSceneCfg = P2SArmSceneCfg(num_envs=MISSING, env_spacing=2.5)
    decimation = 2
    episode_length_s = 10.0
    observation_space = 13   # rail(1)+arm(5)+ee(3)+handle(3)+door_angle(1)
    action_space = 6         # rail(1)+arm(5), no gripper
    state_space = 0


# ─── Base Mixin ───────────────────────────────────────────────────────────────

class _PrinterArmBase(DirectRLEnv):
    """Shared setup and helpers for all printer arm tasks."""

    def _setup_scene(self):
        self.robot = self.scene["robot"]
        self.printer = self.scene["printer"]
        self.ee = self.scene["ee_frame"]
        self.door_handle = self.scene["door_handle_frame"]
        self.print_object = self.scene["print_object"]
        self.build_plate = self.scene["build_plate"]
        self.staging_area = self.scene["staging_area"]
        light_cfg = sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 1.0))
        light_cfg.func("/World/Light", light_cfg)

    # ── Action helpers ────────────────────────────────────────────────────────

    def _process_actions(self, actions: torch.Tensor, include_gripper: bool = True):
        """Convert raw actions [rail(1)+arm(5)+gripper?(1)] to joint targets."""
        current_rail = self.robot.data.joint_pos[:, RAIL_IDX:RAIL_IDX + 1]
        current_arm = self.robot.data.joint_pos[:, ARM_SLICE]

        self._target_rail = current_rail + actions[:, 0:1] * 0.02
        self._target_arm = current_arm + actions[:, 1:6] * 0.05

        if include_gripper and actions.shape[-1] > 6:
            gripper_cmd = actions[:, 6:7]
            self._target_gripper = torch.where(
                gripper_cmd > 0,
                torch.full_like(gripper_cmd, 1.5),    # closed
                torch.full_like(gripper_cmd, -0.1),    # open
            )
        else:
            self._target_gripper = None

    def _apply_targets(self):
        """Write buffered targets to sim."""
        self.robot.set_joint_position_target(self._target_rail, joint_ids=[RAIL_IDX])
        self.robot.set_joint_position_target(self._target_arm, joint_ids=[1, 2, 3, 4, 5])
        if self._target_gripper is not None:
            self.robot.set_joint_position_target(self._target_gripper, joint_ids=[GRIPPER_IDX])

    # ── Reset helpers ─────────────────────────────────────────────────────────

    def _robot_home(self) -> torch.Tensor:
        """[rail, shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper]"""
        return torch.tensor([0.0, 0.0, 0.5, -1.0, 0.0, 0.5, 0.0], device=self.device)

    def _reset_robot(self, env_ids: torch.Tensor, noise_scale: float = 0.05,
                     home: torch.Tensor | None = None):
        n = len(env_ids)
        if home is None:
            home = self._robot_home()
        pos = home.unsqueeze(0).expand(n, -1).clone()
        noise = torch.randn(n, 7, device=self.device) * noise_scale
        noise[:, RAIL_IDX] *= 0.5
        noise[:, GRIPPER_IDX] = 0.0
        self.robot.write_joint_state_to_sim(
            pos + noise,
            torch.zeros(n, 7, device=self.device),
            env_ids=env_ids,
        )

    def _reset_printer(self, env_ids: torch.Tensor, door_angle: float = 0.0):
        n = len(env_ids)
        pos = torch.zeros(n, 4, device=self.device)
        pos[:, DOOR_HINGE_IDX] = door_angle
        self.printer.write_joint_state_to_sim(
            pos, torch.zeros_like(pos), env_ids=env_ids,
        )


# ─── OpenDoor ─────────────────────────────────────────────────────────────────

class OpenDoorEnv(_PrinterArmBase):
    """Train the arm to approach the door handle, grasp it, and pull the door open."""

    cfg: OpenDoorTaskCfg

    def __init__(self, cfg: OpenDoorTaskCfg, render_mode=None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)
        self._prev_actions = None

    def _pre_physics_step(self, actions: torch.Tensor):
        self._process_actions(actions, include_gripper=True)
        self._prev_actions = actions

    def _apply_action(self):
        self._apply_targets()

    def _get_observations(self) -> dict:
        obs = torch.cat([
            self.robot.data.joint_pos[:, RAIL_IDX:RAIL_IDX + 1],    # 1
            self.robot.data.joint_pos[:, ARM_SLICE],                 # 5
            self.ee.data.target_pos_w[:, 0, :3],                     # 3
            self.door_handle.data.target_pos_w[:, 0, :3],            # 3
            self.printer.data.joint_pos[:, DOOR_HINGE_IDX:DOOR_HINGE_IDX + 1],  # 1
        ], dim=-1)
        return {"policy": obs}

    def _get_rewards(self) -> torch.Tensor:
        return (
            R.approach_ee_handle(self) * 2.0
            + R.grasp_handle(self) * 5.0
            + R.open_door_angle(self) * 7.5
            + R.multi_stage_door_bonus(self) * 1.0
            + R.action_rate_l2(self) * 0.01
        )

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        return T.door_fully_open(self), T.time_out(self)

    def _reset_idx(self, env_ids: torch.Tensor):
        if len(env_ids) == 0:
            return
        super()._reset_idx(env_ids)
        self._reset_robot(env_ids)
        self._reset_printer(env_ids, door_angle=0.0)


# ─── PickPrint ────────────────────────────────────────────────────────────────

class PickPrintEnv(_PrinterArmBase):
    """Reach into the open printer, grasp the print object, and lift it."""

    cfg: PickPrintTaskCfg

    def __init__(self, cfg: PickPrintTaskCfg, render_mode=None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)
        self._prev_actions = None

    def _pre_physics_step(self, actions: torch.Tensor):
        self._process_actions(actions, include_gripper=True)
        self._prev_actions = actions

    def _apply_action(self):
        self._apply_targets()

    def _get_observations(self) -> dict:
        ee_pos = self.ee.data.target_pos_w[:, 0, :3]
        obj_pos = self.print_object.data.root_pos_w[:, :3]
        obs = torch.cat([
            self.robot.data.joint_pos[:, RAIL_IDX:RAIL_IDX + 1],    # 1
            self.robot.data.joint_pos[:, ARM_SLICE],                 # 5
            ee_pos,                                                  # 3
            obj_pos,                                                 # 3
            obj_pos - ee_pos,                                        # 3
            self.robot.data.joint_pos[:, GRIPPER_IDX:GRIPPER_IDX + 1],  # 1
        ], dim=-1)
        return {"policy": obs}

    def _get_rewards(self) -> torch.Tensor:
        return (
            R.reach_object(self) * 1.0
            + R.gripper_alignment(self) * 0.5
            + R.grasp_object(self) * 2.0
            + R.lift_object(self) * 5.0
            + R.object_held(self) * 1.0
            + R.action_rate_l2(self) * 0.01
        )

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        terminated = T.object_lifted(self) | T.object_dropped(self)
        return terminated, T.time_out(self)

    def _reset_idx(self, env_ids: torch.Tensor):
        if len(env_ids) == 0:
            return
        super()._reset_idx(env_ids)
        self._reset_robot(env_ids)
        self._reset_printer(env_ids, door_angle=1.57)
        self._randomize_object(env_ids)

    def _randomize_object(self, env_ids: torch.Tensor):
        n = len(env_ids)
        plate_z = self.build_plate.data.root_pos_w[0, 2].item() + 0.015
        base = torch.tensor([0.40, 0.0, plate_z], device=self.device)
        noise = torch.zeros(n, 3, device=self.device)
        noise[:, :2] = sample_uniform(-0.05, 0.05, (n, 2), device=self.device)
        pos = base.unsqueeze(0) + noise
        quat = quat_from_euler_xyz(
            torch.zeros(n, device=self.device),
            torch.zeros(n, device=self.device),
            sample_uniform(-3.14, 3.14, (n,), device=self.device),
        )
        self.print_object.write_root_pose_to_sim(
            torch.cat([pos, quat], dim=-1), env_ids=env_ids,
        )


# ─── PlacePrint ───────────────────────────────────────────────────────────────

class PlacePrintEnv(_PrinterArmBase):
    """Carry the grasped print to the staging area and release it."""

    cfg: PlacePrintTaskCfg

    def __init__(self, cfg: PlacePrintTaskCfg, render_mode=None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)
        self._prev_actions = None

    def _pre_physics_step(self, actions: torch.Tensor):
        self._process_actions(actions, include_gripper=True)
        self._prev_actions = actions

    def _apply_action(self):
        self._apply_targets()

    def _get_observations(self) -> dict:
        obs = torch.cat([
            self.robot.data.joint_pos[:, RAIL_IDX:RAIL_IDX + 1],    # 1
            self.robot.data.joint_pos[:, ARM_SLICE],                 # 5
            self.ee.data.target_pos_w[:, 0, :3],                     # 3
            self.print_object.data.root_pos_w[:, :3],                # 3
            self.staging_area.data.root_pos_w[:, :3],                # 3
            self.robot.data.joint_pos[:, GRIPPER_IDX:GRIPPER_IDX + 1],  # 1
        ], dim=-1)
        return {"policy": obs}

    def _get_rewards(self) -> torch.Tensor:
        return (
            R.approach_staging(self) * 2.0
            + R.place_height(self) * 3.0
            + R.release_at_target(self) * 5.0
            + R.object_held(self) * 1.0
            + R.action_rate_l2(self) * 0.01
        )

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        terminated = T.object_on_staging(self) | T.object_dropped(self)
        return terminated, T.time_out(self)

    def _reset_idx(self, env_ids: torch.Tensor):
        if len(env_ids) == 0:
            return
        super()._reset_idx(env_ids)

        # Start with arm in a "holding" pose, gripper closed
        hold_home = torch.tensor(
            [0.0, 0.0, 0.8, -0.5, -0.3, 0.5, 1.5],
            device=self.device,
        )
        self._reset_robot(env_ids, noise_scale=0.03, home=hold_home)
        self._reset_printer(env_ids, door_angle=1.57)

        # Place object near the approximate EE position for the holding pose
        n = len(env_ids)
        obj_pos = torch.tensor([0.10, -0.05, 0.15], device=self.device)
        obj_pos = obj_pos.unsqueeze(0).expand(n, -1).clone()
        noise = torch.zeros(n, 3, device=self.device)
        noise[:, :2] = sample_uniform(-0.02, 0.02, (n, 2), device=self.device)
        obj_pos = obj_pos + noise
        obj_quat = torch.tensor([1.0, 0.0, 0.0, 0.0], device=self.device)
        obj_quat = obj_quat.unsqueeze(0).expand(n, -1)
        self.print_object.write_root_pose_to_sim(
            torch.cat([obj_pos, obj_quat], dim=-1), env_ids=env_ids,
        )


# ─── CloseDoor ────────────────────────────────────────────────────────────────

class CloseDoorEnv(_PrinterArmBase):
    """Push the open printer door closed."""

    cfg: CloseDoorTaskCfg

    def __init__(self, cfg: CloseDoorTaskCfg, render_mode=None, **kwargs):
        super().__init__(cfg, render_mode, **kwargs)
        self._prev_actions = None

    def _pre_physics_step(self, actions: torch.Tensor):
        self._process_actions(actions, include_gripper=False)
        self._prev_actions = actions

    def _apply_action(self):
        self._apply_targets()

    def _get_observations(self) -> dict:
        obs = torch.cat([
            self.robot.data.joint_pos[:, RAIL_IDX:RAIL_IDX + 1],    # 1
            self.robot.data.joint_pos[:, ARM_SLICE],                 # 5
            self.ee.data.target_pos_w[:, 0, :3],                     # 3
            self.door_handle.data.target_pos_w[:, 0, :3],            # 3
            self.printer.data.joint_pos[:, DOOR_HINGE_IDX:DOOR_HINGE_IDX + 1],  # 1
        ], dim=-1)
        return {"policy": obs}

    def _get_rewards(self) -> torch.Tensor:
        return (
            R.approach_door(self) * 2.0
            + R.close_door_angle(self) * 5.0
            + R.door_closed_bonus(self) * 10.0
            + R.action_rate_l2(self) * 0.01
        )

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        return T.door_closed(self), T.time_out(self)

    def _reset_idx(self, env_ids: torch.Tensor):
        if len(env_ids) == 0:
            return
        super()._reset_idx(env_ids)
        self._reset_robot(env_ids)
        # Door starts open at random angle 1.0~2.0 rad
        n = len(env_ids)
        angles = sample_uniform(1.0, 2.0, (n,), device=self.device)
        pos = torch.zeros(n, 4, device=self.device)
        pos[:, DOOR_HINGE_IDX] = angles
        self.printer.write_joint_state_to_sim(
            pos, torch.zeros_like(pos), env_ids=env_ids,
        )
