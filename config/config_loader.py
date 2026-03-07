"""
config/config_loader.py
-----------------------
Loads config.yaml and merges environment variable overrides.

Environment variables follow the pattern:
  ARM_<SECTION>__<KEY>=value
e.g. ARM_PRINTER__ACCESS_CODE=12345678

Sensitive fields (access_code, api_keys) are NEVER logged.
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Any

_SENSITIVE_KEYS = {"access_code", "api_key", "password", "secret"}
_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (modifies base in place)."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _apply_env_overrides(cfg: dict) -> None:
    """
    Walk environment variables prefixed with ARM_ and apply them.
    ARM_PRINTER__HOST=x  →  cfg["printer"]["host"] = "x"
    ARM_VLM__MAX_TOKENS=512  →  cfg["vlm"]["max_tokens"] = 512
    """
    prefix = "ARM_"
    for key, val in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].lower().split("__")
        node = cfg
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        leaf = parts[-1]
        # Type coercion: try int, float, bool, then string
        if val.lower() in ("true", "yes"):
            val = True
        elif val.lower() in ("false", "no"):
            val = False
        else:
            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    pass
        node[leaf] = val


def load_config(path: Path | None = None) -> dict[str, Any]:
    """
    Load and return the merged configuration dict.

    Args:
        path: Optional override for the YAML path.

    Returns:
        Fully resolved config dict.
    """
    cfg_path = path or _CONFIG_PATH
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    # Allow a .env-style file to set ARM_ vars before applying overrides
    dotenv_path = cfg_path.parent / ".env"
    if dotenv_path.exists():
        _load_dotenv(dotenv_path)

    _apply_env_overrides(cfg)
    return cfg


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no third-party dep required)."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def mask_sensitive(cfg: dict, _depth: int = 0) -> dict:
    """Return a copy of cfg with sensitive values masked (for logging)."""
    if _depth > 10:
        return cfg
    out = {}
    for k, v in cfg.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = mask_sensitive(v, _depth + 1)
        else:
            out[k] = v
    return out
