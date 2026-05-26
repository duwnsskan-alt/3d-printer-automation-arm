#!/usr/bin/env python3
"""Orchestrate all data fetchers defined in data/sources.yaml.

Stub: enumerates sources and writes a placeholder raw-data file.
Replace each `fetch_<source>()` stub with a real fetcher.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("missing dep: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


SKILL_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = SKILL_ROOT / "data" / "sources.yaml"
RAW_DIR = SKILL_ROOT / "data" / "raw"


def load_sources() -> dict:
    with open(SOURCES_FILE) as f:
        return yaml.safe_load(f)


def fetch_stub(name: str, cfg: dict) -> dict:
    """Placeholder. Real fetchers go in scripts/fetchers/<name>.py."""
    return {
        "source": name,
        "status": "not_implemented",
        "cfg": cfg,
    }


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    sources = load_sources()["sources"]

    today = date.today().isoformat()
    out_path = RAW_DIR / f"{today}.json"

    payload = {name: fetch_stub(name, cfg) for name, cfg in sources.items()}
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"wrote {out_path} ({len(payload)} sources, all stubs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
