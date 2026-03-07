"""
src/vision/vlm_orchestrator.py
--------------------------------
VLM orchestrator implementing Code-as-Policy.

Workflow:
1. Receive camera frames + printer state
2. Build a multi-modal prompt describing the situation
3. Call Claude / GPT-4o / Qwen-VL to generate Python robot action code
4. Validate code with SafetyLayer
5. Execute code in sandboxed namespace with RobotAPI

The VLM acts as a high-level planner; it generates SHORT Python snippets
using only the whitelisted robot API calls.
"""

from __future__ import annotations

import base64
import logging
import os
import textwrap
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.robot.robot_api import RobotAPI
    from src.safety.safety_layer import SafetyLayer
    from src.vision.camera_manager import CameraFrame
    from src.printer.bambu_client import PrinterState

log = logging.getLogger(__name__)

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""
You are a robotics controller for a 6-DoF SO-100 robot arm that automates a BambuLab P2S 3D printer.

You receive:
  - Camera images (front view + wrist view)
  - Current printer state (JSON)
  - Current task description

You must respond with ONLY a Python code block that calls the robot API.
Do NOT include explanations outside the code block.
Do NOT import anything.
Only use these API functions:
  open_door()              → opens printer front door
  close_door()             → closes printer front door
  pick_object(x_offset=0.0, y_offset=0.0)  → picks printed object from build plate
  place_object(pose_name="place_hover")    → places object at named location
  move_to_pose(pose_name)  → moves arm to a named pose
  gripper_open()           → opens gripper
  gripper_close(partial=False)  → closes gripper
  wait(seconds)            → waits N seconds
  log(message)             → logs a message

Example response:
```python
log("Opening door to retrieve print")
open_door()
wait(0.5)
pick_object(x_offset=0.0, y_offset=0.0)
place_object()
close_door()
```

