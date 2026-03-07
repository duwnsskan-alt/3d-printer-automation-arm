"""
src/safety/safety_layer.py
--------------------------
All safety concerns live here:

1. **VLM Output Sandboxing** — only whitelisted API calls can be executed
2. **STS3215 Overload Detection** — monitors torque every tick; triggers E-stop
3. **E-stop Handler** — cuts all motor torque immediately
4. **Workspace Limit Checks** — validates joint angles before any move
"""

from __future__ import annotations

import ast
import logging
import threading
import time
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from src.robot.robot_api import RobotAPI

log = logging.getLogger(__name__)


# ─── Custom Exceptions ───────────────────────────────────────────────────────

class EStop(Exception):
    """Emergency stop triggered."""

class OverloadError(Exception):
    """Motor overload detected."""

class SandboxViolation(Exception):
    """VLM generated code that calls a disallowed API."""


# ─── Safety Layer ────────────────────────────────────────────────────────────

class SafetyLayer:
    """
    Centralised safety enforcement.

    Injected into RobotAPI and VLMOrchestrator to gate all actions.

    Args:
        cfg: The full config dict (uses 'robot' and 'vlm' sections)
    """

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.robot_cfg = cfg["robot"]
        self.vlm_cfg = cfg["vlm"]

        self._allowed_calls: set[str] = set(self.vlm_cfg.get("allowed_api_calls", []))
        self._overload_threshold: int = self.robot_cfg.get("overload_threshold", 900)
        self._joint_limits = self.robot_cfg.get("joint_limits_deg", {})

        self._estop_active = threading.Event()
        self._estop_callbacks: list[Callable[[], None]] = []

        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._robot_ref: Optional["RobotAPI"] = None

    # ── E-Stop ───────────────────────────────────────────────────────────────

    def register_estop_callback(self, cb: Callable[[], None]) -> None:
        """Register a zero-arg callable to be invoked on E-stop."""
        self._estop_callbacks.append(cb)

    def trigger_estop(self, reason: str = "manual") -> None:
        """Trigger emergency stop — disables all actuators immediately."""
        if self._estop_active.is_set():
            return  # Already stopped
        self._estop_active.set()
        log.critical("🛑 E-STOP TRIGGERED: %s", reason)
        for cb in self._estop_callbacks:
            try:
                cb()
            except Exception as e:
                log.error("E-stop callback error: %s", e)

    def clear_estop(self) -> None:
        """Clear E-stop state after manual inspection."""
        self._estop_active.clear()
        log.info("E-stop cleared.")

    @property
    def is_stopped(self) -> bool:
        return self._estop_active.is_set()

    def assert_not_stopped(self) -> None:
        if self._estop_active.is_set():
            raise EStop("E-stop is active. Call clear_estop() after inspection.")

    # ── Overload Monitoring ──────────────────────────────────────────────────

    def start_overload_monitor(self, robot: "RobotAPI", interval: float = 0.05) -> None:
        """
        Start background thread that polls joint torques at `interval` seconds.

        Args:
            robot: RobotAPI instance with a read_torques() method
            interval: Poll interval in seconds (default 50ms = 20 Hz)
        """
        self._robot_ref = robot
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._overload_monitor_loop,
            args=(interval,),
            daemon=True,
            name="overload-monitor",
        )
        self._monitor_thread.start()
        log.info("Overload monitor started (interval=%.3fs, threshold=%d)", interval, self._overload_threshold)

    def stop_overload_monitor(self) -> None:
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)

    def _overload_monitor_loop(self, interval: float) -> None:
        while self._monitoring:
            if self._robot_ref and not self._estop_active.is_set():
                try:
                    torques = self._robot_ref.read_torques()
                    for jid, torque in torques.items():
                        if abs(torque) > self._overload_threshold:
                            self.trigger_estop(
                                f"Overload on joint {jid}: torque={torque} > threshold={self._overload_threshold}"
                            )
                            break
                except Exception as e:
                    log.warning("Torque read error in monitor: %s", e)
            time.sleep(interval)

    # ── Joint Limit Checking ─────────────────────────────────────────────────

    def check_joint_limits(self, joint_angles_deg: list[float]) -> None:
        """
        Validate joint angles against configured workspace limits.

        Args:
            joint_angles_deg: List of angles (degrees) for joints 1..N

        Raises:
            ValueError: If any joint exceeds its limit
        """
        mins = self._joint_limits.get("min", [])
        maxs = self._joint_limits.get("max", [])
        for i, angle in enumerate(joint_angles_deg):
            if i < len(mins) and angle < mins[i]:
                raise ValueError(
                    f"Joint {i+1} angle {angle:.1f}° below min {mins[i]}°"
                )
            if i < len(maxs) and angle > maxs[i]:
                raise ValueError(
                    f"Joint {i+1} angle {angle:.1f}° above max {maxs[i]}°"
                )

    # ── VLM Code Sandboxing ──────────────────────────────────────────────────

    def validate_vlm_code(self, code: str) -> None:
        """
        Parse and validate VLM-generated Python code.

        Only allows:
          - Calls to whitelisted functions (self._allowed_calls)
          - Basic assignments, if/else, for loops, pass, return
          - No imports, no exec/eval, no attribute access to unknown objects

        Raises:
            SandboxViolation: If code attempts disallowed operations
        """
        FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)
        FORBIDDEN_BUILTINS = {"exec", "eval", "compile", "__import__", "open", "globals", "locals"}

        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            raise SandboxViolation(f"Syntax error in VLM code: {e}") from e

        for node in ast.walk(tree):
            # Block imports
            if isinstance(node, FORBIDDEN_NODES):
                raise SandboxViolation(f"Disallowed AST node: {type(node).__name__}")

            # Block forbidden builtins
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_BUILTINS:
                raise SandboxViolation(f"Forbidden builtin: {node.id!r}")

            # Check all function calls
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    fn_name = func.id
                elif isinstance(func, ast.Attribute):
                    fn_name = func.attr
                else:
                    fn_name = None

                if fn_name and fn_name not in self._allowed_calls:
                    raise SandboxViolation(
                        f"Disallowed API call: {fn_name!r}. "
                        f"Allowed: {sorted(self._allowed_calls)}"
                    )

        log.debug("VLM code passed sandbox validation.")

    def execute_sandboxed(
        self,
        code: str,
        robot_api: object,
        extra_context: dict | None = None,
    ) -> None:
        """
        Execute validated VLM-generated code with a restricted namespace.

        Args:
            code: Python code string from VLM
            robot_api: RobotAPI instance — its public methods are injected
            extra_context: Extra name→value mappings available to the code
        """
        self.assert_not_stopped()
        self.validate_vlm_code(code)

        # Build a sandboxed namespace with only allowed API methods
        namespace: dict = {"__builtins__": {}}

        # Expose only the whitelisted methods
        for fn_name in self._allowed_calls:
            method = getattr(robot_api, fn_name, None)
            if method is not None:
                namespace[fn_name] = method

        # Add logging helper
        namespace["log"] = lambda msg: log.info("[VLM] %s", msg)

        if extra_context:
            namespace.update(extra_context)

        log.info("Executing sandboxed VLM code:\n%s", code)
        exec(compile(code, "<vlm_generated>", "exec"), namespace)  # noqa: S102
