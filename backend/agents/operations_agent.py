from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend import mem9_client
from backend.business_profile import _user_tag


class OperationsAgent(BaseAgent):
    name = "operations"

    def run(self, context: dict[str, Any]) -> AgentResult:
        if not context.get("payment_allowed"):
            return AgentResult(self.name, "skipped", "No payment executed", {})

        selected = context.get("selected_supplier") or {}
        vendor = selected.get("name") or context.get("vendor_name", "")
        amount = int(context.get("payment_amount", 0))
        invoice_id = context.get("invoice_id", "INV-001")
        payment_url = context.get("payment_url")
        chat_id = context.get("chat_id", "")
        ts = datetime.now(timezone.utc).isoformat()

        log_entry = {
            "timestamp": ts,
            "action": "vendor_payment_prepared",
            "vendor": vendor,
            "amount": amount,
            "invoice_id": invoice_id,
            "payment_url": payment_url,
            "status": context.get("payment_status", "pending"),
        }

        memory_saved = False
        memory_note = ""
        try:
            if mem9_client.is_configured() and chat_id and vendor:
                profile = context.get("profile") or {}
                biz = profile.get("business_name", "")
                content = (
                    f"Payment log for {biz} (telegram {chat_id}): "
                    f"Prepared Rp {amount:,} to registered supplier '{vendor}', invoice {invoice_id}."
                )
                mem9_client.add_memory(
                    content,
                    tags=["coopilot", "payment_log", _user_tag(chat_id)],
                    metadata={
                        "invoice_id": invoice_id,
                        "amount": amount,
                        "vendor": vendor,
                        "supplier_id": selected.get("supplier_id"),
                    },
                )
                memory_saved = True
                memory_note = "Riwayat pembayaran disimpan (scoped perusahaan Anda)"
        except Exception as e:
            memory_note = f"Log lokal saja: {e}"

        return AgentResult(
            self.name,
            "ok",
            "Operational log updated",
            {"log": log_entry, "memory_saved": memory_saved, "memory_note": memory_note},
        )
