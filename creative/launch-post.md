# AgentBill launch post — DRAFT, not published

Status: draft for the user's approval. Nothing posted yet.

Rules for this post: only measured numbers, no user/sales/revenue claims, no invented quotes.

## X / Threads version

Your AI agent burned $3.08 this month. Or did it?

AgentBill meters every token, action, and minute — free allowance first, monthly cap enforced, one shared bill function so the invoice and the balance can never disagree.

Free, open source (MIT), stdlib-only Python, local JSON store, no sign-up, no paid API.

https://github.com/prasadreddys/agentbill

## Longer version (README / Product Hunt style)

AI agents cost money in three currencies at once: tokens, actions, and minutes. AgentBill is the meter: record usage, price it per plan, invoice by month, and check the balance — all offline, all in local files.

- Demo invoice (acme / starter / 2026-11): $3.08 — token $0.08 (5,000 used, 1,000 free, $0.02/1k) + action $1.50 (150 × $0.01) + minute $1.50 (30 × $0.05); cap $50 not hit; balance accrued $3.08, remaining $46.92
- Balance and invoice share one compute function, so they always agree
- Decimal math, half-up rounding to cents

Measured, not estimated: 49 unit tests, all passing. MIT license in LICENSE.
