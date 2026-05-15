"""Mem9 hosted API — add_memory / search_memory."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

MEM9_BASE = os.getenv("MEM9_BASE_URL", "https://api.mem9.ai/v1alpha2/mem9s").rstrip("/")
PROVISION_URL = "https://api.mem9.ai/v1alpha1/mem9s"


def is_configured() -> bool:
    api_key = os.getenv("MEM9_API_KEY", "").strip()
    return bool(api_key) and not api_key.startswith("your_")


def _headers() -> dict[str, str]:
    api_key = os.getenv("MEM9_API_KEY", "").strip()
    if not api_key or api_key.startswith("your_"):
        raise ValueError("Set MEM9_API_KEY in coopilot/.env (or run provision_key())")
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    agent_id = os.getenv("MEM9_AGENT_ID", "coopilot-main").strip()
    if agent_id:
        headers["X-Mnemo-Agent-Id"] = agent_id
    return headers


def provision_key() -> str:
    """Create a new Mem9 space key (no auth required)."""
    r = requests.post(PROVISION_URL, timeout=30)
    r.raise_for_status()
    data = r.json()
    key = data.get("id") or data.get("api_key")
    if not key:
        raise RuntimeError(f"Unexpected provision response: {data}")
    return str(key)


def add_memory(
    content: str,
    *,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    sync: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": content, "sync": sync}
    if tags:
        payload["tags"] = tags
    if metadata:
        payload["metadata"] = metadata
    r = requests.post(f"{MEM9_BASE}/memories", json=payload, headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()


def search_memory(
    query: str = "",
    *,
    limit: int = 5,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}
    if query:
        params["q"] = query
    if tags:
        params["tags"] = ",".join(tags)
    r = requests.get(f"{MEM9_BASE}/memories", params=params, headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()


def test_connection() -> dict[str, Any]:
    marker = "COOPilot dummy vendor: Kopi Nusantara (cost-efficient)"
    write = add_memory(marker, tags=["coopilot", "test", "vendor"], metadata={"source": "connection-test"})
    search = search_memory("Kopi Nusantara cost-efficient")
    memories = search.get("memories") or []
    hit = any(marker.split(":")[0] in (m.get("content") or "") for m in memories)
    return {"write_status": write.get("status"), "search_total": search.get("total", 0), "ok": hit or search.get("total", 0) > 0, "sample": memories[:1]}
