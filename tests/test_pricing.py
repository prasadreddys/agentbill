import copy
import unittest

from agentbill.pricing import chunk_size, validate_plan_file

GOOD = {
    "currency": "USD",
    "plans": [{
        "name": "starter",
        "rates": [
            {"kind": "token", "unit": "1k_tokens", "price_per_unit": 0.02},
            {"kind": "action", "unit": "action", "price_per_unit": 0.01},
        ],
        "free_allowance": {"token": 1000},
        "monthly_cap": 50.0,
    }],
}


class TestChunkSize(unittest.TestCase):
    def test_plain_unit(self):
        self.assertEqual(chunk_size("action", "action"), 1)

    def test_1k_tokens(self):
        self.assertEqual(chunk_size("1k_tokens", "token"), 1000)

    def test_100_tokens(self):
        self.assertEqual(chunk_size("100_tokens", "token"), 100)

    def test_bad_unit_rejected(self):
        with self.assertRaises(ValueError):
            chunk_size("banana", "token")


class TestValidatePlan(unittest.TestCase):
    def test_good_plan_passes(self):
        self.assertEqual(validate_plan_file(copy.deepcopy(GOOD)), GOOD)

    def test_negative_price_rejected(self):
        bad = copy.deepcopy(GOOD)
        bad["plans"][0]["rates"][0]["price_per_unit"] = -0.01
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_missing_price_rejected(self):
        bad = copy.deepcopy(GOOD)
        del bad["plans"][0]["rates"][0]["price_per_unit"]
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_duplicate_kind_rejected(self):
        bad = copy.deepcopy(GOOD)
        bad["plans"][0]["rates"].append(
            {"kind": "token", "unit": "token", "price_per_unit": 0.01})
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_missing_currency_rejected(self):
        bad = copy.deepcopy(GOOD)
        del bad["currency"]
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_missing_plans_rejected(self):
        bad = copy.deepcopy(GOOD)
        bad["plans"] = []
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_duplicate_plan_name_rejected(self):
        bad = copy.deepcopy(GOOD)
        bad["plans"].append(copy.deepcopy(bad["plans"][0]))
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_negative_cap_rejected(self):
        bad = copy.deepcopy(GOOD)
        bad["plans"][0]["monthly_cap"] = -5
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_negative_allowance_rejected(self):
        bad = copy.deepcopy(GOOD)
        bad["plans"][0]["free_allowance"]["token"] = -1
        with self.assertRaises(ValueError):
            validate_plan_file(bad)

    def test_null_cap_allowed(self):
        good = copy.deepcopy(GOOD)
        good["plans"][0]["monthly_cap"] = None
        validate_plan_file(good)

    def test_zero_price_allowed(self):
        good = copy.deepcopy(GOOD)
        good["plans"][0]["rates"][0]["price_per_unit"] = 0
        validate_plan_file(good)


if __name__ == "__main__":
    unittest.main()
