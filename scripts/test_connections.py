"""Run: python scripts/test_connections.py (from coopilot/)"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    print("=== COOPilot connection tests ===\n")

    mem9_ok = False
    print("[1] Mem9 API")
    try:
        from backend import mem9_client

        result = mem9_client.test_connection()
        mem9_ok = bool(result.get("ok"))
        print(f"    OK: {mem9_ok} | write={result.get('write_status')} | hits={result.get('search_total')}")
    except Exception as e:
        print(f"    FAIL: {e}")

    sumopod_ok = False
    print("\n[2] Sumopod LLM (all model roles)")
    try:
        from backend import sumopod_client

        result = sumopod_client.test_all_roles()
        sumopod_ok = bool(result.get("ok"))
        for r in result.get("results", []):
            status = "PASS" if r.get("ok") else "FAIL"
            print(f"    [{status}] {r.get('role')}: model={r.get('model')}")
    except Exception as e:
        print(f"    FAIL: {e}")

    print("\n[3] Repliz (medsos)")
    try:
        from backend import repliz_client

        result = repliz_client.test_connection()
        if result.get("skipped"):
            print("    SKIP: credentials not set (OK for MVP)")
            repliz_ok = True
        else:
            repliz_ok = bool(result.get("ok"))
            print(f"    OK: {repliz_ok} | accounts={result.get('account_count', 0)}")
    except Exception as e:
        print(f"    FAIL: {e}")
        repliz_ok = False

    print("\n=== Summary ===")
    print(f"Mem9:    {'PASS' if mem9_ok else 'FAIL'}")
    print(f"Sumopod: {'PASS' if sumopod_ok else 'FAIL'}")
    print(f"Repliz:  {'PASS/SKIP' if repliz_ok else 'FAIL'}")
    return 0 if (mem9_ok and sumopod_ok and repliz_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
