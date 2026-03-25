"""
event_terms.py — Domain randomization for printer arm tasks.

These functions are called during environment reset to randomize
physical properties and initial conditions, improving sim-to-real transfer.

Usage in task envs:
    from . import event_terms as E
    E.randomize_door_stiffness(self, env_ids)
"""

from __future__ import annotations

import torch
from isaaclab.envs import DirectRLEnv
from isaaclab.utils.math import sample_uniform

DOOR_HINGE_IDX = 3


def randomize_door_stiffness(env: DirectRLEnv, env_ids: torch.Tensor):
    """Randomize door hinge stiffness between 40-60 Nm (nominal 50)."""
    n = len(env_ids)
    stiffness = sample_uniform(40.0, 60.0, (n, 1), device=env.device)
    damping = sample_uniform(8.0, 12.0, (n, 1), device=env.device)
    env.printer.write_joint_stiffness_to_sim(stiffness, joint_ids=[DOOR_HINGE_IDX], env_ids=env_ids)
    env.printer.write_joint_damping_to_sim(damping, joint_ids=[DOOR_HINGE_IDX], env_ids=env_ids)


def randomize_object_mass(env: DirectRLEnv, env_ids: torch.Tensor):
    """Randomize print object mass between 30-100g."""
    n = len(env_ids)
    masses = sample_uniform(0.03, 0.10, (n, 1), device=env.device)
    env.print_object.write_mass_to_sim(masses, env_ids=env_ids)


def randomize_robot_friction(env: DirectRLEnv, env_ids: torch.Tensor):
    """Randomize joint friction scaling (0.8x-1.25x) by adjusting damping."""
    n = len(env_ids)
    scale = sample_uniform(0.8, 1.25, (n, 7), device=env.device)
    base_damping = torch.tensor(
        [10000.0, 40.0, 40.0, 40.0, 40.0, 40.0, 20.0],
        device=env.device,
    ).unsqueeze(0)
    damping = base_damping * scale
    env.robot.write_joint_damping_to_sim(damping, env_ids=env_ids)


def randomize_lighting(env: DirectRLEnv, env_ids: torch.Tensor):
    """Randomize dome light intensity (1500-4000 lux).

    Note: Per-env light randomization is limited in Isaac Lab.
    This randomizes globally on each reset call.
    """
    import isaaclab.sim as sim_utils
    intensity = sample_uniform(1500.0, 4000.0, (1,), device=env.device).item()
    r = sample_uniform(0.85, 1.0, (1,), device=env.device).item()
    g = sample_uniform(0.85, 1.0, (1,), device=env.device).item()
    b = sample_uniform(0.90, 1.0, (1,), device=env.device).item()
    light_cfg = sim_utils.DomeLightCfg(intensity=intensity, color=(r, g, b))
    light_cfg.func("/World/Light", light_cfg)
