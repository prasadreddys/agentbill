"""Invoice computation — the single source of truth for billing math.

Both `invoice` and `balance` call compute_bill(); the math lives in
exactly one place. Money is Decimal, rounded half-up to 2 decimals
per line item.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from .events import aggregate, filter_events
from .pricing import chunk_size, rate_for

CENT = Decimal("0.01")


def money(value):
    """Round a Decimal to cents, half-up. Returns Decimal."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def compute_bill(events, plan, customer, period):
    """Compute the bill for one customer in one YYYY-MM period.

    Returns a dict with used/billable units per kind, line items,
    subtotal, cap handling, total, and event count. A period with no
    events yields a $0.00 bill, not an error.
    """
    if len(period) != 7 or period[4] != "-":
        raise ValueError(f"period must be YYYY-MM, got {period!r}")
    month_events = filter_events(events, customer=customer, period=period)
    used, count = aggregate(month_events)
    allowance = plan.get("free_allowance", {}) or {}
    cap = plan.get("monthly_cap")
    cap_dec = Decimal(str(cap)) if cap is not None else None

    lines = []
    billable = {}
    for kind in sorted(used):
        rate = rate_for(plan, kind)
        if rate is None:
            # Usage with no rate in the plan is reported, never billed.
            billable[kind] = 0
            lines.append({
                "kind": kind,
                "used": used[kind],
                "free_allowance": allowance.get(kind, 0),
                "billable_units": 0,
                "unit": None,
                "price_per_unit": None,
                "amount": "0.00",
                "note": "no rate in plan — not billed",
            })
            continue
        free = allowance.get(kind, 0)
        billable_units = max(0, used[kind] - free)
        billable[kind] = billable_units
        chunk = chunk_size(rate["unit"], kind)
        price = Decimal(str(rate["price_per_unit"]))
        amount = money(Decimal(str(billable_units)) / Decimal(chunk) * price)
        lines.append({
            "kind": kind,
            "used": used[kind],
            "free_allowance": free,
            "billable_units": billable_units,
            "unit": rate["unit"],
            "price_per_unit": str(price),
            "amount": str(amount),
            "note": "",
        })
    subtotal = sum((Decimal(line["amount"]) for line in lines), Decimal("0.00"))
    subtotal = money(subtotal)
    if cap_dec is not None and subtotal > cap_dec:
        total = money(cap_dec)
        cap_applied = True
    else:
        total = subtotal
        cap_applied = False
    return {
        "customer": customer,
        "plan": plan["name"],
        "period": period,
        "currency": "USD",  # replaced by caller with the plan file currency
        "used": used,
        "billable": billable,
        "lines": lines,
        "subtotal": str(subtotal),
        "monthly_cap": str(cap_dec) if cap_dec is not None else None,
        "cap_applied": cap_applied,
        "total": str(total),
        "events": count,
    }


def build_invoice(events, plan_data, plan_name, customer, period):
    """Full invoice dict, including currency and generation time."""
    plan = next(p for p in plan_data["plans"] if p["name"] == plan_name)
    bill = compute_bill(events, plan, customer, period)
    bill["currency"] = plan_data["currency"]
    bill["generated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    bill["invoice_id"] = f"inv-{customer}-{period}"
    return bill


def render_markdown(invoice):
    """Human-readable invoice.md for an invoice dict."""
    lines = [
        f"# Invoice {invoice['invoice_id']}",
        "",
        f"Customer: {invoice['customer']}",
        f"Plan: {invoice['plan']}",
        f"Period: {invoice['period']}",
        f"Currency: {invoice['currency']}",
        f"Generated: {invoice['generated_at_utc']}",
        "",
        "| Kind | Used | Free | Billable | Unit | Price/unit | Amount |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in invoice["lines"]:
        price = item["price_per_unit"] if item["price_per_unit"] is not None else "—"
        unit = item["unit"] if item["unit"] is not None else "—"
        note = f" ({item['note']})" if item["note"] else ""
        lines.append(
            f"| {item['kind']} | {item['used']} | {item['free_allowance']} | "
            f"{item['billable_units']} | {unit} | {price} | "
            f"{item['amount']}{note} |"
        )
    lines += [
        "",
        f"Subtotal: {invoice['subtotal']} {invoice['currency']}",
    ]
    if invoice["monthly_cap"] is not None:
        lines.append(f"Monthly cap: {invoice['monthly_cap']} {invoice['currency']}")
    if invoice["cap_applied"]:
        lines.append("Cap applied: total limited to the monthly cap.")
    lines.append(f"**Total: {invoice['total']} {invoice['currency']}**")
    lines.append("")
    lines.append(f"Events in period: {invoice['events']}")
    return "\n".join(lines) + "\n"
