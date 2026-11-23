"""Usage events: validation, storage, loading, filtering."""

import json
import uuid
from datetime import datetime, timezone

from .store import events_path


def parse_timestamp(value):
    """Parse an ISO-8601 timestamp (date or datetime, 'Z' allowed).

    Returns a timezone-aware datetime in UTC. Raises ValueError on bad input.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    text = value.strip()
    try:
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"invalid ISO-8601 timestamp: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def make_event(agent, customer, kind, units, unit=None, at=None, meta=None):
    """Build and validate one usage event dict. Raises ValueError."""
    if not agent or not isinstance(agent, str):
        raise ValueError("agent must be a non-empty string")
    if not customer or not isinstance(customer, str):
        raise ValueError("customer must be a non-empty string")
    if not kind or not isinstance(kind, str):
        raise ValueError("kind must be a non-empty string")
    if isinstance(units, bool) or not isinstance(units, (int, float)):
        raise ValueError("units must be a number")
    if units < 0:
        raise ValueError("units must be >= 0")
    if unit is not None and (not isinstance(unit, str) or not unit):
        raise ValueError("unit must be a non-empty string")
    if meta is not None and not isinstance(meta, dict):
        raise ValueError("meta must be a dict")
    dt = parse_timestamp(at) if at is not None else datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "timestamp": dt.isoformat().replace("+00:00", "Z"),
        "agent": agent,
        "customer": customer,
        "kind": kind,
        "units": units,
        "unit": unit or kind,
        "meta": meta or {},
    }


def record_event(store_dir, event):
    """Append a validated event dict to the store's events.jsonl."""
    path = events_path(store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def load_events(store_dir):
    """Load all events from the store, in file order. Empty store -> []."""
    path = events_path(store_dir)
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f"corrupt event at {path}:{line_no}")
            for field in ("id", "timestamp", "agent", "customer", "kind", "units"):
                if field not in event:
                    raise ValueError(f"event at {path}:{line_no} missing {field!r}")
            parse_timestamp(event["timestamp"])  # validates
            if event["units"] < 0:
                raise ValueError(f"event at {path}:{line_no} has negative units")
            events.append(event)
    return events


def filter_events(events, agent=None, customer=None, from_date=None, to_date=None, period=None):
    """Filter events. from_date/to_date are inclusive ISO dates (YYYY-MM-DD).

    period is YYYY-MM and matches the event timestamp's year-month.
    """
    out = []
    for event in events:
        if agent is not None and event["agent"] != agent:
            continue
        if customer is not None and event["customer"] != customer:
            continue
        dt = parse_timestamp(event["timestamp"])
        if period is not None and dt.strftime("%Y-%m") != period:
            continue
        if from_date is not None and dt.date().isoformat() < from_date:
            continue
        if to_date is not None and dt.date().isoformat() > to_date:
            continue
        out.append(event)
    return out


def aggregate(events):
    """Aggregate units by kind. Returns {kind: total_units, ...} and count."""
    totals = {}
    for event in events:
        totals[event["kind"]] = totals.get(event["kind"], 0) + event["units"]
    return totals, len(events)
