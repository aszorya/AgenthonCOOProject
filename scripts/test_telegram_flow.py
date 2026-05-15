"""Simulate Telegram main flows without the Telegram API."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEMO_PROFILE = {
    "business_name": "Kopi Senja",
    "business_type": "toko kopi",
    "budget": "2000000",
    "chat_id": "test_user",
    "latitude": -6.2615,
    "longitude": 106.8106,
    "location_label": "Jakarta demo",
}

DEMO_SUPPLIER = {
    "supplier_id": "SUP-DEMO01",
    "name": "Supplier Kopi Demo",
    "contact_person": "Pak Demo",
    "phone_wa": "6281234567890",
    "address": "Jl. Supplier Demo",
    "doku_id": "DOKU-DEMO-VENDOR",
    "products": "biji kopi",
    "default_monthly_amount": 500_000,
}


def _print_run(title: str, run) -> bool:
    print(f"\n=== {title} ===")
    print(f"status: {run.status} | workflow: {run.workflow}")
    for line in run.feed:
        print(f"  {line.get('message', '')}")
    ctx = run.context
    if ctx.get("payment_url"):
        print(f"  PAYMENT: {ctx['payment_url'][:70]}...")
    ok = run.status == "ok"
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    from backend.business_profile import build_business_context, save_profile
    from backend.intent_router import UserIntent
    from backend.orchestrator import run_goal_flow

    print("COOPilot Telegram flow simulation\n")

    try:
        save_profile("test_sim", DEMO_PROFILE)
        print("[setup] Profile saved to Mem9")
    except Exception as e:
        print(f"[setup] Profile cache only: {e}")

    base = {
        "profile": DEMO_PROFILE,
        "business_context": build_business_context(DEMO_PROFILE),
        "registered_suppliers": [DEMO_SUPPLIER],
        "selected_supplier": DEMO_SUPPLIER,
        "budget_available": 2_000_000,
        "payment_amount": 500_000,
        "memory_query": "preferred supplier coffee beans",
    }

    ok_plan = _print_run(
        "Planning (rencana)",
        run_goal_flow({**base, "user_goal": "Tingkatkan penjualan coffee shop"}, UserIntent.PLANNING),
    )
    ok_pay = _print_run(
        "Vendor payment (/bayar)",
        run_goal_flow({**base, "user_goal": "Bayar supplier kopi bulan ini"}, UserIntent.VENDOR_PAYMENT),
    )

    agents_expected_pay = {
        "strategy",
        "memory",
        "orchestrator",
        "operations_plan",
        "finance",
        "payment",
        "communication",
        "operations",
    }
    run = run_goal_flow({**base, "user_goal": "Bayar supplier bulan ini"}, UserIntent.VENDOR_PAYMENT)
    agents_seen = {s.agent for s in run.steps}
    missing = agents_expected_pay - agents_seen
    if missing:
        print(f"\n[WARN] Missing agents in payment flow: {missing}")
    else:
        print("\n[OK] All expected agents executed in payment flow")

    all_ok = ok_plan and ok_pay and not missing
    print("\n=== SUMMARY ===")
    print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
