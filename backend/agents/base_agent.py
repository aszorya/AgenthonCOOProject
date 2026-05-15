from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.config import ModelRole
from backend import sumopod_client


@dataclass
class AgentResult:
    agent: str
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Semua agen executor punya akses LLM via sumopod_client."""

    name: str = "base"
    llm_role: ModelRole = ModelRole.SUB_AGENT

    def llm_chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        role: ModelRole | None = None,
        max_tokens: int = 512,
    ) -> str:
        return sumopod_client.chat(
            prompt,
            system=system,
            role=role or self.llm_role,
            max_tokens=max_tokens,
        )

    @abstractmethod
    def run(self, context: dict[str, Any]) -> AgentResult:
        ...
