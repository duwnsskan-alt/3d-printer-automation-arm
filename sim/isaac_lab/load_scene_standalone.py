"""Standalone script to load SO-100 robot arm + P2S printer in Isaac Sim.

Fixes:
  1. Each URDF is imported to its own USD file, then referenced into the
     stage as a separate prim — prevents P2S from nesting under SO-100.
  2. Materials: printer body=gray, Z-bed=brown, door=black tinted glass.
  3. ArticulationRootAPI + joint drives with stiffness/damping so robot
     parts hold together instead of flying apart.
"""

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
from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdShade, Sdf

from omni.isaac.core import World
from omni.isaac.core.utils.viewports import set_camera_view


# ── Helpers ────────────────────────────────────────────────────────────────────

def copy_assets(src_dir, work_dir):
    """Copy asset directory to a writable location (project mount is read-only)."""
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(src_dir, work_dir)
    print(f"  Copied: {src_dir} -> {work_dir}")


def import_urdf_to_usd(urdf_path, dest_usd, fix_base=True):
    """Import a URDF into a standalone USD file (not the current stage).

    Sets CWD to the URDF directory so relative mesh paths resolve correctly.
    The output USD references mesh .usd files written alongside the STLs.
    """
    prev_cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(urdf_path)))

    _, config = omni.kit.commands.execute("URDFCreateImportConfig")
    config.merge_fixed_joints = False
    config.fix_base = fix_base
    config.make_default_prim = True
    config.create_physics_scene = False  # World handles physics scene
    config.convex_decomp = False
    config.self_collision = False

    result = omni.kit.commands.execute(
        "URDFParseAndImportFile",
        urdf_path=urdf_path,
        import_config=config,
        dest_path=dest_usd,
    )

    os.chdir(prev_cwd)
    print(f"  URDF -> {dest_usd}")
    return result


def create_material(stage, path, color, opacity=1.0, metallic=0.0, roughness=0.5):
    """Create a UsdPreviewSurface material."""
    mat = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*color)
    )
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    if opacity < 1.0:
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.5)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def create_glass_material(stage, path, color=(0.05, 0.05, 0.05), ior=1.5):
    """Create an OmniGlass material for transparent/tinted glass."""
    mat = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Shader")
    shader.CreateIdAttr("OmniGlass")
    shader.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*color)
    )
    shader.CreateInput("glass_ior", Sdf.ValueTypeNames.Float).Set(ior)
    shader.CreateInput("thin_walled", Sdf.ValueTypeNames.Bool).Set(True)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def bind_material(stage, prim_path, material):
    """Bind material to a prim (children inherit via USD material inheritance)."""
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        print(f"  WARNING: {prim_path} not found for material binding")
        return
    UsdShade.MaterialBindingAPI.Apply(prim)
    UsdShade.MaterialBindingAPI(prim).Bind(material)
    print(f"  Material -> {prim_path}")


