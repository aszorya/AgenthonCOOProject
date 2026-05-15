from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend import repliz_client


class SocialAgent(BaseAgent):
    """Agen medsos — Repliz untuk eksekusi, Sumopod untuk draft konten."""

    name = "social"

    def run(self, context: dict[str, Any]) -> AgentResult:
        topic = context.get("social_topic", context.get("user_goal", "promo kopi online"))
        if not repliz_client.is_configured():
            try:
                draft = self.llm_chat(
                    f"Write a short Instagram caption (max 80 words) for: {topic}",
                    system="You are COOPilot Social Agent. Casual, engaging.",
                )
                return AgentResult(
                    self.name,
                    "skipped",
                    "Repliz not configured — draft only",
                    {"caption_draft": draft, "repliz_connected": False},
                )
            except Exception as e:
                return AgentResult(self.name, "error", str(e), {})

        try:
            accounts = repliz_client.list_accounts()
            draft = self.llm_chat(
                f"Write a short Instagram caption for: {topic}. Brand: coffee shop online.",
                system="You are COOPilot Social Agent.",
            )
            return AgentResult(
                self.name,
                "ok",
                f"Social ready ({len(accounts)} account(s) on Repliz)",
                {
                    "caption_draft": draft,
                    "repliz_connected": True,
                    "accounts": accounts[:5],
                },
            )
        except Exception as e:
            return AgentResult(self.name, "error", str(e), {})
