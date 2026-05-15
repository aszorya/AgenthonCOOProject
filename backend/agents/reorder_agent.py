from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend import inventory_service
from backend.supplier_registry import find_supplier, list_suppliers


class ReorderAgent(BaseAgent):
    """Deteksi stok rendah dan siapkan pemesanan ulang ke vendor terkait."""

    name = "reorder"

    def run(self, context: dict[str, Any]) -> AgentResult:
        chat_id = context.get("chat_id")
        if not chat_id:
            return AgentResult(self.name, "skipped", "No chat_id", {})

        low_items = inventory_service.items_needing_reorder(chat_id)
        if not low_items:
            return AgentResult(self.name, "ok", "Stok masih cukup", {"reorder_items": []})

        suppliers = list_suppliers(chat_id)
        orders: list[dict[str, Any]] = []

        for item_row in low_items:
            item_name = item_row.get("item", "")
            vendor = None
            linked = item_row.get("linked_vendor")
            if linked:
                vendor = find_supplier(chat_id, str(linked))
            if not vendor and suppliers:
                vendor = find_supplier(chat_id, item_name) or suppliers[0]

            orders.append(
                {
                    "item": item_name,
                    "current_qty": item_row.get("qty"),
                    "min_qty": item_row.get("min_qty"),
                    "vendor": (vendor or {}).get("name"),
                    "vendor_id": (vendor or {}).get("supplier_id"),
                }
            )

        context["reorder_items"] = low_items
        context["reorder_orders"] = orders

        vendor = None
        if orders and orders[0].get("vendor"):
            vendor = find_supplier(chat_id, str(orders[0]["vendor"]))
        if not vendor and suppliers:
            vendor = suppliers[0]
        if vendor:
            context["selected_supplier"] = vendor
            context["payment_allowed"] = True
            context["vendor_name"] = vendor.get("name")
            context["payment_amount"] = int(vendor.get("default_monthly_amount") or 500_000)
            context["user_goal"] = f"Reorder otomatis: {', '.join(o['item'] for o in orders[:3])}"

        return AgentResult(
            self.name,
            "ok",
            f"{len(low_items)} bahan perlu dipesan ulang",
            {"reorder_items": low_items, "reorder_orders": orders},
        )
