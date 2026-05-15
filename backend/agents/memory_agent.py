from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent


class MemoryAgent(BaseAgent):
    """Only uses suppliers explicitly registered by this company — no global Mem9 guess."""

    name = "memory"

    def run(self, context: dict[str, Any]) -> AgentResult:
        suppliers = context.get("registered_suppliers") or []
        selected = context.get("selected_supplier")

        if not suppliers:
            return AgentResult(
                self.name,
                "blocked",
                "Belum ada vendor. Jalankan /mulai untuk discovery otomatis",
                {},
            )

        if selected:
            return AgentResult(
                self.name,
                "ok",
                f"Supplier terpilih: {selected.get('name')}",
                {
                    "vendor_name": selected.get("name"),
                    "supplier_contact": selected.get("phone_wa"),
                    "selected_supplier": selected,
                    "registered_suppliers": suppliers,
                },
            )

        names = ", ".join(s.get("name", "") for s in suppliers)
        return AgentResult(
            self.name,
            "ok",
            f"{len(suppliers)} supplier terdaftar: {names}",
            {"registered_suppliers": suppliers, "vendor_name": suppliers[0].get("name")},
        )
