# Exit Signals — Thresholds & Scoring

Five signals score the cycle. Each maps to a state: CLEAR / WATCH / WARNING / EXIT.

> Thresholds below are scaffolds. Calibrate against `cycle_phases.md` before
> running the framework live. Do not trust any threshold marked `TBD`.

---

## Signal 1 — Spot/Contract Price Divergence

Spot prices lead contract prices by 1–2 quarters. A widening negative spread
(spot below contract) is the earliest tell of demand softening.

**Metric**: `spot_price / contract_price - 1` for DDR5 8Gb (4-week MA)

| State    | Threshold       |
| -------- | --------------- |
| CLEAR    | spread > 0%     |
| WATCH    | -5% to 0%       |
| WARNING  | -15% to -5%     |
| EXIT     | < -15%          |

Source: TrendForce weekly spot, monthly contract.

---

## Signal 2 — Supplier DIO (Days of Inventory Outstanding)

Inventory buildup at Micron/Hynix/Samsung is the textbook lagging-then-cliff
signal. Track Micron quarterly (cleanest reporter).

**Metric**: Micron DIO from latest 10-Q

| State    | Threshold          |
| -------- | ------------------ |
| CLEAR    | DIO < 120 days     |
| WATCH    | 120–140 days       |
| WARNING  | 140–160 days       |
| EXIT     | > 160 days         |

Source: Micron IR `https://investors.micron.com`

---

## Signal 3 — Hyperscaler Capex Guidance

HBM demand is downstream of MSFT/META/GOOGL/AMZN AI capex. Watch for YoY
deceleration in forward guidance, not trailing spend.

**Metric**: Aggregate next-FY capex guidance YoY % change (weighted by HBM share)

| State    | Threshold       |
| -------- | --------------- |
| CLEAR    | > +20% YoY      |
| WATCH    | +5% to +20%     |
| WARNING  | -5% to +5%      |
| EXIT     | < -5%           |

Source: Quarterly earnings calls.

---

## Signal 4 — Industry Capex / Capacity Additions

Supply-side: when laggards (CXMT, Nanya) announce aggressive node migrations
or new fabs, the next glut is being built.

**Metric**: TBD — needs definition (wafer-start additions vs. demand growth)

| State    | Threshold |
| -------- | --------- |
| CLEAR    | TBD       |
| WATCH    | TBD       |
| WARNING  | TBD       |
| EXIT     | TBD       |

Source: WSTS, SEMI, company capex disclosures.

---

## Signal 5 — Pricing Momentum

Month-over-month contract price change. Direction matters more than level.

**Metric**: 3-month rolling MoM contract price change (DDR5 8Gb)

| State    | Threshold        |
| -------- | ---------------- |
| CLEAR    | > +2% MoM        |
| WATCH    | 0% to +2%        |
| WARNING  | -3% to 0%        |
| EXIT     | < -3% MoM        |

Source: TrendForce monthly contract.

---

## Scoring rule

Per `SKILL.md`:

- 0–1 signals in WARNING+ → HOLD
- 2 signals in WARNING+ → TRIM 30%
- 3+ signals in WARNING+ → EXIT 60%+
