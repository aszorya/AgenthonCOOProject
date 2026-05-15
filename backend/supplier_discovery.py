"""Discover nearby suppliers via OpenStreetMap Overpass (factual POI data)."""

from __future__ import annotations

import re
from typing import Any

import requests

from backend.geo_utils import format_distance, haversine_km

OVERPASS_ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)

# Map business keywords → OSM shop tags to search
_CATEGORY_TAGS: dict[str, list[str]] = {
    "kopi": ["coffee", "tea", "bakery"],
    "coffee": ["coffee", "tea", "bakery"],
    "makanan": ["supermarket", "greengrocer", "convenience", "wholesale"],
    "food": ["supermarket", "greengrocer", "convenience", "wholesale"],
    "bahan": ["wholesale", "trade", "hardware", "chemist"],
    "material": ["wholesale", "trade", "hardware"],
    "default": ["wholesale", "trade", "supermarket", "convenience", "hardware"],
}


def _tags_for_query(query: str, business_type: str = "") -> list[str]:
    text = f"{query} {business_type}".lower()
    tags: list[str] = []
    for key, shop_tags in _CATEGORY_TAGS.items():
        if key != "default" and key in text:
            tags.extend(shop_tags)
    if not tags:
        tags = list(_CATEGORY_TAGS["default"])
    return list(dict.fromkeys(tags))


def _build_address(tags: dict[str, Any]) -> str:
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
        tags.get("addr:city") or tags.get("addr:town"),
        tags.get("addr:postcode"),
    ]
    line = ", ".join(p for p in parts if p)
    return line or tags.get("addr:full") or tags.get("address") or "Alamat tidak tercatat di OSM"


def _element_coords(el: dict[str, Any]) -> tuple[float, float] | None:
    if el.get("type") == "node":
        lat, lon = el.get("lat"), el.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    center = el.get("center") or {}
    lat, lon = center.get("lat"), center.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None


def find_nearby_suppliers(
    lat: float,
    lon: float,
    *,
    query: str = "",
    business_type: str = "",
    radius_m: int = 8000,
    limit: int = 5,
) -> list[dict[str, Any]]:
    shop_tags = _tags_for_query(query, business_type)
    tag_filters = "\n".join(
        f'  node["shop"="{t}"](around:{radius_m},{lat},{lon});\n'
        f'  way["shop"="{t}"](around:{radius_m},{lat},{lon});'
        for t in shop_tags[:6]
    )
    overpass = f"""
[out:json][timeout:30];
(
{tag_filters}
  node["amenity"="marketplace"](around:{radius_m},{lat},{lon});
  way["amenity"="marketplace"](around:{radius_m},{lat},{lon});
);
out center 40;
"""
    elements: list[dict[str, Any]] = []
    last_err: Exception | None = None
    headers = {
        "User-Agent": "COOPilotAI/1.0",
        "Accept": "application/json",
    }
    for url in OVERPASS_ENDPOINTS:
        try:
            r = requests.post(
                url,
                data=overpass.encode("utf-8"),
                headers={**headers,
                         "Content-Type": "application/x-www-form-urlencoded"},
                timeout=45,
            )
            r.raise_for_status()
            elements = r.json().get("elements") or []
            break
        except Exception as e:
            last_err = e
    if not elements and last_err:
        raise last_err

    results: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or tags.get("brand") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_names:
            continue
        coords = _element_coords(el)
        if not coords:
            continue
        slat, slon = coords
        dist = haversine_km(lat, lon, slat, slon)
        seen_names.add(key)
        phone = tags.get("phone") or tags.get("contact:phone") or ""
        results.append(
            {
                "name": name,
                "address": _build_address(tags),
                "latitude": slat,
                "longitude": slon,
                "distance_km": round(dist, 2),
                "distance_label": format_distance(dist),
                "phone": re.sub(r"[^\d+]", "", phone) if phone else "",
                "shop_type": tags.get("shop") or tags.get("amenity") or "supplier",
                "source": "osm_discovery",
                "osm_id": f"{el.get('type')}/{el.get('id')}",
            }
        )

    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]


def format_recommendations(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Tidak ada supplier terdekat ditemukan di peta OSM. Perluas radius atau ubah kategori."
    lines = ["*Top rekomendasi supplier terdekat* (data OpenStreetMap):\n"]
    for i, s in enumerate(items, 1):
        lines.append(
            f"{i}. *{s['name']}* ({s.get('shop_type', '-')})\n"
            f"   📍 {s.get('address', '-')}\n"
            f"   Jarak: {s.get('distance_label', '?')}"
            + (f"\n   Tel: `{s['phone']}`" if s.get("phone") else "")
        )
    return "\n".join(lines)
