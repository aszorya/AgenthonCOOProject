"""Sumopod — pusat pemanggilan LLM (OpenAI-compatible, multi-model per role)."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from backend.config import ModelRole, get_model, get_sumopod_api_key, get_sumopod_base_url

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_sumopod_api_key(), base_url=get_sumopod_base_url())
    return _client


def chat(
    prompt: str,
    *,
    system: str | None = None,
    role: ModelRole = ModelRole.SUB_AGENT,
    max_tokens: int = 512,
) -> str:
    model = get_model(role)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = get_client().chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


def test_role(role: ModelRole) -> dict[str, Any]:
    reply = chat(
        "Reply with exactly: COOPilot OK",
        system="Connectivity test. One short line only.",
        role=role,
        max_tokens=32,
    )
    return {
        "role": role.value,
        "model": get_model(role),
        "ok": bool(reply),
        "reply": reply,
    }


def test_all_roles() -> dict[str, Any]:
    results = [test_role(r) for r in ModelRole]
    return {"ok": all(r["ok"] for r in results), "results": results}
