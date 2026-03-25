"""
sim/local/train_place_print.py — Local launcher for the PlacePrint task.

Usage:
    conda activate env_isaaclab
    python sim/local/train_place_print.py
    python sim/local/train_place_print.py --headless --num_envs 64
"""

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true", help="Run without GUI")
parser.add_argument("--num_envs", type=int, default=1, help="Number of parallel envs")
parser.add_argument("--max_iterations", type=int, default=8000, help="Training iterations")
args, unknown = parser.parse_known_args()

from sim_init import init_sim
app = init_sim(headless=args.headless)

from printer_arm_tasks.tasks.printer_arm_task import PlacePrintTaskCfg, PlacePrintEnv
from printer_arm_tasks.agents.rsl_rl_cfg import PlacePrintPPOCfg
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
from rsl_rl.runners import OnPolicyRunner

env_cfg = PlacePrintTaskCfg()
env_cfg.scene.num_envs = args.num_envs

agent_cfg = PlacePrintPPOCfg()
agent_cfg.max_iterations = args.max_iterations

env = PlacePrintEnv(cfg=env_cfg)
env = RslRlVecEnvWrapper(env)
runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir="output/place_print", device="cuda:0")
runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=True)

env.close()
app.close()
