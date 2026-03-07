"""
Isaac Lab task registration for the printer arm tasks.
"""

import gymnasium as gym

from .printer_arm_task import OpenDoorEnv, PickPrintEnv, OpenDoorTaskCfg, PickPrintTaskCfg

gym.register(
    id="PrinterArm-OpenDoor-v0",
    entry_point="sim.isaac_lab.tasks.printer_arm_task:OpenDoorEnv",
    disable_env_checker=True,
    kwargs={"cfg": OpenDoorTaskCfg(num_envs=1)},
)

gym.register(
    id="PrinterArm-PickPrint-v0",
    entry_point="sim.isaac_lab.tasks.printer_arm_task:PickPrintEnv",
    disable_env_checker=True,
    kwargs={"cfg": PickPrintTaskCfg(num_envs=1)},
)
