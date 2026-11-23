import unittest

from agentbill.events import make_event
from agentbill.invoice import compute_bill, money
from decimal import Decimal

PLAN = {
    "name": "starter",
    "rates": [
        {"kind": "token", "unit": "1k_tokens", "price_per_unit": 0.02},
        {"kind": "action", "unit": "action", "price_per_unit": 0.01},
        {"kind": "minute", "unit": "minute", "price_per_unit": 0.05},
    ],
    "free_allowance": {"token": 1000, "action": 100},
    "monthly_cap": 50.0,
}

NO_CAP = {**PLAN, "monthly_cap": None}


def events_for(specs, period="2026-11"):
    out = []
    for kind, units in specs:
        out.append(make_event(
            agent="a1", customer="acme", kind=kind, units=units,
            at=f"{period}-05T10:00:00Z"))
    return out


class TestMoney(unittest.TestCase):
    def test_half_up(self):
        # 0.005 rounds to 0.01 (half-up), not 0.00 (banker's).
        self.assertEqual(money(Decimal("0.005")), Decimal("0.01"))
        self.assertEqual(money(Decimal("2.345")), Decimal("2.35"))
        self.assertEqual(money(Decimal("2.344")), Decimal("2.34"))


class TestComputeBill(unittest.TestCase):
    def test_free_allowance_deducted(self):
        bill = compute_bill(events_for([("token", 5000)]), PLAN, "acme", "2026-11")
        self.assertEqual(bill["used"], {"token": 5000})
        self.assertEqual(bill["billable"], {"token": 4000})
        self.assertEqual(bill["total"], "0.08")

    def test_allowance_covers_all(self):
        bill = compute_bill(events_for([("token", 500)]), PLAN, "acme", "2026-11")
        self.assertEqual(bill["total"], "0.00")

    def test_cap_applied(self):
        bill = compute_bill(events_for([("minute", 100000)]), PLAN, "acme", "2026-11")
        # 100000 x $0.05 = $5000, capped at $50.
        self.assertEqual(bill["subtotal"], "5000.00")
        self.assertTrue(bill["cap_applied"])
        self.assertEqual(bill["total"], "50.00")

    def test_cap_not_applied_below_cap(self):
        bill = compute_bill(events_for([("minute", 30)]), PLAN, "acme", "2026-11")
        self.assertFalse(bill["cap_applied"])
        self.assertEqual(bill["total"], "1.50")

    def test_zero_events_zero_invoice(self):
        bill = compute_bill([], PLAN, "acme", "2026-11")
        self.assertEqual(bill["total"], "0.00")
        self.assertEqual(bill["events"], 0)
        self.assertEqual(bill["lines"], [])

    def test_multi_kind_demo_total(self):
        bill = compute_bill(
            events_for([("token", 5000), ("action", 250), ("minute", 30)]),
            PLAN, "acme", "2026-11")
        self.assertEqual(bill["subtotal"], "3.08")
        self.assertEqual(bill["total"], "3.08")
        self.assertEqual(bill["events"], 3)

    def test_out_of_period_excluded(self):
        events = events_for([("token", 5000)], period="2026-11")
        events += events_for([("token", 10000)], period="2026-10")
        bill = compute_bill(events, PLAN, "acme", "2026-11")
        self.assertEqual(bill["used"], {"token": 5000})

    def test_other_customer_excluded(self):
        events = [make_event(agent="a1", customer="other", kind="token",
                             units=99999, at="2026-11-05T10:00:00Z")]
        bill = compute_bill(events, PLAN, "acme", "2026-11")
        self.assertEqual(bill["total"], "0.00")

    def test_unpriced_kind_listed_not_billed(self):
        bill = compute_bill(events_for([("call", 10)]), PLAN, "acme", "2026-11")
        self.assertEqual(bill["total"], "0.00")
        self.assertEqual(len(bill["lines"]), 1)
        self.assertIn("no rate", bill["lines"][0]["note"])

    def test_rounding_half_up_per_line(self):
        plan = {"name": "odd", "rates": [
            {"kind": "action", "unit": "action", "price_per_unit": 0.015}],
            "free_allowance": {}, "monthly_cap": None}
        bill = compute_bill(events_for([("action", 3)]), plan, "acme", "2026-11")
        # 3 x $0.015 = $0.045 -> $0.05 half-up.
        self.assertEqual(bill["total"], "0.05")

    def test_bad_period_rejected(self):
        with self.assertRaises(ValueError):
            compute_bill([], PLAN, "acme", "2026/11")


if __name__ == "__main__":
    unittest.main()
