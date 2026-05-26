---
name: semicon-cycle-monitor
description: Monitor DRAM/HBM semiconductor cycle exit signals and generate weekly portfolio action reports. Use when user asks about semiconductor cycle status, memory market timing, SK Hynix/Samsung/Micron position evaluation, or wants to run the weekly signal check. Triggers on phrases like "사이클 점검", "탈출 신호", "메모리 사이클", "반도체 모니터링", "weekly signal check".
---

# Semiconductor Cycle Monitor

A systematic framework for tracking the DRAM/HBM memory cycle and generating actionable portfolio decisions for Yeojun's positions (SK Hynix, Samsung Electronics).

## When to invoke

This skill runs in three modes:

1. **Weekly automated scan** (cron-triggered): Pull latest data, score signals, generate report, send Telegram alert if state changes.
2. **Ad-hoc analysis**: User asks a cycle-related question → load latest snapshot + framework, answer.
3. **Backtest/calibration**: User wants to verify framework against historical cycles (1995, 2001, 2008, 2018, 2022).

## Core framework

The cycle is evaluated through **5 exit signals**, each with explicit thresholds defined in `framework/exit_signals.md`. Each signal has 4 states:

- 🟢 **CLEAR** — far from trigger
- 🟡 **WATCH** — approaching trigger
- 🟠 **WARNING** — trigger zone entered
- 🔴 **EXIT** — fully triggered

**Decision rule**:

- 0–1 signals in WARNING/EXIT → HOLD
- 2 signals in WARNING+ → START TRIMMING (30%)
- 3+ signals in WARNING+ → AGGRESSIVE EXIT (60%+)

Position-specific rules and tax considerations live in `framework/portfolio_rules.md`.

## Required workflow for weekly scan

When running the weekly scan, follow this exact sequence:

1. **Load context** — `view CLAUDE.md` for portfolio state and last scan's signal levels
2. **Pull fresh data** — run `scripts/fetch_all.py` (orchestrates all fetchers)
3. **Score signals** — run `scripts/signal_check.py`, which outputs JSON to `data/snapshots/YYYY-MM-DD.json`
4. **Compare to last week** — diff against previous snapshot; flag any state transitions
5. **Generate report** — write `reports/weekly_YYYY-MM-DD.md` using the template
6. **Alert decision**:
   - State transition occurred (any signal moved between buckets) → send Telegram alert
   - 2+ signals in WARNING/EXIT for first time → send urgent alert
   - Otherwise → log silently, no alert

## Data sources

All sources defined in `data/sources.yaml`. Primary sources:

- **TrendForce** (DRAM/NAND contract & spot prices) — paid feed or scrape
- **Micron Investor Relations** (DIO, capex, Idaho fab timeline)
- **SK Hynix / Samsung IR** (quarterly earnings, HBM guidance)
- **Hyperscaler earnings** (MSFT, META, GOOGL, AMZN capex guidance)
- **DRAMeXchange** (spot price tracker)
- **WSTS** (industry-level revenue data)
- Backup: web search via Claude API when scrapers fail

## Output contract

Every weekly run MUST produce:

1. `data/snapshots/YYYY-MM-DD.json` — structured signal scores
2. `reports/weekly_YYYY-MM-DD.md` — human-readable summary
3. Telegram message (if alert criteria met) — concise, action-oriented

## Anti-patterns

- **Don't** invent signal scores from training-data memory. Always pull fresh.
- **Don't** add new signals without updating `framework/exit_signals.md` first.
- **Don't** include personal positions in any data file committed to git (CLAUDE.md has portfolio, but `.gitignore` it).
- **Don't** send Telegram alerts on every run — only on state transitions or 2+ WARNING signals.
- **Don't** confuse contract price (smoothed, lagged) with spot price (leading indicator). Track both separately.

## Historical calibration

The framework was calibrated against 5 prior cycles. See `framework/cycle_phases.md` for what each signal looked like at peaks vs troughs of 1995, 2001, 2008, 2018, and 2022 cycles. When uncertain about a current reading, compare to the analog cycle phase.
