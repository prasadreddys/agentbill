import os
import tempfile
import unittest
from pathlib import Path

from agentbill.events import (
    aggregate, filter_events, load_events, make_event, parse_timestamp, record_event,
)

SAMPLE = {"agent": "a1", "customer": "acme", "kind": "token", "units": 100}


class TestMakeEvent(unittest.TestCase):
    def test_valid_event_has_id_and_timestamp(self):
        event = make_event(**SAMPLE)
        self.assertEqual(event["agent"], "a1")
        self.assertEqual(event["units"], 100)
        self.assertTrue(event["id"])
        parse_timestamp(event["timestamp"])

    def test_negative_units_rejected(self):
        with self.assertRaises(ValueError):
            make_event(**{**SAMPLE, "units": -1})

    def test_zero_units_allowed(self):
        self.assertEqual(make_event(**{**SAMPLE, "units": 0})["units"], 0)

    def test_bad_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            make_event(**SAMPLE, at="not-a-date")

    def test_bad_agent_rejected(self):
        with self.assertRaises(ValueError):
            make_event(**{**SAMPLE, "agent": ""})

    def test_z_timestamp_parsed(self):
        dt = parse_timestamp("2026-11-05T10:00:00Z")
        self.assertEqual(dt.strftime("%Y-%m"), "2026-11")

    def test_meta_passthrough(self):
        event = make_event(**SAMPLE, meta={"run": "r1"})
        self.assertEqual(event["meta"], {"run": "r1"})


class TestStoreRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name) / "store"

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_then_load(self):
        event = make_event(**SAMPLE, at="2026-11-05T10:00:00Z")
        record_event(self.store, event)
        loaded = load_events(self.store)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["id"], event["id"])

    def test_empty_store_loads_empty(self):
        self.assertEqual(load_events(self.store), [])

    def test_corrupt_line_rejected(self):
        self.store.mkdir(parents=True)
        (self.store / "events.jsonl").write_text('{"agent": "x"}\n')
        with self.assertRaises(ValueError):
            load_events(self.store)


class TestFiltering(unittest.TestCase):
    def setUp(self):
        self.events = [
            make_event(agent="a1", customer="acme", kind="token", units=100, at="2026-11-05T10:00:00Z"),
            make_event(agent="a1", customer="acme", kind="action", units=5, at="2026-11-20T10:00:00Z"),
            make_event(agent="a2", customer="other", kind="token", units=7, at="2026-10-01T10:00:00Z"),
        ]

    def test_filter_by_customer(self):
        self.assertEqual(len(filter_events(self.events, customer="acme")), 2)

    def test_filter_by_agent(self):
        self.assertEqual(len(filter_events(self.events, agent="a2")), 1)

    def test_filter_by_period(self):
        self.assertEqual(len(filter_events(self.events, period="2026-11")), 2)
        self.assertEqual(len(filter_events(self.events, period="2026-10")), 1)

    def test_filter_by_date_range_inclusive(self):
        got = filter_events(self.events, from_date="2026-11-05", to_date="2026-11-05")
        self.assertEqual(len(got), 1)

    def test_aggregate_sums_by_kind(self):
        totals, count = aggregate(self.events)
        self.assertEqual(totals, {"token": 107, "action": 5})
        self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
