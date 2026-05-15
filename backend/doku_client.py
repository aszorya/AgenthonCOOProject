"""DOKU Checkout — generate payment link (sandbox/production)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

CHECKOUT_PATH = "/checkout/v1/payment"
SANDBOX_URL = "https://api-sandbox.doku.com/checkout/v1/payment"
PRODUCTION_URL = "https://api.doku.com/checkout/v1/payment"


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def is_configured() -> bool:
    cid = _env("DOKU_CLIENT_ID")
    secret = _env("DOKU_SECRET_KEY")
    return bool(cid and secret) and not secret.startswith("your_")


def _api_url() -> str:
    if _env("DOKU_CHECKOUT_URL"):
        return _env("DOKU_CHECKOUT_URL")
    sandbox = _env("DOKU_SANDBOX").lower() in ("1", "true", "yes")
    return SANDBOX_URL if sandbox or not _env("DOKU_SANDBOX") else PRODUCTION_URL


def _generate_digest(body_str: str) -> str:
    raw = hashlib.sha256(body_str.encode("utf-8")).digest()
    return base64.b64encode(raw).decode("utf-8")


def _generate_signature(
    client_id: str,
    request_id: str,
    timestamp: str,
    digest: str,
    secret: str,
) -> str:
    component = (
        f"Client-Id:{client_id}\n"
        f"Request-Id:{request_id}\n"
        f"Request-Timestamp:{timestamp}\n"
        f"Request-Target:{CHECKOUT_PATH}\n"
        f"Digest:{digest}"
    )
    sig = hmac.new(secret.encode("utf-8"), component.encode("utf-8"), hashlib.sha256).digest()
    return "HMACSHA256=" + base64.b64encode(sig).decode("utf-8")


def generate_payment_link(
    amount: int,
    invoice_id: str,
    description: str = "",
    *,
    payment_due_minutes: int = 60,
    vendor_doku_id: str = "",
    payee_name: str = "",
) -> dict[str, Any]:
    if not is_configured():
        raise ValueError("Set DOKU_CLIENT_ID and DOKU_SECRET_KEY in coopilot/.env")

    client_id = _env("DOKU_CLIENT_ID")
    secret = _env("DOKU_SECRET_KEY")
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    body: dict[str, Any] = {
        "order": {
            "amount": int(amount),
            "invoice_number": invoice_id[:64],
        },
        "payment": {"payment_due_date": payment_due_minutes},
    }
    info: dict[str, Any] = {}
    if description:
        info["description"] = description[:200]
    if vendor_doku_id:
        info["vendor_doku_id"] = str(vendor_doku_id)[:64]
    if payee_name:
        info["payee_name"] = str(payee_name)[:120]
    if info:
        body["additional_info"] = info

    body_str = json.dumps(body, separators=(",", ":"))
    digest = _generate_digest(body_str)
    signature = _generate_signature(client_id, request_id, timestamp, digest, secret)

    headers = {
        "Content-Type": "application/json",
        "Client-Id": client_id,
        "Request-Id": request_id,
        "Request-Timestamp": timestamp,
        "Signature": signature,
    }

    r = requests.post(_api_url(), data=body_str, headers=headers, timeout=60)
    if not r.ok:
        raise RuntimeError(f"DOKU HTTP {r.status_code}: {r.text[:500]}")

    data = r.json()
    response = data.get("response") or data
    payment = response.get("payment") or {}
    order = response.get("order") or {}
    payment_url = payment.get("url") or data.get("payment_url")

    return {
        "status": "ok",
        "invoice_id": order.get("invoice_number") or invoice_id,
        "amount": int(order.get("amount") or amount),
        "description": description,
        "payment_url": payment_url,
        "session_id": order.get("session_id"),
        "expired_date": payment.get("expired_date"),
        "raw_message": data.get("message"),
    }


def test_connection(*, amount: int = 10000) -> dict[str, Any]:
    invoice = f"COOPILOT-TEST-{uuid.uuid4().hex[:8].upper()}"
    result = generate_payment_link(amount, invoice, "COOPilot connection test")
    return {
        "ok": bool(result.get("payment_url")),
        "invoice_id": result.get("invoice_id"),
        "payment_url": result.get("payment_url"),
        "amount": result.get("amount"),
    }
