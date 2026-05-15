"""Notifikasi Telegram saat auto-reorder terpicu."""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import AgentResult
from backend import telegram_outbound


def send_reorder_notification(
    chat_id: int | str,
    *,
    business_name: str,
    reorder_items: list[dict[str, Any]],
    reorder_orders: list[dict[str, Any]] | None = None,
    vendor_name: str = "",
    payment_url: str = "",
    payment_amount: int = 0,
    trigger_source: str = "",
    last_sale: dict[str, Any] | None = None,
) -> AgentResult:
    if not reorder_items:
        return AgentResult("notification", "skipped", "Tidak ada reorder", {})

    if not chat_id:
        return AgentResult("notification", "skipped", "chat_id tidak ada", {})

    if not telegram_outbound.is_configured():
        return AgentResult(
            "notification",
            "skipped",
            "TELEGRAM_BOT_TOKEN tidak diset — notifikasi dilewati",
            {},
        )

    text = telegram_outbound.format_reorder_notification(
        business_name=business_name or "Bisnis Anda",
        reorder_items=reorder_items,
        reorder_orders=reorder_orders,
        vendor_name=vendor_name,
        payment_url=payment_url or "",
        payment_amount=int(payment_amount or 0),
        trigger_source=trigger_source,
        last_sale=last_sale,
    )

    try:
        telegram_outbound.send_message(chat_id, text, parse_mode="Markdown")
        return AgentResult(
            "notification",
            "ok",
            "Notifikasi reorder terkirim ke Telegram pemilik bisnis",
            {"telegram_reorder_notified": True},
        )
    except Exception as e:
        plain = text.replace("*", "")
        try:
            telegram_outbound.send_message(chat_id, plain)
            return AgentResult(
                "notification",
                "ok",
                "Notifikasi reorder terkirim (plain text)",
                {"telegram_reorder_notified": True},
            )
        except Exception as e2:
            return AgentResult(
                "notification",
                "error",
                f"Gagal kirim notifikasi: {e2}",
                {"telegram_reorder_error": str(e)},
            )
