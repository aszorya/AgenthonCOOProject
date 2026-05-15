"""Inventory & auto-reorder state per company (Mem9 + cache)."""

from __future__ import annotations

import json
from typing import Any

from backend import mem9_client
from backend.business_profile import _user_tag

INVENTORY_TAG = "inventory"
_inventory_cache: dict[str, list[dict[str, Any]]] = {}
DEFAULT_REORDER_THRESHOLD = 20  # percent of initial qty


def _cache_key(chat_id: int | str) -> str:
    return str(chat_id)


def list_inventory(chat_id: int | str) -> list[dict[str, Any]]:
    key = _cache_key(chat_id)
    if key in _inventory_cache:
        return list(_inventory_cache[key])

    items: list[dict[str, Any]] = []
    if not mem9_client.is_configured():
        return items

    try:
        hits = mem9_client.search_memory("", tags=[_user_tag(chat_id), INVENTORY_TAG], limit=50)
        for m in hits.get("memories") or []:
            meta = m.get("metadata") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            raw = meta.get("inventory_json")
            if raw:
                row = json.loads(raw)
                if row.get("item"):
                    items.append(row)
    except Exception:
        pass

    _inventory_cache[key] = items
    return items


def seed_from_supplies(chat_id: int | str, supply_needs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Initialize inventory rows from supply analysis (default qty 100 units)."""
    seeded: list[dict[str, Any]] = []
    for need in supply_needs:
        name = need.get("name") or need.get("category") or "item"
        qty = int(need.get("default_qty", 100))
        row = {
            "item": name,
            "qty": qty,
            "initial_qty": qty,
            "reorder_threshold_pct": DEFAULT_REORDER_THRESHOLD,
            "unit": need.get("unit", "unit"),
            "linked_vendor": need.get("preferred_vendor"),
        }
        _save_row(chat_id, row)
        seeded.append(row)
    return seeded


def _save_row(chat_id: int | str, row: dict[str, Any]) -> None:
    if mem9_client.is_configured():
        mem9_client.add_memory(
            f"Inventory {row.get('item')} qty={row.get('qty')} for telegram {chat_id}",
            tags=["coopilot", INVENTORY_TAG, _user_tag(chat_id), f"inv_{row.get('item', '')[:20]}"],
            metadata={"inventory_json": json.dumps(row, ensure_ascii=False)},
            sync=True,
        )
    key = _cache_key(chat_id)
    existing = [r for r in list_inventory(chat_id) if r.get("item") != row.get("item")]
    existing.append(row)
    _inventory_cache[key] = existing


def update_stock(chat_id: int | str, item: str, qty: int) -> dict[str, Any]:
    item = item.strip()
    rows = list_inventory(chat_id)
    row = next((r for r in rows if r.get("item", "").lower() == item.lower()), None)
    if not row:
        row = {
            "item": item,
            "qty": qty,
            "initial_qty": qty,
            "reorder_threshold_pct": DEFAULT_REORDER_THRESHOLD,
            "unit": "unit",
        }
    else:
        row["qty"] = qty
        if not row.get("initial_qty"):
            row["initial_qty"] = qty
    _save_row(chat_id, row)
    return row


def deduct_stock(chat_id: int | str, item: str, amount: float) -> dict[str, Any]:
    """Kurangi stok bahan baku setelah penjualan."""
    item = item.strip()
    rows = list_inventory(chat_id)
    row = next((r for r in rows if r.get("item", "").lower() == item.lower()), None)
    if not row:
        row = {
            "item": item,
            "qty": 100,
            "initial_qty": 100,
            "reorder_threshold_pct": DEFAULT_REORDER_THRESHOLD,
            "unit": "unit",
        }
    amt = max(0.0, float(amount))
    prev = float(row.get("qty", 0))
    new_qty = max(0.0, prev - amt)
    row["qty"] = int(new_qty) if new_qty == int(new_qty) else round(new_qty, 2)
    if not row.get("initial_qty"):
        row["initial_qty"] = max(int(prev), 100)
    _save_row(chat_id, row)
    return row


def items_needing_reorder(chat_id: int | str) -> list[dict[str, Any]]:
    low: list[dict[str, Any]] = []
    for row in list_inventory(chat_id):
        qty = int(row.get("qty", 0))
        initial = int(row.get("initial_qty", qty) or qty or 100)
        threshold = int(row.get("reorder_threshold_pct", DEFAULT_REORDER_THRESHOLD))
        min_qty = max(1, (initial * threshold) // 100)
        if qty <= min_qty:
            low.append({**row, "reorder": True, "min_qty": min_qty})
    return low
