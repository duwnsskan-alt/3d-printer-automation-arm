# Portfolio Rules

Position-specific execution rules. Read together with `exit_signals.md`.

## Positions tracked

- **SK Hynix (000660.KS)** — primary HBM beneficiary, highest cycle beta
- **Samsung Electronics (005930.KS)** — diversified, HBM laggard, lower beta
- *(Micron — watchlist only, not held)*

## Trim sequencing

When the framework says "TRIM 30%", execute in this order:

1. SK Hynix first (higher beta → trim faster on warning)
2. Samsung Electronics second (only after 3+ signals in WARNING+)

When "EXIT 60%+":
- SK Hynix → cut to 30% of original
- Samsung Electronics → cut to 50% of original
- Hold residual until 4+ signals or fundamental thesis break

## Tax considerations (KR resident)

- KR domestic equities: no capital gains tax under threshold (대주주 요건)
- Above threshold or foreign account: factor in 22% on gains, 15.4% on dividends
- Prefer trimming in tax year where other losses offset gains
- Do NOT trim purely for tax reasons if framework says HOLD

## Override conditions

The framework can be overridden in these cases:

1. **Black swan / thesis break** — accounting fraud, sanctions, war affecting fab → exit immediately, ignore signal count
2. **HBM3E/HBM4 supply lockout** — if long-term supply agreements lock customers in, lower the trigger sensitivity
3. **Korean won crisis** — FX moves >15% can dominate signal noise; pause framework, re-evaluate

## Re-entry rules

After trim/exit, re-entry requires:

- 0 signals in WARNING+ for 2 consecutive monthly readings, AND
- Contract price MoM positive for 2 consecutive months, AND
- Hyperscaler capex guidance back to CLEAR

Re-entry is staged: 30% of trimmed amount per month over 3 months.
