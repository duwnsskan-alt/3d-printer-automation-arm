"""
Scene configuration for P2S printer + SO-100 arm with linear rail.

Joint index mapping (robot):
  0: rail_slide  (prismatic, Y-axis)
  1: shoulder_pan
  2: shoulder_lift
  3: elbow_flex
  4: wrist_flex
  5: wrist_roll
  6: gripper

Joint index mapping (printer):
  0: Z_axis
  1: Y_axis
  2: X_axis
  3: door_hinge
"""

from __future__ import annotations

import os

from isaaclab.scene import InteractiveSceneCfg
from isaaclab.assets import ArticulationCfg, RigidObjectCfg
from isaaclab.sensors import CameraCfg, FrameTransformerCfg
from isaaclab.sensors.frame_transformer.frame_transformer_cfg import OffsetCfg
from isaaclab.sim.spawners.from_files import UrdfFileCfg
from isaaclab.sim.converters.urdf_converter_cfg import UrdfConverterCfg
from isaaclab.sim.spawners.shapes import CuboidCfg, CylinderCfg
from isaaclab.sim.schemas.schemas_cfg import (
    RigidBodyPropertiesCfg,
    CollisionPropertiesCfg,
    MassPropertiesCfg,
)
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.utils import configclass
from isaaclab.actuators import ImplicitActuatorCfg

import isaaclab.sim as sim_utils


# ─── Asset Paths ──────────────────────────────────────────────────────────────

_PROJECT_ROOT = os.environ.get("PROJECT_ROOT", "/workspace/project")

SO100_RAIL_URDF_PATH = os.path.join(
    _PROJECT_ROOT, "sim/isaac_lab/assets/so100/so100_rail.urdf"
)
P2S_URDF_PATH = os.path.join(
    _PROJECT_ROOT, "sim/isaac_lab/assets/p2s/urdf/p2s_printer.urdf"
)


