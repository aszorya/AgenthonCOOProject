from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend import inventory_service


class InventoryAgent(BaseAgent):
    """Seed inventory & cek auto-reorder."""

    name = "inventory"

    def run(self, context: dict[str, Any]) -> AgentResult:
        chat_id = context.get("chat_id")
        if not chat_id:
            return AgentResult(self.name, "skipped", "No chat_id", {})

        mode = context.get("inventory_mode", "seed")

        if mode == "check_reorder":
            low = inventory_service.items_needing_reorder(chat_id)
            if not low:
                return AgentResult(self.name, "ok", "Stok masih aman", {"reorder_items": []})
            return AgentResult(
                self.name,
                "ok",
                f"{len(low)} item perlu reorder otomatis",
                {"reorder_items": low, "auto_reorder_triggered": True},
            )

        supplies = context.get("supply_needs") or []
        if not supplies:
            return AgentResult(self.name, "skipped", "Tidak ada supply untuk di-inventory", {})

        vendors = context.get("discovered_vendors") or []
        enriched = []
        for need in supplies:
            n = need.get("name", "")
            linked = next(
                (v.get("name") for v in vendors if (v.get("supply_category") or "").lower() == n.lower()),
                None,
            )
            enriched.append({**need, "preferred_vendor": linked})
        seeded = inventory_service.seed_from_supplies(chat_id, enriched)
        return AgentResult(
            self.name,
            "ok",
            f"Inventory diinisialisasi ({len(seeded)} item)",
            {"inventory": seeded},
        )
