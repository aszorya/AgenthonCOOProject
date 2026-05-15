"""Central config: Sumopod LLM credentials + model slugs per role."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


# Bahan baku inti yang dicari vendornya (paling sering dipakai)
MAX_CORE_SUPPLIES = 4

class ModelRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    SUB_AGENT = "sub_agent"
    DEMO = "demo"


_ROLE_ENV: dict[ModelRole, str] = {
    ModelRole.ORCHESTRATOR: "MODEL_ORCHESTRATOR",
    ModelRole.SUB_AGENT: "MODEL_SUB_AGENT",
    ModelRole.DEMO: "MODEL_DEMO",
}

_DEFAULT_MODEL: dict[ModelRole, str] = {
    ModelRole.ORCHESTRATOR: "gpt-4o-mini",
    ModelRole.SUB_AGENT: "deepseek-v3-2",
    ModelRole.DEMO: "claude-haiku-4-5",
}


def get_model(role: ModelRole) -> str:
    return os.getenv(_ROLE_ENV[role], _DEFAULT_MODEL[role]).strip()


def _env(name: str, fallback: str = "") -> str:
    return (os.getenv(name) or fallback).strip()


def get_sumopod_api_key() -> str:
    key = _env("SUMOPOD_API_KEY") or _env("LLM_API_KEY")
    if not key or key.startswith("your_"):
        raise ValueError("Set SUMOPOD_API_KEY in coopilot/.env")
    return key


def get_sumopod_base_url() -> str:
    return _env("SUMOPOD_API_BASE_URL") or _env("LLM_API_BASE_URL") or "https://ai.sumopod.com/v1"
