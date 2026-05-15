from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend.business_profile import build_business_context
from backend import supplier_registry, telegram_outbound
from backend.supplier_registry import dedupe_suppliers


class VendorOutreachAgent(BaseAgent):
    """Hubungi vendor terpilih, kumpulkan info pembelian, daftarkan otomatis."""

    name = "vendor_outreach"

    def run(self, context: dict[str, Any]) -> AgentResult:
        profile = context.get("profile") or {}
        chat_id = context.get("chat_id")
        vendors = dedupe_suppliers(context.get("discovered_vendors") or [])
        if not vendors:
            return AgentResult(self.name, "blocked", "Tidak ada vendor untuk dihubungi", {})

        biz = build_business_context(profile)
        outreach_log: list[dict[str, Any]] = []
        saved: list[dict[str, Any]] = []

        for v in vendors:
            vendor_name = v.get("name", "")
            phone = v.get("phone") or v.get("phone_wa") or ""
            products = v.get("products") or v.get("supply_category") or "-"
            channel = v.get("channel", v.get("source", "maps"))

            prompt = f"""Buat pesan pertama ke vendor (Bahasa Indonesia, profesional, max 6 kalimat):
- Dari: {biz}
- Vendor: {vendor_name} ({channel})
- Produk yang dibutuhkan: {products}
- Alamat vendor: {v.get('address', '-')}

Minta: daftar harga, MOQ, metode pembayaran (transfer/DOKU), rekening/DOKU ID, kontak konfirmasi.
Jangan mengarang fakta baru."""

            try:
                message = self.llm_chat(
                    prompt,
                    system="COOPilot Vendor Outreach. Facts only.",
                    max_tokens=400,
                )
            except Exception as e:
                message = (
                    f"Halo, kami dari {profile.get('business_name', 'bisnis kami')}. "
                    f"Ingin memesan {products}. Mohon info harga, MOQ, dan pembayaran. Terima kasih."
                )
                outreach_log.append({"vendor": vendor_name, "error": str(e)})

            telegram_sent = False
            tg_id = (v.get("telegram_id") or "").strip()
            if tg_id and telegram_outbound.is_configured():
                try:
                    telegram_outbound.send_message(int(tg_id), message)
                    telegram_sent = True
                except Exception:
                    pass

            supplier_row = supplier_registry.supplier_from_discovery(v)
            supplier_row["products"] = products
            supplier_row["phone_wa"] = phone
            supplier_row["contact_person"] = vendor_name
            supplier_row["default_monthly_amount"] = int(context.get("default_order_amount", 500_000))
            supplier_row["source"] = "auto_discovery"
            supplier_row["outreach_message"] = message
            supplier_row["outreach_channel"] = "telegram" if telegram_sent else "whatsapp_draft"

            if chat_id:
                try:
                    supplier_registry.save_supplier(chat_id, supplier_row)
                    saved.append(supplier_row)
                except Exception:
                    saved.append(supplier_row)

            outreach_log.append(
                {
                    "vendor": vendor_name,
                    "channel": channel,
                    "telegram_sent": telegram_sent,
                    "phone": phone,
                    "message_preview": message[:200],
                    "purchase_info_requested": [
                        "harga",
                        "MOQ",
                        "metode pembayaran",
                        "rekening/DOKU ID",
                    ],
                }
            )

        return AgentResult(
            self.name,
            "ok",
            f"Pesan outreach disiapkan untuk {len(vendors)} vendor ({len(saved)} tersimpan)",
            {
                "outreach_log": outreach_log,
                "registered_suppliers": saved,
                "registered_suppliers_count": len(saved),
            },
        )
