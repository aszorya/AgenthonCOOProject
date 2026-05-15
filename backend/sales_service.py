"""Catatan penjualan harian dari dashboard kasir."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from backend import mem9_client
from backend.business_profile import _user_tag

SALES_TAG = "cashier_sales"
_sales_cache: dict[str, list[dict[str, Any]]] = {}


def _today() -> str:
    return date.today().isoformat()


def record_sale(
    chat_id: int | str,
    *,
    product: str,
    qty: int,
    cashier_name: str = "kasir",
    unit_price: float = 0,
) -> dict[str, Any]:
    sale = {
        "sale_id": f"SALE-{uuid.uuid4().hex[:8].upper()}",
        "date": _today(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "product": product.strip(),
        "qty": max(1, int(qty)),
        "cashier": cashier_name.strip() or "kasir",
        "unit_price": float(unit_price or 0),
        "total": float(unit_price or 0) * max(1, int(qty)),
        "chat_id": str(chat_id),
    }

    key = str(chat_id)
    _sales_cache.setdefault(key, []).append(sale)

    if mem9_client.is_configured():
        mem9_client.add_memory(
            f"Cashier sale {sale['sale_id']}: {sale['qty']}x {sale['product']} "
            f"by {sale['cashier']} on {sale['date']} (telegram {chat_id})",
            tags=["coopilot", SALES_TAG, _user_tag(chat_id), f"sale_{sale['date']}"],
            metadata={"sale_json": json.dumps(sale, ensure_ascii=False)},
            sync=True,
        )
    return sale


def list_sales(chat_id: int | str, *, day: str | None = None) -> list[dict[str, Any]]:
    day = day or _today()
    key = str(chat_id)
    cached = [s for s in _sales_cache.get(key, []) if s.get("date") == day]

    if mem9_client.is_configured():
        try:
            hits = mem9_client.search_memory(
                "",
                tags=[_user_tag(chat_id), SALES_TAG, f"sale_{day}"],
                limit=100,
            )
            from_mem9: list[dict[str, Any]] = []
            seen: set[str] = set()
            for m in hits.get("memories") or []:
                meta = m.get("metadata") or {}
                if isinstance(meta, str):
                    meta = json.loads(meta)
                raw = meta.get("sale_json")
                if raw:
                    row = json.loads(raw)
                    sid = row.get("sale_id")
                    if sid and sid not in seen:
                        seen.add(sid)
                        from_mem9.append(row)
            if from_mem9:
                merged = {s["sale_id"]: s for s in cached}
                for s in from_mem9:
                    merged[s["sale_id"]] = s
                return sorted(merged.values(), key=lambda x: x.get("timestamp", ""))
        except Exception:
            pass

    return sorted(cached, key=lambda x: x.get("timestamp", ""))


def daily_summary(chat_id: int | str, *, day: str | None = None) -> dict[str, Any]:
    sales = list_sales(chat_id, day=day)
    total_qty = sum(int(s.get("qty", 0)) for s in sales)
    total_revenue = sum(float(s.get("total", 0)) for s in sales)
    by_product: dict[str, int] = {}
    for s in sales:
        p = s.get("product", "?")
        by_product[p] = by_product.get(p, 0) + int(s.get("qty", 0))
    return {
        "date": day or _today(),
        "transaction_count": len(sales),
        "total_qty": total_qty,
        "total_revenue": total_revenue,
        "by_product": by_product,
        "sales": sales,
    }
