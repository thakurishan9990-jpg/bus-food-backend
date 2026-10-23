"""Razorpay payments.

Three jobs: open a Razorpay order for one of ours, verify the signature the
browser hands back, and refund when a payment lands after the kitchen cut-off
has already passed.

The key secret is used for HTTP basic auth and for the HMAC signature. It never
leaves this module and is never sent to the browser — the browser only ever
sees the key id, which is public by design.
"""

import hmac
from hashlib import sha256

import httpx

from app.config import settings
from app.utils.errors import BadRequestError

RAZORPAY_API = "https://api.razorpay.com/v1"
TIMEOUT = 15.0


def _auth() -> tuple[str, str]:
    return (settings.razorpay_key_id, settings.razorpay_key_secret)


def to_paise(amount_inr: int) -> int:
    """Razorpay works in the smallest currency unit. ₹367 -> 36700.

    Money is whole rupees end to end, so this is integer arithmetic only.
    """
    return amount_inr * 100


def create_payment_order(order_id: int, amount_inr: int, *, notes: dict | None = None) -> str:
    """Open a Razorpay order and return its id. Raises BadRequestError if Razorpay refuses."""
    try:
        resp = httpx.post(
            f"{RAZORPAY_API}/orders",
            auth=_auth(),
            json={
                "amount": to_paise(amount_inr),
                "currency": "INR",
                "receipt": f"dhabago_{order_id}",
                "notes": notes or {},
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except (httpx.HTTPError, KeyError) as exc:
        raise BadRequestError(f"Could not start the payment: {exc}") from exc


def verify_signature(razorpay_order_id: str, razorpay_payment_id: str, signature: str) -> bool:
    """Check the HMAC Razorpay returns to the browser.

    The signature is HMAC-SHA256 of "<order_id>|<payment_id>" keyed with the
    secret. Compared in constant time — a plain == here would leak the digest
    one byte at a time.
    """
    expected = hmac.new(
        settings.razorpay_key_secret.encode(),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
        sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def refund(razorpay_payment_id: str) -> bool:
    """Refund a payment in full. Used when the bus got too close while the
    passenger was still on the checkout screen — we take no money for food the
    kitchen can no longer make in time."""
    try:
        resp = httpx.post(
            f"{RAZORPAY_API}/payments/{razorpay_payment_id}/refund",
            auth=_auth(),
            json={"speed": "normal"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        return False
