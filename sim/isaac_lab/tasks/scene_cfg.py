"""
sim/isaac_lab/tasks/scene_cfg.py
---------------------------------
Isaac Lab scene configuration for P2S + SO-100 simulation.

Defines all rigid bodies, articulations, sensors, and their initial
poses. The SO-100 arm is modelled from its official URDF (TheRobotStudio/SO-ARM100);
the P2S printer body and door are custom rigid body assets.

SO-100 joint names (from URDF):
  shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper
Links: base → shoulder → upper_arm → lower_arm → wrist → gripper → jaw
"""

from __future__ import annotations

from isaaclab.scene import InteractiveSceneCfg
from isaaclab.assets import ArticulationCfg, RigidObjectCfg
from isaaclab.sensors import CameraCfg, FrameTransformerCfg
from isaaclab.sensors.frame_transformer.frame_transformer_cfg import OffsetCfg
from isaaclab.sim.spawners.from_files import UsdFileCfg, UrdfFileCfg
from isaaclab.sim.schemas.schemas_cfg import RigidBodyPropertiesCfg, CollisionPropertiesCfg
from isaaclab.utils import configclass
from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR

import isaaclab.sim as sim_utils


# ─── Asset Paths ──────────────────────────────────────────────────────────────
# These USD/URDF files need to be generated or obtained separately.
# Refer to docs/assets.md for instructions on generating the P2S URDF.

SO100_URDF_PATH = "sim/isaac_lab/assets/so100/so100.urdf"
P2S_USD_PATH = "sim/isaac_lab/assets/p2s/p2s_body.usd"
P2S_DOOR_USD_PATH = "sim/isaac_lab/assets/p2s/p2s_door.usd"
BUILD_PLATE_USD_PATH = "sim/isaac_lab/assets/p2s/build_plate.usd"
PRINT_OBJECT_USD_PATH = "sim/isaac_lab/assets/objects/generic_print.usd"


@configclass
class P2SArmSceneCfg(InteractiveSceneCfg):
    """
    Full scene for P2S + SO-100 arm.

    World frame origin is at the SO-100 arm base.
    The P2S is placed 0.4m in front of the arm base.
    """

    # ── Ground Plane ──────────────────────────────────────────────────────────
    ground = sim_utils.GroundPlaneCfg()

    # ── Lighting ──────────────────────────────────────────────────────────────
    dome_light = sim_utils.DomeLightCfg(
        intensity=2000.0,
        color=(0.9, 0.9, 1.0),
    )
    key_light = sim_utils.SphereLightCfg(
        intensity=3000.0,
        radius=0.1,
        prim_path="/World/envs/env_.*/KeyLight",
    )

    # ── SO-100 Robot Arm ──────────────────────────────────────────────────────
    robot: ArticulationCfg = ArticulationCfg(
        prim_path="/World/envs/env_.*/Robot",
        spawn=UrdfFileCfg(
            asset_path=SO100_URDF_PATH,
            activate_contact_sensors=True,
            rigid_props=RigidBodyPropertiesCfg(
                rigid_body_enabled=True,
                max_linear_velocity=10.0,
                max_angular_velocity=50.0,
                max_depenetration_velocity=1.0,
                disable_gravity=False,
            ),
            collision_props=CollisionPropertiesCfg(
                contact_offset=0.005,
                rest_offset=0.0,
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.0),
            joint_pos={
                "shoulder_pan":  0.0,
                "shoulder_lift": -0.5,
                "elbow_flex":    1.0,
                "wrist_flex":    0.0,
                "wrist_roll":    0.5,
                "gripper":       0.0,
            },
        ),
        actuators={
            "arm_joints": sim_utils.ImplicitActuatorCfg(
                joint_names_expr=["shoulder_pan", "shoulder_lift", "elbow_flex",
                                  "wrist_flex", "wrist_roll"],
                velocity_limit=3.14,  # rad/s
                effort_limit=10.0,    # Nm
                stiffness=400.0,
                damping=40.0,
            ),
            "gripper": sim_utils.ImplicitActuatorCfg(
                joint_names_expr=["gripper"],
                velocity_limit=0.5,
                effort_limit=5.0,
                stiffness=200.0,
                damping=20.0,
            ),
        },
    )

    # ── P2S Printer Body (static) ─────────────────────────────────────────────
    printer_body: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/PrinterBody",
        spawn=UsdFileCfg(
            usd_path=P2S_USD_PATH,
            rigid_props=RigidBodyPropertiesCfg(
                kinematic_enabled=True,  # Static — not simulated dynamically
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.0),  # 40cm in front of arm base
        ),
    )

    # ── P2S Door (articulated hinge) ──────────────────────────────────────────
    printer_door: ArticulationCfg = ArticulationCfg(
        prim_path="/World/envs/env_.*/PrinterDoor",
        spawn=UsdFileCfg(
            usd_path=P2S_DOOR_USD_PATH,
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.0),
            joint_pos={"door_hinge": 0.0},  # Closed
        ),
        actuators={
            "door_hinge": sim_utils.ImplicitActuatorCfg(
                joint_names_expr=["door_hinge"],
                stiffness=50.0,
                damping=10.0,
                effort_limit=20.0,
            ),
        },
    )

    # ── Build Plate ───────────────────────────────────────────────────────────
    build_plate: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/BuildPlate",
        spawn=UsdFileCfg(
            usd_path=BUILD_PLATE_USD_PATH,
            rigid_props=RigidBodyPropertiesCfg(kinematic_enabled=True),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.18),  # 18cm above ground (inside printer)
        ),
    )

    # ── Print Object ──────────────────────────────────────────────────────────
    print_object: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/PrintObject",
        spawn=UsdFileCfg(
            usd_path=PRINT_OBJECT_USD_PATH,
            mass_props=sim_utils.MassPropertiesCfg(mass=0.05),  # 50g
            collision_props=CollisionPropertiesCfg(
                contact_offset=0.001,
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.19),  # On build plate
        ),
    )

    # ── End-Effector Frame Sensor ─────────────────────────────────────────────
    ee_frame: FrameTransformerCfg = FrameTransformerCfg(
        prim_path="/World/envs/env_.*/Robot/gripper",
        debug_vis=False,
        target_frames=[
            FrameTransformerCfg.FrameCfg(
                prim_path="/World/envs/env_.*/Robot/gripper",
                name="end_effector",
                offset=OffsetCfg(pos=(0.0, 0.0, 0.10)),  # 10cm from flange
            ),
        ],
    )

    # ── Cameras ───────────────────────────────────────────────────────────────
    front_camera: CameraCfg = CameraCfg(
        prim_path="/World/envs/env_.*/FrontCamera",
        update_period=0.033,  # 30 fps
        height=480,
        width=640,
        data_types=["rgb", "depth"],
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=24.0,
            focus_distance=0.4,
            horizontal_aperture=20.955,
        ),
        offset=CameraCfg.OffsetCfg(
            pos=(0.0, -0.5, 0.4),
            rot=(0.707, 0.0, 0.0, 0.707),  # Looking at printer
            convention="world",
        ),
    )

    wrist_camera: CameraCfg = CameraCfg(
        prim_path="/World/envs/env_.*/Robot/wrist/WristCamera",
        update_period=0.02,  # 50 fps
        height=480,
        width=640,
        data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=8.0,
            focus_distance=0.15,
            horizontal_aperture=20.955,
        ),
    )
