"""
COOPilot Telegram — onboarding ringkas, discovery vendor otomatis, pembayaran DOKU.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from backend.business_profile import (
    build_business_context,
    cache_profile,
    format_profile_summary,
    has_profile,
    is_profile_complete,
    load_profile,
    save_location,
    save_profile,
    set_active_business_chat_id,
)
from backend.intent_router import UserIntent, detect_intent
from backend.orchestrator import (
    run_auto_reorder_flow,
    run_find_supplier_flow,
    run_goal_flow,
    run_supply_chain_flow,
)
from backend.location_service import forward_geocode, reverse_geocode
from backend.supplier_registry import (
    clear_suppliers_local,
    find_supplier,
    format_supplier_list,
    list_suppliers,
    save_supplier,
)
from backend import inventory_service
from channels.formatters import escape_md, format_feed_line, format_workflow_summary

logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger("coopilot.telegram")

# Onboarding: jenis usaha → nama → modal → lokasi
BIZ_TYPE, BIZ_NAME, MODAL, BIZ_LOCATION = range(4)

# Supplier manual (/tambah_supplier)
SUP_NAME, SUP_CONTACT, SUP_PHONE, SUP_ADDRESS, SUP_TELEGRAM, SUP_DOKU, SUP_PRODUCTS, SUP_AMOUNT = range(
    20, 28
)

FEED_DELAY_SEC = float(os.getenv("TELEGRAM_FEED_DELAY", "0.45"))
LOCATION_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📍 Kirim lokasi usaha", request_location=True)],
        ["Ketik alamat teks"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def _token() -> str:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise ValueError("Set TELEGRAM_BOT_TOKEN in coopilot/.env")
    return token


def _get_profile(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return load_profile(chat_id) or context.user_data.get("profile")


async def _safe_reply(message, text: str, **kwargs) -> None:
    try:
        await message.reply_text(text, **kwargs)
    except Exception:
        await message.reply_text(re.sub(r"[*_`\[]", "", text))


async def _run_and_feed(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    goal: str,
    runner,
    label: str,
) -> None:
    chat_id = update.effective_chat.id
    profile = _get_profile(chat_id, context) or {}
    wf_context = _build_wf_context(chat_id, context, goal, profile, None)

    status_msg = await update.message.reply_text(
        f"⏳ *{escape_md(label)}*...",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        run = await asyncio.to_thread(runner, wf_context)
    except Exception as e:
        logger.exception("workflow failed")
        await status_msg.edit_text(f"❌ Gagal: {escape_md(str(e))}")
        return

    await status_msg.edit_text(
        f"📋 *{escape_md(label)}* ({run.status})",
        parse_mode=ParseMode.MARKDOWN,
    )
    for entry in run.feed:
        await _safe_reply(update.message, format_feed_line(entry), parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(FEED_DELAY_SEC)

    if run.status == "ok":
        await _safe_reply(update.message, format_workflow_summary(run), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"Workflow berhenti: status={run.status}")


def _build_wf_context(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    goal: str,
    profile: dict,
    selected_supplier: dict | None,
) -> dict:
    suppliers = list_suppliers(chat_id)
    wf: dict = {
        "chat_id": chat_id,
        "user_goal": goal,
        "profile": profile,
        "business_context": build_business_context(profile),
        "registered_suppliers": suppliers,
    }
    try:
        wf["budget_available"] = float(str(profile.get("budget", "0")).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        wf["budget_available"] = 0
    if selected_supplier:
        wf["selected_supplier"] = selected_supplier
        wf["vendor_name"] = selected_supplier.get("name")
        amt = int(selected_supplier.get("default_monthly_amount", 0))
        wf["payment_amount"] = amt if amt > 0 else wf.get("payment_amount", 0)
        wf["payment_allowed"] = False
    return wf


# --- Onboarding ---


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    context.user_data.pop("in_onboarding", None)
    profile = _get_profile(chat_id, context)

    if is_profile_complete(profile):
        name = profile.get("business_name", "bisnis Anda")
        await _safe_reply(
            update.message,
            f"Halo! COOPilot untuk *{escape_md(name)}*.\n\n"
            "/mulai — discovery semua bahan inti\n"
            "/tambah_supplier — vendor tetap (input manual)\n"
            "/cari_supplier — cari vendor bahan yang belum ada supplier manual\n"
            "/vendor — daftar vendor\n"
            "/reset_vendor — kosongkan vendor (demo ulang)\n"
            "/bayar <nama> — pembayaran DOKU\n"
            "/stok — cek inventory | /reorder — isi ulang otomatis\n"
            "/lokasi | /profile | /setup | /help",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    context.user_data["in_onboarding"] = True
    context.user_data["onboarding"] = {}
    await _safe_reply(
        update.message,
        "Selamat datang di *COOPilot AI*.\n\n"
        "Langkah 1/4: *Jenis usaha* Anda?\n"
        "(contoh: toko kopi, warung makan, bakery online)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return BIZ_TYPE


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["in_onboarding"] = True
    context.user_data["onboarding"] = {}
    await _safe_reply(
        update.message,
        "Setup ulang bisnis.\n*Jenis usaha*? (contoh: toko kopi)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return BIZ_TYPE


async def onboard_biz_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["onboarding"]["business_type"] = update.message.text.strip()
    await update.message.reply_text("Nama bisnis / brand?")
    return BIZ_NAME


async def onboard_biz_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["onboarding"]["business_name"] = update.message.text.strip()
    await update.message.reply_text("Modal operasional bulanan (angka, contoh: 2000000):")
    return MODAL


async def onboard_modal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = re.sub(r"[^\d]", "", update.message.text)
    if not raw:
        await update.message.reply_text("Masukkan angka modal, contoh: 2000000")
        return MODAL
    context.user_data["onboarding"]["budget"] = raw
    context.user_data["onboarding"]["modal"] = raw
    await _safe_reply(
        update.message,
        "Langkah terakhir: *lokasi usaha*.\n"
        "Kirim pin 📍 GPS **atau** ketik alamat lengkap (kota, jalan).",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=LOCATION_KEYBOARD,
    )
    return BIZ_LOCATION


async def _finish_and_discover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = context.user_data.get("onboarding", {})
    chat_id = update.effective_chat.id
    try:
        save_profile(chat_id, profile)
        context.user_data["profile"] = profile
        mem_note = "Profil tersimpan."
    except Exception as e:
        cache_profile(chat_id, profile)
        set_active_business_chat_id(chat_id)
        context.user_data["profile"] = profile
        mem_note = f"Profil cache lokal: {e}"

    context.user_data.pop("in_onboarding", None)
    await _safe_reply(
        update.message,
        f"✅ Profil selesai!\n"
        f"*{escape_md(profile['business_name'])}* — {escape_md(profile['business_type'])}\n"
        f"Modal: Rp {int(profile['budget']):,}\n"
        f"Lokasi: {escape_md(profile.get('location_label', 'tercatat'))}\n{mem_note}\n\n"
        "Dashboard kasir otomatis terhubung ke bisnis ini.\n"
        "Memulai agen discovery vendor...",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )

    wf_context = _build_wf_context(chat_id, context, "Setup rantai pasok awal", profile, None)
    try:
        run = await asyncio.to_thread(run_supply_chain_flow, wf_context)
        for entry in run.feed:
            await _safe_reply(update.message, format_feed_line(entry), parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(FEED_DELAY_SEC)
        if run.status == "ok":
            await _safe_reply(update.message, format_workflow_summary(run), parse_mode=ParseMode.MARKDOWN)
            await update.message.reply_text(
                "Vendor siap. Gunakan /vendor, /bayar <nama>, /stok, /reorder."
            )
        else:
            await update.message.reply_text(f"Discovery: status={run.status}. Coba /mulai lagi.")
    except Exception as e:
        logger.exception("supply chain after onboarding")
        await update.message.reply_text(f"Discovery gagal: {e}. Jalankan /mulai.")

    return ConversationHandler.END


async def onboard_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    loc = update.message.location
    if loc:
        lat, lon = loc.latitude, loc.longitude
        try:
            geo = reverse_geocode(lat, lon)
            label = geo.get("display_name", "")[:200]
        except Exception:
            label = f"{lat:.5f}, {lon:.5f}"
        context.user_data["onboarding"]["latitude"] = lat
        context.user_data["onboarding"]["longitude"] = lon
        context.user_data["onboarding"]["location_label"] = label
        return await _finish_and_discover(update, context)

    text = (update.message.text or "").strip()
    if text.lower() in ("ketik alamat teks",):
        await update.message.reply_text("Ketik alamat lengkap bisnis Anda:")
        return BIZ_LOCATION

    if len(text) < 5:
        await update.message.reply_text(
            "Kirim lokasi 📍 atau ketik alamat (min. 5 karakter).",
            reply_markup=LOCATION_KEYBOARD,
        )
        return BIZ_LOCATION

    try:
        geo = forward_geocode(text)
        if not geo:
            await update.message.reply_text("Alamat tidak ditemukan. Coba lebih spesifik atau kirim GPS.")
            return BIZ_LOCATION
        context.user_data["onboarding"]["latitude"] = geo["latitude"]
        context.user_data["onboarding"]["longitude"] = geo["longitude"]
        context.user_data["onboarding"]["location_label"] = geo.get("display_name", text)[:200]
    except Exception as e:
        await update.message.reply_text(f"Geocoding gagal: {e}. Kirim pin GPS.")
        return BIZ_LOCATION

    return await _finish_and_discover(update, context)


async def onboard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("in_onboarding", None)
    context.user_data.pop("adding_supplier", None)
    await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# --- Commands ---


# --- Supplier manual ---


async def cmd_tambah_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if not has_profile(chat_id):
        await update.message.reply_text("Setup perusahaan dulu: /setup")
        return ConversationHandler.END

    context.user_data["adding_supplier"] = True
    context.user_data["new_supplier"] = {"source": "manual"}
    await _safe_reply(
        update.message,
        "📦 *Vendor tetap* (input manual)\n\n(1/8) Nama supplier / perusahaan?",
        parse_mode=ParseMode.MARKDOWN,
    )
    return SUP_NAME


async def sup_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_supplier"]["name"] = update.message.text.strip()
    await update.message.reply_text("Nama contact person di supplier?")
    return SUP_CONTACT


async def sup_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_supplier"]["contact_person"] = update.message.text.strip()
    await update.message.reply_text("Nomor WhatsApp supplier? (contoh: 62812...)")
    return SUP_PHONE


async def sup_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = re.sub(r"[^\d+]", "", update.message.text.strip())
    if len(phone) < 10:
        await update.message.reply_text("Nomor tidak valid. Contoh: 62812345678")
        return SUP_PHONE
    context.user_data["new_supplier"]["phone_wa"] = phone
    await update.message.reply_text("Alamat lengkap supplier?")
    return SUP_ADDRESS


async def sup_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_supplier"]["address"] = update.message.text.strip()
    await update.message.reply_text(
        "Telegram User ID vendor? (angka, dari @userinfobot — ketik - jika belum ada)"
    )
    return SUP_TELEGRAM


async def sup_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw not in ("-", "skip", "lewati"):
        tid = re.sub(r"[^\d]", "", raw)
        if tid:
            context.user_data["new_supplier"]["telegram_id"] = tid
    await update.message.reply_text("Nomor/ID DOKU vendor? Ketik - jika belum ada.")
    return SUP_DOKU


async def sup_doku(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw not in ("-", "skip", "lewati"):
        context.user_data["new_supplier"]["doku_id"] = raw
    await update.message.reply_text(
        "Produk / bahan yang disuplai?\n"
        "(contoh: biji kopi — penting untuk /cari_supplier tahu bahan sudah terdaftar)"
    )
    return SUP_PRODUCTS


async def sup_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_supplier"]["products"] = update.message.text.strip()
    await update.message.reply_text("Nominal pembayaran rutin per bulan (angka, contoh: 500000):")
    return SUP_AMOUNT


async def sup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = re.sub(r"[^\d]", "", update.message.text)
    if not raw:
        await update.message.reply_text("Masukkan angka, contoh: 500000")
        return SUP_AMOUNT

    chat_id = update.effective_chat.id
    supplier = context.user_data.get("new_supplier", {})
    supplier["default_monthly_amount"] = int(raw)
    supplier["source"] = "manual"

    try:
        save_supplier(chat_id, supplier)
        note = "Supplier manual tersimpan."
    except Exception as e:
        note = f"Tersimpan cache: {e}"

    context.user_data.pop("adding_supplier", None)
    await _safe_reply(
        update.message,
        f"✅ Vendor manual terdaftar!\n"
        f"*{escape_md(supplier['name'])}*\n"
        f"Produk: {escape_md(supplier.get('products', '-'))}\n"
        f"WA: `{supplier.get('phone_wa', '-')}`\n"
        f"Nominal: Rp {supplier['default_monthly_amount']:,}\n{note}\n\n"
        f"/cari_supplier — discovery bahan lain yang belum punya vendor manual\n"
        f"/bayar {escape_md(supplier['name'])}",
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationHandler.END


async def cmd_cari_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not has_profile(chat_id):
        await update.message.reply_text("Setup dulu: /setup")
        return

    profile = _get_profile(chat_id, context) or {}
    if profile.get("latitude") is None:
        await update.message.reply_text("Lokasi belum ada. Kirim /lokasi dulu.")
        return

    await update.message.reply_text(
        "🔍 Mencari vendor untuk bahan yang *belum* punya supplier manual...",
        parse_mode=ParseMode.MARKDOWN,
    )
    wf_context = _build_wf_context(chat_id, context, "Cari supplier bahan belum manual", profile, None)
    await _run_and_feed(
        update,
        context,
        goal="Find supplier",
        runner=run_find_supplier_flow,
        label="Cari supplier",
    )


async def cmd_mulai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not has_profile(update.effective_chat.id):
        await update.message.reply_text("Setup dulu: /setup")
        return
    await _run_and_feed(
        update,
        context,
        goal="Discovery vendor otomatis",
        runner=run_supply_chain_flow,
        label="Supply chain discovery",
    )


async def cmd_vendor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not has_profile(chat_id):
        await update.message.reply_text("Setup dulu: /setup")
        return
    text = format_supplier_list(chat_id)
    if "Belum ada" in text:
        text += "\n\nJalankan /mulai untuk discovery otomatis."
    await _safe_reply(update.message, f"*Vendor terdaftar:*\n\n{text}", parse_mode=ParseMode.MARKDOWN)


async def cmd_reset_vendor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    clear_suppliers_local(chat_id)
    await _safe_reply(
        update.message,
        "✅ Daftar vendor di sesi ini dikosongkan.\n\n"
        "• /vendor — seharusnya kosong\n"
        "• /mulai — discovery ulang (max ~4 toko unik, bukan toko sama 8×)\n\n"
        "_Data lama di Mem9 cloud:_ ganti `MEM9_API_KEY` di `.env` lalu restart bot, "
        "atau jalankan `python scripts/reset_demo.py --chat-id "
        f"{chat_id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_stok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not has_profile(chat_id):
        await update.message.reply_text("Setup dulu: /setup")
        return
    args = context.args or []
    if len(args) >= 2 and args[-1].isdigit():
        item = " ".join(args[:-1])
        qty = int(args[-1])
        row = inventory_service.update_stock(chat_id, item, qty)
        await update.message.reply_text(f"Stok *{item}* → {qty} {row.get('unit', 'unit')}", parse_mode=ParseMode.MARKDOWN)
        return

    items = inventory_service.list_inventory(chat_id)
    if not items:
        await update.message.reply_text("Inventory kosong. Jalankan /mulai dulu.")
        return
    lines = [f"• {r['item']}: {r['qty']} {r.get('unit', 'unit')}" for r in items]
    await update.message.reply_text("*Stok saat ini:*\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_reorder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not has_profile(update.effective_chat.id):
        await update.message.reply_text("Setup dulu: /setup")
        return
    await _run_and_feed(
        update,
        context,
        goal="Auto-reorder stok rendah",
        runner=run_auto_reorder_flow,
        label="Auto-reorder",
    )


async def cmd_lokasi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not has_profile(update.effective_chat.id):
        await update.message.reply_text("Setup dulu: /setup")
        return
    context.user_data["awaiting_location_update"] = True
    await update.message.reply_text(
        "Kirim lokasi GPS baru atau ketik alamat:",
        reply_markup=LOCATION_KEYBOARD,
    )


async def handle_location_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("awaiting_location_update"):
        return
    chat_id = update.effective_chat.id
    loc = update.message.location
    if loc:
        lat, lon = loc.latitude, loc.longitude
        try:
            geo = reverse_geocode(lat, lon)
            label = geo.get("display_name", "")[:200]
        except Exception:
            label = f"{lat:.5f}, {lon:.5f}"
        try:
            save_location(chat_id, lat, lon, label)
            note = "Lokasi tersimpan."
        except Exception as e:
            profile = _get_profile(chat_id, context) or {}
            profile.update(latitude=lat, longitude=lon, location_label=label)
            cache_profile(chat_id, profile)
            note = f"Cache: {e}"
        context.user_data.pop("awaiting_location_update", None)
        await update.message.reply_text(f"✅ {label}\n{note}\n/mulai untuk refresh vendor.", reply_markup=ReplyKeyboardRemove())
        return

    text = (update.message.text or "").strip()
    if len(text) < 5:
        return
    try:
        geo = forward_geocode(text)
        if geo:
            save_location(chat_id, geo["latitude"], geo["longitude"], geo.get("display_name", text)[:200])
            context.user_data.pop("awaiting_location_update", None)
            await update.message.reply_text("✅ Lokasi diperbarui.\n/mulai untuk refresh vendor.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await update.message.reply_text(f"Gagal: {e}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(
        update.message,
        "*COOPilot — Operasional Otomatis*\n\n"
        "/setup — nama bisnis, jenis usaha, modal, lokasi\n"
        "/mulai — discovery semua bahan inti\n"
        "/tambah_supplier — vendor tetap (manual)\n"
        "/cari_supplier — discovery bahan tanpa vendor manual\n"
        "/vendor — daftar vendor\n"
        "/reset_vendor — kosongkan vendor untuk demo ulang\n"
        "/bayar <nama> — pembayaran DOKU\n"
        "/kirim_invoice <nama>\n"
        "/stok [item] [qty] — lihat/update stok\n"
        "/reorder — isi ulang otomatis jika stok rendah\n"
        "/rencana — roadmap operasional\n"
        "/lokasi | /profile | /cancel\n\n"
        "_Dashboard kasir:_ `streamlit run dashboard/cashier_app.py` (tanpa Chat ID)",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = _get_profile(update.effective_chat.id, context)
    if not is_profile_complete(profile):
        await update.message.reply_text("Profil belum lengkap. /setup")
        return
    await _safe_reply(
        update.message,
        f"*Profil*\n{format_profile_summary(profile)}",
        parse_mode=ParseMode.MARKDOWN,
    )


def _resolve_supplier(chat_id: int, name_arg: str) -> dict | None:
    suppliers = list_suppliers(chat_id)
    if not suppliers:
        return None
    if name_arg:
        found = find_supplier(chat_id, name_arg)
        if found:
            return found
    if len(suppliers) == 1:
        return suppliers[0]
    return None


async def _run_payment_workflow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    goal: str,
    supplier_name: str = "",
) -> None:
    chat_id = update.effective_chat.id
    if not has_profile(chat_id):
        await update.message.reply_text("Profil belum lengkap. /setup")
        return

    selected = _resolve_supplier(chat_id, supplier_name)
    if not selected:
        await _safe_reply(
            update.message,
            "Pilih vendor:\n\n" + format_supplier_list(chat_id) + "\n\n/bayar <nama> | /mulai",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    profile = _get_profile(chat_id, context) or {}
    wf_context = _build_wf_context(chat_id, context, goal, profile, selected)
    status_msg = await update.message.reply_text(
        f"⏳ Pembayaran ke *{escape_md(selected.get('name', ''))}*...",
        parse_mode=ParseMode.MARKDOWN,
    )
    try:
        run = await asyncio.to_thread(run_goal_flow, wf_context, UserIntent.VENDOR_PAYMENT)
    except Exception as e:
        await status_msg.edit_text(f"❌ {e}")
        return

    for entry in run.feed:
        await _safe_reply(update.message, format_feed_line(entry), parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(FEED_DELAY_SEC)

    if run.status == "ok":
        await _safe_reply(update.message, format_workflow_summary(run), parse_mode=ParseMode.MARKDOWN)
        tg_ok = run.context.get("telegram_invoice_sent")
        extra = "Invoice Telegram: ✅" if tg_ok else "Invoice Telegram: belum (vendor perlu telegram_id)"
        await update.message.reply_text(f"✅ Selesai.\n{extra}\nWA: {run.context.get('supplier_phone', '-')}")
    else:
        await update.message.reply_text(f"Workflow: {run.status}")


async def cmd_bayar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name_arg = " ".join(context.args) if context.args else ""
    goal = f"Bayar vendor {name_arg}".strip() if name_arg else "Bayar vendor"
    await _run_payment_workflow(update, context, goal, supplier_name=name_arg)


async def cmd_kirim_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name_arg = " ".join(context.args) if context.args else ""
    if not name_arg:
        await update.message.reply_text("Gunakan: /kirim_invoice <nama_vendor>")
        return
    await _run_payment_workflow(update, context, f"Kirim invoice ke {name_arg}", supplier_name=name_arg)


async def cmd_rencana(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not has_profile(update.effective_chat.id):
        await update.message.reply_text("Setup dulu: /setup")
        return
    goal = " ".join(context.args) if context.args else "Rencana operasional bisnis"
    profile = _get_profile(update.effective_chat.id, context) or {}
    wf_context = _build_wf_context(update.effective_chat.id, context, goal, profile, None)
    await _run_and_feed(update, context, goal=goal, runner=lambda c: run_goal_flow(c, UserIntent.PLANNING), label="Planning")


async def handle_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if (
        context.user_data.get("in_onboarding")
        or context.user_data.get("adding_supplier")
        or context.user_data.get("awaiting_location_update")
    ):
        return
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    intent = detect_intent(text)
    chat_id = update.effective_chat.id
    profile = _get_profile(chat_id, context) or {}

    if intent == UserIntent.VENDOR_PAYMENT:
        await update.message.reply_text("Gunakan /bayar <nama_vendor> — lihat /vendor")
        return
    if intent == UserIntent.SUPPLY_CHAIN:
        await cmd_mulai(update, context)
        return
    if re.search(r"\b(cari|rekomendasi).*(supplier|vendor)\b", text, re.I):
        await cmd_cari_supplier(update, context)
        return
    if intent == UserIntent.AUTO_REORDER:
        await cmd_reorder(update, context)
        return
    if not has_profile(chat_id):
        await update.message.reply_text("Mulai dengan /setup")
        return

    wf_context = _build_wf_context(chat_id, context, text, profile, None)
    await _run_and_feed(
        update,
        context,
        goal=text,
        runner=lambda c: run_goal_flow(c, intent),
        label=intent.value,
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Telegram error: %s", context.error, exc_info=context.error)


def _global_fallbacks() -> list[CommandHandler]:
    mapping = {
        "help": cmd_help,
        "profile": cmd_profile,
        "lokasi": cmd_lokasi,
        "mulai": cmd_mulai,
        "tambah_supplier": cmd_tambah_supplier,
        "cari_supplier": cmd_cari_supplier,
        "carisupplier": cmd_cari_supplier,
        "carisup": cmd_cari_supplier,
        "vendor": cmd_vendor,
        "daftar_supplier": cmd_vendor,
        "reset_vendor": cmd_reset_vendor,
        "stok": cmd_stok,
        "reorder": cmd_reorder,
        "bayar": cmd_bayar,
        "cancel": onboard_cancel,
    }
    return [CommandHandler(k, mapping[k]) for k in mapping]


def build_application() -> Application:
    app = Application.builder().token(_token()).build()
    fallbacks = _global_fallbacks()

    onboarding = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start), CommandHandler("setup", cmd_setup)],
        states={
            BIZ_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_biz_type)],
            BIZ_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_biz_name)],
            MODAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_modal)],
            BIZ_LOCATION: [
                MessageHandler(filters.LOCATION, onboard_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, onboard_location),
            ],
        },
        fallbacks=fallbacks,
        name="company_onboarding",
    )

    supplier_onboarding = ConversationHandler(
        entry_points=[CommandHandler("tambah_supplier", cmd_tambah_supplier)],
        states={
            SUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_name)],
            SUP_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_contact)],
            SUP_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_phone)],
            SUP_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_address)],
            SUP_TELEGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_telegram)],
            SUP_DOKU: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_doku)],
            SUP_PRODUCTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_products)],
            SUP_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sup_amount)],
        },
        fallbacks=fallbacks + [CommandHandler("tambah_supplier", cmd_tambah_supplier)],
        name="supplier_onboarding",
    )

    for h in fallbacks:
        app.add_handler(h, group=-1)

    app.add_handler(onboarding)
    app.add_handler(supplier_onboarding)
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("mulai", cmd_mulai))
    app.add_handler(CommandHandler("tambah_supplier", cmd_tambah_supplier))
    app.add_handler(CommandHandler("cari_supplier", cmd_cari_supplier))
    app.add_handler(CommandHandler("carisupplier", cmd_cari_supplier))
    app.add_handler(CommandHandler("carisup", cmd_cari_supplier))
    app.add_handler(CommandHandler("daftar_supplier", cmd_vendor))
    app.add_handler(CommandHandler("vendor", cmd_vendor))
    app.add_handler(CommandHandler("reset_vendor", cmd_reset_vendor))
    app.add_handler(CommandHandler("stok", cmd_stok))
    app.add_handler(CommandHandler("reorder", cmd_reorder))
    app.add_handler(CommandHandler("lokasi", cmd_lokasi))
    app.add_handler(CommandHandler("bayar", cmd_bayar))
    app.add_handler(CommandHandler("kirim_invoice", cmd_kirim_invoice))
    app.add_handler(CommandHandler("rencana", cmd_rencana))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location_update))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    logger.info("COOPilot Telegram bot starting...")
    build_application().run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
