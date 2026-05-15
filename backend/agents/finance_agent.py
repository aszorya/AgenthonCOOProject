from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent


class FinanceAgent(BaseAgent):
    name = "finance"

    def run(self, context: dict[str, Any]) -> AgentResult:
        budget = float(context.get("budget_available", 2_000_000))
        amount = float(context.get("payment_amount", 500_000))
        ok = amount <= budget
        return AgentResult(
            self.name,
            "ok" if ok else "blocked",
            "Budget verified" if ok else "Insufficient budget",
            {"budget_available": budget, "payment_amount": amount, "remaining": budget - amount},
        )
