"""Approval is bound to a transaction fingerprint. Any change invalidates it."""
import time
from .verification import verify

APPROVAL_TTL_SECONDS = 300


def create_approval(result: dict, now: float | None = None) -> dict:
    if result["decision"] != "VERIFIED":
        raise ValueError("Cannot approve a blocked transaction")
    return {"fingerprint": result["transaction_fingerprint"], "created": now or time.time(), "used": False}


def authorize_payment(approval: dict, intent: dict, offer: dict, cart: list[dict], now: float | None = None) -> tuple[bool, str]:
    """Server re-verifies from scratch right before payment. Returns (ok, reason)."""
    now = now or time.time()
    if approval["used"]:
        return False, "replay: approval already used"
    if now - approval["created"] > APPROVAL_TTL_SECONDS:
        return False, "stale: approval expired"
    fresh = verify(intent, offer, cart)
    if fresh["decision"] != "VERIFIED":
        return False, "blocked: transaction no longer verifies"
    if fresh["transaction_fingerprint"] != approval["fingerprint"]:
        return False, "changed: transaction differs from what the user approved"
    approval["used"] = True
    return True, "ok"
