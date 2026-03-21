"""Standalone script to load SO-100 robot arm + P2S printer in Isaac Sim."""

import shutil
import os

from isaacsim import SimulationApp

simulation_app = SimulationApp({
    "headless": False,
    "width": 1920,
    "height": 1080,
    "window_title": "P2S + SO-100 Scene",
})

# -- Imports after SimulationApp --
import numpy as np
import omni.kit.commands
import omni.usd
from pxr import Gf, UsdGeom

from omni.isaac.core import World
from omni.isaac.core.utils.viewports import set_camera_view


def copy_assets(src_dir, work_dir):
    """Copy asset directory to a writable location (project is mounted read-only)."""
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(src_dir, work_dir)
    print(f"Copied assets: {src_dir} -> {work_dir}")


def import_urdf(urdf_path, fix_base=True, make_default_prim=False, create_physics_scene=False):
    """Import a URDF file into the current stage and return the prim path."""
    status, import_config = omni.kit.commands.execute("URDFCreateImportConfig")
    import_config.merge_fixed_joints = False
    import_config.fix_base = fix_base
    import_config.make_default_prim = make_default_prim
    import_config.create_physics_scene = create_physics_scene

    result = omni.kit.commands.execute(
        "URDFParseAndImportFile",
        urdf_path=urdf_path,
        import_config=import_config,
        dest_path="",
    )
    # Result may be a string or tuple depending on Isaac Sim version
    if isinstance(result, tuple):
        prim_path = result[1] if len(result) > 1 else result[0]
    else:
        prim_path = result
    return prim_path


def set_prim_position(prim_path, x, y, z):
    """Translate a USD prim to a world position."""
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        print(f"WARNING: Prim not found at {prim_path}, skipping position")
        return
    xformable = UsdGeom.Xformable(prim)
    xformable.ClearXformOpOrder()
    xformable.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
    print(f"Positioned {prim_path} at ({x}, {y}, {z})")


def main():
    # ── Copy assets to writable locations ────────────────────────────────────
    so100_work = "/tmp/so100_import"
    p2s_work = "/tmp/p2s_import"

    copy_assets("/workspace/project/sim/isaac_lab/assets/so100", so100_work)
    copy_assets("/workspace/project/sim/isaac_lab/assets/p2s", p2s_work)

    so100_urdf = os.path.join(so100_work, "so100.urdf")
    p2s_urdf = os.path.join(p2s_work, "urdf", "p2s_printer.urdf")

    # Set CWD to SO-100 work dir for mesh resolution
    os.chdir(so100_work)

    # ── Create world ─────────────────────────────────────────────────────────
    world = World(stage_units_in_meters=1.0)
    world.scene.add_default_ground_plane()

    # ── Import SO-100 (first: creates physics scene + default prim) ──────────
    so100_prim = import_urdf(
        so100_urdf,
        fix_base=True,
        make_default_prim=True,
        create_physics_scene=True,
    )
    print(f"SO-100 imported at: {so100_prim}")

    # ── Import P2S printer (second: no default prim, no physics scene) ───────
    p2s_prim = import_urdf(
        p2s_urdf,
        fix_base=True,
        make_default_prim=False,
        create_physics_scene=False,
    )
    print(f"P2S imported at: {p2s_prim}")

    # ── Position P2S 0.4m in front of the robot arm ──────────────────────────
    if p2s_prim:
        set_prim_position(str(p2s_prim), 0.40, 0.0, 0.0)

    # ── Camera: pull back to show both objects ───────────────────────────────
    set_camera_view(
        eye=np.array([0.8, 0.8, 0.6]),
        target=np.array([0.2, 0.0, 0.15]),
        camera_prim_path="/OmniverseKit_Persp",
    )

    # ── Run simulation ───────────────────────────────────────────────────────
    world.reset()
    print("=" * 60)
    print("  P2S Printer + SO-100 Robot Arm loaded!")
    print("  View: vncviewer localhost:5900")
    print("=" * 60)

    while simulation_app.is_running():
        world.step(render=True)

    simulation_app.close()


if __name__ == "__main__":
    main()
