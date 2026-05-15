"""Route user goals to COOPilot workflows."""

from __future__ import annotations

import re
from enum import Enum


class UserIntent(str, Enum):
    VENDOR_PAYMENT = "vendor_payment"
    PLANNING = "planning"
    MARKETING = "marketing"
    SUPPLY_CHAIN = "supply_chain"
    AUTO_REORDER = "auto_reorder"
    HELP = "help"


_PAYMENT = re.compile(
    r"\b(bayar|pembayaran|transfer|supplier|vendor|invoice|tagih)\b",
    re.I,
)
_MARKETING = re.compile(
    r"\b(campaign|marketing|iklan|promosi|penjualan|jualan|ads)\b",
    re.I,
)
_PLANNING = re.compile(
    r"\b(rencana|strategi|tingkatkan|tumbuh|goal|target|operasional)\b",
    re.I,
)
_SUPPLY = re.compile(r"\b(mulai|setup.?vendor|rantai.?pasok|discovery)\b", re.I)
_REORDER = re.compile(r"\b(reorder|stok.?habis|restock|isi.?ulang)\b", re.I)


def detect_intent(text: str) -> UserIntent:
    t = (text or "").strip()
    if not t:
        return UserIntent.HELP
    if _REORDER.search(t):
        return UserIntent.AUTO_REORDER
    if _SUPPLY.search(t):
        return UserIntent.SUPPLY_CHAIN
    if _PAYMENT.search(t):
        return UserIntent.VENDOR_PAYMENT
    if _MARKETING.search(t):
        return UserIntent.MARKETING
    if _PLANNING.search(t):
        return UserIntent.PLANNING
    return UserIntent.PLANNING
