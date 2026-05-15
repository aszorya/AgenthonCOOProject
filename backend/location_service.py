"""Geocoding via OpenStreetMap Nominatim (no API key)."""

from __future__ import annotations

from typing import Any

import requests

NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "COOPilotAI/1.0 (hackathon; contact@coopilot.local)"


def reverse_geocode(lat: float, lon: float) -> dict[str, Any]:
    r = requests.get(
        NOMINATIM_REVERSE,
        params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    addr = data.get("address") or {}
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("county")
        or ""
    )
    return {
        "display_name": data.get("display_name", ""),
        "city": city,
        "province": addr.get("state") or addr.get("region") or "",
        "road": addr.get("road") or "",
        "suburb": addr.get("suburb") or addr.get("neighbourhood") or "",
    }


def forward_geocode(query: str, *, limit: int = 1) -> dict[str, Any] | None:
    """Resolve alamat teks menjadi koordinat (Indonesia preferred)."""
    q = (query or "").strip()
    if not q:
        return None
    r = requests.get(
        NOMINATIM_SEARCH,
        params={"q": q, "format": "json", "limit": limit, "countrycodes": "id"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return None
    hit = rows[0]
    return {
        "latitude": float(hit["lat"]),
        "longitude": float(hit["lon"]),
        "display_name": hit.get("display_name", q),
    }
