#!/bin/bash
# AgentBill v1 — unit suite + demo e2e. Stdlib only, no network.
set -e
cd "$(dirname "$0")"

echo "=== unit tests ==="
python3 -m unittest discover -s tests -v

echo
echo "=== demo e2e: record -> meter -> invoice -> balance ==="
DEMO=$(mktemp -d /tmp/agentbill-demo.XXXXXX)
STORE="$DEMO/store"
OUT="$DEMO/invoice"

python3 -m agentbill plan --store "$STORE" --plan examples/plans.json

# The demo events from examples/events.jsonl (Nov + one Oct event).
python3 -m agentbill record --store "$STORE" --agent demo-agent --customer acme --kind token --units 5000 --at 2026-11-05T10:00:00Z > /dev/null
python3 -m agentbill record --store "$STORE" --agent demo-agent --customer acme --kind action --units 250 --at 2026-11-06T11:00:00Z > /dev/null
python3 -m agentbill record --store "$STORE" --agent demo-agent --customer acme --kind minute --units 30 --at 2026-11-07T12:00:00Z > /dev/null
python3 -m agentbill record --store "$STORE" --agent demo-agent --customer acme --kind token --units 10000 --at 2026-10-20T09:00:00Z > /dev/null

echo "--- meter (Nov 2026) ---"
python3 -m agentbill meter --store "$STORE" --customer acme --from 2026-11-01 --to 2026-11-30

echo "--- invoice (2026-11) ---"
python3 -m agentbill invoice --store "$STORE" --customer acme --plan starter --period 2026-11 --out "$OUT"
cat "$OUT/invoice.md"

echo "--- balance (agent self-check) ---"
python3 -m agentbill balance --store "$STORE" --customer acme --plan starter --period 2026-11

echo "--- check against hand-computed expected invoice ---"
python3 - "$OUT/invoice.json" examples/expected-invoice.json <<'PYEOF'
import json, sys
invoice = json.load(open(sys.argv[1]))
expected = json.load(open(sys.argv[2]))
assert invoice["total"] == expected["expected_total"], (invoice["total"], expected["expected_total"])
assert invoice["subtotal"] == expected["expected_subtotal"]
assert invoice["events"] == expected["events"]
by_kind = {line["kind"]: line for line in invoice["lines"]}
for exp in expected["expected_lines"]:
    line = by_kind[exp["kind"]]
    assert line["amount"] == exp["amount"], (line, exp)
    assert line["billable_units"] == exp["billable_units"], (line, exp)
print(f"demo invoice matches hand-computed expected total: ${expected['expected_total']} "
      f"(token $0.08 + action $1.50 + minute $1.50)")
PYEOF

echo "demo store: $DEMO"
echo "demo done."
