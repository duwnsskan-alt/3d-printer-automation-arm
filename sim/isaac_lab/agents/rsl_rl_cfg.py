"""
sim/isaac_lab/agents/rsl_rl_cfg.py
------------------------------------
RSL-RL PPO agent configurations for printer arm tasks.

These are passed to the IsaacLab RSL-RL runner via:
  python -m isaaclab.app.run --task PrinterArm-OpenDoor-v0 \
    --agent sim.isaac_lab.agents.rsl_rl_cfg:OpenDoorPPOCfg

RSL-RL docs: https://github.com/leggedrobotics/rsl_rl
"""

from __future__ import annotations

from isaaclab.utils import configclass
from isaaclab_rl.rsl_rl import (
    RslRlOnPolicyRunnerCfg,
    RslRlPpoActorCriticCfg,
    RslRlPpoAlgorithmCfg,
)


# ─── Open Door ────────────────────────────────────────────────────────────────

@configclass
class OpenDoorPPOCfg(RslRlOnPolicyRunnerCfg):
    """PPO config for PrinterArm-OpenDoor-v0."""

    num_steps_per_env = 24          # Rollout horizon per env per update
    max_iterations = 5_000          # Total training iterations
    save_interval = 500             # Checkpoint every N iterations
    experiment_name = "open_door"
    empirical_normalization = False

    policy: RslRlPpoActorCriticCfg = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_hidden_dims=[256, 128, 64],
        critic_hidden_dims=[256, 128, 64],
        activation="elu",
    )

    algorithm: RslRlPpoAlgorithmCfg = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.005,
        num_learning_epochs=5,
        num_mini_batches=4,          # mini_batch_size = num_envs * num_steps / num_mini_batches
        learning_rate=1.0e-3,
        schedule="adaptive",         # lr annealing based on KL divergence
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


# ─── Pick Print ───────────────────────────────────────────────────────────────

@configclass
class PickPrintPPOCfg(RslRlOnPolicyRunnerCfg):
    """PPO config for PrinterArm-PickPrint-v0."""

    num_steps_per_env = 32          # Longer horizon — pick needs more context
    max_iterations = 8_000
    save_interval = 500
    experiment_name = "pick_print"
    empirical_normalization = False

    policy: RslRlPpoActorCriticCfg = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_hidden_dims=[512, 256, 128],
        critic_hidden_dims=[512, 256, 128],
        activation="elu",
    )

    algorithm: RslRlPpoAlgorithmCfg = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.008,          # Slightly higher — more exploration needed for grasp
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=3.0e-4,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )
