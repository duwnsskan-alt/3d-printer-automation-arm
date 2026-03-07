"""
sim/isaac_lab/export_dataset.py
---------------------------------
Run a trained Isaac Lab policy and collect rollout data.
Exports each episode as an .npz file compatible with DatasetPipeline.

Usage:
  python sim/isaac_lab/export_dataset.py \
    --task PrinterArm-OpenDoor-v0 \
    --checkpoint sim/checkpoints/open_door_latest.pt \
    --num_episodes 500 \
    --output_dir data/sim_episodes/open_door
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import torch

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def collect_episode(env, policy, task_str: str) -> dict | None:
    """
    Run one episode and collect observations, actions, and images.

    Returns:
        Dict with keys: joint_positions, actions, timestamps, front_images,
        wrist_images, task, success
    """
    obs, _ = env.reset()
    done = False

    joint_positions = []
    actions_list = []
    timestamps = []
    front_images = []
    wrist_images = []

    t = 0
    dt = env.cfg.sim.dt * env.cfg.decimation

    while not done:
        with torch.no_grad():
            action = policy(obs)

        joint_positions.append(obs["policy"][:, :6].cpu().numpy()[0])
        actions_list.append(action.cpu().numpy()[0])
        timestamps.append(t * dt)

        # Collect camera images if available
        if hasattr(env, "front_camera") and env.front_camera.data.output.get("rgb") is not None:
            img = env.front_camera.data.output["rgb"][0].cpu().numpy()  # [H, W, 4] RGBA
            front_images.append(img[:, :, :3])  # Drop alpha
        if hasattr(env, "wrist_camera") and env.wrist_camera.data.output.get("rgb") is not None:
            img = env.wrist_camera.data.output["rgb"][0].cpu().numpy()
            wrist_images.append(img[:, :, :3])

        obs, reward, terminated, truncated, info = env.step(action)
        done = (terminated | truncated).any().item()
        t += 1

        if t > 500:  # Safety cap
            break

    success = terminated.any().item() if hasattr(terminated, "any") else bool(terminated)

    return {
        "joint_positions": np.array(joint_positions, dtype=np.float32),
        "actions": np.array(actions_list, dtype=np.float32),
        "timestamps": np.array(timestamps, dtype=np.float64),
        "front_images": np.array(front_images, dtype=np.uint8) if front_images else np.empty((0,)),
        "wrist_images": np.array(wrist_images, dtype=np.uint8) if wrist_images else np.empty((0,)),
        "task": task_str,
        "success": success,
    }


def main():
    parser = argparse.ArgumentParser(description="Export Isaac Lab rollouts as npz episodes")
    parser.add_argument("--task", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--num_episodes", type=int, default=500)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Import Isaac Lab app (must be done before other imports)
    from isaaclab.app import AppLauncher
    launcher = AppLauncher(headless=True)
    simulation_app = launcher.app

    import gymnasium as gym
    import sim.isaac_lab.tasks  # noqa: F401 — registers tasks

    env = gym.make(args.task, num_envs=1, render_mode=None)

    # Load trained policy checkpoint
    # (format depends on RL framework — here assume RSL-RL ActorCriticModel)
    checkpoint = torch.load(args.checkpoint, map_location=args.device)
    # Extract just the actor
    policy = checkpoint.get("actor", checkpoint)
    policy.eval()
    policy.to(args.device)

    task_str_map = {
        "PrinterArm-OpenDoor-v0": "open printer door",
        "PrinterArm-PickPrint-v0": "pick printed object from build plate",
    }
    task_str = task_str_map.get(args.task, args.task)

    collected = 0
    success_count = 0
    episode_idx = 0

    while collected < args.num_episodes:
        ep_data = collect_episode(env, policy, task_str)
        if ep_data is None:
            continue

        if ep_data["success"]:
            success_count += 1

        out_path = output_dir / f"episode_{episode_idx:06d}.npz"
        np.savez_compressed(out_path, **ep_data)
        collected += 1
        episode_idx += 1

        if collected % 50 == 0:
            log.info(
                "Collected %d/%d episodes (success rate: %.1f%%)",
                collected, args.num_episodes,
                100 * success_count / collected,
            )

    env.close()
    simulation_app.close()
    log.info(
        "Done! %d episodes saved to %s (success: %.1f%%)",
        collected, output_dir,
        100 * success_count / max(collected, 1),
    )


if __name__ == "__main__":
    main()
