"""
src/vision/zed_camera.py
-------------------------
ZED stereo camera wrapper with depth support.

Same public interface as Camera (open, close, get_frame) so CameraManager
can use either interchangeably via duck typing.

Install: ZED SDK must be installed system-wide from stereolabs.com.
         The Python wheel (pyzed) is installed as part of the SDK.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

from .camera_manager import CameraFrame

log = logging.getLogger(__name__)

try:
    import pyzed.sl as sl

    _ZED_AVAILABLE = True
except ImportError:
    _ZED_AVAILABLE = False

# Map config strings to ZED SDK enums
_RESOLUTION_MAP = {
    "HD2K": sl.RESOLUTION.HD2K if _ZED_AVAILABLE else None,
    "HD1080": sl.RESOLUTION.HD1080 if _ZED_AVAILABLE else None,
    "HD720": sl.RESOLUTION.HD720 if _ZED_AVAILABLE else None,
    "VGA": sl.RESOLUTION.VGA if _ZED_AVAILABLE else None,
}

_DEPTH_MODE_MAP = {
    "ULTRA": sl.DEPTH_MODE.ULTRA if _ZED_AVAILABLE else None,
    "QUALITY": sl.DEPTH_MODE.QUALITY if _ZED_AVAILABLE else None,
    "PERFORMANCE": sl.DEPTH_MODE.PERFORMANCE if _ZED_AVAILABLE else None,
    "NONE": sl.DEPTH_MODE.NONE if _ZED_AVAILABLE else None,
}


class ZedCamera:
    """
    ZED stereo camera capture with depth.

    Args:
        label: Friendly name (e.g. "front")
        resolution: ZED resolution string (HD720, HD1080, HD2K, VGA)
        depth_mode: Depth quality (ULTRA, QUALITY, PERFORMANCE, NONE)
        depth_min_m: Minimum depth range in meters
        depth_max_m: Maximum depth range in meters
        fps: Target capture framerate
        serial_number: ZED serial number (0 = auto-detect first camera)
    """

    def __init__(
        self,
        label: str,
        resolution: str = "HD720",
        depth_mode: str = "ULTRA",
        depth_min_m: float = 0.15,
        depth_max_m: float = 2.0,
        fps: int = 30,
        serial_number: int = 0,
        width: int = 1280,
        height: int = 720,
        **kwargs,
    ) -> None:
        if not _ZED_AVAILABLE:
            raise ImportError(
                "ZED SDK not found. Install from https://www.stereolabs.com/developers/release"
            )
        self.label = label
        self.resolution = resolution
        self.depth_mode = depth_mode
        self.depth_min_m = depth_min_m
        self.depth_max_m = depth_max_m
        self.fps = fps
        self.serial_number = serial_number
        self.width = width
        self.height = height

        self._zed: Optional[sl.Camera] = None
        self._latest: Optional[CameraFrame] = None
        self._latest_depth: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._drop_count = 0

        # Pre-allocate ZED Mat objects for efficient reuse
        self._image_mat: Optional[sl.Mat] = None
        self._depth_mat: Optional[sl.Mat] = None

    def open(self) -> None:
        """Initialize ZED camera and start background grab thread."""
        self._zed = sl.Camera()

        init_params = sl.InitParameters()
        init_params.camera_resolution = _RESOLUTION_MAP.get(
            self.resolution, sl.RESOLUTION.HD720
        )
        init_params.camera_fps = self.fps
        init_params.depth_mode = _DEPTH_MODE_MAP.get(
            self.depth_mode, sl.DEPTH_MODE.ULTRA
        )
        init_params.depth_minimum_distance = self.depth_min_m * 1000  # mm
        init_params.depth_maximum_distance = self.depth_max_m * 1000  # mm
        init_params.coordinate_units = sl.UNIT.MILLIMETER
        if self.serial_number:
            init_params.set_from_serial_number(self.serial_number)

        status = self._zed.open(init_params)
        if status != sl.ERROR_CODE.SUCCESS:
            raise IOError(f"ZED camera {self.label!r} open failed: {status}")

        # Pre-allocate Mat objects
        self._image_mat = sl.Mat()
        self._depth_mat = sl.Mat()

        # Runtime parameters for grab loop
        self._runtime_params = sl.RuntimeParameters()

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"zed-{self.label}",
        )
        self._thread.start()

        # Wait for first frame
        for _ in range(50):
            if self._latest is not None:
                break
            time.sleep(0.05)
        else:
            log.warning("ZED %r: no frame within 2.5s", self.label)

        info = self._zed.get_camera_information()
        res = info.camera_configuration.resolution
        log.info(
            "ZED %r opened: %dx%d @ %d fps, depth=%s",
            self.label, res.width, res.height, self.fps, self.depth_mode,
        )

    def close(self) -> None:
        """Stop grab thread and close ZED camera."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._zed:
            self._zed.close()
            self._zed = None
        log.info("ZED %r closed.", self.label)

    def get_frame(self) -> Optional[CameraFrame]:
        """Return the most recent frame (non-blocking)."""
        with self._lock:
            return self._latest

    def get_depth(self) -> Optional[np.ndarray]:
        """Return the most recent depth map as float32 (meters). None if unavailable."""
        with self._lock:
            return self._latest_depth

    def _capture_loop(self) -> None:
        """Background thread: grab frames + depth at target fps."""
        interval = 1.0 / max(self.fps, 1)

        while self._running:
            t0 = time.monotonic()

            if self._zed.grab(self._runtime_params) == sl.ERROR_CODE.SUCCESS:
                # Retrieve left RGB image
                self._zed.retrieve_image(self._image_mat, sl.VIEW.LEFT)
                image_bgr = self._image_mat.get_data()[:, :, :3].copy()  # BGRA → BGR

                # Retrieve depth map (float, mm) → convert to meters
                depth = None
                if self.depth_mode != "NONE":
                    self._zed.retrieve_measure(self._depth_mat, sl.MEASURE.DEPTH)
                    depth_mm = self._depth_mat.get_data().copy()
                    depth = (depth_mm / 1000.0).astype(np.float32)  # mm → m

                frame = CameraFrame(
                    label=self.label,
                    image=image_bgr,
                    timestamp=time.time(),
                    width=image_bgr.shape[1],
                    height=image_bgr.shape[0],
                    depth=depth,
                )

                with self._lock:
                    self._latest = frame
                    self._latest_depth = depth
                self._frame_count += 1
            else:
                self._drop_count += 1
                if self._drop_count % 30 == 1:
                    log.warning("ZED %r: %d dropped frames", self.label, self._drop_count)

            elapsed = time.monotonic() - t0
            sleep_t = max(0, interval - elapsed)
            time.sleep(sleep_t)
