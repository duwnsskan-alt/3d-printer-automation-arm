"""
sim/local/train_close_door.py — Local launcher for the CloseDoor task.

Usage:
    conda activate env_isaaclab
    python sim/local/train_close_door.py
    python sim/local/train_close_door.py --headless --num_envs 64
"""

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true", help="Run without GUI")
parser.add_argument("--num_envs", type=int, default=1, help="Number of parallel envs")
parser.add_argument("--max_iterations", type=int, default=5000, help="Training iterations")
args, unknown = parser.parse_known_args()

from sim_init import init_sim
app = init_sim(headless=args.headless)

from printer_arm_tasks.tasks.printer_arm_task import CloseDoorTaskCfg, CloseDoorEnv
from printer_arm_tasks.agents.rsl_rl_cfg import CloseDoorPPOCfg
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
from rsl_rl.runners import OnPolicyRunner

env_cfg = CloseDoorTaskCfg()
env_cfg.scene.num_envs = args.num_envs

agent_cfg = CloseDoorPPOCfg()
agent_cfg.max_iterations = args.max_iterations

env = CloseDoorEnv(cfg=env_cfg)
env = RslRlVecEnvWrapper(env)
runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir="output/close_door", device="cuda:0")
runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=True)

env.close()
app.close()
