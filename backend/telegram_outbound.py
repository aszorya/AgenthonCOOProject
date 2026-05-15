"""Send Telegram messages to other users (vendor invoice, notifications)."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def is_configured() -> bool:
    return bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())


def send_message(
    chat_id: int | str,
    text: str,
    *,
    parse_mode: str | None = None,
    disable_preview: bool = True,
) -> dict[str, Any]:
    """Send via Bot API. Recipient must have started this bot at least once."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    payload: dict[str, Any] = {
        "chat_id": int(chat_id),
        "text": text[:4096],
        "disable_web_page_preview": disable_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json=payload,
        timeout=30,
    )
    data = r.json()
    if not data.get("ok"):
        desc = data.get("description", r.text[:300])
        raise RuntimeError(f"Telegram send failed: {desc}")
    return data.get("result") or {}


def format_invoice_message(
    *,
    business_name: str,
    vendor_name: str,
    products: str,
    invoice_id: str,
    amount: int,
    payment_url: str,
    vendor_doku_id: str = "",
) -> str:
    lines = [
        f"📄 Invoice dari {business_name}",
        f"Kepada: {vendor_name}",
        f"Item: {products}",
        f"Invoice: {invoice_id}",
        f"Nominal: Rp {amount:,}",
    ]
    if vendor_doku_id:
        lines.append(f"DOKU Vendor ID: {vendor_doku_id}")
    if payment_url:
        lines.append(f"Link pembayaran: {payment_url}")
    lines.append("\nMohon konfirmasi penerimaan. — COOPilot AI")
    return "\n".join(lines)


def format_reorder_notification(
    *,
    business_name: str,
    reorder_items: list[dict[str, Any]],
    reorder_orders: list[dict[str, Any]] | None = None,
    vendor_name: str = "",
    payment_url: str = "",
    payment_amount: int = 0,
    trigger_source: str = "",
    last_sale: dict[str, Any] | None = None,
) -> str:
    """Pesan notifikasi reorder ke pemilik bisnis (Telegram)."""
    lines = [
        "🔔 *Reorder otomatis terpicu*",
        f"Bisnis: {business_name}",
    ]
    if trigger_source:
        lines.append(f"Sumber: {trigger_source}")
    if last_sale:
        lines.append(
            f"Picu penjualan: {last_sale.get('qty')}x {last_sale.get('product')} "
            f"(kasir: {last_sale.get('cashier', '-')})"
        )
    lines.append("\n*Bahan stok rendah:*")
    for row in reorder_items[:6]:
        qty = row.get("qty", "?")
        min_q = row.get("min_qty", "?")
        unit = row.get("unit", "unit")
        lines.append(f"• {row.get('item', '?')}: sisa {qty} {unit} (ambang {min_q})")

    if reorder_orders:
        lines.append("\n*Rencana pesan:*")
        for o in reorder_orders[:4]:
            lines.append(f"• {o.get('item')} → vendor {o.get('vendor') or '-'}")

    if vendor_name:
        lines.append(f"\n*Vendor dipilih:* {vendor_name}")
    if payment_amount:
        lines.append(f"*Nominal:* Rp {payment_amount:,}")
    if payment_url:
        lines.append(f"*Link DOKU:* {payment_url}")
    elif vendor_name:
        lines.append("\n_Link pembayaran belum tersedia — cek /bayar di bot._")

    lines.append("\n— COOPilot AI")
    return "\n".join(lines)
