"""
Dashboard kasir COOPilot — catat penjualan, update stok, auto-reorder.

Bisnis otomatis = pemilik yang sudah /setup di Telegram (tanpa input Chat ID).

Jalankan dari folder coopilot/:
  streamlit run dashboard/cashier_app.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend.business_profile import format_profile_summary, resolve_cashier_chat_id
from backend import inventory_service, sales_service
from backend.orchestrator import run_cashier_sale_flow

st.set_page_config(page_title="COOPilot Kasir", page_icon="🧾", layout="wide")

st.title("🧾 Dashboard Kasir COOPilot")
st.caption("Catat penjualan → agen update stok bahan baku → auto-reorder jika stok rendah")

chat_id, profile = resolve_cashier_chat_id()

with st.sidebar:
    st.header("Bisnis aktif")
    cashier_name = st.text_input("Nama kasir", value="Kasir 1")
    st.divider()
    if profile and chat_id:
        st.markdown(format_profile_summary(profile))
        st.caption("Terhubung ke pemilik yang /setup di Telegram.")
    else:
        st.warning(
            "Belum ada bisnis terdaftar.\n\n"
            "Pemilik bisnis harus menyelesaikan **/setup** di bot Telegram COOPilot dulu."
        )

if not chat_id or not profile:
    st.info(
        "**Kasir tidak perlu memasukkan Chat ID.**\n\n"
        "1. Pemilik buka bot Telegram → `/setup`\n"
        "2. Selesaikan profil bisnis\n"
        "3. Refresh halaman dashboard ini\n\n"
        "Opsional admin: set `CASHIER_CHAT_ID` di `.env` jika ada banyak bisnis."
    )
    st.stop()

tab_sale, tab_history, tab_stock, tab_agents = st.tabs(
    ["Input penjualan", "Laporan hari ini", "Stok bahan baku", "Log agen"]
)

with tab_sale:
    st.subheader("Catat penjualan")
    with st.form("sale_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            product = st.text_input("Produk terjual", placeholder="Espresso, Latte, ...")
        with col2:
            qty = st.number_input("Jumlah", min_value=1, value=1, step=1)
        with col3:
            unit_price = st.number_input("Harga satuan (Rp)", min_value=0, value=0, step=1000)
        submitted = st.form_submit_button("Simpan & proses agen", type="primary", use_container_width=True)

    if submitted:
        if not product.strip():
            st.error("Nama produk wajib diisi.")
        else:
            with st.spinner("Agen memproses penjualan, stok, dan reorder..."):
                run = run_cashier_sale_flow(
                    {
                        "chat_id": chat_id,
                        "profile": profile,
                        "product": product.strip(),
                        "qty": int(qty),
                        "unit_price": float(unit_price),
                        "cashier_name": cashier_name,
                    }
                )
            st.session_state["last_run"] = run.to_dict()
            if run.status == "ok":
                st.success("Penjualan diproses.")
            else:
                st.warning(f"Selesai dengan status: {run.status}")

            for entry in run.feed:
                icon = {"ok": "✅", "blocked": "⛔", "error": "❌"}.get(entry.get("status"), "▶️")
                st.write(f"{icon} {entry.get('message', '')}")

            if run.context.get("stock_updates"):
                st.markdown("**Perubahan stok**")
                for u in run.context["stock_updates"]:
                    st.write(
                        f"- {u['item']}: -{u['deducted']} → sisa **{u['remaining']}** {u.get('unit', '')}"
                    )
            if run.context.get("payment_url"):
                st.markdown(f"**Link pembayaran reorder:** {run.context['payment_url']}")
            if run.context.get("telegram_reorder_notified"):
                st.info("Notifikasi reorder terkirim ke Telegram pemilik bisnis.")

with tab_history:
    st.subheader(f"Penjualan — {date.today().isoformat()}")
    summary = sales_service.daily_summary(chat_id)
    m1, m2, m3 = st.columns(3)
    m1.metric("Transaksi", summary["transaction_count"])
    m2.metric("Unit terjual", summary["total_qty"])
    m3.metric("Omzet (Rp)", f"{summary['total_revenue']:,.0f}")

    if summary["by_product"]:
        st.markdown("**Per produk**")
        for name, count in summary["by_product"].items():
            st.write(f"- {name}: {count} unit")

    if summary["sales"]:
        st.dataframe(
            [
                {
                    "Waktu": s.get("timestamp", "")[:19],
                    "Produk": s.get("product"),
                    "Qty": s.get("qty"),
                    "Kasir": s.get("cashier"),
                    "Total": s.get("total"),
                }
                for s in summary["sales"]
            ],
            use_container_width=True,
        )
    else:
        st.caption("Belum ada penjualan hari ini.")

with tab_stock:
    st.subheader("Stok bahan baku")
    items = inventory_service.list_inventory(chat_id)
    if not items:
        st.caption("Stok kosong. Jalankan /mulai di Telegram untuk inisialisasi.")
    else:
        for row in items:
            qty = row.get("qty", 0)
            initial = row.get("initial_qty", 100)
            pct = int(qty / initial * 100) if initial else 0
            st.progress(min(pct / 100, 1.0), text=f"{row['item']}: {qty} {row.get('unit', '')}")
            if row.get("linked_vendor"):
                st.caption(f"Vendor: {row['linked_vendor']}")

        low = inventory_service.items_needing_reorder(chat_id)
        if low:
            st.warning("Stok rendah: " + ", ".join(r["item"] for r in low))

with tab_agents:
    st.subheader("Log agen terakhir")
    last = st.session_state.get("last_run")
    if not last:
        st.caption("Belum ada proses. Input penjualan di tab pertama.")
    else:
        st.json(last)
