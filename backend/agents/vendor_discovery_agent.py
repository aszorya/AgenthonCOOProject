from __future__ import annotations

import json
import re
from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend import vendor_search
from backend.config import MAX_CORE_SUPPLIES
from backend.supplier_registry import dedupe_suppliers, vendor_dedupe_key


def _pick_best_vendor(
    candidates: list[dict[str, Any]],
    supply_name: str,
    llm_chat,
    *,
    exclude_keys: set[str],
) -> dict[str, Any] | None:
    real = [c for c in candidates if c.get("source") not in ("ecommerce_stub", "repliz_stub")]
    pool = real or candidates
    pool = [c for c in pool if vendor_dedupe_key(c) and vendor_dedupe_key(c) not in exclude_keys]
    if not pool:
        return None
    if len(pool) == 1:
        return pool[0]

    lines = []
    for i, c in enumerate(pool[:8], 1):
        lines.append(
            f"{i}. {c.get('name')} | channel={c.get('channel')} | "
            f"jarak={c.get('distance_label', '-')} | tel={c.get('phone') or '-'} | "
            f"alamat={c.get('address', '-')[:80]}"
        )
    prompt = f"""Kategori supply: {supply_name}
Kandidat vendor (toko berbeda, jangan pilih yang sama dengan kategori lain):
{chr(10).join(lines)}

Pilih SATU nomor terbaik (harga/kualitas/jarak). Balas JSON:
{{"choice": 1, "reason": "singkat"}}"""
    try:
        raw = llm_chat(prompt, system="COOPilot Vendor Ranker. JSON only.", max_tokens=200)
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            data = json.loads(m.group(0))
            idx = int(data.get("choice", 1)) - 1
            if 0 <= idx < len(pool):
                chosen = dict(pool[idx])
                chosen["rank_reason"] = data.get("reason", "")
                return chosen
    except Exception:
        pass
    return pool[0]


class VendorDiscoveryAgent(BaseAgent):
    """Cari vendor per kategori supply (maps + stub ecommerce/social)."""

    name = "vendor_discovery"

    def run(self, context: dict[str, Any]) -> AgentResult:
        profile = context.get("profile") or {}
        lat, lon = profile.get("latitude"), profile.get("longitude")
        if lat is None or lon is None:
            return AgentResult(self.name, "blocked", "Lokasi bisnis belum ada (GPS/alamat)", {})

        supplies = context.get("supply_needs") or []
        if not supplies:
            return AgentResult(self.name, "blocked", "Belum ada daftar supply — jalankan supply analysis dulu", {})

        business_type = profile.get("business_type", "")
        selected_vendors: list[dict[str, Any]] = []
        all_candidates: list[dict[str, Any]] = []
        used_keys: set[str] = set()
        skipped_duplicate = 0

        for need in supplies[:MAX_CORE_SUPPLIES]:
            name = need.get("search_query") or need.get("name") or ""
            if not name:
                continue
            candidates = vendor_search.search_all_channels(
                float(lat),
                float(lon),
                name,
                business_type=business_type,
            )
            all_candidates.extend(candidates)
            best = _pick_best_vendor(candidates, name, self.llm_chat, exclude_keys=used_keys)
            if not best:
                skipped_duplicate += 1
                continue
            key = vendor_dedupe_key(best)
            if key in used_keys:
                skipped_duplicate += 1
                continue
            used_keys.add(key)
            best["products"] = need.get("name")
            best["supply_category"] = need.get("name")
            selected_vendors.append(best)

        selected_vendors = dedupe_suppliers(selected_vendors)

        if not selected_vendors:
            return AgentResult(
                self.name,
                "blocked",
                "Tidak ada vendor unik ditemukan. Coba /lokasi atau /tambah_supplier manual.",
                {"candidates": all_candidates},
            )

        msg = f"{len(selected_vendors)} vendor unik untuk {len(supplies[:MAX_CORE_SUPPLIES])} bahan inti"
        if skipped_duplicate:
            msg += f" ({skipped_duplicate} kategori pakai toko yang sudah dipilih)"

        return AgentResult(
            self.name,
            "ok",
            msg,
            {
                "discovered_vendors": selected_vendors,
                "vendor_candidates": all_candidates,
            },
        )
