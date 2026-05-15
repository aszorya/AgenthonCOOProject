from __future__ import annotations

import json
import re
from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend.config import MAX_CORE_SUPPLIES


def _parse_supply_list(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return [
                    {
                        "name": str(x.get("name", x.get("category", ""))).strip(),
                        "unit": str(x.get("unit", "unit")).strip(),
                        "priority": str(x.get("priority", "high")),
                        "search_query": str(x.get("search_query", x.get("name", ""))).strip(),
                    }
                    for x in data
                    if isinstance(x, dict) and (x.get("name") or x.get("category"))
                ]
        except json.JSONDecodeError:
            pass

    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        if len(line) < 2:
            continue
        items.append({"name": line, "unit": "unit", "priority": "medium", "search_query": line})
    return items[:MAX_CORE_SUPPLIES]


class SupplyAnalysisAgent(BaseAgent):
    """Analisis jenis usaha → daftar kebutuhan bahan/supply."""

    name = "supply_analysis"

    def run(self, context: dict[str, Any]) -> AgentResult:
        profile = context.get("profile") or {}
        business_type = profile.get("business_type") or context.get("business_type", "")
        business_name = profile.get("business_name", "")

        if not business_type:
            return AgentResult(self.name, "blocked", "Jenis usaha belum diisi", {})

        prompt = f"""Bisnis: {business_name} ({business_type})

Identifikasi TEPAT {MAX_CORE_SUPPLIES} bahan baku yang PALING SERING dipakai sehari-hari untuk jenis usaha ini.
Contoh toko kopi: biji kopi, air, gula, susu — BUKAN perlengkapan jarang dipakai.

Balas HANYA JSON array dengan {MAX_CORE_SUPPLIES} item:
[
  {{"name": "biji kopi", "unit": "kg", "priority": "high", "search_query": "wholesale coffee beans"}},
  {{"name": "gula", "unit": "kg", "priority": "high", "search_query": "grocery sugar supplier"}},
  {{"name": "susu", "unit": "liter", "priority": "high", "search_query": "dairy milk"}},
  {{"name": "air", "unit": "liter", "priority": "high", "search_query": "drinking water supplier"}}
]

Bahasa Indonesia untuk name. Harus tepat {MAX_CORE_SUPPLIES} item."""

        try:
            raw = self.llm_chat(
                prompt,
                system="COOPilot Supply Analyst. Output valid JSON array only.",
                max_tokens=800,
            )
            supplies = _parse_supply_list(raw)[:MAX_CORE_SUPPLIES]
            if not supplies:
                return AgentResult(self.name, "error", "Gagal memparse daftar supply", {"raw": raw})
            return AgentResult(
                self.name,
                "ok",
                f"{len(supplies)} bahan inti (paling sering dipakai) diidentifikasi",
                {"supply_needs": supplies, "supply_analysis_raw": raw},
            )
        except Exception as e:
            return AgentResult(self.name, "error", str(e), {})
