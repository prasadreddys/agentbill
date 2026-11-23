"""Price-plan loading and validation.

Plan file format:
    {"currency": "USD",
     "plans": [{"name": "starter",
                "rates": [{"kind": "token", "unit": "1k_tokens",
                           "price_per_unit": 0.02}, ...],
                "free_allowance": {"token": 1000, "action": 100},
                "monthly_cap": 50.0}]}

Rates are priced per `unit` of usage. The unit string names the chunk
that one price buys: "action" / "minute" / "call" / "token" = 1 unit of
that kind; "1k_tokens" = 1,000 tokens; "100_tokens" = 100 tokens.
"""

import json
import re
from decimal import Decimal, InvalidOperation

from .store import plans_path

_CHUNK_RE = re.compile(r"^(\d+)(k|m)?_(.+)$")


def chunk_size(unit, kind):
    """How many raw units of `kind` one priced unit covers."""
    if unit == kind:
        return 1
    match = _CHUNK_RE.match(unit or "")
    if match:
        number = int(match.group(1))
        scale = {"k": 1000, "m": 1000000}.get(match.group(2) or "", 1)
        return number * scale
    if unit in ("action", "minute", "call", "token", "second", "hour"):
        return 1
    raise ValueError(f"cannot interpret rate unit {unit!r} for kind {kind!r}")


def _price(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{where}: price_per_unit must be a number")
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{where}: price_per_unit is not a number")
    if price < 0:
        raise ValueError(f"{where}: price_per_unit must be >= 0")
    return price


def validate_plan_file(data):
    """Validate a parsed plan file. Returns it unchanged. Raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError("plan file must be a JSON object")
    if "currency" not in data or not isinstance(data["currency"], str) or not data["currency"]:
        raise ValueError("plan file missing 'currency' (non-empty string)")
    if "plans" not in data or not isinstance(data["plans"], list) or not data["plans"]:
        raise ValueError("plan file missing non-empty 'plans' list")
    seen_names = set()
    for i, plan in enumerate(data["plans"]):
        where = f"plans[{i}]"
        if not isinstance(plan, dict):
            raise ValueError(f"{where}: plan must be an object")
        if "name" not in plan or not isinstance(plan["name"], str) or not plan["name"]:
            raise ValueError(f"{where}: missing 'name' (non-empty string)")
        if plan["name"] in seen_names:
            raise ValueError(f"{where}: duplicate plan name {plan['name']!r}")
        seen_names.add(plan["name"])
        if "rates" not in plan or not isinstance(plan["rates"], list) or not plan["rates"]:
            raise ValueError(f"{where}: missing non-empty 'rates' list")
        seen_kinds = set()
        for j, rate in enumerate(plan["rates"]):
            rwhere = f"{where}.rates[{j}]"
            if not isinstance(rate, dict):
                raise ValueError(f"{rwhere}: rate must be an object")
            for field in ("kind", "unit", "price_per_unit"):
                if field not in rate:
                    raise ValueError(f"{rwhere}: missing {field!r}")
            if not isinstance(rate["kind"], str) or not rate["kind"]:
                raise ValueError(f"{rwhere}: 'kind' must be a non-empty string")
            if rate["kind"] in seen_kinds:
                raise ValueError(f"{where}: duplicate kind {rate['kind']!r} in one plan")
            seen_kinds.add(rate["kind"])
            if not isinstance(rate["unit"], str) or not rate["unit"]:
                raise ValueError(f"{rwhere}: 'unit' must be a non-empty string")
            chunk_size(rate["unit"], rate["kind"])  # validates the unit
            _price(rate["price_per_unit"], rwhere)
        allowance = plan.get("free_allowance", {})
        if not isinstance(allowance, dict):
            raise ValueError(f"{where}: 'free_allowance' must be an object")
        for kind, amount in allowance.items():
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
                raise ValueError(f"{where}: free_allowance[{kind!r}] must be >= 0")
        cap = plan.get("monthly_cap")
        if cap is not None:
            if isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0:
                raise ValueError(f"{where}: 'monthly_cap' must be >= 0 or null")
    return data


def load_plan_file(path):
    """Load and validate a plan file from disk."""
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"plan file {path} is not valid JSON: {exc}")
    return validate_plan_file(data)


def store_plans(store_dir, data):
    """Persist a validated plan file into the store."""
    path = plans_path(store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def load_stored_plans(store_dir):
    """Load the plan file stored in the store. Raises ValueError if absent."""
    path = plans_path(store_dir)
    if not path.exists():
        raise ValueError(
            f"no price plan in store {store_dir!r} — run 'agentbill plan' first"
        )
    return load_plan_file(path)


def find_plan(data, name):
    """Return the plan dict named `name`, or raise ValueError."""
    for plan in data["plans"]:
        if plan["name"] == name:
            return plan
    raise ValueError(f"no plan named {name!r} in stored plans")


def rate_for(plan, kind):
    """Return the rate dict for `kind` in a plan, or None if unpriced."""
    for rate in plan["rates"]:
        if rate["kind"] == kind:
            return rate
    return None
