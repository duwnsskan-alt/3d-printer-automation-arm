"""
sim/local/run_full_cycle.py — Full-cycle evaluation: chain 4 trained sub-policies.

Runs a state machine:  OPEN_DOOR -> PICK_PRINT -> PLACE_PRINT -> CLOSE_DOOR -> DONE

Each stage loads a pre-trained checkpoint and runs until the stage's termination
condition is met or a max-step limit is reached. If a stage fails, it retries
up to 2 times before aborting.

Usage:
    conda activate env_isaaclab
    python sim/local/run_full_cycle.py --checkpoint_dir output/
    python sim/local/run_full_cycle.py --checkpoint_dir output/ --headless
"""

import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true")
parser.add_argument("--checkpoint_dir", type=str, default="output",
                    help="Root dir containing open_door/, pick_print/, etc. subdirs")
parser.add_argument("--max_steps_per_stage", type=int, default=500)
parser.add_argument("--max_retries", type=int, default=2)
args = parser.parse_args()

from sim_init import init_sim
app = init_sim(headless=args.headless)

import torch
from printer_arm_tasks.tasks.printer_arm_task import (
    OpenDoorTaskCfg, OpenDoorEnv,
    PickPrintTaskCfg, PickPrintEnv,
    PlacePrintTaskCfg, PlacePrintEnv,
    CloseDoorTaskCfg, CloseDoorEnv,
)
from printer_arm_tasks.agents.rsl_rl_cfg import (
    OpenDoorPPOCfg, PickPrintPPOCfg, PlacePrintPPOCfg, CloseDoorPPOCfg,
)
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
from rsl_rl.runners import OnPolicyRunner


# ── Stage definitions ─────────────────────────────────────────────────────────

STAGES = [
    {
        "name": "OPEN_DOOR",
        "env_cls": OpenDoorEnv,
        "cfg_cls": OpenDoorTaskCfg,
        "agent_cls": OpenDoorPPOCfg,
        "checkpoint_subdir": "open_door",
    },
    {
        "name": "PICK_PRINT",
        "env_cls": PickPrintEnv,
        "cfg_cls": PickPrintTaskCfg,
        "agent_cls": PickPrintPPOCfg,
        "checkpoint_subdir": "pick_print",
    },
    {
        "name": "PLACE_PRINT",
        "env_cls": PlacePrintEnv,
        "cfg_cls": PlacePrintTaskCfg,
        "agent_cls": PlacePrintPPOCfg,
        "checkpoint_subdir": "place_print",
    },
    {
        "name": "CLOSE_DOOR",
        "env_cls": CloseDoorEnv,
        "cfg_cls": CloseDoorTaskCfg,
        "agent_cls": CloseDoorPPOCfg,
        "checkpoint_subdir": "close_door",
    },
]


def find_latest_checkpoint(checkpoint_dir: str, subdir: str) -> str | None:
    """Find the latest model_*.pt checkpoint in a subdirectory."""
    path = os.path.join(checkpoint_dir, subdir)
    if not os.path.isdir(path):
        return None
    ckpts = sorted(
        [f for f in os.listdir(path) if f.startswith("model_") and f.endswith(".pt")],
        key=lambda f: int(f.replace("model_", "").replace(".pt", "")),
    )
    if not ckpts:
        return None
    return os.path.join(path, ckpts[-1])


def run_stage(stage: dict, device: str = "cuda:0") -> bool:
    """Run a single stage. Returns True if the stage's termination condition was met."""
    ckpt = find_latest_checkpoint(args.checkpoint_dir, stage["checkpoint_subdir"])
    if ckpt is None:
        print(f"  [SKIP] No checkpoint found for {stage['name']}")
        return False

    print(f"  Loading checkpoint: {ckpt}")

    env_cfg = stage["cfg_cls"]()
    env_cfg.scene.num_envs = 1

    agent_cfg = stage["agent_cls"]()

    env = stage["env_cls"](cfg=env_cfg)
    wrapped = RslRlVecEnvWrapper(env)

    runner = OnPolicyRunner(wrapped, agent_cfg.to_dict(), log_dir=None, device=device)
    runner.load(ckpt)
    policy = runner.get_inference_policy(device=device)

    obs, _ = wrapped.get_observations()
    success = False

    for step in range(args.max_steps_per_stage):
        actions = policy(obs)
        obs, _, dones, infos = wrapped.step(actions)

        if dones.any():
            # Check if it was a success termination (not timeout)
            terminated = infos.get("terminated", dones)
            if terminated.any():
                success = True
            break

    env.close()
    return success


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Full Cycle Evaluation")
    print("=" * 60)

    for stage in STAGES:
        print(f"\n>> Stage: {stage['name']}")

        success = False
        for attempt in range(1, args.max_retries + 1):
            print(f"  Attempt {attempt}/{args.max_retries}")
            success = run_stage(stage)
            if success:
                print(f"  [OK] {stage['name']} completed successfully")
                break
            else:
                print(f"  [FAIL] {stage['name']} did not reach termination")

        if not success:
            print(f"\n[ABORT] {stage['name']} failed after {args.max_retries} retries.")
            print("Full cycle incomplete.")
            break
    else:
        print("\n" + "=" * 60)
        print("  FULL CYCLE COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
    app.close()
