"""Registered suppliers per Telegram company — only these may be paid."""

from __future__ import annotations

import json
import uuid
from typing import Any

from backend import mem9_client
from backend.business_profile import _user_tag

SUPPLIER_TAG = "supplier_registry"
_supplier_cache: dict[str, list[dict[str, Any]]] = {}
_supplier_ignore_mem9: set[str] = set()


def _cache_key(chat_id: int | str) -> str:
    return str(chat_id)


def vendor_dedupe_key(supplier: dict[str, Any]) -> str:
    """Satu toko fisik = satu kunci (OSM id atau nama)."""
    oid = (supplier.get("osm_id") or "").strip()
    if oid:
        return f"osm:{oid}"
    name = (supplier.get("name") or "").strip().lower()
    if name:
        return f"name:{name}"
    return ""


def _merge_product_labels(existing: str, new_label: str) -> str:
    parts: list[str] = []
    for raw in f"{existing}, {new_label}".split(","):
        p = raw.strip()
        if p and p not in parts:
            parts.append(p)
    return ", ".join(parts)


def dedupe_suppliers(suppliers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gabung entri duplikat (toko sama, produk berbeda)."""
    merged: dict[str, dict[str, Any]] = {}
    for s in suppliers:
        key = vendor_dedupe_key(s)
        if not key:
            continue
        if key in merged:
            m = merged[key]
            m["products"] = _merge_product_labels(
                str(m.get("products") or ""),
                str(s.get("products") or s.get("supply_category") or ""),
            )
            if s.get("phone_wa") and not m.get("phone_wa"):
                m["phone_wa"] = s["phone_wa"]
            if s.get("phone") and not m.get("phone_wa"):
                m["phone_wa"] = s["phone"]
        else:
            row = dict(s)
            if not row.get("products") and row.get("supply_category"):
                row["products"] = row["supply_category"]
            merged[key] = row
    return list(merged.values())


def cache_suppliers(chat_id: int | str, suppliers: list[dict[str, Any]]) -> None:
    _supplier_cache[_cache_key(chat_id)] = dedupe_suppliers(suppliers)


def clear_suppliers_local(chat_id: int | str) -> None:
    """Kosongkan vendor di sesi ini; tidak tarik ulang Mem9 sampai ada save/discovery baru."""
    key = _cache_key(chat_id)
    _supplier_cache[key] = []
    _supplier_ignore_mem9.add(key)


def allow_mem9_suppliers(chat_id: int | str) -> None:
    _supplier_ignore_mem9.discard(_cache_key(chat_id))


def supplier_from_discovery(item: dict[str, Any]) -> dict[str, Any]:
    """Map OSM discovery row to registrable supplier draft."""
    return {
        "name": item.get("name", ""),
        "contact_person": item.get("name", ""),
        "phone_wa": item.get("phone") or item.get("phone_wa") or "",
        "address": item.get("address", ""),
        "products": item.get("products") or item.get("supply_category") or item.get("shop_type", "bahan/supply"),
        "default_monthly_amount": 0,
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "source": "auto_discovery",
        "osm_id": item.get("osm_id"),
    }


def save_supplier(chat_id: int | str, supplier: dict[str, Any]) -> dict[str, Any]:
    allow_mem9_suppliers(chat_id)
    supplier = {
        **supplier,
        "chat_id": str(chat_id),
        "source": supplier.get("source") or "registered",
    }
    key = vendor_dedupe_key(supplier)
    existing = dedupe_suppliers(list_suppliers(chat_id, use_cache=False))

    if key:
        for i, ex in enumerate(existing):
            if vendor_dedupe_key(ex) == key:
                supplier["supplier_id"] = ex.get("supplier_id") or f"SUP-{uuid.uuid4().hex[:8].upper()}"
                merged_products = _merge_product_labels(
                    str(ex.get("products") or ""),
                    str(supplier.get("products") or ""),
                )
                existing[i] = {**ex, **supplier, "products": merged_products}
                supplier = existing[i]
                cache_suppliers(chat_id, existing)
                _persist_supplier_mem9(chat_id, supplier)
                return supplier

    supplier["supplier_id"] = supplier.get("supplier_id") or f"SUP-{uuid.uuid4().hex[:8].upper()}"
    existing.append(supplier)
    cache_suppliers(chat_id, existing)
    _persist_supplier_mem9(chat_id, supplier)
    return supplier


def _persist_supplier_mem9(chat_id: int | str, supplier: dict[str, Any]) -> None:
    if not mem9_client.is_configured():
        return
    content = (
        f"COOPilot registered supplier (telegram {chat_id}): "
        f"Name={supplier.get('name')}; Contact={supplier.get('contact_person')}; "
        f"WA={supplier.get('phone_wa')}; Telegram={supplier.get('telegram_id', '-')}; "
        f"DOKU={supplier.get('doku_id', '-')}; Address={supplier.get('address', '-')}; "
        f"Products={supplier.get('products')}; "
        f"DefaultAmount=Rp {supplier.get('default_monthly_amount')}."
    )
    mem9_client.add_memory(
        content,
        tags=["coopilot", SUPPLIER_TAG, _user_tag(chat_id), f"sup_{supplier['supplier_id']}"],
        metadata={"supplier_json": json.dumps(supplier, ensure_ascii=False), "chat_id": str(chat_id)},
        sync=True,
    )


def _parse_supplier(meta: dict, content: str) -> dict[str, Any] | None:
    raw = meta.get("supplier_json") if meta else None
    if raw:
        return json.loads(raw)
    return None


def list_suppliers(chat_id: int | str, *, use_cache: bool = True) -> list[dict[str, Any]]:
    key = _cache_key(chat_id)
    if use_cache and key in _supplier_cache:
        return list(_supplier_cache[key])

    if key in _supplier_ignore_mem9:
        return []

    if not mem9_client.is_configured():
        return _supplier_cache.get(key, [])

    suppliers: list[dict[str, Any]] = []
    try:
        hits = mem9_client.search_memory("", tags=[_user_tag(chat_id), SUPPLIER_TAG], limit=50)
        for m in hits.get("memories") or []:
            meta = m.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            sup = _parse_supplier(meta, m.get("content") or "")
            if sup and sup.get("name"):
                suppliers.append(sup)
    except Exception:
        pass

    suppliers = dedupe_suppliers(suppliers)
    cache_suppliers(chat_id, suppliers)
    return suppliers


def has_suppliers(chat_id: int | str) -> bool:
    return len(list_suppliers(chat_id)) > 0


def find_supplier(chat_id: int | str, name_query: str) -> dict[str, Any] | None:
    q = (name_query or "").strip().lower()
    if not q:
        return None
    for s in list_suppliers(chat_id):
        if q in (s.get("name") or "").lower():
            return s
    return None


def format_supplier_list(chat_id: int | str) -> str:
    from backend.supplier_matching import is_manual_supplier

    suppliers = list_suppliers(chat_id)
    if not suppliers:
        return "Belum ada supplier terdaftar."
    lines = []
    for i, s in enumerate(suppliers, 1):
        src = "manual" if is_manual_supplier(s) else s.get("source", "auto")
        extra = []
        if s.get("address"):
            extra.append(f"📍 {s['address'][:60]}")
        if s.get("telegram_id"):
            extra.append(f"TG: `{s['telegram_id']}`")
        if s.get("doku_id"):
            extra.append(f"DOKU: `{s['doku_id']}`")
        detail = "\n   ".join(extra) if extra else ""
        lines.append(
            f"{i}. *{s.get('name')}* [{src}] — {s.get('products', '-')}\n"
            f"   WA: {s.get('phone_wa') or '-'} | Rp {int(s.get('default_monthly_amount', 0)):,}/bulan"
            + (f"\n   {detail}" if detail else "")
        )
    return "\n".join(lines)
