from __future__ import annotations

import uuid
from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend import doku_client


class PaymentAgent(BaseAgent):
    name = "payment"

    def run(self, context: dict[str, Any]) -> AgentResult:
        if not context.get("payment_allowed"):
            return AgentResult(
                self.name,
                "blocked",
                "Pembayaran ditolak: supplier belum dipilih/didaftarkan",
                {},
            )

        selected = context.get("selected_supplier")
        if not selected or not selected.get("name"):
            return AgentResult(
                self.name,
                "blocked",
                "Tidak ada vendor valid. Jalankan /mulai lalu /bayar <nama>",
                {},
            )

        amount = int(context.get("payment_amount") or selected.get("default_monthly_amount") or 0)
        if amount <= 0:
            return AgentResult(self.name, "blocked", "Nominal pembayaran tidak valid", {})

        vendor = selected["name"]
        vendor_doku = (selected.get("doku_id") or "").strip()
        invoice_id = context.get("invoice_id") or f"INV-{selected.get('supplier_id', 'COO')}-{uuid.uuid4().hex[:6].upper()}"

        desc = f"Pembayaran ke {vendor} — {selected.get('products', '')}"
        if vendor_doku:
            desc += f" | DOKU vendor: {vendor_doku}"

        try:
            link = doku_client.generate_payment_link(
                amount,
                invoice_id,
                desc,
                vendor_doku_id=vendor_doku,
                payee_name=vendor,
            )
            data = {
                **link,
                "invoice_id": link.get("invoice_id") or invoice_id,
                "payment_url": link.get("payment_url"),
                "payment_status": "pending",
                "vendor_name": vendor,
                "vendor_doku_id": vendor_doku,
                "payment_amount": amount,
            }
            msg = "DOKU payment link generated"
            if vendor_doku:
                msg += f" (vendor DOKU: {vendor_doku})"
            if not data.get("payment_url"):
                msg = "Payment prepared (no URL)"
            return AgentResult(self.name, "ok", msg, data)
        except Exception as e:
            return AgentResult(self.name, "error", str(e), {"invoice_id": invoice_id, "amount": amount})
