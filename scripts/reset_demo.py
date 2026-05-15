"""
Reset COOPilot untuk demo video — hentikan bot, bersihkan cache lokal.

Dari folder coopilot/:
  python scripts/reset_demo.py
  python scripts/reset_demo.py --stop-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACTIVE_BUSINESS = ROOT / "data" / "active_business.json"


def stop_telegram() -> None:
    if sys.platform == "win32":
        ps = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -match 'run_telegram|telegram_bot' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }",
            ],
            capture_output=True,
            text=True,
        )
        killed = [x.strip() for x in ps.stdout.splitlines() if x.strip()]
        if killed:
            print(f"Bot Telegram dihentikan (PID: {', '.join(killed)})")
        else:
            print("Tidak ada proses bot Telegram yang berjalan.")
    else:
        subprocess.run(["pkill", "-f", "run_telegram"], check=False)
        print("pkill run_telegram dijalankan.")


def clear_local_state(chat_id: str | None = None) -> None:
    from backend import business_profile, inventory_service, sales_service, supplier_registry

    business_profile._profile_cache.clear()
    if chat_id:
        supplier_registry.clear_suppliers_local(chat_id)
    else:
        supplier_registry._supplier_cache.clear()
    inventory_service._inventory_cache.clear()
    sales_service._sales_cache.clear()

    if ACTIVE_BUSINESS.is_file():
        ACTIVE_BUSINESS.unlink()
        print(f"Dihapus: {ACTIVE_BUSINESS}")
    else:
        print("Tidak ada active_business.json (sudah bersih).")

    print("Cache lokal (profil, vendor, stok, penjualan) dikosongkan.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset COOPilot untuk demo")
    parser.add_argument("--stop-only", action="store_true", help="Hanya hentikan bot")
    parser.add_argument("--chat-id", type=str, default="", help="Kosongkan vendor cache untuk chat_id ini")
    args = parser.parse_args()

    print("=== COOPilot Demo Reset ===\n")
    stop_telegram()

    if args.stop_only:
        return 0

    clear_local_state(args.chat_id.strip() or None)

    print(
        "\n--- Langkah demo berikutnya ---\n"
        "1. Ganti MEM9_API_KEY di .env (key baru) agar vendor/profil lama di cloud hilang.\n"
        "2. Jalankan bot: python scripts/run_telegram.py\n"
        "3. Di Telegram: /reset_vendor lalu /setup atau /mulai\n"
        "4. Cek /vendor — max ~4 vendor unik (bukan toko yang sama 8x)\n"
        "\nCatatan: Mem9 menambah memori baru tiap simpan; dedupe di /vendor menggabung toko sama."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
