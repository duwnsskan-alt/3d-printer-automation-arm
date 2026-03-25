"""
sim/local/train_open_door.py
-----------------------------
Local launcher for the OpenDoor task.

Usage:
    conda activate env_isaaclab
    python sim/local/train_open_door.py                    # GUI, 1 env
    python sim/local/train_open_door.py --headless         # Headless training
    python sim/local/train_open_door.py --num_envs 64      # Multi-env training
"""

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true", help="Run without GUI")
parser.add_argument("--num_envs", type=int, default=1, help="Number of parallel envs")
parser.add_argument("--max_iterations", type=int, default=5000, help="Training iterations")
args, unknown = parser.parse_known_args()

# ── Launch Isaac Sim ────────────────────────────────────────────────────────
from sim_init import init_sim
app = init_sim(headless=args.headless)

# ── Isaac Lab imports (must come after SimulationApp) ───────────────────────
from printer_arm_tasks.tasks.printer_arm_task import OpenDoorTaskCfg, OpenDoorEnv
from printer_arm_tasks.agents.rsl_rl_cfg import OpenDoorPPOCfg
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
from rsl_rl.runners import OnPolicyRunner

# ── Configure ──────────────────────────────────────────────────────────────
env_cfg = OpenDoorTaskCfg()
env_cfg.scene.num_envs = args.num_envs

agent_cfg = OpenDoorPPOCfg()
agent_cfg.max_iterations = args.max_iterations

# ── Train ──────────────────────────────────────────────────────────────────
env = OpenDoorEnv(cfg=env_cfg)
env = RslRlVecEnvWrapper(env)
runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir="output/open_door", device="cuda:0")
runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=True)

env.close()
app.close()
