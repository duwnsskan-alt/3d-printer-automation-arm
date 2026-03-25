"""
sim/local/view_scene.py
------------------------
Launch the scene in GUI mode for visual inspection.
No training — loads the scene and steps with zero actions.

Usage:
    conda activate env_isaaclab
    python sim/local/view_scene.py                     # OpenDoor scene
    python sim/local/view_scene.py --task pick_print   # PickPrint scene
"""

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, default="open_door", choices=["open_door", "pick_print"])
args, unknown = parser.parse_known_args()

# ── Launch Isaac Sim with GUI ──────────────────────────────────────────────
from sim_init import init_sim
app = init_sim(headless=False)

# ── Isaac Lab imports ──────────────────────────────────────────────────────
import torch
from printer_arm_tasks.tasks.printer_arm_task import (
    OpenDoorTaskCfg, OpenDoorEnv,
    PickPrintTaskCfg, PickPrintEnv,
)

# ── Select task ────────────────────────────────────────────────────────────
if args.task == "open_door":
    cfg = OpenDoorTaskCfg()
    cfg.scene.num_envs = 1
    env = OpenDoorEnv(cfg=cfg)
else:
    cfg = PickPrintTaskCfg()
    cfg.scene.num_envs = 1
    env = PickPrintEnv(cfg=cfg)

print(f"\n{'='*50}")
print(f"  Scene loaded: {args.task}")
print(f"  Use mouse to orbit camera")
print(f"  Close window or Ctrl+C to exit")
print(f"{'='*50}\n")

# ── Step loop (zero actions) ───────────────────────────────────────────────
action_dim = cfg.action_space if isinstance(cfg.action_space, int) else cfg.action_space.shape[0]
zero_action = torch.zeros(1, action_dim, device=env.device)

try:
    while app.is_running():
        env.step(zero_action)
except KeyboardInterrupt:
    pass

env.close()
app.close()
