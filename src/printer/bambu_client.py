"""
src/printer/bambu_client.py
---------------------------
BambuLab P2S LAN-mode client.

Connects via:
  • MQTT over TLS (port 8883) for live telemetry and commands
  • FTPS (port 990) for job file upload

Usage:
    client = BambuClient(cfg["printer"])
    client.connect()
    client.on_print_complete = my_callback
    # Upload and start a job
    client.upload_and_print("path/to/model.3mf")
"""

from __future__ import annotations

import ftplib
import json
import logging
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


# ─── Data Structures ────────────────────────────────────────────────────────

@dataclass
class PrinterState:
    """Snapshot of the last received printer telemetry."""
    stage: str = "UNKNOWN"        # MC_PRINT_STAGE
    progress: int = 0             # 0-100 %
    layer: int = 0
    total_layers: int = 0
    nozzle_temp: float = 0.0
    bed_temp: float = 0.0
    fan_speed: int = 0
    error_code: int = 0
    gcode_state: str = "IDLE"     # IDLE | RUNNING | PAUSE | FINISH | FAILED
    raw: dict = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.gcode_state in ("FINISH",)

    @property
    def is_error(self) -> bool:
        return self.gcode_state in ("FAILED",) or self.error_code != 0


# ─── Main Client ────────────────────────────────────────────────────────────

