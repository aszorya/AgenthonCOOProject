"""Business profile — onboarding per Telegram user, stored in Mem9."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from backend import mem9_client

PROFILE_TAG = "business_profile"
_profile_cache: dict[str, dict[str, Any]] = {}

# Satu bisnis aktif = pemilik yang terakhir /setup (dipakai dashboard kasir)
_ACTIVE_BUSINESS_PATH = Path(__file__).resolve().parents[1] / "data" / "active_business.json"

REQUIRED_FIELDS = (
    "business_name",
    "business_type",
    "budget",
    "latitude",
    "longitude",
)


def _user_tag(chat_id: int | str) -> str:
    return f"telegram_{chat_id}"


def cache_profile(chat_id: int | str, profile: dict[str, Any]) -> None:
    _profile_cache[str(chat_id)] = profile


def is_profile_complete(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    for key in REQUIRED_FIELDS:
        val = profile.get(key)
        if val is None or (isinstance(val, str) and not str(val).strip()):
            return False
    return True


def set_active_business_chat_id(chat_id: int | str) -> None:
    """Tandai bisnis aktif (pemilik yang /setup) — dipakai dashboard kasir otomatis."""
    cid = str(chat_id)
    _ACTIVE_BUSINESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ACTIVE_BUSINESS_PATH.write_text(
        json.dumps({"chat_id": cid}, ensure_ascii=False),
        encoding="utf-8",
    )


def get_active_business_chat_id() -> str | None:
    if not _ACTIVE_BUSINESS_PATH.is_file():
        return None
    try:
        data = json.loads(_ACTIVE_BUSINESS_PATH.read_text(encoding="utf-8"))
        cid = str(data.get("chat_id") or "").strip()
        return cid or None
    except (json.JSONDecodeError, OSError):
        return None


def _profiles_from_mem9_search() -> dict[str, dict[str, Any]]:
    """Semua profil bisnis di Mem9 (chat_id → profile)."""
    found: dict[str, dict[str, Any]] = {}
    if not mem9_client.is_configured():
        return found
    try:
        hits = mem9_client.search_memory("", tags=["coopilot", PROFILE_TAG], limit=50)
        for m in hits.get("memories") or []:
            meta = m.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            raw = meta.get("profile_json")
            cid = str(meta.get("chat_id") or "").strip()
            if raw and cid:
                profile = json.loads(raw)
                if is_profile_complete(profile):
                    found[cid] = profile
    except Exception:
        pass
    return found


def resolve_cashier_chat_id() -> tuple[str | None, dict[str, Any] | None]:
    """
    Chat ID untuk dashboard kasir — tanpa input manual.
    Prioritas: CASHIER_CHAT_ID (.env) → bisnis aktif (/setup) → cache → satu profil di Mem9.
    """
    env_id = (os.getenv("CASHIER_CHAT_ID") or "").strip()
    if env_id:
        profile = load_profile(env_id)
        if profile and is_profile_complete(profile):
            return env_id, profile

    active_id = get_active_business_chat_id()
    if active_id:
        profile = load_profile(active_id)
        if profile and is_profile_complete(profile):
            return active_id, profile

    complete_cached = {
        cid: p
        for cid, p in _profile_cache.items()
        if is_profile_complete(p)
    }
    if len(complete_cached) == 1:
        cid = next(iter(complete_cached))
        return cid, complete_cached[cid]

    from_mem9 = _profiles_from_mem9_search()
    if active_id and active_id in from_mem9:
        return active_id, from_mem9[active_id]
    if len(from_mem9) == 1:
        cid = next(iter(from_mem9))
        set_active_business_chat_id(cid)
        return cid, from_mem9[cid]
    if len(from_mem9) > 1 and active_id in from_mem9:
        return active_id, from_mem9[active_id]

    return None, None


def save_profile(chat_id: int | str, profile: dict[str, Any]) -> dict[str, Any]:
    payload = {**profile, "chat_id": str(chat_id)}
    cache_profile(chat_id, payload)
    set_active_business_chat_id(chat_id)
    loc = f" Location: {profile.get('latitude')},{profile.get('longitude')} ({profile.get('location_label', '')})."
    content = (
        f"COOPilot business profile (telegram {chat_id}): "
        f"Brand '{profile.get('business_name')}' ({profile.get('business_type')}). "
        f"Budget Rp {profile.get('budget')}.{loc}"
    )
    return mem9_client.add_memory(
        content,
        tags=["coopilot", PROFILE_TAG, _user_tag(chat_id)],
        metadata={"profile_json": json.dumps(payload, ensure_ascii=False), "chat_id": str(chat_id)},
        sync=True,
    )


def save_location(chat_id: int | str, lat: float, lon: float, label: str = "") -> dict[str, Any]:
    profile = load_profile(chat_id) or {"chat_id": str(chat_id)}
    profile["latitude"] = lat
    profile["longitude"] = lon
    profile["location_label"] = label
    return save_profile(chat_id, profile)


def _parse_profile_from_content(content: str) -> dict[str, Any] | None:
    if "Brand '" not in content:
        return None
    name_m = re.search(r"Brand '([^']+)'", content)
    if not name_m:
        return None
    return {"business_name": name_m.group(1).strip()}


def load_profile(chat_id: int | str) -> dict[str, Any] | None:
    cached = _profile_cache.get(str(chat_id))
    if cached and cached.get("business_name"):
        return cached

    if not mem9_client.is_configured():
        return cached

    try:
        hits = mem9_client.search_memory("", tags=[_user_tag(chat_id), PROFILE_TAG], limit=10)
        memories = hits.get("memories") or []
        if not memories:
            hits = mem9_client.search_memory(f"business profile telegram {chat_id}", limit=10)
            memories = hits.get("memories") or []

        for m in memories:
            meta = m.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            raw = meta.get("profile_json")
            if raw:
                profile = json.loads(raw)
                cache_profile(chat_id, profile)
                return profile
            parsed = _parse_profile_from_content(m.get("content") or "")
            if parsed and parsed.get("business_name"):
                cache_profile(chat_id, parsed)
                return parsed
        return None
    except Exception:
        return _profile_cache.get(str(chat_id))


def has_profile(chat_id: int | str) -> bool:
    return is_profile_complete(load_profile(chat_id))


def build_business_context(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "Perusahaan belum terdaftar"
    if profile.get("raw_memory"):
        return profile["raw_memory"]
    loc = profile.get("location_label") or f"{profile.get('latitude')},{profile.get('longitude')}"
    return (
        f"{profile.get('business_name')} ({profile.get('business_type')}). "
        f"Lokasi: {loc}. Budget Rp {profile.get('budget')}."
    )


def format_profile_summary(profile: dict[str, Any]) -> str:
    loc = profile.get("location_label")
    if not loc and profile.get("latitude") is not None:
        loc = f"{profile.get('latitude')}, {profile.get('longitude')}"
    lines = [
        f"*Nama bisnis:* {profile.get('business_name', '-')}",
        f"*Jenis usaha:* {profile.get('business_type', '-')}",
        f"*Modal operasional:* Rp {int(profile.get('budget', 0) or 0):,}",
        f"*Lokasi:* {loc or '-'}",
    ]
    return "\n".join(lines)
