"""AgentBill CLI: record, meter, plan, invoice, balance, init."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .events import aggregate, filter_events, load_events, make_event, record_event
from .invoice import build_invoice, compute_bill, render_markdown
from .pricing import find_plan, load_plan_file, load_stored_plans, store_plans
from .store import ensure_store

SAMPLE_PLANS = {
    "currency": "USD",
    "plans": [
        {
            "name": "starter",
            "rates": [
                {"kind": "token", "unit": "1k_tokens", "price_per_unit": 0.02},
                {"kind": "action", "unit": "action", "price_per_unit": 0.01},
                {"kind": "minute", "unit": "minute", "price_per_unit": 0.05},
            ],
            "free_allowance": {"token": 1000, "action": 100},
            "monthly_cap": 50.0,
        }
    ],
}

SAMPLE_EVENTS = [
    {"agent": "demo-agent", "customer": "acme", "kind": "token",
     "units": 5000, "at": "2026-11-05T10:00:00Z"},
    {"agent": "demo-agent", "customer": "acme", "kind": "action",
     "units": 250, "at": "2026-11-06T11:00:00Z"},
    {"agent": "demo-agent", "customer": "acme", "kind": "minute",
     "units": 30, "at": "2026-11-07T12:00:00Z"},
]


def _fail(message):
    print(f"agentbill: error: {message}", file=sys.stderr)
    return 2


def _parse_meta(pairs):
    meta = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"meta must be KEY=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        meta[key] = value
    return meta


def cmd_record(args):
    try:
        event = make_event(
            agent=args.agent, customer=args.customer, kind=args.kind,
            units=args.units, unit=args.unit, at=args.at,
            meta=_parse_meta(args.meta),
        )
    except ValueError as exc:
        return _fail(str(exc))
    ensure_store(args.store)
    record_event(args.store, event)
    print(event["id"])
    return 0


def cmd_meter(args):
    try:
        events = load_events(args.store)
        filtered = filter_events(
            events, agent=args.agent, customer=args.customer,
            from_date=args.from_date, to_date=args.to_date,
        )
        totals, count = aggregate(filtered)
    except ValueError as exc:
        return _fail(str(exc))
    period = "all time"
    if args.from_date or args.to_date:
        period = f"{args.from_date or '...'} to {args.to_date or '...'}"
    print(f"events: {count}  period: {period}")
    for kind in sorted(totals):
        print(f"  {kind}: {totals[kind]}")
    print("---JSON---")
    print(json.dumps({
        "events": count, "period": period, "totals": totals,
        "agent": args.agent, "customer": args.customer,
    }, sort_keys=True))
    return 0


def cmd_plan(args):
    try:
        data = load_plan_file(args.plan)
    except (ValueError, OSError) as exc:
        return _fail(str(exc))
    ensure_store(args.store)
    store_plans(args.store, data)
    for plan in data["plans"]:
        print(f"plan stored: {plan['name']}")
    return 0


def cmd_invoice(args):
    try:
        plan_data = load_stored_plans(args.store)
        plan = find_plan(plan_data, args.plan)
        events = load_events(args.store)
        invoice = build_invoice(events, plan_data, args.plan, args.customer, args.period)
    except ValueError as exc:
        return _fail(str(exc))
    out = Path(args.out) if args.out else Path("invoices") / f"{args.customer}-{args.period}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "invoice.json", "w", encoding="utf-8") as fh:
        json.dump(invoice, fh, indent=2, sort_keys=True)
        fh.write("\n")
    with open(out / "invoice.md", "w", encoding="utf-8") as fh:
        fh.write(render_markdown(invoice))
    print(f"total: {invoice['total']} {invoice['currency']} ({len(invoice['lines'])} lines)")
    print(f"invoice written to {out}")
    return 0


def cmd_balance(args):
    try:
        plan_data = load_stored_plans(args.store)
        plan = find_plan(plan_data, args.plan)
        events = load_events(args.store)
        period = args.period
        if period is None:
            # Latest month with any event for this customer, else current month.
            mine = [e for e in events if e["customer"] == args.customer]
            if mine:
                period = max(e["timestamp"][:7] for e in mine)
            else:
                from datetime import datetime, timezone
                period = datetime.now(timezone.utc).strftime("%Y-%m")
        bill = compute_bill(events, plan, args.customer, period)
    except ValueError as exc:
        return _fail(str(exc))
    cap = bill["monthly_cap"]
    accrued = float(bill["total"])
    remaining = round(float(cap) - accrued, 2) if cap is not None else None
    print(json.dumps({
        "customer": args.customer,
        "plan": args.plan,
        "period": period,
        "used": bill["used"],
        "billable": bill["billable"],
        "accrued_usd": accrued,
        "cap_usd": float(cap) if cap is not None else None,
        "remaining_usd_or_null": remaining,
        "events": bill["events"],
    }, sort_keys=True))
    return 0


def cmd_init(args):
    target = Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)
    plans_path = target / "plans.json"
    with open(plans_path, "w", encoding="utf-8") as fh:
        json.dump(SAMPLE_PLANS, fh, indent=2, sort_keys=True)
        fh.write("\n")
    events_path = target / "events.jsonl"
    with open(events_path, "w", encoding="utf-8") as fh:
        for sample in SAMPLE_EVENTS:
            event = make_event(
                agent=sample["agent"], customer=sample["customer"],
                kind=sample["kind"], units=sample["units"], at=sample["at"],
            )
            fh.write(json.dumps(event, sort_keys=True) + "\n")
    print(f"wrote {plans_path}")
    print(f"wrote {events_path}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="agentbill",
        description="Usage metering and invoicing for AI agent products (local, $0).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("record", help="record one usage event")
    p.add_argument("--store", default="./agentbill-store")
    p.add_argument("--agent", required=True)
    p.add_argument("--customer", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--units", required=True, type=float)
    p.add_argument("--unit", default=None)
    p.add_argument("--at", default=None)
    p.add_argument("--meta", nargs="*", default=[])
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("meter", help="aggregate usage")
    p.add_argument("--store", default="./agentbill-store")
    p.add_argument("--agent", default=None)
    p.add_argument("--customer", default=None)
    p.add_argument("--from", dest="from_date", default=None)
    p.add_argument("--to", dest="to_date", default=None)
    p.set_defaults(func=cmd_meter)

    p = sub.add_parser("plan", help="load and validate a price plan file")
    p.add_argument("--store", default="./agentbill-store")
    p.add_argument("--plan", required=True)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("invoice", help="invoice a customer for a month")
    p.add_argument("--store", default="./agentbill-store")
    p.add_argument("--customer", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--period", required=True, help="YYYY-MM")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_invoice)

    p = sub.add_parser("balance", help="agent self-check: accrued spend for a period")
    p.add_argument("--store", default="./agentbill-store")
    p.add_argument("--customer", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--period", default=None, help="YYYY-MM (default: latest month)")
    p.set_defaults(func=cmd_balance)

    p = sub.add_parser("init", help="write sample plans.json + events.jsonl")
    p.add_argument("--dir", required=True)
    p.set_defaults(func=cmd_init)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
