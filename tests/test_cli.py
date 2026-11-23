import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agentbill.cli import main

ROOT = Path(__file__).resolve().parent.parent


def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = str(Path(self.tmp.name) / "store")
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()


class TestCliE2E(CliTestCase):
    def test_record_meter_invoice_balance_match_expected(self):
        # Load the sample plan.
        code, out = run_cli("plan", "--store", self.store,
                            "--plan", str(ROOT / "examples" / "plans.json"))
        self.assertEqual(code, 0)
        self.assertIn("starter", out)
        # Record the demo events exactly as in examples/events.jsonl.
        for kind, units, at in [
                ("token", 5000, "2026-11-05T10:00:00Z"),
                ("action", 250, "2026-11-06T11:00:00Z"),
                ("minute", 30, "2026-11-07T12:00:00Z"),
                ("token", 10000, "2026-10-20T09:00:00Z")]:
            code, event_id = run_cli(
                "record", "--store", self.store, "--agent", "demo-agent",
                "--customer", "acme", "--kind", kind, "--units", str(units),
                "--at", at)
            self.assertEqual(code, 0, event_id)
            self.assertEqual(len(event_id.strip()), 36)  # uuid4
        # Meter: November only, via date filter.
        code, out = run_cli("meter", "--store", self.store, "--customer", "acme",
                            "--from", "2026-11-01", "--to", "2026-11-30")
        self.assertEqual(code, 0)
        meter = json.loads(out.split("---JSON---")[1])
        self.assertEqual(meter["totals"], {"token": 5000, "action": 250, "minute": 30})
        self.assertEqual(meter["events"], 3)
        # Invoice for 2026-11, checked against the hand-computed example.
        expected = json.loads((ROOT / "examples" / "expected-invoice.json").read_text())
        code, out = run_cli("invoice", "--store", self.store, "--customer", "acme",
                            "--plan", "starter", "--period", "2026-11",
                            "--out", str(self.out))
        self.assertEqual(code, 0, out)
        invoice = json.loads((self.out / "invoice.json").read_text())
        self.assertEqual(invoice["total"], expected["expected_total"])
        self.assertEqual(invoice["subtotal"], expected["expected_subtotal"])
        self.assertEqual(invoice["events"], expected["events"])
        by_kind = {line["kind"]: line for line in invoice["lines"]}
        for exp in expected["expected_lines"]:
            line = by_kind[exp["kind"]]
            self.assertEqual(line["amount"], exp["amount"])
            self.assertEqual(line["billable_units"], exp["billable_units"])
        self.assertTrue((self.out / "invoice.md").exists())
        # Balance must equal the invoice accrued amount (same computation).
        code, out = run_cli("balance", "--store", self.store, "--customer", "acme",
                            "--plan", "starter", "--period", "2026-11")
        self.assertEqual(code, 0)
        balance = json.loads(out)
        self.assertEqual(balance["accrued_usd"], float(invoice["total"]))
        self.assertEqual(balance["remaining_usd_or_null"], 50.0 - 3.08)
        self.assertEqual(balance["used"], {"token": 5000, "action": 250, "minute": 30})
        self.assertEqual(balance["events"], 3)

    def test_zero_event_invoice_is_zero_not_error(self):
        run_cli("plan", "--store", self.store,
                "--plan", str(ROOT / "examples" / "plans.json"))
        code, out = run_cli("invoice", "--store", self.store, "--customer", "ghost",
                            "--plan", "starter", "--period", "2026-11",
                            "--out", str(self.out))
        self.assertEqual(code, 0, out)
        invoice = json.loads((self.out / "invoice.json").read_text())
        self.assertEqual(invoice["total"], "0.00")

    def test_balance_without_period_uses_latest_month(self):
        run_cli("plan", "--store", self.store,
                "--plan", str(ROOT / "examples" / "plans.json"))
        run_cli("record", "--store", self.store, "--agent", "a", "--customer", "acme",
                "--kind", "action", "--units", "10", "--at", "2026-11-03T00:00:00Z")
        code, out = run_cli("balance", "--store", self.store, "--customer", "acme",
                            "--plan", "starter")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["period"], "2026-11")

    def test_init_writes_templates(self):
        target = Path(self.tmp.name) / "tpl"
        code, out = run_cli("init", "--dir", str(target))
        self.assertEqual(code, 0)
        self.assertTrue((target / "plans.json").exists())
        events = (target / "events.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(events), 3)

    def test_record_negative_units_rejected(self):
        code, out = run_cli("record", "--store", self.store, "--agent", "a",
                            "--customer", "c", "--kind", "token", "--units", "-5")
        self.assertEqual(code, 2)

    def test_invoice_without_plan_errors(self):
        code, out = run_cli("invoice", "--store", self.store, "--customer", "acme",
                            "--plan", "starter", "--period", "2026-11")
        self.assertEqual(code, 2)

    def test_unknown_plan_errors(self):
        run_cli("plan", "--store", self.store,
                "--plan", str(ROOT / "examples" / "plans.json"))
        code, out = run_cli("invoice", "--store", self.store, "--customer", "acme",
                            "--plan", "nope", "--period", "2026-11")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