@configclass
class P2SArmSceneCfg(InteractiveSceneCfg):
    """Full scene: SO-100 on linear rail + P2S printer + objects + sensors."""

    # ── Ground Plane ──────────────────────────────────────────────────────────
    terrain = TerrainImporterCfg(
        prim_path="/World/ground",
        terrain_type="plane",
        collision_group=-1,
        physics_material=sim_utils.RigidBodyMaterialCfg(
            static_friction=0.5,
            dynamic_friction=0.5,
            restitution=0.0,
        ),
    )

    # ── SO-100 Robot Arm on Linear Rail ───────────────────────────────────────
    robot: ArticulationCfg = ArticulationCfg(
        prim_path="/World/envs/env_.*/Robot",
        spawn=UrdfFileCfg(
            asset_path=SO100_RAIL_URDF_PATH,
            fix_base=True,
            joint_drive=UrdfConverterCfg.JointDriveCfg(
                gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                    stiffness=400.0, damping=40.0
                ),
            ),
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
                "rail_slide":    0.0,
                "shoulder_pan":  0.0,
                "shoulder_lift": 0.5,
                "elbow_flex":   -1.0,
                "wrist_flex":    0.0,
                "wrist_roll":    0.5,
                "gripper":       0.0,
            },
        ),
        actuators={
            "rail": ImplicitActuatorCfg(
                joint_names_expr=["rail_slide"],
                velocity_limit=0.5,
                effort_limit=200.0,
                stiffness=100000.0,
                damping=10000.0,
            ),
            "arm_joints": ImplicitActuatorCfg(
                joint_names_expr=[
                    "shoulder_pan", "shoulder_lift", "elbow_flex",
                    "wrist_flex", "wrist_roll",
                ],
                velocity_limit=3.14,
                effort_limit=10.0,
                stiffness=400.0,
                damping=40.0,
            ),
            "gripper": ImplicitActuatorCfg(
                joint_names_expr=["gripper"],
                velocity_limit=0.5,
                effort_limit=5.0,
                stiffness=200.0,
                damping=20.0,
            ),
        },
    )

    # ── P2S Printer ───────────────────────────────────────────────────────────
    printer: ArticulationCfg = ArticulationCfg(
        prim_path="/World/envs/env_.*/Printer",
        spawn=UrdfFileCfg(
            asset_path=P2S_URDF_PATH,
            fix_base=True,
            joint_drive=UrdfConverterCfg.JointDriveCfg(
                gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                    stiffness=50.0, damping=10.0
                ),
            ),
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
            pos=(0.40, 0.0, 0.0),
            joint_pos={
                "Z_axis": 0.0,
                "Y_axis": 0.0,
                "X_axis": 0.0,
                "door_hinge": 0.0,
            },
        ),
        actuators={
            "door": ImplicitActuatorCfg(
                joint_names_expr=["door_hinge"],
                stiffness=50.0,
                damping=10.0,
                effort_limit=20.0,
            ),
            "gantry": ImplicitActuatorCfg(
                joint_names_expr=["Z_axis", "Y_axis", "X_axis"],
                stiffness=10000.0,
                damping=1000.0,
                effort_limit=100.0,
            ),
        },
    )

    # ── Build Plate ───────────────────────────────────────────────────────────
    build_plate: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/BuildPlate",
        spawn=CuboidCfg(
            size=(0.256, 0.256, 0.003),
            rigid_props=RigidBodyPropertiesCfg(kinematic_enabled=True),
            collision_props=CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=(0.15, 0.15, 0.15),
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.16),
        ),
    )

    # ── Print Object ──────────────────────────────────────────────────────────
    print_object: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/PrintObject",
        spawn=CylinderCfg(
            radius=0.020,
            height=0.030,
            rigid_props=RigidBodyPropertiesCfg(
                rigid_body_enabled=True,
                disable_gravity=False,
            ),
            mass_props=MassPropertiesCfg(mass=0.05),
            collision_props=CollisionPropertiesCfg(contact_offset=0.001),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=(0.9, 0.3, 0.1),
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(0.40, 0.0, 0.19),
        ),
    )

    # ── Staging Area (print placement target) ─────────────────────────────────
    staging_area: RigidObjectCfg = RigidObjectCfg(
        prim_path="/World/envs/env_.*/StagingArea",
        spawn=CuboidCfg(
            size=(0.15, 0.15, 0.003),
            rigid_props=RigidBodyPropertiesCfg(kinematic_enabled=True),
            collision_props=CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=(0.2, 0.5, 0.2),
            ),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(0.0, -0.3, 0.0),
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
                offset=OffsetCfg(pos=(0.0, 0.0, 0.10)),
            ),
        ],
    )

    # ── Door Handle Frame Sensor ──────────────────────────────────────────────
    door_handle_frame: FrameTransformerCfg = FrameTransformerCfg(
        prim_path="/World/envs/env_.*/Printer/Door_1",
        debug_vis=False,
        target_frames=[
            FrameTransformerCfg.FrameCfg(
                prim_path="/World/envs/env_.*/Printer/door_handle_marker",
                name="door_handle",
                offset=OffsetCfg(pos=(0.0, 0.0, 0.0)),
            ),
        ],
    )

    # ── Wrist Camera ──────────────────────────────────────────────────────────
    # Disabled by default for state-based RL. Enable for vision tasks.
    # wrist_camera: CameraCfg = CameraCfg(
    #     prim_path="/World/envs/env_.*/Robot/wrist_camera_link/WristCam",
    #     update_period=0.0,
    #     height=200,
    #     width=200,
    #     data_types=["rgb", "distance_to_image_plane"],
    #     spawn=sim_utils.PinholeCameraCfg(
    #         focal_length=8.0,
    #         focus_distance=0.15,
    #         horizontal_aperture=20.955,
    #         clipping_range=(0.01, 1.5),
    #     ),
    #     offset=CameraCfg.OffsetCfg(
    #         pos=(0.0, 0.0, 0.0),
    #         rot=(1.0, 0.0, 0.0, 0.0),
    #         convention="ros",
    #     ),
    # )
