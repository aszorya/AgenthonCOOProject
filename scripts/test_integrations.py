"""Test Mem9, DOKU, Sumopod + run Phase 2 vendor payment workflow."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MOCK_PROFILE = {
    "business_name": "Kopi Senja",
    "business_type": "toko kopi",
    "budget": "2000000",
    "latitude": -6.2615,
    "longitude": 106.8106,
    "location_label": "Jakarta Selatan",
}

MOCK_SUPPLIER = {
    "supplier_id": "SUP-TEST01",
    "name": "Supplier Kopi Test",
    "contact_person": "Pak Andi",
    "phone_wa": "6281234567890",
    "address": "Jl. Supplier 1, Jakarta",
    "telegram_id": "",
    "doku_id": "DOKU-VENDOR-TEST",
    "products": "biji kopi arabika",
    "default_monthly_amount": 500_000,
    "source": "registered",
}


def main() -> int:
    print("=== COOPilot Integration + Phase 2 Tests ===\n")
    ok_all = True

    print("[1] Mem9")
    try:
        from backend import mem9_client

        r = mem9_client.test_connection()
        ok = bool(r.get("ok"))
        print(f"    {'PASS' if ok else 'FAIL'} | write={r.get('write_status')} hits={r.get('search_total')}")
        ok_all &= ok
    except Exception as e:
        print(f"    FAIL: {e}")
        ok_all = False

    print("\n[2] DOKU Checkout")
    try:
        from backend import doku_client

        if not doku_client.is_configured():
            print("    SKIP: credentials missing")
        else:
            r = doku_client.test_connection(amount=10000)
            ok = bool(r.get("ok"))
            print(f"    {'PASS' if ok else 'FAIL'} | invoice={r.get('invoice_id')}")
            if r.get("payment_url"):
                print(f"    url: {r['payment_url'][:80]}...")
            ok_all &= ok
    except Exception as e:
        print(f"    FAIL: {e}")
        ok_all = False

    print("\n[3] Phase 2 — Vendor payment workflow (gated)")
    try:
        from backend.business_profile import build_business_context
        from backend.orchestrator import run_vendor_payment_workflow

        ctx = {
            "user_goal": "Bayar supplier bulan ini",
            "profile": MOCK_PROFILE,
            "business_context": build_business_context(MOCK_PROFILE),
            "registered_suppliers": [MOCK_SUPPLIER],
            "selected_supplier": MOCK_SUPPLIER,
            "budget_available": 2_000_000,
            "payment_amount": 500_000,
        }
        run = run_vendor_payment_workflow(ctx)
        print(f"    status: {run.status}")
        for line in run.feed:
            print(f"    → [{line['agent']}] {line['status']}: {line['message'][:80]}")
        if run.context.get("payment_url"):
            print(f"    payment_url: {str(run.context['payment_url'])[:80]}...")
        ok = run.status == "ok"
        print(f"    {'PASS' if ok else 'FAIL'}")
        ok_all &= ok
    except Exception as e:
        print(f"    FAIL: {e}")
        ok_all = False

    print("\n[4] Supplier discovery (OSM)")
    try:
        from backend import supplier_discovery

        items = supplier_discovery.find_nearby_suppliers(
            -6.2615, 106.8106, query="kopi", business_type="coffee", limit=3
        )
        ok = isinstance(items, list)
        print(f"    {'PASS' if ok else 'FAIL'} | found={len(items)}")
        for s in items[:2]:
            print(f"      - {s.get('name')} ({s.get('distance_label')})")
        ok_all &= ok
    except Exception as e:
        print(f"    WARN/SKIP discovery: {e}")

    print("\n=== Summary ===")
    print("ALL PASS" if ok_all else "SOME FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
