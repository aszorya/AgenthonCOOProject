from __future__ import annotations

import json
import re
from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend import inventory_service


def _parse_deductions(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    rows = data.get("deductions") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("item", "")).strip()
        if not name:
            continue
        out.append(
            {
                "item": name,
                "amount": float(row.get("amount", 1)),
                "unit": str(row.get("unit", "unit")),
            }
        )
    return out


class SalesInventoryAgent(BaseAgent):
    """Dari produk yang laku → kurangi stok bahan baku."""

    name = "sales_inventory"

    def run(self, context: dict[str, Any]) -> AgentResult:
        chat_id = context.get("chat_id")
        sale = context.get("last_sale") or {}
        profile = context.get("profile") or {}

        if not chat_id or not sale.get("product"):
            return AgentResult(self.name, "blocked", "Data penjualan tidak lengkap", {})

        product = sale["product"]
        qty_sold = int(sale.get("qty", 1))
        business_type = profile.get("business_type", "")
        inv_rows = inventory_service.list_inventory(chat_id)
        inv_items = ", ".join(f"{r['item']} ({r.get('qty', 0)} {r.get('unit', 'unit')})" for r in inv_rows)

        prompt = f"""Bisnis: {business_type}
Penjualan: {qty_sold} unit produk "{product}"
Stok bahan baku saat ini: {inv_items or 'belum ada'}

Estimasi penggunaan bahan baku PER 1 unit produk terjual, lalu kalikan untuk {qty_sold} unit.
Balas JSON:
{{"deductions": [{{"item": "biji kopi", "amount": 0.04, "unit": "kg"}}]}}

Hanya item yang ada di daftar stok atau bahan inti bisnis ini. Jangan mengarang item aneh."""

        try:
            raw = self.llm_chat(
                prompt,
                system="COOPilot Sales-Inventory Agent. JSON only, realistic BOM.",
                max_tokens=400,
            )
            deductions = _parse_deductions(raw)
        except Exception as e:
            return AgentResult(self.name, "error", str(e), {})

        if not deductions:
            return AgentResult(self.name, "error", "Gagal parse pengurangan stok", {"raw": raw})

        updated: list[dict[str, Any]] = []
        for d in deductions:
            total_deduct = float(d["amount"]) * qty_sold
            row = inventory_service.deduct_stock(chat_id, d["item"], total_deduct)
            updated.append(
                {
                    "item": d["item"],
                    "deducted": total_deduct,
                    "remaining": row.get("qty"),
                    "unit": d.get("unit", row.get("unit")),
                }
            )

        return AgentResult(
            self.name,
            "ok",
            f"Stok diperbarui untuk {len(updated)} bahan baku",
            {"stock_updates": updated, "deductions": deductions},
        )
