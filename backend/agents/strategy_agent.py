from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend.business_profile import build_business_context


class StrategyAgent(BaseAgent):
    name = "strategy"

    def run(self, context: dict[str, Any]) -> AgentResult:
        goal = context.get("user_goal", "")
        biz = build_business_context(context.get("profile"))
        suppliers = context.get("registered_suppliers") or []
        sup_text = (
            "Supplier terdaftar: " + ", ".join(f"{s.get('name')} ({s.get('products')})" for s in suppliers)
            if suppliers
            else "Belum ada supplier terdaftar."
        )
        prompt = (
            f"Business context: {biz}\n{sup_text}\n"
            f"Goal: {goal}\n"
            "Berikan 3 bullet strategi operasional. JANGAN mengarang nama perusahaan/supplier baru."
        )
        try:
            plan = self.llm_chat(
                prompt,
                system="COOPilot Strategy Agent. Only use provided facts.",
            )
            return AgentResult(self.name, "ok", "Strategy drafted", {"plan": plan})
        except Exception as e:
            return AgentResult(self.name, "error", str(e), {})
