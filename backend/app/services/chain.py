"""Intent-to-Payment Integrity Chain: eight stages, each hashed and linked to the one before it.
Everything is recomputed from stored rows on every call, so it can never show a stale 'all good'."""
import hashlib, json
from ..core.fingerprint import intent_fingerprint, sha256_hex
from . import service as s
from .payments import get_payment_row


def _stage(n, key, title, status, h, detail):
    return {"n": n, "key": key, "title": title, "status": status, "hash": h, "detail": detail}


def build_chain(conn, tid):
    r = s._row(conn, "transactions", tid, "transaction")
    ir, orow = s._row(conn, "intents", r["intent_id"], "intent"), s._row(conn, "offers", r["offer_id"], "offer")
    intent, offer, cart = json.loads(ir["constraints_json"]), json.loads(orow["offer_json"]), json.loads(r["cart_json"])
    v = s._evaluate(conn, r)
    consent = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (tid,)).fetchone()
    pay = get_payment_row(conn, tid)
    ev = conn.execute("SELECT hash FROM audit_events WHERE transaction_id=? ORDER BY id DESC LIMIT 1", (tid,)).fetchone()
    fp_intact = intent_fingerprint(intent) == ir["fingerprint"]
    high = [t for t in v["threats"] if t["severity"] == "high"]
    cstate = s.consent_state(consent)

    stages = [
        _stage(1, "intent", "Original customer intent", "ok", sha256_hex({"instruction": ir["instruction"]}), "The customer's own words."),
        _stage(2, "passport", "Intent Passport", "ok" if fp_intact and ir["status"] == "CONFIRMED" else "broken" if not fp_intact else "pending",
               ir["fingerprint"], f"Structured constraints ({ir['source']}); " + ("confirmed by the customer." if ir["status"] == "CONFIRMED" else "NOT confirmed yet.") + ("" if fp_intact else " Fingerprint mismatch!")),
        _stage(3, "offer", "Merchant offer (untrusted)", "warn" if high else "ok", sha256_hex(offer),
               f"{len(v['threats'])} finding(s), {len(high)} high-severity. Merchant text is data, never instructions."),
        _stage(4, "cart", "Final cart and server total", "ok", sha256_hex({"cart": cart, "total": v["server_total"]}), f"Server-computed total: {v['server_total']} minor units."),
        _stage(5, "verification", "Deterministic verification", "ok" if v["decision"] == "VERIFIED" else "blocked", v["transaction_fingerprint"],
               "PASS" if v["decision"] == "VERIFIED" else "BLOCKED: " + ", ".join(c["id"] for c in v["checks"] if not c["passed"])),
        _stage(6, "consent", "Explicit human consent", {"ACTIVE": "ok", "CONSUMED": "ok", "EXPIRED": "broken", "REJECTED": "blocked", "NONE": "pending"}[cstate],
               sha256_hex({"consent": consent["id"], "fingerprint": consent["fingerprint"]}) if consent else None,
               {"NONE": "Not asked yet.", "REJECTED": "Customer rejected.", "ACTIVE": "Granted; waiting for payment.", "CONSUMED": "Granted and used once.", "EXPIRED": "Expired."}[cstate]),
        _stage(7, "payment", "PayPal Sandbox order and capture", {"COMPLETED": "ok", "FAILED": "broken", "CANCELLED": "blocked", "EXPIRED": "broken"}.get(pay["state"] if pay else "", "pending"),
               sha256_hex({"order": pay["paypal_order_id"], "capture": pay["capture_id"], "amount": pay["amount_minor"], "currency": pay["currency"]}) if pay else None,
               f"State {pay['state']}." if pay else "No payment started."),
        _stage(8, "audit", "Tamper-evident audit trail", "ok", ev["hash"] if ev else None, "Hash-chained audit events for this transaction."),
    ]
    # Cross-stage bindings: the same fingerprint / amount must appear at every stage that exists.
    bindings = []
    if consent and consent["decision"] == "GRANTED":
        bindings.append({"name": "consent is bound to the verified transaction fingerprint", "ok": consent["fingerprint"] == v["transaction_fingerprint"]})
    if pay:
        bindings.append({"name": "PayPal amount equals the server-computed total", "ok": pay["amount_minor"] == v["server_total"]})
        bindings.append({"name": "PayPal currency equals the intent currency", "ok": pay["currency"] == intent["currency"]})
        if consent:
            bindings.append({"name": "payment exists only with a granted consent", "ok": consent["decision"] == "GRANTED"})
    prev = ""
    for st in stages:
        if st["hash"] is None:
            st["link"] = None
            continue
        prev = hashlib.sha256((prev + st["hash"]).encode()).hexdigest()
        st["link"] = prev
    return {"transaction_id": tid, "stages": stages, "bindings": bindings, "intact": all(b["ok"] for b in bindings) and fp_intact,
            "head_link": prev or None,
            "note": "Each link = SHA-256(previous link + this stage's hash). Changing any earlier stage changes every later link."}
