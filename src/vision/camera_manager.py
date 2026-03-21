"""
src/vision/camera_manager.py
-----------------------------
Manages multiple USB cameras (front + wrist).

Provides:
  - Threaded capture loops with latest-frame caching
  - Synchronized multi-camera snapshot
  - JPEG encoding for VLM API calls (base64)
  - Optional recording to disk
"""

from __future__ import annotations

import base64
import io
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class CameraFrame:
    """A captured frame with metadata."""
    label: str
    image: np.ndarray         # BGR image array
    timestamp: float = field(default_factory=time.time)
    width: int = 0
    height: int = 0
    depth: Optional[np.ndarray] = None  # float32 depth in meters (ZED only)

    def to_jpeg_b64(self, quality: int = 85) -> str:
        """Encode frame to base64 JPEG string (for API calls)."""
        _, buf = cv2.imencode(".jpg", self.image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf.tobytes()).decode()

    def to_pil(self):
        """Convert to PIL Image (for local VLM inference)."""
        from PIL import Image
        rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)


class Camera:
    """
    Single-camera capture thread.

    Args:
        label: Friendly name ("front" or "wrist")
        device: CV2 device path or index
        width, height, fps: Capture params
    """

    def __init__(self, label: str, device: str | int, width: int, height: int, fps: int) -> None:
        self.label = label
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps

        self._cap: Optional[cv2.VideoCapture] = None
        self._latest: Optional[CameraFrame] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._drop_count = 0

    def open(self) -> None:
        """Open capture device and start background thread."""
        self._cap = cv2.VideoCapture(self.device)
        if not self._cap.isOpened():
            raise IOError(f"Cannot open camera {self.label!r} at {self.device!r}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Disable internal buffering for low-latency global shutter
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"camera-{self.label}",
        )
        self._thread.start()
        # Wait for first frame
        for _ in range(50):
            if self._latest:
                break
            time.sleep(0.05)
        else:
            log.warning("Camera %r: no frame within 2.5s", self.label)
        log.info("Camera %r opened: %dx%d @ %d fps", self.label, self.width, self.height, self.fps)

    def close(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()

    def get_frame(self) -> Optional[CameraFrame]:
        """Return the most recent frame (non-blocking)."""
        with self._lock:
            return self._latest

    def _capture_loop(self) -> None:
        interval = 1.0 / max(self.fps, 1)
        while self._running:
            t0 = time.monotonic()
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._latest = CameraFrame(
                        label=self.label,
                        image=frame,
                        timestamp=time.time(),
                        width=frame.shape[1],
                        height=frame.shape[0],
                    )
                self._frame_count += 1
            else:
                self._drop_count += 1
                if self._drop_count % 30 == 1:
                    log.warning("Camera %r: %d dropped frames", self.label, self._drop_count)
            elapsed = time.monotonic() - t0
            sleep_t = max(0, interval - elapsed)
            time.sleep(sleep_t)


class CameraManager:
    """
    Manages all cameras defined in config.

    Usage:
        mgr = CameraManager(cfg["cameras"])
        mgr.open_all()
        frames = mgr.capture_all()
        mgr.close_all()
    """

    def __init__(self, cameras_cfg: dict) -> None:
        self._cameras: dict[str, Camera] = {}
        for label, cam_cfg in cameras_cfg.items():
            cam_type = cam_cfg.get("type", "usb")
            if cam_type == "zed":
                try:
                    from .zed_camera import ZedCamera
                except ImportError:
                    raise ImportError(
                        f"Camera {label!r} is configured as 'zed' but ZED SDK is not installed."
                    )
                self._cameras[label] = ZedCamera(
                    label=label,
                    resolution=cam_cfg.get("resolution", "HD720"),
                    depth_mode=cam_cfg.get("depth_mode", "ULTRA"),
                    depth_min_m=cam_cfg.get("depth_min_m", 0.15),
                    depth_max_m=cam_cfg.get("depth_max_m", 2.0),
                    fps=cam_cfg.get("fps", 30),
                    serial_number=cam_cfg.get("serial_number", 0),
                    width=cam_cfg.get("width", 1280),
                    height=cam_cfg.get("height", 720),
                )
            else:
                self._cameras[label] = Camera(
                    label=label,
                    device=cam_cfg["device"],
                    width=cam_cfg.get("width", 1280),
                    height=cam_cfg.get("height", 720),
                    fps=cam_cfg.get("fps", 30),
                )

    def open_all(self) -> None:
        for cam in self._cameras.values():
            cam.open()

    def close_all(self) -> None:
        for cam in self._cameras.values():
            cam.close()

    def get_frame(self, label: str) -> Optional[CameraFrame]:
        """Get the latest frame from a specific camera."""
        cam = self._cameras.get(label)
        return cam.get_frame() if cam else None

    def capture_all(self) -> dict[str, CameraFrame]:
        """
        Capture synchronised frames from all cameras.

        Returns:
            Dict mapping label → CameraFrame (None entries omitted)
        """
        result = {}
        for label, cam in self._cameras.items():
            frame = cam.get_frame()
            if frame is not None:
                result[label] = frame
            else:
                log.warning("No frame available from camera %r", label)
        return result

    def capture_all_b64(self, quality: int = 85) -> dict[str, str]:
        """Return dict of label → base64 JPEG string."""
        frames = self.capture_all()
        return {label: frame.to_jpeg_b64(quality) for label, frame in frames.items()}

    def save_snapshot(self, output_dir: str | Path, prefix: str = "") -> dict[str, Path]:
        """Save current frames as PNG files to output_dir. Returns {label: path}."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = {}
        for label, frame in self.capture_all().items():
            ts = int(frame.timestamp * 1000)
            fname = f"{prefix}{label}_{ts}.png"
            path = output_dir / fname
            cv2.imwrite(str(path), frame.image)
            saved[label] = path
        return saved

    def __enter__(self) -> "CameraManager":
        self.open_all()
        return self

    def __exit__(self, *_) -> None:
        self.close_all()