class BambuClient:
    """
    Manages MQTT connection to a BambuLab P2S and FTPS uploads.

    Args:
        cfg: The "printer" section of config.yaml
    """

    PUSH_ALL_CMD = {
        "pushing": {"sequence_id": "0", "command": "pushall"}
    }

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.serial: str = cfg["serial"]
        self.host: str = cfg["host"]
        self.access_code: str = cfg.get("access_code") or self._require_env("BAMBU_ACCESS_CODE")
        self.mqtt_port: int = cfg.get("mqtt_port", 8883)
        self.ftps_port: int = cfg.get("ftps_port", 990)
        self.ca_cert: Optional[str] = cfg.get("ca_cert")

        self._topic_report = cfg["topic_report"].format(serial=self.serial)
        self._topic_request = cfg["topic_request"].format(serial=self.serial)
        self._completion_states: set[str] = set(cfg.get("completion_states", ["FINISH"]))

        self.state = PrinterState()
        self._state_lock = threading.Lock()

        # Callbacks — assign externally
        self.on_print_complete: Optional[Callable[[PrinterState], None]] = None
        self.on_print_failed: Optional[Callable[[PrinterState], None]] = None
        self.on_state_update: Optional[Callable[[PrinterState], None]] = None

        self._mqtt = mqtt.Client(client_id=f"arm-controller-{self.serial}")
        self._mqtt.username_pw_set("bblp", self.access_code)
        self._configure_tls()
        self._mqtt.on_connect = self._on_mqtt_connect
        self._mqtt.on_message = self._on_mqtt_message
        self._mqtt.on_disconnect = self._on_mqtt_disconnect

        self._connected = threading.Event()
        self._stop = threading.Event()
        self._last_complete_notified = False

    # ── Public API ───────────────────────────────────────────────────────────

    def connect(self, timeout: float = 15.0) -> None:
        """Connect to printer MQTT broker and block until connected."""
        log.info("Connecting to printer MQTT %s:%d", self.host, self.mqtt_port)
        self._mqtt.connect_async(self.host, self.mqtt_port, keepalive=60)
        self._mqtt.loop_start()
        if not self._connected.wait(timeout=timeout):
            raise TimeoutError(f"MQTT connect timeout after {timeout}s")
        log.info("MQTT connected. Requesting full state push.")
        self._publish(self.PUSH_ALL_CMD)

    def disconnect(self) -> None:
        """Gracefully disconnect."""
        self._stop.set()
        self._mqtt.loop_stop()
        self._mqtt.disconnect()
        log.info("MQTT disconnected.")

    def get_state(self) -> PrinterState:
        with self._state_lock:
            return self.state

    def send_gcode(self, gcode: str) -> None:
        """Send a raw G-code command to the printer."""
        payload = {
            "print": {
                "sequence_id": "1",
                "command": "gcode_line",
                "param": gcode,
            }
        }
        self._publish(payload)
        log.debug("Sent G-code: %s", gcode)

    def upload_and_print(self, local_path: str | Path, remote_name: str | None = None) -> None:
        """
        Upload a .3mf file via FTPS and trigger a print.

        Args:
            local_path: Path to the local .3mf file
            remote_name: Filename on the printer; defaults to local basename
        """
        local_path = Path(local_path)
        remote_name = remote_name or local_path.name
        log.info("Uploading %s → printer:/%s", local_path, remote_name)
        self._ftps_upload(local_path, remote_name)

        # Trigger print via MQTT
        payload = {
            "print": {
                "sequence_id": "2",
                "command": "project_file",
                "param": f"Metadata/plate_1.gcode",
                "url": f"ftp:///sdcard/{remote_name}",
                "bed_leveling": True,
                "flow_cali": False,
                "vibration_cali": True,
                "layer_inspect": False,
                "use_ams": False,
            }
        }
        self._publish(payload)
        log.info("Print job submitted: %s", remote_name)
        self._last_complete_notified = False  # Reset so we catch next completion

    # ── MQTT Internals ───────────────────────────────────────────────────────

    def _configure_tls(self) -> None:
        ctx = ssl.create_default_context()
        if self.ca_cert and Path(self.ca_cert).exists():
            ctx.load_verify_locations(self.ca_cert)
        else:
            # BambuLab uses a self-signed cert in LAN mode;
            # disable verification if no cert provided (use with caution on LAN).
            log.warning(
                "No CA cert configured — disabling TLS verification. "
                "Provide config.printer.ca_cert for production."
            )
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self._mqtt.tls_set_context(ctx)

    def _on_mqtt_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            log.error("MQTT connect failed: rc=%d", rc)
            return
        log.info("MQTT connected (rc=0). Subscribing to report topic.")
        client.subscribe(self._topic_report)
        self._connected.set()

    def _on_mqtt_disconnect(self, client, userdata, rc) -> None:
        self._connected.clear()
        if not self._stop.is_set():
            log.warning("MQTT disconnected (rc=%d). Will auto-reconnect.", rc)

    def _on_mqtt_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.warning("Malformed MQTT message: %s", e)
            return

        self._parse_state(payload)

    def _parse_state(self, payload: dict) -> None:
        """Parse the BambuLab report JSON into our PrinterState."""
        print_info = payload.get("print", {})
        if not print_info:
            return

        with self._state_lock:
            s = self.state
            s.raw = print_info
            s.gcode_state = print_info.get("gcode_state", s.gcode_state)
            s.stage = print_info.get("mc_print_stage", s.stage)
            s.progress = int(print_info.get("mc_percent", s.progress))
            s.layer = int(print_info.get("layer_num", s.layer))
            s.total_layers = int(print_info.get("total_layer_num", s.total_layers))
            s.error_code = int(print_info.get("mc_print_error_code", s.error_code))

            # Temperatures may be nested
            temps = print_info.get("nozzle_temper", None)
            if temps is not None:
                s.nozzle_temp = float(temps)
            bed_t = print_info.get("bed_temper", None)
            if bed_t is not None:
                s.bed_temp = float(bed_t)

            is_done = s.gcode_state in self._completion_states
            is_err = s.is_error

        if self.on_state_update:
            self.on_state_update(self.state)

        # Fire completion callback exactly once per print cycle
        if is_done and not self._last_complete_notified:
            self._last_complete_notified = True
            log.info("Print complete! State=%s, Progress=%d%%", self.state.gcode_state, self.state.progress)
            if self.on_print_complete:
                threading.Thread(
                    target=self.on_print_complete,
                    args=(self.state,),
                    daemon=True,
                    name="on_print_complete",
                ).start()
        elif is_err:
            log.error("Printer error! Code=%d State=%s", self.state.error_code, self.state.gcode_state)
            if self.on_print_failed:
                threading.Thread(
                    target=self.on_print_failed,
                    args=(self.state,),
                    daemon=True,
                    name="on_print_failed",
                ).start()

    def _publish(self, payload: dict) -> None:
        self._mqtt.publish(
            self._topic_request,
            json.dumps(payload),
            qos=1,
        )

    # ── FTPS ─────────────────────────────────────────────────────────────────

    def _ftps_upload(self, local_path: Path, remote_name: str) -> None:
        """Upload file to printer's SD card via FTPS."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # BambuLab self-signed

        with ftplib.FTP_TLS(context=ctx) as ftps:
            ftps.connect(self.host, self.ftps_port)
            ftps.login("bblp", self.access_code)
            ftps.prot_p()  # Switch to data connection protection

            with open(local_path, "rb") as f:
                ftps.storbinary(f"STOR /sdcard/{remote_name}", f)

        log.info("FTPS upload complete: %s", remote_name)

    @staticmethod
    def _require_env(name: str) -> str:
        import os
        val = os.environ.get(name)
        if not val:
            raise EnvironmentError(f"Required environment variable {name!r} is not set.")
        return val
