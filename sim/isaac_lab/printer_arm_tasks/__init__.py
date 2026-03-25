"""
Printer Arm Tasks — Isaac Lab environments for 3D printer automation.

Tasks:
  - PrinterArm-OpenDoor-v0:   Open the P2S front door
  - PrinterArm-PickPrint-v0:  Pick a finished print from the build plate
  - PrinterArm-PlacePrint-v0: Place the print on the staging area
  - PrinterArm-CloseDoor-v0:  Push the door closed
"""

__version__ = "0.2.0"

import gymnasium as gym

gym.register(
    id="PrinterArm-OpenDoor-v0",
    entry_point="printer_arm_tasks.tasks.printer_arm_task:OpenDoorEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "printer_arm_tasks.tasks.printer_arm_task:OpenDoorTaskCfg",
        "rsl_rl_cfg_entry_point": "printer_arm_tasks.agents.rsl_rl_cfg:OpenDoorPPOCfg",
    },
)

gym.register(
    id="PrinterArm-PickPrint-v0",
    entry_point="printer_arm_tasks.tasks.printer_arm_task:PickPrintEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "printer_arm_tasks.tasks.printer_arm_task:PickPrintTaskCfg",
        "rsl_rl_cfg_entry_point": "printer_arm_tasks.agents.rsl_rl_cfg:PickPrintPPOCfg",
    },
)

gym.register(
    id="PrinterArm-PlacePrint-v0",
    entry_point="printer_arm_tasks.tasks.printer_arm_task:PlacePrintEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "printer_arm_tasks.tasks.printer_arm_task:PlacePrintTaskCfg",
        "rsl_rl_cfg_entry_point": "printer_arm_tasks.agents.rsl_rl_cfg:PlacePrintPPOCfg",
    },
)

gym.register(
    id="PrinterArm-CloseDoor-v0",
    entry_point="printer_arm_tasks.tasks.printer_arm_task:CloseDoorEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "printer_arm_tasks.tasks.printer_arm_task:CloseDoorTaskCfg",
        "rsl_rl_cfg_entry_point": "printer_arm_tasks.agents.rsl_rl_cfg:CloseDoorPPOCfg",
    },
)
