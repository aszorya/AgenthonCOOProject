from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult, BaseAgent
from backend.business_profile import build_business_context
from backend import telegram_outbound


class CommunicationAgent(BaseAgent):
    name = "communication"

    def run(self, context: dict[str, Any]) -> AgentResult:
        selected = context.get("selected_supplier") or {}
        profile = context.get("profile") or {}
        vendor = selected.get("name") or context.get("vendor_name", "")
        contact = selected.get("contact_person", "")
        phone = selected.get("phone_wa", "")
        products = selected.get("products", "")
        amount = int(context.get("payment_amount", 0))
        invoice_id = context.get("invoice_id", "INV-001")
        payment_url = context.get("payment_url") or ""
        vendor_doku = (selected.get("doku_id") or "").strip()
        telegram_id = (selected.get("telegram_id") or "").strip()
        biz_name = profile.get("business_name") or build_business_context(profile).split("—")[0]

        if not vendor:
            return AgentResult(self.name, "blocked", "Tidak ada supplier untuk dikontak", {})

        invoice_text = telegram_outbound.format_invoice_message(
            business_name=biz_name,
            vendor_name=vendor,
            products=products,
            invoice_id=invoice_id,
            amount=amount,
            payment_url=payment_url,
            vendor_doku_id=vendor_doku,
        )

        telegram_sent = False
        telegram_error = ""
        if telegram_id and telegram_outbound.is_configured():
            try:
                telegram_outbound.send_message(int(telegram_id), invoice_text)
                telegram_sent = True
            except Exception as e:
                telegram_error = str(e)

        prompt = f"""Buat pesan WhatsApp ke supplier (Bahasa Indonesia, profesional):
- Dari bisnis: {build_business_context(profile)}
- Kepada: {contact or vendor} ({phone})
- Alamat supplier: {selected.get('address', '-')}
- Supplier: {vendor}
- Produk/bahan: {products}
- Invoice: {invoice_id}
- Nominal: Rp {amount:,}
- DOKU vendor ID: {vendor_doku or '-'}
- Link pembayaran DOKU: {payment_url}
- Telegram invoice: {'terkirim' if telegram_sent else 'belum (vendor perlu /start bot)'}

Minta konfirmasi penerimaan invoice. Max 5 kalimat. Jangan buat nama/fakta baru."""
        try:
            message = self.llm_chat(
                prompt,
                system="COOPilot Communication Agent. Use ONLY facts provided. No invented names.",
            )
        except Exception as e:
            message = (
                f"Halo {contact or vendor}, dari {biz_name}. "
                f"Invoice {invoice_id} Rp {amount:,} untuk {products}. "
                f"Link: {payment_url}. Mohon konfirmasi."
            )
            if not telegram_sent and telegram_error:
                message += f"\n(Telegram: {telegram_error})"

        channels = ["whatsapp"]
        if telegram_sent:
            channels.append("telegram")
        status_msg = f"Pesan siap — {', '.join(channels)}"
        if telegram_id and not telegram_sent:
            status_msg += f" (TG gagal: {telegram_error or 'vendor belum /start bot'})"

        return AgentResult(
            self.name,
            "ok",
            status_msg,
            {
                "confirmation_message": message,
                "supplier_phone": phone,
                "channel": ",".join(channels),
                "telegram_invoice_sent": telegram_sent,
                "telegram_id": telegram_id,
                "invoice_text": invoice_text,
            },
        )
