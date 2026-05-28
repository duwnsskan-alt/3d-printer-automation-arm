"""Spawn the RL scene (same scene_cfg.py, materials, lights, robot at home pose)
without running PPO. Steps the sim with zero actions so the user can navigate
in Isaac Sim GUI and tweak prims interactively.

Usage (inside docker, what run_sim.sh --inspect wires up):
  python inspect_rl_env.py --task PrinterArm-OpenDoor-v0 --num_envs 1 --enable_cameras
"""

import argparse
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, default="PrinterArm-OpenDoor-v0")
parser.add_argument("--num_envs", type=int, default=1)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = False
args.enable_cameras = True

print(f"[inspect] DISPLAY={os.environ.get('DISPLAY')!r} headless={args.headless} "
      f"enable_cameras={args.enable_cameras}")

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app
print("[inspect] SimulationApp launched, GUI should be visible now.")


# --- Imports after AppLauncher ----------------------------------------------
import torch
import gymnasium as gym

from isaaclab_tasks.utils.parse_cfg import parse_env_cfg

import isaaclab_tasks  # noqa: F401  registers built-in tasks
import sim.isaac_lab.printer_arm_tasks  # noqa: F401  registers our PrinterArm-* tasks


def main():
    env_cfg = parse_env_cfg(args.task, num_envs=args.num_envs)
    env = gym.make(args.task, cfg=env_cfg, render_mode="rgb_array")
    print(f"[inspect] env created: {args.task}, num_envs={args.num_envs}")
    print(f"[inspect] obs_space={env.observation_space.shape}, "
          f"act_space={env.action_space.shape}")
    env.reset()

    # Zero-action loop. Render every step so the GUI viewport stays live.
    action_dim = env.action_space.shape[-1]
    zero = torch.zeros((args.num_envs, action_dim),
                       device=env.unwrapped.device)
    step = 0
    while simulation_app.is_running():
        env.step(zero)
        step += 1
        # Periodic reset so any user-driven articulation drift snaps back —
        # comment this out if you want totally free manual manipulation.
        if step % 500 == 0:
            env.reset()

    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
