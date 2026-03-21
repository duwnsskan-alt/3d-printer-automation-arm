"""Load SO-100 robot arm URDF into Isaac Sim with a ground plane and camera."""

import argparse
import sys

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Load SO-100 robot arm in Isaac Sim")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# -- Isaac Sim imports (must come after AppLauncher) --
import numpy as np
import omni.isaac.core.utils.prims as prim_utils
from omni.isaac.core import World
from isaacsim.asset.importer.urdf import URDFImporter

import omni.usd
from pxr import Gf, UsdGeom


def main():
    world = World(stage_units_in_meters=1.0)

    # Ground plane
    world.scene.add_default_ground_plane()

    # Import URDF
    urdf_path = "/workspace/project/sim/isaac_lab/assets/so100/so100.urdf"

    importer = URDFImporter()
    import_config = importer.get_import_config()
    import_config.merge_fixed_joints = False
    import_config.fix_base = True
    import_config.make_default_prim = True
    import_config.create_physics_scene = True

    result, prim_path = importer.import_robot(
        urdf_path=urdf_path,
        import_config=import_config,
        dest_path="/World/so100",
    )

    if result:
        print(f"SO-100 loaded at {prim_path}")
    else:
        print("Failed to import URDF")
        simulation_app.close()
        return

    # Position camera to view the robot
    stage = omni.usd.get_context().get_stage()
    camera_path = "/World/Camera"
    camera = UsdGeom.Camera.Define(stage, camera_path)
    camera.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 1000.0))
    xform = UsdGeom.Xformable(camera.GetPrim())
    xform.ClearXformOpOrder()
    xform.AddTranslateOp().Set(Gf.Vec3d(0.5, 0.5, 0.4))
    xform.AddRotateXYZOp().Set(Gf.Vec3f(-30, 0, 135))

    # Set viewport camera
    from omni.kit.viewport.utility import get_active_viewport
    viewport = get_active_viewport()
    if viewport:
        viewport.set_active_camera(camera_path)

    # Reset and run simulation loop
    world.reset()
    print("Simulation running. View at http://localhost:6080/vnc.html")

    while simulation_app.is_running():
        world.step(render=True)

    simulation_app.close()


if __name__ == "__main__":
    main()
