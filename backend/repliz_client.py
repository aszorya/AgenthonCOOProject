"""Repliz — tool API medsos (bukan LLM). https://api.repliz.com"""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

REPLIZ_BASE = "https://api.repliz.com"


def is_configured() -> bool:
    access = os.getenv("REPLIZ_ACCESS_KEY", "").strip()
    secret = os.getenv("REPLIZ_SECRET_KEY", "").strip()
    return bool(access and secret) and not access.startswith("your_")


def _auth() -> tuple[str, str]:
    if not is_configured():
        raise ValueError("Set REPLIZ_ACCESS_KEY and REPLIZ_SECRET_KEY in coopilot/.env")
    return os.getenv("REPLIZ_ACCESS_KEY", "").strip(), os.getenv("REPLIZ_SECRET_KEY", "").strip()


def list_accounts() -> list[dict[str, Any]]:
    """GET /public/account — akun medsos terhubung."""
    r = requests.get(f"{REPLIZ_BASE}/public/account", auth=_auth(), timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        return data
    return data.get("data") or data.get("accounts") or []


def get_schedules(limit: int = 10) -> dict[str, Any]:
    """GET /public/schedule — jadwal posting terbaru."""
    r = requests.get(
        f"{REPLIZ_BASE}/public/schedule",
        auth=_auth(),
        params={"limit": limit},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def test_connection() -> dict[str, Any]:
    if not is_configured():
        return {"ok": False, "skipped": True, "message": "Repliz credentials not set"}
    accounts = list_accounts()
    return {"ok": True, "account_count": len(accounts), "accounts": accounts[:3]}
