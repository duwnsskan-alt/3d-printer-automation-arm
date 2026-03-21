"""Standalone script to load SO-100 robot arm in Isaac Sim with ground plane."""

import shutil
import os

from isaacsim import SimulationApp

simulation_app = SimulationApp({
    "headless": False,
    "width": 1920,
    "height": 1080,
    "window_title": "SO-100 Robot Arm",
})

# -- Imports after SimulationApp --
import numpy as np
import omni.kit.commands
import omni.usd
from pxr import Gf, UsdGeom

from omni.isaac.core import World
from omni.isaac.core.utils.viewports import set_camera_view


def main():
    # Copy URDF + meshes to a writable location (project is mounted read-only)
    src_dir = "/workspace/project/sim/isaac_lab/assets/so100"
    work_dir = "/tmp/so100_import"
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(src_dir, work_dir)
    urdf_path = os.path.join(work_dir, "so100.urdf")
    os.chdir(work_dir)
    print(f"Copied URDF assets to {work_dir}")

    world = World(stage_units_in_meters=1.0)

    # Add ground plane
    world.scene.add_default_ground_plane()

    # Get import config
    status, import_config = omni.kit.commands.execute("URDFCreateImportConfig")
    import_config.merge_fixed_joints = False
    import_config.fix_base = True
    import_config.make_default_prim = True
    import_config.create_physics_scene = True

    # Parse and import from writable directory
    prim_path = omni.kit.commands.execute(
        "URDFParseAndImportFile",
        urdf_path=urdf_path,
        import_config=import_config,
        dest_path="",
    )

    print(f"SO-100 imported at: {prim_path}")

    # Set camera to view the robot
    set_camera_view(
        eye=np.array([0.5, 0.5, 0.4]),
        target=np.array([0.0, 0.0, 0.15]),
        camera_prim_path="/OmniverseKit_Persp",
    )

    # Reset world and run
    world.reset()
    print("=" * 60)
    print("  SO-100 Robot Arm loaded!")
    print("  View: VNC on port 5900")
    print("=" * 60)

    while simulation_app.is_running():
        world.step(render=True)

    simulation_app.close()


if __name__ == "__main__":
    main()
