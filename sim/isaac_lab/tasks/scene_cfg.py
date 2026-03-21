"""
sim/isaac_lab/tasks/scene_cfg.py
---------------------------------
Isaac Lab scene configuration for P2S + SO-100 simulation.

Defines all rigid bodies, articulations, sensors, and their initial
poses. The SO-100 arm is modelled from its official URDF (TheRobotStudio/SO-ARM100);
the P2S printer is loaded from a pre-processed URDF (inlined from xacro).

Build plate and print object use Isaac Lab primitive spawners (CuboidCfg,
CylinderCfg) instead of external USD files — no asset generation step needed.

SO-100 joint names (from URDF):
  shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper
Links: base -> shoulder -> upper_arm -> lower_arm -> wrist -> gripper -> jaw
"""

from __future__ import annotations

import os

from isaaclab.scene import InteractiveSceneCfg
from isaaclab.assets import ArticulationCfg, RigidObjectCfg
from isaaclab.sensors import CameraCfg, FrameTransformerCfg
from isaaclab.sensors.frame_transformer.frame_transformer_cfg import OffsetCfg
from isaaclab.sim.spawners.from_files import UrdfFileCfg
from isaaclab.sim.spawners.shapes import CuboidCfg, CylinderCfg
from isaaclab.sim.schemas.schemas_cfg import (
    RigidBodyPropertiesCfg,
    CollisionPropertiesCfg,
    MassPropertiesCfg,
)
from isaaclab.utils import configclass

import isaaclab.sim as sim_utils


# ─── Asset Paths ──────────────────────────────────────────────────────────────
# Resolve paths relative to the project root (mounted at /workspace/project in container).
# At runtime, PROJECT_ROOT env var is set by run_sim.sh / launch_sim.sh.

_PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "/workspace/project")

SO100_URDF_PATH = os.path.join(_PROJECT_ROOT, "sim/isaac_lab/assets/so100/so100.urdf")
P2S_URDF_PATH = os.path.join(
    _PROJECT_ROOT, "sim/isaac_lab/assets/p2s/urdf/p2s_printer.urdf"
)


@configclass
class P2SArmSceneCfg(InteractiveSceneCfg):
    """
    Full scene for P2S + SO-100 arm.

    World frame origin is at the SO-100 arm base.
    The P2S is placed 0.4m in front of the arm base.

    Asset strategy:
      - SO-100: URDF with STL meshes (sim/isaac_lab/assets/so100/)
      - P2S printer: Pre-processed URDF with STL meshes (sim/isaac_lab/assets/p2s/)
        The full printer URDF is loaded as an articulation so Isaac Lab can
        actuate the door_hinge joint directly.
      - Build plate: Isaac Lab CuboidCfg primitive (no USD needed)
      - Print object: Isaac Lab CylinderCfg primitive (no USD needed)
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

    # ── P2S Printer (full articulation from URDF) ────────────────────────────
    # The P2S URDF includes all links (body, Z-bed, Y-axis, X-axis nozzle,
    # Door) and joints. We load it as an articulation so the door_hinge joint
    # is directly controllable for the OpenDoor task.
    # The gantry joints (Z-axis, Y-axis, X-axis) are present but locked at
    # home position via high stiffness — the robot does not interact with them.
    printer: ArticulationCfg = ArticulationCfg(
        prim_path="/World/envs/env_.*/Printer",
        spawn=UrdfFileCfg(
            asset_path=P2S_URDF_PATH,
            fix_base=True,  # Printer is bolted to the table
            rigid_props=RigidBodyPropertiesCfg(
                rigid_body_enabled=True,
                max_linear_velocity=5.0,
                max_angular_velocity=20.0,
                disable_gravity=False,
            ),
            collision_props=CollisionPropertiesCfg(
                contact_offset=0.005,
                rest_offset=0.0,
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.0),  # 40cm in front of arm base
            joint_pos={
                "Z-axis": 0.0,
                "Y-axis": 0.0,
                "X-axis": 0.0,
                "door_hinge": 0.0,  # Closed
            },
        ),
        actuators={
            # Door hinge: the joint the robot needs to open
            "door": sim_utils.ImplicitActuatorCfg(
                joint_names_expr=["door_hinge"],
                stiffness=50.0,
                damping=10.0,
                effort_limit=20.0,
            ),
            # Gantry axes: locked in place (high stiffness, not robot-controlled)
            "gantry": sim_utils.ImplicitActuatorCfg(
                joint_names_expr=["Z-axis", "Y-axis", "X-axis"],
                stiffness=10000.0,
                damping=1000.0,
                effort_limit=100.0,
            ),
        },
    )

    # ── Build Plate (primitive cuboid) ───────────────────────────────────────
    # Approximate dimensions of the P2S build plate: 256mm x 256mm x 3mm
    # Placed inside the printer at Z-bed height.
    build_plate: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/BuildPlate",
        spawn=CuboidCfg(
            size=(0.256, 0.256, 0.003),
            rigid_props=RigidBodyPropertiesCfg(kinematic_enabled=True),
            collision_props=CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=(0.15, 0.15, 0.15),  # Dark build plate
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.16),  # Sitting on Z-bed inside printer
        ),
    )

    # ── Print Object (primitive cylinder) ────────────────────────────────────
    # Generic printed object: small cylinder (~40mm diameter, 30mm tall, 50g)
    print_object: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/PrintObject",
        spawn=CylinderCfg(
            radius=0.020,
            height=0.030,
            rigid_props=RigidBodyPropertiesCfg(
                rigid_body_enabled=True,
                disable_gravity=False,
            ),
            mass_props=MassPropertiesCfg(mass=0.05),  # 50g
            collision_props=CollisionPropertiesCfg(
                contact_offset=0.001,
            ),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=(0.9, 0.3, 0.1),  # Orange PLA color
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
