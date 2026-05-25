"""Shared SO-100 utilities for Isaac Sim standalone scripts.

Camera spec is the single source of truth — used by:
  - load_so100_standalone.py (SO-100 only viewer)
  - load_scene_standalone.py (SO-100 + P2S scene viewer)
  - scene_cfg.py RL env CameraCfg should mirror these values

URDF defines the mount link (wrist_camera_link) and joint origin (position +
orientation in jaw frame). This helper attaches a UsdGeom.Camera prim to that
link so the camera is visible in viewport, can be selected, and renders RGB.
"""

from pxr import Usd, UsdGeom, Sdf


# Camera intrinsics (mirror in scene_cfg.py CameraCfg if changed)
CAMERA_FOCAL_LENGTH = 8.0       # mm
CAMERA_FOCUS_DISTANCE = 0.15    # m
CAMERA_HORIZONTAL_APERTURE = 20.955  # mm
CAMERA_CLIP_NEAR = 0.01
CAMERA_CLIP_FAR = 1.5


def attach_wrist_camera(stage, robot_root_path=None,
                        link_name="gripper_camera_link",
                        cam_name="WristCam"):
    """Add a Camera prim under <robot>/.../<link_name>.

    If robot_root_path is None, traverses the entire stage to find the link.
    Returns the camera prim path, or None if the link wasn't found.
    """
    if robot_root_path:
        root = stage.GetPrimAtPath(robot_root_path)
        if not root.IsValid():
            print(f"  WARNING: robot root '{robot_root_path}' not found")
            return None
        search_iter = Usd.PrimRange(root)
    else:
        search_iter = stage.Traverse()

    target_prim = None
    for prim in search_iter:
        if prim.GetName() == link_name:
            target_prim = prim
            break
    if target_prim is None:
        print(f"  WARNING: link '{link_name}' not found in stage")
        return None

    cam_path = f"{target_prim.GetPath().pathString}/{cam_name}"
    cam = UsdGeom.Camera.Define(stage, cam_path)
    cam.CreateFocalLengthAttr(CAMERA_FOCAL_LENGTH)
    cam.CreateFocusDistanceAttr(CAMERA_FOCUS_DISTANCE)
    cam.CreateHorizontalApertureAttr(CAMERA_HORIZONTAL_APERTURE)
    cam.CreateClippingRangeAttr((CAMERA_CLIP_NEAR, CAMERA_CLIP_FAR))
    print(f"  Camera attached: {cam_path}")
    return cam_path