def setup_joint_drives(stage, robot_path, angular_stiffness=400.0,
                       angular_damping=40.0, linear_stiffness=10000.0,
                       linear_damping=1000.0):
    """Add position drives to all joints under robot_path.

    The URDF importer already sets ArticulationRootAPI — we only configure
    drive stiffness/damping so joints hold position instead of collapsing.
    """
    robot = stage.GetPrimAtPath(robot_path)
    if not robot.IsValid():
        print(f"  WARNING: {robot_path} not found for physics setup")
        return

    joint_count = 0
    for prim in Usd.PrimRange(robot):
        tn = prim.GetTypeName()
        if "RevoluteJoint" in tn:
            drive = UsdPhysics.DriveAPI.Apply(prim, "angular")
            drive.CreateTypeAttr().Set("force")
            drive.CreateStiffnessAttr().Set(angular_stiffness)
            drive.CreateDampingAttr().Set(angular_damping)
            drive.CreateTargetPositionAttr().Set(0.0)
            joint_count += 1
        elif "PrismaticJoint" in tn:
            drive = UsdPhysics.DriveAPI.Apply(prim, "linear")
            drive.CreateTypeAttr().Set("force")
            drive.CreateStiffnessAttr().Set(linear_stiffness)
            drive.CreateDampingAttr().Set(linear_damping)
            drive.CreateTargetPositionAttr().Set(0.0)
            joint_count += 1
    print(f"  Drives configured: {joint_count} joints under {robot_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # ── Copy assets to writable locations ──────────────────────────────────────
    so100_work = "/tmp/so100_import"
    p2s_work = "/tmp/p2s_import"
    copy_assets("/workspace/project/sim/isaac_lab/assets/so100", so100_work)
    copy_assets("/workspace/project/sim/isaac_lab/assets/p2s", p2s_work)

    so100_urdf = os.path.join(so100_work, "so100.urdf")
    p2s_urdf = os.path.join(p2s_work, "urdf", "p2s_printer.urdf")

    # ── World ──────────────────────────────────────────────────────────────────
    world = World(stage_units_in_meters=1.0)
    world.scene.add_default_ground_plane()

    # ── Import each URDF to its own USD file ───────────────────────────────────
    # Writing to separate files guarantees they are independent prim trees.
    print("[1/5] Importing SO-100 URDF...")
    so100_usd = os.path.join(so100_work, "so100_imported.usd")
    import_urdf_to_usd(so100_urdf, so100_usd, fix_base=True)

    print("[2/5] Importing P2S URDF...")
    p2s_usd = os.path.join(p2s_work, "urdf", "p2s_imported.usd")
    import_urdf_to_usd(p2s_urdf, p2s_usd, fix_base=True)

    # ── Reference both USD files into the live stage ───────────────────────────
    print("[3/5] Building scene...")
    stage = omni.usd.get_context().get_stage()

    # SO-100 at origin
    so100_prim = stage.DefinePrim("/World/SO100", "Xform")
    so100_prim.GetReferences().AddReference(so100_usd)
    print("  SO-100 -> /World/SO100")

    # P2S at 0.4m in front
    p2s_prim = stage.DefinePrim("/World/P2S", "Xform")
    p2s_prim.GetReferences().AddReference(p2s_usd)
    p2s_xform = UsdGeom.Xformable(p2s_prim)
    # Referenced prim may already have xform ops — clear and re-set
    p2s_xform.ClearXformOpOrder()
    p2s_xform.AddTranslateOp().Set(Gf.Vec3d(0.4, 0.0, 0.0))
    print("  P2S -> /World/P2S at (0.4, 0, 0)")

    # Debug: print top-level prim tree
    print("  Stage hierarchy:")
    for prim in stage.Traverse():
        depth = prim.GetPath().pathString.count("/")
        if depth <= 3:
            print(f"    {'  ' * depth}{prim.GetPath()} [{prim.GetTypeName()}]")

    # ── Materials for P2S ──────────────────────────────────────────────────────
    print("[4/5] Setting materials...")
    gray = create_material(
        stage, "/World/Looks/PrinterBody",
        color=(0.5, 0.5, 0.5), metallic=0.1, roughness=0.6,
    )
    brown = create_material(
        stage, "/World/Looks/BuildPlate",
        color=(0.55, 0.35, 0.15), roughness=0.7,
    )
    glass = create_glass_material(
        stage, "/World/Looks/TintedGlass",
        color=(0.05, 0.05, 0.05),
    )

    # Printer body parts -> gray
    bind_material(stage, "/World/P2S/base_link", gray)
    bind_material(stage, "/World/P2S/Y_axis_1", gray)
    bind_material(stage, "/World/P2S/X_axis_nozzle_1", gray)
    # Z-bed (build plate surface) -> brown
    bind_material(stage, "/World/P2S/Z_bed_1", brown)
    # Door -> black tinted glass
    bind_material(stage, "/World/P2S/Door_1", glass)

    # ── Physics: articulation + joint drives ───────────────────────────────────
    print("[5/5] Configuring physics...")
    # SO-100: stiffness/damping from scene_cfg.py
    setup_joint_drives(
        stage, "/World/SO100",
        angular_stiffness=400.0,
        angular_damping=40.0,
    )
    # P2S: door hinge=soft, gantry axes=very stiff (locked)
    setup_joint_drives(
        stage, "/World/P2S",
        angular_stiffness=50.0,
        angular_damping=10.0,
        linear_stiffness=10000.0,
        linear_damping=1000.0,
    )

    # ── Camera ─────────────────────────────────────────────────────────────────
    set_camera_view(
        eye=np.array([0.8, 0.8, 0.6]),
        target=np.array([0.2, 0.0, 0.15]),
        camera_prim_path="/OmniverseKit_Persp",
    )

    # ── Run simulation ─────────────────────────────────────────────────────────
    world.reset()
    print("=" * 60)
    print("  Scene loaded: SO-100 + P2S Printer")
    print("  SO-100: /World/SO100 (origin)")
    print("  P2S:    /World/P2S   (0.4m forward)")
    print("  View:   http://localhost:6080/vnc.html")
    print("=" * 60)

    while simulation_app.is_running():
        world.step(render=True)

    simulation_app.close()


if __name__ == "__main__":
    main()
