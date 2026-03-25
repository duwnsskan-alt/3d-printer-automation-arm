"""
rsl_rl_cfg.py — RSL-RL PPO agent configurations for all printer arm tasks.

Each task has its own PPO config tuned for its observation/action space
and expected training horizon. RTX 2070 8GB target: num_envs=64.
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
    """PPO config for PrinterArm-OpenDoor-v0. obs=13, act=7."""

    num_steps_per_env = 24
    max_iterations = 5_000
    save_interval = 500
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
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


# ─── Pick Print ──────────────────────────────────────────────────────────────

@configclass
class PickPrintPPOCfg(RslRlOnPolicyRunnerCfg):
    """PPO config for PrinterArm-PickPrint-v0. obs=16, act=7."""

    num_steps_per_env = 32
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
        entropy_coef=0.008,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=3.0e-4,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


# ─── Place Print ─────────────────────────────────────────────────────────────

@configclass
class PlacePrintPPOCfg(RslRlOnPolicyRunnerCfg):
    """PPO config for PrinterArm-PlacePrint-v0. obs=16, act=7."""

    num_steps_per_env = 32
    max_iterations = 8_000
    save_interval = 500
    experiment_name = "place_print"
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
        entropy_coef=0.008,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=3.0e-4,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


# ─── Close Door ──────────────────────────────────────────────────────────────

@configclass
class CloseDoorPPOCfg(RslRlOnPolicyRunnerCfg):
    """PPO config for PrinterArm-CloseDoor-v0. obs=13, act=6."""

    num_steps_per_env = 24
    max_iterations = 5_000
    save_interval = 500
    experiment_name = "close_door"
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
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


# ─── Full Cycle ──────────────────────────────────────────────────────────────

@configclass
class FullCyclePPOCfg(RslRlOnPolicyRunnerCfg):
    """PPO config for PrinterArm-FullCycle-v0 (future use)."""

    num_steps_per_env = 48
    max_iterations = 20_000
    save_interval = 1000
    experiment_name = "full_cycle"
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
        entropy_coef=0.01,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-4,
        schedule="adaptive",
        gamma=0.995,
        lam=0.95,
        desired_kl=0.008,
        max_grad_norm=1.0,
    )
