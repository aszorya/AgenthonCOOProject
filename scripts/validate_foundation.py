"""Phase 1 — validasi fondasi Sumopod saja (abaikan Mem9 & DOKU).

Run from coopilot/:
  .\\.venv\\Scripts\\python scripts\\validate_foundation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _check_env() -> list[str]:
    from backend.config import ModelRole, get_model, get_sumopod_api_key, get_sumopod_base_url

    issues: list[str] = []
    try:
        key = get_sumopod_api_key()
        if len(key) < 10:
            issues.append("SUMOPOD_API_KEY terlalu pendek")
    except ValueError as e:
        issues.append(str(e))

    base = get_sumopod_base_url()
    if not base.startswith("http"):
        issues.append("SUMOPOD_API_BASE_URL tidak valid")

    print("  Config:")
    print(f"    base_url: {base}")
    print(f"    orchestrator model: {get_model(ModelRole.ORCHESTRATOR)}")
    print(f"    sub_agent model:    {get_model(ModelRole.SUB_AGENT)}")
    print(f"    demo model:         {get_model(ModelRole.DEMO)}")
    return issues


def _test_sumopod_roles() -> tuple[bool, list[dict]]:
    from backend import sumopod_client

    print("\n[2] Sumopod — ping tiap model role")
    result = sumopod_client.test_all_roles()
    rows = result.get("results") or []
    for r in rows:
        status = "PASS" if r.get("ok") else "FAIL"
        print(f"    [{status}] {r.get('role')}: {r.get('model')}")
        if r.get("reply"):
            print(f"           → {str(r.get('reply'))[:120]}")
        if r.get("error"):
            print(f"           error: {r['error']}")
    return bool(result.get("ok")), rows


def _test_sumopod_roles_safe() -> tuple[bool, list[dict]]:
    from backend.config import ModelRole
    from backend import sumopod_client

    print("\n[2] Sumopod — ping tiap model role")
    rows: list[dict] = []
    all_ok = True
    for role in ModelRole:
        try:
            r = sumopod_client.test_role(role)
            rows.append(r)
            status = "PASS" if r.get("ok") else "FAIL"
            print(f"    [{status}] {r.get('role')}: {r.get('model')}")
            if r.get("reply"):
                print(f"           → {str(r.get('reply'))[:120]}")
        except Exception as e:
            all_ok = False
            from backend.config import get_model

            row = {"role": role.value, "model": get_model(role), "ok": False, "error": str(e)}
            rows.append(row)
            print(f"    [FAIL] {role.value}: {get_model(role)}")
            print(f"           error: {e}")
    return all_ok, rows


def _test_orchestrator_smoke() -> bool:
    print("\n[3] Orchestrator smoke (gpt-4o-mini)")
    try:
        from backend.orchestrator import orchestrate_plan

        plan = orchestrate_plan(
            "Meningkatkan penjualan coffee shop online dalam 1 bulan",
            "Budget marketing 2 juta",
        )
        ok = len(plan.strip()) > 20
        print(f"    [{'PASS' if ok else 'FAIL'}] plan length={len(plan)} chars")
        if ok:
            print(f"           preview: {plan[:180].replace(chr(10), ' ')}...")
        return ok
    except Exception as e:
        print(f"    [FAIL] {e}")
        return False


def _test_strategy_agent_smoke() -> bool:
    print("\n[4] Strategy agent smoke (sub-agent model)")
    try:
        from backend.agents.strategy_agent import StrategyAgent

        result = StrategyAgent().run({"user_goal": "Tingkatkan repeat customer coffee shop"})
        ok = result.status == "ok" and bool(result.data.get("plan"))
        print(f"    [{'PASS' if ok else 'FAIL'}] status={result.status}")
        if result.data.get("plan"):
            preview = str(result.data["plan"])[:180].replace("\n", " ")
            print(f"           preview: {preview}...")
        elif result.message:
            print(f"           message: {result.message}")
        return ok
    except Exception as e:
        print(f"    [FAIL] {e}")
        return False


def main() -> int:
    print("=== COOPilot Phase 1: Foundation Validation ===")
    print("    (Mem9 & DOKU diabaikan — belum ada API key resmi)\n")

    print("[1] Environment & model config")
    env_issues = _check_env()
    if env_issues:
        for i in env_issues:
            print(f"    [FAIL] {i}")
        return 1
    print("    [PASS] env OK")

    sumopod_ok, _ = _test_sumopod_roles_safe()
    orch_ok = _test_orchestrator_smoke()
    strat_ok = _test_strategy_agent_smoke()

    print("\n=== Phase 1 Summary ===")
    checks = {
        "Sumopod (3 models)": sumopod_ok,
        "Orchestrator": orch_ok,
        "Strategy agent": strat_ok,
    }
    for name, ok in checks.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")

    all_pass = all(checks.values())
    if not all_pass:
        print("\n  Tips jika model FAIL:")
        print("  - Cek slug model di dashboard Sumopod (MODEL_* di .env)")
        print("  - Coba ganti deepseek-v4-flash → deepseek-chat jika tidak dikenali")
        print("  - Coba ganti Haiku ke slug yang tercantum di Sumopod")
    else:
        print("\n  Fondasi siap — lanjut Phase 2 (vendor payment workflow).")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
