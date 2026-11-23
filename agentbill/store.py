"""Store layout: a directory of local JSON files.

    <store>/
      events.jsonl   one JSON object per usage event
      plans.json     the validated price-plan file
"""

from pathlib import Path


def ensure_store(store_dir):
    path = Path(store_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def events_path(store_dir):
    return Path(store_dir) / "events.jsonl"


def plans_path(store_dir):
    return Path(store_dir) / "plans.json"
