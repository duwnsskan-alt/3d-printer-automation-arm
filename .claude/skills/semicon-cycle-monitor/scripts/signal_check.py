#!/usr/bin/env python3
"""Score the 5 exit signals from latest raw data, emit snapshot JSON.

Stub: emits all signals as CLEAR with null metric values until fetchers
and scoring logic are implemented.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = SKILL_ROOT / "data" / "raw"
SNAP_DIR = SKILL_ROOT / "data" / "snapshots"

STATES = ("CLEAR", "WATCH", "WARNING", "EXIT")

SIGNAL_DEFS = {
    "signal_1_spot_contract_divergence": "spot/contract spread (4w MA)",
    "signal_2_supplier_dio":             "Micron DIO (days)",
    "signal_3_hyperscaler_capex":        "aggregate next-FY capex YoY %",
    "signal_4_capacity_additions":       "TBD",
    "signal_5_pricing_momentum":         "3mo rolling MoM contract %",
}


def score_signal_1(_raw) -> tuple[str, float | None]:
    return "CLEAR", None  # TODO


def score_signal_2(_raw) -> tuple[str, float | None]:
    return "CLEAR", None  # TODO


def score_signal_3(_raw) -> tuple[str, float | None]:
    return "CLEAR", None  # TODO


def score_signal_4(_raw) -> tuple[str, float | None]:
    return "CLEAR", None  # TODO


def score_signal_5(_raw) -> tuple[str, float | None]:
    return "CLEAR", None  # TODO


SCORERS = {
    "signal_1_spot_contract_divergence": score_signal_1,
    "signal_2_supplier_dio":             score_signal_2,
    "signal_3_hyperscaler_capex":        score_signal_3,
    "signal_4_capacity_additions":       score_signal_4,
    "signal_5_pricing_momentum":         score_signal_5,
}


def decision(states: list[str]) -> str:
    warn_or_worse = sum(1 for s in states if s in ("WARNING", "EXIT"))
    if warn_or_worse >= 3:
        return "EXIT 60%+"
    if warn_or_worse == 2:
        return "TRIM 30%"
    return "HOLD"


def main() -> int:
    today = date.today().isoformat()
    raw_path = RAW_DIR / f"{today}.json"
    raw = json.loads(raw_path.read_text()) if raw_path.exists() else {}

    signals = {}
    for name, scorer in SCORERS.items():
        state, metric = scorer(raw)
        signals[name] = {
            "description": SIGNAL_DEFS[name],
            "state":       state,
            "metric":      metric,
        }

    snapshot = {
        "date":     today,
        "signals":  signals,
        "decision": decision([s["state"] for s in signals.values()]),
    }

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SNAP_DIR / f"{today}.json"
    out_path.write_text(json.dumps(snapshot, indent=2))

    print(f"wrote {out_path}")
    print(f"decision: {snapshot['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
