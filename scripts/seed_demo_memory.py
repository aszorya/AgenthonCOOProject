"""Seed Mem9 with coffee shop demo context for vendor payment workflow."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEEDS = [
    (
        "Business: Kopi Senja — online coffee shop. Monthly ops budget Rp 2.000.000. "
        "User prefers cost-efficient vendors over premium suppliers.",
        ["coopilot", "business", "profile"],
    ),
    (
        "Preferred coffee bean supplier: Kopi Nusantara (cost-efficient, reliable delivery, "
        "typical monthly order Rp 500.000).",
        ["coopilot", "vendor", "supplier", "coffee"],
    ),
    (
        "Last month paid Kopi Nusantara for beans. User satisfied with price vs quality ratio.",
        ["coopilot", "payment", "history"],
    ),
]


def main() -> int:
    from backend import mem9_client

    if not mem9_client.is_configured():
        print("FAIL: MEM9_API_KEY not set")
        return 1

    print("Seeding Mem9 demo memories...")
    for content, tags in SEEDS:
        r = mem9_client.add_memory(content, tags=tags, metadata={"source": "seed_demo"})
        print(f"  [{r.get('status', 'ok')}] {content[:60]}...")

    hits = mem9_client.search_memory("supplier kopi cost-efficient", limit=3)
    print(f"\nVerify search: {hits.get('total', 0)} hit(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
