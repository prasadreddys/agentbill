# AgentBill v1

Usage metering and invoicing for AI agent products — across providers,
local-first. Agent products need billing that meters what an agent
actually does (actions, tokens, minutes), applies a price plan, and
produces an invoice the agent itself can check. AgentBill is that,
as a stdlib-only Python CLI with local JSON files.

**Free / $0. No network. No paid APIs. Stdlib-only Python 3.12 —
no dependencies to install.**

## Quick start

```bash
cd agentbill
python3 -m unittest discover -s tests -v   # unit suite
./run_tests.sh                              # unit suite + demo e2e

# 1. Write a price plan (or use the sample):
python3 -m agentbill init --dir ./my-plan
#    edit ./my-plan/plans.json

# 2. Store the plan:
python3 -m agentbill plan --store ./store --plan ./my-plan/plans.json

# 3. Record usage (your agent, your app, or a webhook shim):
python3 -m agentbill record --store ./store --agent demo-agent \
  --customer acme --kind token --units 5000
python3 -m agentbill record --store ./store --agent demo-agent \
  --customer acme --kind action --units 250

# 4. See usage:
python3 -m agentbill meter --store ./store --customer acme

# 5. Invoice a month (free allowance first, cap applied):
python3 -m agentbill invoice --store ./store --customer acme \
  --plan starter --period 2026-11

# 6. Agent self-check before acting:
python3 -m agentbill balance --store ./store --customer acme \
  --plan starter --period 2026-11
```

## Data store

A store is a directory of local JSON files (default `./agentbill-store`):

- `events.jsonl` — one JSON object per usage event (append-only)
- `plans.json` — the validated price-plan file

Nothing leaves the machine. There is no server, no account, no sync.

## Price-plan format (`plans.json`)

```json
{"currency": "USD",
 "plans": [{"name": "starter",
            "rates": [{"kind": "token", "unit": "1k_tokens", "price_per_unit": 0.02},
                      {"kind": "action", "unit": "action", "price_per_unit": 0.01},
                      {"kind": "minute", "unit": "minute", "price_per_unit": 0.05}],
            "free_allowance": {"token": 1000, "action": 100},
            "monthly_cap": 50.0}]}
```

- `currency` — ISO code, e.g. `USD`.
- `rates` — one per kind. `unit` names the chunk one price buys:
  `action` / `minute` / `call` / `token` = 1 raw unit;
  `1k_tokens` = 1,000 tokens; `100_tokens` = 100 tokens.
- `free_allowance` — units per kind deducted before billing, each month.
- `monthly_cap` — max charge per month, or `null` for no cap.

Validation rejects: negative prices, missing/unknown fields, a
duplicate kind in one plan, a duplicate plan name, a negative
allowance, and a negative cap.

## Invoice format

`invoice --out DIR` writes `invoice.json` + `invoice.md`:

- Per kind: used, free allowance, billable units, unit, price, amount.
- Amounts are rounded half-up to 2 decimals, per line.
- Subtotal, then the cap: if subtotal exceeds `monthly_cap`, the
  total is the cap and `cap_applied` is true.
- A month with no events produces a $0.00 invoice honestly — not an error.
- Usage of a kind with no rate in the plan is listed, never billed.

`balance` prints one JSON object an agent can read before acting:
`used`, `billable`, `accrued_usd`, `cap_usd`, `remaining_usd_or_null`,
`events`. Its accrued amount is computed by the exact same function
as the invoice — the math lives in one place (`invoice.compute_bill`).

## Demo (hand-computed)

`examples/` has a starter plan and 4 events for customer `acme`.
For 2026-11 (the October event is out of period):

| Kind | Used | Free | Billable | Amount |
|---|---|---|---|---|
| token | 5000 | 1000 | 4000 | $0.08 |
| action | 250 | 100 | 150 | $1.50 |
| minute | 30 | 0 | 30 | $1.50 |
| **Total** | | | | **$3.08** |

See `examples/expected-invoice.json`. `run_tests.sh` checks the
demo invoice against these numbers.

## Layout

```
agentbill/
  agentbill/  __init__.py __main__.py cli.py events.py pricing.py invoice.py store.py
  tests/      stdlib unittest only
  examples/   plans.json, events.jsonl, expected-invoice.json
  run_tests.sh
```

## Limitations (honest)

- Local files only: no multi-machine sync, no concurrent-write
  locking — one writer at a time.
- No payments: AgentBill computes what is owed; it never charges
  a card, moves money, or talks to Stripe/a bank.
- No tax handling, no proration, no refunds/credits — v1 bills
  whole months from recorded events.
- Rounding is per line, half-up to cents; a plan with fractional
  cents per unit can accumulate a cent of rounding per line.
- Events are trusted as recorded: AgentBill does not verify that
  an agent really used what was recorded — pair it with ProofRun
  if the usage itself needs proof.
- Currency is a label from the plan file; no FX conversion.
