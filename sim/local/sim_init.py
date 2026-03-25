"""
sim/local/sim_init.py
----------------------
Common Isaac Sim initialization for local execution.
Must be called before any isaaclab imports.

Usage:
    from sim_init import init_sim
    app = init_sim(headless=True)
    # now import isaaclab modules...
"""

import os
import sys


def init_sim(headless: bool = False, width: int = 1280, height: int = 720):
    """Initialize SimulationApp and configure asset paths for local execution."""
    # Set project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    os.environ.setdefault("PROJECT_ROOT", project_root)

    # Add printer_arm_tasks to path
    isaac_lab_dir = os.path.join(project_root, "sim", "isaac_lab")
    if isaac_lab_dir not in sys.path:
        sys.path.insert(0, isaac_lab_dir)

    # EULA acceptance
    os.environ["ACCEPT_EULA"] = "Y"
    os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": headless, "width": width, "height": height})

    # Set cloud asset root to S3 (Nucleus not available locally)
    import carb
    settings = carb.settings.get_settings()
    s3_root = settings.get("/persistent/isaac/asset_root/default")
    if s3_root and not settings.get("/persistent/isaac/asset_root/cloud"):
        settings.set("/persistent/isaac/asset_root/cloud", s3_root)

    return app
