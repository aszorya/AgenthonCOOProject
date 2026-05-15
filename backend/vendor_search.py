"""Multi-channel vendor search: maps (OSM), ecommerce stub, social (Repliz stub)."""

from __future__ import annotations

from typing import Any

from backend import repliz_client, supplier_discovery


def search_maps(
    lat: float,
    lon: float,
    *,
    supply_name: str,
    business_type: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    items = supplier_discovery.find_nearby_suppliers(
        lat,
        lon,
        query=supply_name,
        business_type=business_type,
        limit=limit,
    )
    for row in items:
        row["channel"] = "maps"
        row["supply_category"] = supply_name
    return items


def search_ecommerce(supply_name: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """
    Placeholder ecommerce discovery.
    Butuh integrasi API marketplace (Tokopedia/Shopee/Blibli) untuk hasil nyata.
    """
    return [
        {
            "name": f"[Ecommerce] Cari '{supply_name}' di marketplace",
            "address": "Integrasi API marketplace belum dikonfigurasi",
            "phone": "",
            "source": "ecommerce_stub",
            "channel": "ecommerce",
            "supply_category": supply_name,
            "note": "Hubungkan API Tokopedia/Shopee untuk hasil otomatis",
        }
    ][:limit]


def search_social(supply_name: str, business_type: str = "") -> list[dict[str, Any]]:
    """
    Social discovery via Repliz (akun terhubung).
    Repliz saat ini tidak punya endpoint pencarian vendor — hanya verifikasi koneksi.
    """
    if not repliz_client.is_configured():
        return []
    try:
        repliz_client.test_connection()
        return [
            {
                "name": f"[Social] Supplier {supply_name} via Repliz",
                "address": "Gunakan DM/comment manual atau endpoint Repliz pencarian jika tersedia",
                "phone": "",
                "source": "repliz_stub",
                "channel": "social",
                "supply_category": supply_name,
                "note": "Repliz terhubung; perlu endpoint search vendor dari Repliz",
            }
        ]
    except Exception:
        return []


def search_all_channels(
    lat: float,
    lon: float,
    supply_name: str,
    *,
    business_type: str = "",
    maps_limit: int = 5,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    try:
        candidates.extend(
            search_maps(lat, lon, supply_name=supply_name, business_type=business_type, limit=maps_limit)
        )
    except Exception:
        pass
    candidates.extend(search_ecommerce(supply_name, limit=2))
    candidates.extend(search_social(supply_name, business_type))
    return candidates