If you cannot determine the correct action, call log("UNCERTAIN: <reason>") and do nothing else.
""").strip()


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class VLMOrchestrator:
    """
    High-level VLM-based planner.

    Args:
        cfg: Full config dict
        safety: SafetyLayer for code validation
        robot: RobotAPI for code execution
    """

    def __init__(self, cfg: dict, safety: "SafetyLayer", robot: "RobotAPI") -> None:
        self.cfg = cfg
        self.vlm_cfg = cfg["vlm"]
        self.safety = safety
        self.robot = robot

        self._fallback_order: list[str] = self.vlm_cfg.get("fallback_order", ["claude"])
        self._max_retries: int = self.vlm_cfg.get("max_retries", 3)
        self._temperature: float = self.vlm_cfg.get("temperature", 0.0)
        self._max_tokens: int = self.vlm_cfg.get("max_tokens", 1024)

        # Lazy-loaded model clients
        self._qwen_pipeline = None

    # ── Public API ────────────────────────────────────────────────────────────

    def plan_and_execute(
        self,
        task: str,
        frames: dict[str, "CameraFrame"],
        printer_state: "PrinterState",
    ) -> bool:
        """
        Generate and execute a VLM action plan.

        Args:
            task: Natural language task description (e.g. "pick up finished print")
            frames: Dict of label→CameraFrame from CameraManager
            printer_state: Current printer state

        Returns:
            True if execution succeeded, False otherwise
        """
        import json

        state_json = {
            "gcode_state": printer_state.gcode_state,
            "progress": printer_state.progress,
            "layer": printer_state.layer,
            "total_layers": printer_state.total_layers,
            "nozzle_temp": printer_state.nozzle_temp,
            "bed_temp": printer_state.bed_temp,
        }

        code = self._generate_with_fallback(task, frames, state_json)
        if not code:
            log.error("VLM returned no code after all fallbacks.")
            return False

        try:
            self.safety.execute_sandboxed(code, self.robot, extra_context={
                "printer_state": state_json,
            })
            return True
        except Exception as e:
            log.error("VLM code execution failed: %s", e)
            return False

    # ── VLM Dispatch ─────────────────────────────────────────────────────────

    def _generate_with_fallback(
        self,
        task: str,
        frames: dict,
        state_json: dict,
    ) -> Optional[str]:
        """Try each provider in fallback order until one succeeds."""
        for provider in self._fallback_order:
            for attempt in range(self._max_retries):
                try:
                    code = self._call_provider(provider, task, frames, state_json)
                    if code:
                        log.info("VLM code generated by %s (attempt %d)", provider, attempt + 1)
                        return code
                except Exception as e:
                    log.warning("VLM provider %s attempt %d failed: %s", provider, attempt + 1, e)
                    time.sleep(1.5 ** attempt)  # Exponential backoff
        return None

    def _call_provider(
        self,
        provider: str,
        task: str,
        frames: dict,
        state_json: dict,
    ) -> Optional[str]:
        """Dispatch to the appropriate VLM provider."""
        if provider == "claude":
            return self._call_claude(task, frames, state_json)
        elif provider == "openai":
            return self._call_openai(task, frames, state_json)
        elif provider == "qwen_local":
            return self._call_qwen_local(task, frames, state_json)
        else:
            raise ValueError(f"Unknown VLM provider: {provider!r}")

    # ── Claude ────────────────────────────────────────────────────────────────

    def _call_claude(self, task: str, frames: dict, state_json: dict) -> Optional[str]:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        content = self._build_content_blocks(task, frames, state_json, api="claude")

        response = client.messages.create(
            model=self.vlm_cfg.get("model_claude", "claude-opus-4-5"),
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        return self._extract_code(response.content[0].text)

    # ── OpenAI ────────────────────────────────────────────────────────────────

    def _call_openai(self, task: str, frames: dict, state_json: dict) -> Optional[str]:
        import openai

        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        content = self._build_content_blocks(task, frames, state_json, api="openai")

        response = client.chat.completions.create(
            model=self.vlm_cfg.get("model_openai", "gpt-4o"),
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        )
        return self._extract_code(response.choices[0].message.content)

    # ── Qwen Local ────────────────────────────────────────────────────────────

    def _call_qwen_local(self, task: str, frames: dict, state_json: dict) -> Optional[str]:
        """
        Run Qwen2.5-VL locally via HuggingFace transformers.
        Lazy-loads the pipeline on first call.
        """
        import json
        from transformers import AutoProcessor, AutoModelForVision2Seq
        import torch
        from PIL import Image

        if self._qwen_pipeline is None:
            model_id = self.vlm_cfg.get("model_qwen_local", "Qwen/Qwen2.5-VL-7B-Instruct")
            device = self.vlm_cfg.get("qwen_device", "cuda")
            log.info("Loading Qwen2.5-VL model: %s on %s", model_id, device)
            self._qwen_pipeline = {
                "processor": AutoProcessor.from_pretrained(model_id),
                "model": AutoModelForVision2Seq.from_pretrained(
                    model_id,
                    torch_dtype=torch.float16,
                    device_map=device,
                ),
            }
            log.info("Qwen2.5-VL loaded.")

        processor = self._qwen_pipeline["processor"]
        model = self._qwen_pipeline["model"]

        pil_images = [
            frame.to_pil() for frame in frames.values() if frame is not None
        ]

        user_msg = (
            f"Task: {task}\n"
            f"Printer state: {json.dumps(state_json)}\n"
            f"Generate robot API code to accomplish this task."
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    *[{"type": "image", "image": img} for img in pil_images],
                    {"type": "text", "text": user_msg},
                ],
            },
        ]

        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(
            text=[text],
            images=pil_images if pil_images else None,
            return_tensors="pt",
        ).to(model.device)

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=self._max_tokens,
                do_sample=False,
            )
        output_text = processor.batch_decode(
            output_ids[:, inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )[0]

        return self._extract_code(output_text)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_content_blocks(
        self, task: str, frames: dict, state_json: dict, api: str
    ) -> list | str:
        """Build multi-modal content blocks for the VLM API."""
        import json

        if api == "claude":
            content = []
            for label, frame in frames.items():
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": frame.to_jpeg_b64(),
                    },
                })
                content.append({"type": "text", "text": f"[Camera: {label}]"})
            content.append({
                "type": "text",
                "text": f"Task: {task}\nPrinter state: {json.dumps(state_json, indent=2)}",
            })
            return content

        elif api == "openai":
            content = []
            for label, frame in frames.items():
                b64 = frame.to_jpeg_b64()
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
                content.append({"type": "text", "text": f"[Camera: {label}]"})
            content.append({
                "type": "text",
                "text": f"Task: {task}\nPrinter state: {json.dumps(state_json, indent=2)}",
            })
            return content

        return f"Task: {task}\nPrinter state: {json.dumps(state_json)}"

    @staticmethod
    def _extract_code(text: str) -> Optional[str]:
        """
        Extract Python code block from VLM response.
        Accepts ```python ... ``` or plain code.
        """
        if not text:
            return None

        # Try to extract from ```python ... ``` block
        import re
        match = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try plain ``` block
        match = re.search(r"```\s*(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # If no code block markers, return the full response (assume it's all code)
        return text.strip() or None
