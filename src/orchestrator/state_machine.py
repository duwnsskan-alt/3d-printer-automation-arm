"""
src/orchestrator/state_machine.py
----------------------------------
Main automation state machine.

States:
  IDLE          → Waiting for print completion signal
  OPEN_DOOR     → Robot opens printer front door
  PICK          → Robot picks up finished print
  PLACE         → Robot places print at staging area
  CLOSE_DOOR    → Robot closes printer front door
  NEXT_PRINT    → Upload and start next job
  ERROR         → Fault state; requires manual reset
  ESTOP         → Emergency stop active

Transitions are driven by:
  - BambuClient MQTT callbacks (print_complete → IDLE→OPEN_DOOR)
  - VLM/VLA execution success/failure
  - Safety layer events

Each state has a configurable timeout (config.state_machine.timeouts).
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto
from pathlib import Path
from queue import Queue, Empty
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.printer.bambu_client import BambuClient, PrinterState
    from src.robot.robot_api import RobotAPI
    from src.vision.vlm_orchestrator import VLMOrchestrator
    from src.vision.camera_manager import CameraManager
    from src.safety.safety_layer import SafetyLayer

log = logging.getLogger(__name__)


# ─── State Enum ──────────────────────────────────────────────────────────────

class State(Enum):
    IDLE = auto()
    OPEN_DOOR = auto()
    PICK = auto()
    PLACE = auto()
    CLOSE_DOOR = auto()
    NEXT_PRINT = auto()
    ERROR = auto()
    ESTOP = auto()


# ─── Events ──────────────────────────────────────────────────────────────────

class Event(Enum):
    PRINT_COMPLETE = auto()
    PRINT_FAILED = auto()
    ACTION_SUCCESS = auto()
    ACTION_FAILED = auto()
    ESTOP_TRIGGERED = auto()
    ESTOP_CLEARED = auto()
    RESET = auto()
    SHUTDOWN = auto()


# ─── State Machine ────────────────────────────────────────────────────────────

class AutomationStateMachine:
    """
    Main orchestrator state machine for the 3D printer automation system.

    Args:
        cfg: Full config dict
        printer: BambuClient instance
        robot: RobotAPI instance
        vlm: VLMOrchestrator instance
        cameras: CameraManager instance
        safety: SafetyLayer instance
        next_job_path: Optional path to the next .3mf file to print
    """

    def __init__(
        self,
        cfg: dict,
        printer: "BambuClient",
        robot: "RobotAPI",
        vlm: "VLMOrchestrator",
        cameras: "CameraManager",
        safety: "SafetyLayer",
        next_job_path: Optional[Path] = None,
    ) -> None:
        self.cfg = cfg
        self.printer = printer
        self.robot = robot
        self.vlm = vlm
        self.cameras = cameras
        self.safety = safety
        self.next_job_path = next_job_path

        self.sm_cfg = cfg.get("state_machine", {})
        self.timeouts: dict[str, float] = self.sm_cfg.get("timeouts", {
            "open_door": 30,
            "pick": 45,
            "place": 45,
            "close_door": 30,
            "next_print": 60,
        })

        self._state = State.IDLE
        self._state_lock = threading.Lock()
        self._event_queue: Queue[tuple[Event, object]] = Queue()
        self._running = False
        self._main_thread: Optional[threading.Thread] = None

        # Printer state snapshot at time of print completion
        self._completed_print_state: Optional["PrinterState"] = None

        # State change listeners
        self._on_state_change: list[Callable[[State, State], None]] = []

        # Wire up printer callbacks
        self.printer.on_print_complete = self._handle_print_complete
        self.printer.on_print_failed = self._handle_print_failed

        # Wire up safety E-stop
        self.safety.register_estop_callback(self._handle_estop)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the state machine event loop in a background thread."""
        self._running = True
        self._main_thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="state-machine",
        )
        self._main_thread.start()
        log.info("State machine started in state: %s", self._state.name)

    def stop(self) -> None:
        """Signal the state machine to shut down."""
        self._event_queue.put((Event.SHUTDOWN, None))
        if self._main_thread:
            self._main_thread.join(timeout=10.0)
        log.info("State machine stopped.")

    def reset_error(self) -> None:
        """Manually reset from ERROR state back to IDLE."""
        self._event_queue.put((Event.RESET, None))

    def clear_estop(self) -> None:
        """Clear E-stop and return to IDLE."""
        self.safety.clear_estop()
        self._event_queue.put((Event.ESTOP_CLEARED, None))

    def get_state(self) -> State:
        with self._state_lock:
            return self._state

    def on_state_change(self, cb: Callable[[State, State], None]) -> None:
        """Register a callback invoked when state changes: cb(old_state, new_state)."""
        self._on_state_change.append(cb)

    # ── Event Loop ────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main event processing loop."""
        while self._running:
            try:
                event, data = self._event_queue.get(timeout=0.5)
            except Empty:
                continue

            if event == Event.SHUTDOWN:
                log.info("Shutdown event received.")
                self._running = False
                break

            self._process_event(event, data)

    def _process_event(self, event: Event, data: object) -> None:
        """State transition logic."""
        current = self.get_state()
        log.info("Event %s in state %s", event.name, current.name)

        # ── Global E-stop override ─────────────────────────────────────────
        if event == Event.ESTOP_TRIGGERED:
            self._transition_to(State.ESTOP)
            return

        if event == Event.ESTOP_CLEARED and current == State.ESTOP:
            self._transition_to(State.IDLE)
            return

        if event == Event.RESET and current == State.ERROR:
            self._transition_to(State.IDLE)
            return

        # ── Normal transitions ──────────────────────────────────────────────
        if current == State.IDLE:
            if event == Event.PRINT_COMPLETE:
                self._completed_print_state = data
                self._transition_to(State.OPEN_DOOR)
                self._dispatch_action(State.OPEN_DOOR)

        elif current == State.OPEN_DOOR:
            if event == Event.ACTION_SUCCESS:
                self._transition_to(State.PICK)
                self._dispatch_action(State.PICK)
            elif event == Event.ACTION_FAILED:
                self._transition_to(State.ERROR)

        elif current == State.PICK:
            if event == Event.ACTION_SUCCESS:
                self._transition_to(State.PLACE)
                self._dispatch_action(State.PLACE)
            elif event == Event.ACTION_FAILED:
                self._transition_to(State.ERROR)

        elif current == State.PLACE:
            if event == Event.ACTION_SUCCESS:
                self._transition_to(State.CLOSE_DOOR)
                self._dispatch_action(State.CLOSE_DOOR)
            elif event == Event.ACTION_FAILED:
                self._transition_to(State.ERROR)

        elif current == State.CLOSE_DOOR:
            if event == Event.ACTION_SUCCESS:
                if self.next_job_path:
                    self._transition_to(State.NEXT_PRINT)
                    self._dispatch_action(State.NEXT_PRINT)
                else:
                    log.info("No next job queued. Returning to IDLE.")
                    self._transition_to(State.IDLE)
            elif event == Event.ACTION_FAILED:
                self._transition_to(State.ERROR)

        elif current == State.NEXT_PRINT:
            if event == Event.ACTION_SUCCESS:
                log.info("Next print job started. Returning to IDLE.")
                self._transition_to(State.IDLE)
            elif event == Event.ACTION_FAILED:
                self._transition_to(State.ERROR)

        elif current in (State.ERROR, State.ESTOP):
            log.warning("Event %s ignored in state %s", event.name, current.name)

    def _transition_to(self, new_state: State) -> None:
        """Perform state transition and notify listeners."""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
        log.info("State: %s → %s", old_state.name, new_state.name)
        for cb in self._on_state_change:
            try:
                cb(old_state, new_state)
            except Exception as e:
                log.error("State change callback error: %s", e)

    # ── Action Dispatch ───────────────────────────────────────────────────────

    def _dispatch_action(self, state: State) -> None:
        """
        Run the action for the given state in a background thread.
        Puts ACTION_SUCCESS or ACTION_FAILED into the event queue when done.
        """
        threading.Thread(
            target=self._run_action,
            args=(state,),
            daemon=True,
            name=f"action-{state.name}",
        ).start()

    def _run_action(self, state: State) -> None:
        """Execute the action corresponding to a state."""
        timeout_map = {
            State.OPEN_DOOR: self.timeouts.get("open_door", 30),
            State.PICK: self.timeouts.get("pick", 45),
            State.PLACE: self.timeouts.get("place", 45),
            State.CLOSE_DOOR: self.timeouts.get("close_door", 30),
            State.NEXT_PRINT: self.timeouts.get("next_print", 60),
        }

        timeout = timeout_map.get(state, 60)
        deadline = time.time() + timeout

        try:
            if state == State.OPEN_DOOR:
                success = self._action_open_door()
            elif state == State.PICK:
                success = self._action_pick()
            elif state == State.PLACE:
                success = self._action_place()
            elif state == State.CLOSE_DOOR:
                success = self._action_close_door()
            elif state == State.NEXT_PRINT:
                success = self._action_next_print()
            else:
                log.warning("No action defined for state %s", state.name)
                success = True

            if time.time() > deadline:
                log.error("Action %s timed out after %.0fs", state.name, timeout)
                success = False

        except Exception as e:
            log.error("Action %s raised exception: %s", state.name, e, exc_info=True)
            success = False

        event = Event.ACTION_SUCCESS if success else Event.ACTION_FAILED
        self._event_queue.put((event, None))

    # ── Individual Actions ────────────────────────────────────────────────────

    def _action_open_door(self) -> bool:
        """Use VLM to plan and execute door-open sequence."""
        frames = self.cameras.capture_all()
        task = "Open the BambuLab P2S front door. The door handle is on the right side."
        return self.vlm.plan_and_execute(task, frames, self._completed_print_state)

    def _action_pick(self) -> bool:
        """Use VLM to pick the printed object."""
        frames = self.cameras.capture_all()
        task = (
            "Pick up the finished 3D print from the build plate. "
            "The object is centered on the magnetic build plate inside the open printer."
        )
        return self.vlm.plan_and_execute(task, frames, self._completed_print_state)

    def _action_place(self) -> bool:
        """Place the print at the output staging area."""
        frames = self.cameras.capture_all()
        task = "Place the 3D printed object at the staging tray to the right of the printer."
        return self.vlm.plan_and_execute(task, frames, self._completed_print_state)

    def _action_close_door(self) -> bool:
        """Close the printer door."""
        frames = self.cameras.capture_all()
        task = "Close the BambuLab P2S front door firmly until it latches."
        return self.vlm.plan_and_execute(task, frames, self._completed_print_state)

    def _action_next_print(self) -> bool:
        """Upload and start the next print job."""
        if not self.next_job_path or not self.next_job_path.exists():
            log.warning("No valid next job path configured.")
            return False
        try:
            self.printer.upload_and_print(self.next_job_path)
            log.info("Next print job queued: %s", self.next_job_path)
            return True
        except Exception as e:
            log.error("Failed to start next print: %s", e)
            return False

    # ── Printer Callbacks ─────────────────────────────────────────────────────

    def _handle_print_complete(self, state: "PrinterState") -> None:
        """Called by BambuClient MQTT thread when print finishes."""
        log.info("Print complete callback triggered!")
        self._event_queue.put((Event.PRINT_COMPLETE, state))

    def _handle_print_failed(self, state: "PrinterState") -> None:
        """Called by BambuClient MQTT thread when print fails."""
        log.error("Print FAILED callback triggered.")
        self._event_queue.put((Event.PRINT_FAILED, state))

    # ── Safety Callbacks ──────────────────────────────────────────────────────

    def _handle_estop(self) -> None:
        """Called by SafetyLayer on E-stop trigger."""
        self._event_queue.put((Event.ESTOP_TRIGGERED, None))
