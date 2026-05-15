"""Cocokkan bahan baku dengan supplier manual yang sudah terdaftar."""

from __future__ import annotations

import re
from typing import Any

MANUAL_SOURCES = frozenset({"registered", "manual"})


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", _norm(text)))
    stop = {"dan", "atau", "the", "untuk", "dari", "bahan", "supply"}
    return words - stop


def supply_matches_supplier_product(supply_name: str, supplier_products: str) -> bool:
    """True jika kategori supply sudah dicakup produk supplier manual."""
    need = _norm(supply_name)
    prod = _norm(supplier_products)
    if not need or not prod:
        return False
    if need in prod or prod in need:
        return True
    ta, tb = _tokens(need), _tokens(prod)
    if not ta or not tb:
        return False
    return bool(ta & tb)


def is_manual_supplier(supplier: dict[str, Any]) -> bool:
    return (supplier.get("source") or "").lower() in MANUAL_SOURCES


def filter_supplies_without_manual(
    supply_needs: list[dict[str, Any]],
    suppliers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (missing_supplies, already_covered_supplies).
    Hanya supplier manual/register yang dianggap sudah diinput user.
    """
    manual = [s for s in suppliers if is_manual_supplier(s)]
    missing: list[dict[str, Any]] = []
    covered: list[dict[str, Any]] = []
    for need in supply_needs:
        name = need.get("name") or need.get("search_query") or ""
        if any(supply_matches_supplier_product(name, s.get("products", "")) for s in manual):
            covered.append(need)
        else:
            missing.append(need)
    return missing, covered
