"""
src/vla/vla_engine.py
---------------------
VLA (Vision-Language-Action) inference engine.

Wraps SmolVLA (450M) or OpenVLA-OFT (7B) via HuggingFace LeRobot
for real-time low-level joint control.

The VLA runs in a separate thread at ~10-50 Hz.
It receives: camera observations + task language description
It outputs: normalized joint action vectors which are sent directly to servos.

Architecture:
  VLAEngine.infer_loop()  →  LeRobot policy.select_action()
                          →  denormalize actions
                          →  RobotAPI.move_joints_raw()
"""

from __future__ import annotations

import logging
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.robot.robot_api import RobotAPI
    from src.vision.camera_manager import CameraManager, CameraFrame
    from src.safety.safety_layer import SafetyLayer

log = logging.getLogger(__name__)


@dataclass
class Observation:
    """Single observation fed to the VLA."""
    task_description: str
    joint_positions: list[float]    # Normalized [-1, 1]
    joint_velocities: list[float]
    images: dict[str, np.ndarray]   # label → HWC uint8 RGB
    timestamp: float = field(default_factory=time.time)


class VLAEngine:
    """
    Real-time VLA inference for low-level robot control.

    The engine runs a continuous predict→act loop.
    It supports action chunking: predict K actions, execute all K,
    then predict again. This reduces inference latency impact.

    Args:
        cfg: Full config dict
        robot: RobotAPI instance for reading state and sending commands
        cameras: CameraManager for live observations
        safety: SafetyLayer for E-stop checks
    """

    # Joint position ranges for SO-100 (encoder ticks → normalized float)
    # SO-100 has 5 arm joints + 1 gripper = 6 total (Feetech STS3215 servos)
    TICK_MIN = 0
    TICK_MAX = 4096
    NORMALIZED_MIN = -1.0
    NORMALIZED_MAX = 1.0

    def __init__(
        self,
        cfg: dict,
        robot: "RobotAPI",
        cameras: "CameraManager",
        safety: "SafetyLayer",
    ) -> None:
        self.cfg = cfg
        self.vla_cfg = cfg["vla"]
        self.robot = robot
        self.cameras = cameras
        self.safety = safety

        self.model_name: str = self.vla_cfg.get("model", "smolvla")
        self.device: str = self.vla_cfg.get("device", "cuda")
        self.inference_hz: float = self.vla_cfg.get("inference_hz", 20)
        self.chunk_size: int = self.vla_cfg.get("action_chunk_size", 4)
        self.obs_history: int = self.vla_cfg.get("obs_history", 2)

        self._policy = None  # Lazy-loaded
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._task_description: str = ""
        self._obs_buffer: deque[Observation] = deque(maxlen=self.obs_history)

        # Action execution state
        self._pending_actions: deque[np.ndarray] = deque()
        self._actions_lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def load_model(self) -> None:
        """Load the VLA model from disk or HuggingFace Hub. Call once at startup."""
        log.info("Loading VLA model: %s on %s", self.model_name, self.device)
        if self.model_name == "smolvla":
            self._load_smolvla()
        elif self.model_name == "openvla_oft":
            self._load_openvla_oft()
        else:
            raise ValueError(f"Unknown VLA model: {self.model_name!r}")
        log.info("VLA model loaded.")

    def _load_smolvla(self) -> None:
        """Load SmolVLA from LeRobot."""
        from lerobot.common.policies.smolvla.modeling_smolvla import SmolVLAPolicy
        from lerobot.common.policies.smolvla.configuration_smolvla import SmolVLAConfig

        model_path = self.vla_cfg.get("smolvla_path", "lerobot/smolvla")
        self._policy = SmolVLAPolicy.from_pretrained(model_path)
        self._policy = self._policy.to(self.device)
        self._policy.eval()
        log.info("SmolVLA loaded from %s", model_path)

    def _load_openvla_oft(self) -> None:
        """Load OpenVLA-OFT from HuggingFace."""
        from lerobot.common.policies.openvla_oft.modeling_openvla_oft import OpenVLAOFTPolicy

        model_path = self.vla_cfg.get(
            "openvla_path",
            "openvla/openvla-oft-prismatic-dinosiglip-224px+mx-bridge+n=1",
        )
        self._policy = OpenVLAOFTPolicy.from_pretrained(model_path)
        self._policy = self._policy.to(self.device)
        self._policy.eval()
        log.info("OpenVLA-OFT loaded from %s", model_path)

    def start(self, task: str) -> None:
        """Start the VLA inference loop for the given task."""
        if self._policy is None:
            self.load_model()

        self._task_description = task
        self._running = True
        self._pending_actions.clear()
        self._obs_buffer.clear()

        self._thread = threading.Thread(
            target=self._infer_loop,
            daemon=True,
            name="vla-infer",
        )
        self._thread.start()
        log.info("VLA engine started for task: %r", task)

    def stop(self) -> None:
        """Stop the inference loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        log.info("VLA engine stopped.")

    # ── Inference Loop ────────────────────────────────────────────────────────

    def _infer_loop(self) -> None:
        """
        Main predict-act loop.

        Runs at inference_hz. When the pending action buffer empties,
        calls the policy to generate a new action chunk.
        """
        interval = 1.0 / self.inference_hz
        import torch

        while self._running:
            t0 = time.monotonic()

            if self.safety.is_stopped:
                log.warning("VLA loop: E-stop active, pausing.")
                time.sleep(0.1)
                continue

            try:
                # 1. Gather observation
                obs = self._collect_observation()
                self._obs_buffer.append(obs)

                # 2. If action buffer empty, run inference
                with self._actions_lock:
                    need_inference = len(self._pending_actions) == 0

                if need_inference and len(self._obs_buffer) >= 1:
                    actions = self._run_inference(list(self._obs_buffer))
                    with self._actions_lock:
                        for a in actions:
                            self._pending_actions.append(a)

                # 3. Execute next action from chunk
                with self._actions_lock:
                    if self._pending_actions:
                        action = self._pending_actions.popleft()
                    else:
                        action = None

                if action is not None:
                    self._execute_action(action)

            except Exception as e:
                log.error("VLA infer loop error: %s", e, exc_info=True)

            elapsed = time.monotonic() - t0
            sleep_t = max(0.0, interval - elapsed)
            time.sleep(sleep_t)

    def _collect_observation(self) -> Observation:
        """Build an Observation from current robot + camera state."""
        import cv2

        # Read joint positions (ticks) and normalize to [-1, 1]
        raw_positions = self.robot.get_joint_positions()
        norm_positions = self._normalize_ticks(raw_positions)

        # Build image dict (RGB uint8)
        images = {}
        for label, frame in self.cameras.capture_all().items():
            rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
            images[label] = rgb

        return Observation(
            task_description=self._task_description,
            joint_positions=norm_positions,
            joint_velocities=[0.0] * len(norm_positions),  # Could read from servos
            images=images,
        )

    def _run_inference(self, obs_history: list[Observation]) -> list[np.ndarray]:
        """
        Run the VLA policy on an observation.

        Args:
            obs_history: List of recent observations

        Returns:
            List of action arrays (one per chunk step)
        """
        import torch

        # Use the most recent observation for simplicity
        # (multi-frame history would stack along batch dim)
        obs = obs_history[-1]

        # Build policy input batch
        # LeRobot policies expect a specific observation format
        batch = self._build_policy_batch(obs)

        with torch.no_grad():
            action_tensor = self._policy.select_action(batch)

        # action_tensor shape: [chunk_size, action_dim] or [action_dim]
        if action_tensor.ndim == 1:
            actions = [action_tensor.cpu().numpy()]
        else:
            actions = [a.cpu().numpy() for a in action_tensor]

        # Trim to configured chunk size
        return actions[:self.chunk_size]

    def _build_policy_batch(self, obs: Observation) -> dict:
        """
        Convert Observation to LeRobot policy input format.

        LeRobot policies expect:
          observation.state: [B, state_dim] float32
          observation.images.<cam_key>: [B, C, H, W] float32 [0,1]
          task: list of strings
        """
        import torch
        import torchvision.transforms.functional as TF
        from PIL import Image as PILImage

        state = torch.tensor(obs.joint_positions, dtype=torch.float32).unsqueeze(0)  # [1, D]

        image_tensors = {}
        for label, img in obs.images.items():
            pil = PILImage.fromarray(img)
            # Resize to model's expected input
            pil = pil.resize((224, 224))
            t = TF.to_tensor(pil).unsqueeze(0)  # [1, C, H, W]
            image_tensors[label] = t.to(self.device)

        return {
            "observation.state": state.to(self.device),
            "observation.images": image_tensors,
            "task": [obs.task_description],
        }

    def _execute_action(self, action: np.ndarray) -> None:
        """
        Convert normalized action to servo commands and execute.

        Args:
            action: Normalized action vector, shape [n_joints] or [n_joints+1]
                    (last element may be gripper if included)
        """
        n_joints = len(self.cfg["robot"]["joint_ids"])

        joint_actions = action[:n_joints]
        gripper_action = action[n_joints] if len(action) > n_joints else None

        # Denormalize to encoder ticks
        ticks = self._denormalize_to_ticks(joint_actions.tolist())

        self.robot.move_joints_raw(ticks, speed=self.cfg["robot"].get("max_velocity", 300))

        # Handle gripper
        if gripper_action is not None:
            # Convention: > 0.0 = close, <= 0.0 = open
            if gripper_action > 0.0:
                self.robot.gripper_close()
            else:
                self.robot.gripper_open()

    # ── Normalization Helpers ─────────────────────────────────────────────────

    def _normalize_ticks(self, ticks: list[int]) -> list[float]:
        """Convert encoder ticks to normalized floats in [-1, 1]."""
        mid = (self.TICK_MAX + self.TICK_MIN) / 2
        half_range = (self.TICK_MAX - self.TICK_MIN) / 2
        return [(t - mid) / half_range for t in ticks]

    def _denormalize_to_ticks(self, normed: list[float]) -> list[int]:
        """Convert normalized floats back to encoder ticks."""
        mid = (self.TICK_MAX + self.TICK_MIN) / 2
        half_range = (self.TICK_MAX - self.TICK_MIN) / 2
        return [
            int(np.clip(n * half_range + mid, self.TICK_MIN, self.TICK_MAX))
            for n in normed
        ]
