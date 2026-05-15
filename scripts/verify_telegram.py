"""Verify TELEGRAM_BOT_TOKEN. Run: python scripts/verify_telegram.py"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def _main() -> int:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print("FAIL: TELEGRAM_BOT_TOKEN empty in .env")
        return 1
    from telegram import Bot

    me = await Bot(token).get_me()
    print(f"PASS: @{me.username} ({me.first_name})")
    print(f"Chat: https://t.me/{me.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
