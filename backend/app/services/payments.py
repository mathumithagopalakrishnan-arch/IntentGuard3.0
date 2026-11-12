"""Intent-bound PayPal Sandbox checkout with a persistent payment state machine.

Lifecycle (payments.state):
  CREATING -> ORDER_CREATED -> CAPTURING -> COMPLETED
                         \\-> CAPTURE_PENDING (PayPal says the capture is pending)
  FAILED / CANCELLED / EXPIRED are terminal. A new payment needs a new transaction and a new consent.

Trust rules (each one is covered by a test):
  * The amount sent to PayPal is the server-recomputed total of the verified transaction, never a client value.
  * An order is created only when a consent exists, is GRANTED, unexpired and unused, and the transaction still verifies
    with the same fingerprint the customer approved.
  * Capture happens only after PayPal itself reports APPROVED for THIS order, with the amount, currency and custom_id we expect.
  * The consent is consumed in the same write transaction that moves the payment to CAPTURING (one-time use).
  * Network calls never run inside a database transaction, so a slow PayPal cannot hold the database lock.
"""
import json, time, urllib.parse, uuid
from ..config import settings
from ..core.money import from_paypal_value, to_paypal_value
from ..database.db import tx
from . import service as s
from .paypal import PayPalError

ALLOWED_NEXT = {
    "CREATING": {"ORDER_CREATED", "FAILED", "EXPIRED"},
    "ORDER_CREATED": {"CAPTURING", "CANCELLED", "EXPIRED", "FAILED"},
    "CAPTURING": {"COMPLETED", "CAPTURE_PENDING", "FAILED"},
    "CAPTURE_PENDING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(), "FAILED": set(), "CANCELLED": set(), "EXPIRED": set(),
}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED"}


def get_payment_row(conn, tid):
    return conn.execute("SELECT * FROM payments WHERE transaction_id=?", (tid,)).fetchone()


def payment_view(p):
    if p is None:
        return None
    return {"id": p["id"], "transaction_id": p["transaction_id"], "state": p["state"], "amount_minor": p["amount_minor"], "currency": p["currency"],
            "paypal_order_id": p["paypal_order_id"], "paypal_status": p["paypal_status"], "capture_id": p["capture_id"], "capture_status": p["capture_status"],
            "approve_url": p["approve_url"] if p["state"] == "ORDER_CREATED" else None,
            "error_code": p["error_code"], "error_message": p["error_message"], "attempts": p["attempts"],
            "created_at": p["created_at"], "updated_at": p["updated_at"], "sandbox": True}


def _set(conn, tid, new_state=None, **cols):
    """Write columns, and when a state is given, enforce the state machine."""
    if new_state:
        cur = get_payment_row(conn, tid)["state"]
        if new_state != cur and new_state not in ALLOWED_NEXT[cur]:
            raise s.ServiceError(409, f"illegal payment transition {cur} -> {new_state}")
        cols["state"] = new_state
    cols["updated_at"] = s._now_iso()
    keys = list(cols)
    conn.execute(f"UPDATE payments SET {', '.join(k + '=?' for k in keys)} WHERE transaction_id=?", [cols[k] for k in keys] + [tid])


def _refuse(conn, tid, intent_id, reason, status=409, terminal_state=None):
    """Record the refusal in the audit chain (kept even though the request fails), optionally closing the payment."""
    if terminal_state and get_payment_row(conn, tid):
        _set(conn, tid, terminal_state, error_code="refused", error_message=reason)
    s.audit(conn, "payment_refused", {"reason": reason}, intent_id, tid)
    return s.ServiceError(status, reason)


def build_order_payload(offer: dict, cart: list[dict], tid: str, currency: str) -> dict:
    """Order Orders v2 body built ONLY from stored, server-verified data."""
    catalog = {i["id"]: i for i in offer["items"]}
    items, sub = [], 0
    for line in cart:
        it = catalog[line["item_id"]]
        items.append({"name": it["name"][:127], "quantity": str(line["qty"]),
                      "unit_amount": {"currency_code": currency, "value": to_paypal_value(it["unit_price"], currency)}})
        sub += it["unit_price"] * line["qty"]
    ship, tax = offer.get("shipping", 0), offer.get("tax", 0)
    total = sub + ship + tax
    base = settings.PAYPAL_RETURN_URL().rstrip("/")
    cancel = settings.PAYPAL_CANCEL_URL().rstrip("/")
    return {"intent": "CAPTURE",
            "purchase_units": [{"reference_id": "default", "custom_id": tid, "invoice_id": "IG-" + tid,
                                "description": "IntentGuard Sandbox demo purchase (synthetic, no real goods)"[:127],
                                "amount": {"currency_code": currency, "value": to_paypal_value(total, currency),
                                           "breakdown": {"item_total": {"currency_code": currency, "value": to_paypal_value(sub, currency)},
                                                         "shipping": {"currency_code": currency, "value": to_paypal_value(ship, currency)},
                                                         "tax_total": {"currency_code": currency, "value": to_paypal_value(tax, currency)}}},
                                "items": items}],
            "payment_source": {"paypal": {"experience_context": {
                "brand_name": "IntentGuard (Sandbox demo)", "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
                "landing_page": "LOGIN", "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                "return_url": f"{base}/{tid}", "cancel_url": f"{cancel}/{tid}"}}}}, total


def _approve_link(order: dict):
    for link in order.get("links", []) or []:
        if link.get("rel") in ("payer-action", "approve") and isinstance(link.get("href"), str):
            u = urllib.parse.urlparse(link["href"])
            host = (u.hostname or "").lower()
            if u.scheme == "https" and (host == "sandbox.paypal.com" or host.endswith(".sandbox.paypal.com")):
                return link["href"]
    return None


def _consent_for_checkout(conn, tid, r, now):
    """All the gates for starting a checkout. Returns (consent_row, fresh_verification) or raises ServiceError."""
    c = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (tid,)).fetchone()
    st = s.consent_state(c, now)
    if st == "NONE":
        raise _refuse(conn, tid, r["intent_id"], "no customer consent exists for this transaction")
    if st == "REJECTED":
        raise _refuse(conn, tid, r["intent_id"], "the customer rejected this transaction")
    if st == "CONSUMED":
        raise _refuse(conn, tid, r["intent_id"], "this approval was already used (replay blocked)")
    if st == "EXPIRED":
        raise _refuse(conn, tid, r["intent_id"], "consent expired: please approve the transaction again")
    fresh = s._evaluate(conn, r)
    if fresh["decision"] != "VERIFIED":
        raise _refuse(conn, tid, r["intent_id"], "the transaction no longer passes verification")
    if fresh["transaction_fingerprint"] != c["fingerprint"] or fresh["transaction_fingerprint"] != r["fingerprint"]:
        raise _refuse(conn, tid, r["intent_id"], "the transaction changed after the customer approved it; approval is void")
    return c, fresh


def start_checkout(conn, client, tid, now=None):
    now = time.time() if now is None else now
    if not client.configured:  # refuse BEFORE any payment row exists, so adding credentials later just works
        raise s.ServiceError(503, "PayPal Sandbox credentials are not set (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET in backend/.env). Nothing was started.")
    problem = None
    with tx(conn):
        r = s._row(conn, "transactions", tid, "transaction")
        p = get_payment_row(conn, tid)
        if p is not None:
            if p["state"] in ("COMPLETED", "CAPTURING", "CAPTURE_PENDING"):
                return payment_view(p)
            if p["state"] == "ORDER_CREATED":
                c = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (tid,)).fetchone()
                if s.consent_state(c, now) != "ACTIVE":
                    _set(conn, tid, "EXPIRED", error_code="consent_expired", error_message="consent expired before the buyer approved")
                    s.audit(conn, "payment_expired", {"order": p["paypal_order_id"]}, r["intent_id"], tid)
                    problem = "consent expired before payment: please approve the transaction again"
                else:
                    return payment_view(p)  # idempotent: same order, same approval link
            elif p["state"] != "CREATING":
                problem = f"payment is {p['state']}; create a new transaction to try again"
        if problem is None and (p is None or p["state"] == "CREATING"):
            if p is None:
                try:
                    c, fresh = _consent_for_checkout(conn, tid, r, now)
                except s.ServiceError as e:
                    problem = e.message
                    c = fresh = None
                if problem is None:
                    cur = json.loads(s._row(conn, "offers", r["offer_id"], "offer")["offer_json"])["currency"]
                    if cur not in settings.PAYPAL_CURRENCIES():
                        problem = f"currency {cur} is not enabled for the PayPal Sandbox demo (enabled: {sorted(settings.PAYPAL_CURRENCIES())})"
                        s.audit(conn, "payment_refused", {"reason": problem}, r["intent_id"], tid)
                    elif not fresh["server_total"] or fresh["server_total"] <= 0:
                        problem = "nothing to pay"
                        s.audit(conn, "payment_refused", {"reason": problem}, r["intent_id"], tid)
                    else:
                        conn.execute("INSERT INTO payments(id,transaction_id,state,amount_minor,currency,create_request_id) VALUES(?,?,'CREATING',?,?,?)",
                                     (uuid.uuid4().hex, tid, fresh["server_total"], cur, uuid.uuid4().hex))
                        s.audit(conn, "payment_checkout_started", {"amount_minor": fresh["server_total"], "currency": cur, "sandbox": True}, r["intent_id"], tid)
            else:
                c = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (tid,)).fetchone()
                try:
                    c, fresh = _consent_for_checkout(conn, tid, r, now)
                except s.ServiceError as e:
                    if s.consent_state(c, now) == "EXPIRED":
                        _set(conn, tid, "EXPIRED", error_code="consent_expired", error_message="consent expired while creating the order")
                        s.audit(conn, "payment_expired", {}, r["intent_id"], tid)
                    else:
                        _set(conn, tid, "FAILED", error_code="authorization_changed", error_message=e.message)
                    problem = e.message
                else:
                    cur = json.loads(s._row(conn, "offers", r["offer_id"], "offer")["offer_json"])["currency"]
                    if fresh["server_total"] != p["amount_minor"] or cur != p["currency"]:
                        problem = "the transaction amount or currency changed while creating the order"
                        _set(conn, tid, "FAILED", error_code="amount_changed", error_message=problem)
                        s.audit(conn, "payment_refused", {"reason": problem}, r["intent_id"], tid)
    if problem:
        raise s.ServiceError(409, problem)

    # ---- network call, outside any DB transaction ----
    p = get_payment_row(conn, tid)
    r = s._row(conn, "transactions", tid, "transaction")
    offer = json.loads(s._row(conn, "offers", r["offer_id"], "offer")["offer_json"])
    payload, total = build_order_payload(offer, json.loads(r["cart_json"]), tid, p["currency"])
    if total != p["amount_minor"]:  # stored data changed between the gate and now: stop
        with tx(conn):
            _set(conn, tid, "FAILED", error_code="amount_changed", error_message="server total changed during checkout")
            s.audit(conn, "payment_refused", {"reason": "server total changed during checkout"}, r["intent_id"], tid)
        raise s.ServiceError(409, "the transaction changed during checkout; nothing was sent to PayPal")
    try:
        order = client.create_order(payload, p["create_request_id"])
        if not isinstance(order.get("id"), str) or not order["id"] or order.get("status") not in ("CREATED", "PAYER_ACTION_REQUIRED"):
            raise PayPalError("PayPal returned an unexpected order response.", code="bad_response")
        link = _approve_link(order)
        if not link:
            raise PayPalError("PayPal did not return a Sandbox approval link.", code="no_approve_link")
    except PayPalError as e:
        with tx(conn):
            _set(conn, tid, None, attempts=p["attempts"] + 1, error_code=e.code, error_message=e.message)
            if not e.retryable:
                _set(conn, tid, "FAILED")
            s.audit(conn, "paypal_order_failed", {"code": e.code, "retryable": e.retryable, "http": e.status}, r["intent_id"], tid)
        raise s.ServiceError(502 if not e.retryable else 503, e.message + (" You can safely retry." if e.retryable else ""))
    with tx(conn):
        cur = get_payment_row(conn, tid)
        if cur["state"] == "CREATING":
            _set(conn, tid, "ORDER_CREATED", paypal_order_id=order["id"], approve_url=link, paypal_status=order.get("status"), error_code=None, error_message=None)
            s.audit(conn, "paypal_order_created", {"order_id": order["id"], "amount_minor": cur["amount_minor"], "currency": cur["currency"], "sandbox": True}, r["intent_id"], tid)
    return payment_view(get_payment_row(conn, tid))


def _check_order_matches(order, p, tid):
    """Authoritative PayPal data must match what we stored and what the customer approved."""
    units = order.get("purchase_units") or []
    if len(units) != 1:
        return "PayPal order does not have exactly one purchase unit"
    u = units[0]
    if u.get("custom_id") != tid:
        return "PayPal order belongs to a different transaction"
    amt = u.get("amount") or {}
    if amt.get("currency_code") != p["currency"]:
        return "PayPal currency does not match the approved transaction"
    try:
        if from_paypal_value(amt.get("value"), p["currency"]) != p["amount_minor"]:
            return "PayPal amount does not match the approved transaction"
    except ValueError:
        return "PayPal amount is unreadable"
    return None


def confirm_and_capture(conn, client, tid, order_id, now=None):
    now = time.time() if now is None else now
    if not isinstance(order_id, str) or not order_id or len(order_id) > 64:
        raise s.ServiceError(422, "order_id is required")
    deferred = None  # refusals are raised AFTER the commit so their audit rows are kept
    with tx(conn):
        r = s._row(conn, "transactions", tid, "transaction")
        p = get_payment_row(conn, tid)
        if p is None:
            raise s.ServiceError(409, "no checkout was started for this transaction")
        if p["paypal_order_id"] != order_id:
            deferred = _refuse(conn, tid, r["intent_id"], "this PayPal order ID is not the order created for this transaction")
        elif p["state"] == "COMPLETED":
            return payment_view(p)  # duplicate request: never captures twice
        elif p["state"] in TERMINAL:
            raise s.ServiceError(409, f"payment is {p['state']}; create a new transaction to try again")
    if deferred:
        raise deferred
    # ---- authoritative PayPal state (network, outside the DB transaction) ----
    try:
        order = client.get_order(order_id)
    except PayPalError as e:
        raise s.ServiceError(503 if e.retryable else 502, e.message + (" You can safely retry." if e.retryable else ""))
    already_started = p["state"] in ("CAPTURING", "CAPTURE_PENDING")
    if order.get("status") == "COMPLETED" and already_started:
        recovery_problem = None
        with tx(conn):
            current = get_payment_row(conn, tid)
            if current["state"] == "COMPLETED":
                return payment_view(current)
            if current["state"] not in ("CAPTURING", "CAPTURE_PENDING"):
                recovery_problem = s.ServiceError(409, f"payment is {current['state']}; capture recovery is no longer available")
            else:
                bad = _check_order_matches(order, current, tid)
                if bad:
                    recovery_problem = _refuse(conn, tid, r["intent_id"], bad, terminal_state="FAILED")
        if recovery_problem:
            raise recovery_problem
        return _record_capture(conn, tid, r, order, current)
    if order.get("status") != "APPROVED":
        with tx(conn):
            s.audit(conn, "payment_not_approved", {"paypal_status": order.get("status")}, r["intent_id"], tid)
        raise s.ServiceError(409, f"PayPal reports the order as {order.get('status')}, not APPROVED. The buyer has not approved it, so nothing was captured.")
    return_problem = None
    with tx(conn):
        p = get_payment_row(conn, tid)
        if p["state"] == "COMPLETED":
            return payment_view(p)
        if p["state"] not in ("ORDER_CREATED", "CAPTURING", "CAPTURE_PENDING"):
            return_problem = f"payment is {p['state']}; capture is no longer available"
        elif not p["capture_request_id"] and p["state"] in ("CAPTURING", "CAPTURE_PENDING"):
            deferred = _refuse(conn, tid, r["intent_id"], "capture request id is missing; refusing to send a capture", terminal_state="FAILED")
        else:
            bad = _check_order_matches(order, p, tid)
        if deferred is None and return_problem is None and bad:
            deferred = _refuse(conn, tid, r["intent_id"], bad, terminal_state="FAILED")
        elif deferred is None and return_problem is None and p["state"] == "ORDER_CREATED":
            c = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (tid,)).fetchone()
            if s.consent_state(c, now) == "EXPIRED":
                _set(conn, tid, "EXPIRED", error_code="consent_expired", error_message="consent expired before capture")
                s.audit(conn, "payment_expired", {"order": order_id}, r["intent_id"], tid)
                return_problem = "consent expired before capture: nothing was captured. Please approve a new transaction."
            else:
                fresh = s._evaluate(conn, r)
                if fresh["decision"] != "VERIFIED" or fresh["transaction_fingerprint"] != c["fingerprint"] or fresh["server_total"] != p["amount_minor"]:
                    deferred = _refuse(conn, tid, r["intent_id"], "the transaction changed after approval; capture refused", terminal_state="FAILED")
                else:
                    s.consume_consent_in_tx(conn, tid, now)  # atomic one-time use; raises (and rolls back) if missing/used
                    _set(conn, tid, "CAPTURING", capture_request_id=uuid.uuid4().hex, paypal_status="APPROVED")
                    s.audit(conn, "payment_capture_started", {"order_id": order_id}, r["intent_id"], tid)
        # else: retry of an interrupted capture. The consent was already consumed and the same capture request id is reused.
    if deferred:
        raise deferred
    if return_problem:
        raise s.ServiceError(409, return_problem)
    p = get_payment_row(conn, tid)
    if p["state"] not in ("CAPTURING", "CAPTURE_PENDING") or not p["capture_request_id"]:
        raise s.ServiceError(409, f"payment is {p['state']}; no valid capture attempt is available")
    try:
        cap = client.capture_order(order_id, p["capture_request_id"])
    except PayPalError as e:
        if e.retryable:
            with tx(conn):
                _set(conn, tid, None, attempts=p["attempts"] + 1, error_code=e.code, error_message=e.message)
                s.audit(conn, "paypal_capture_unknown", {"code": e.code, "http": e.status}, r["intent_id"], tid)
            raise s.ServiceError(503, e.message + " The capture outcome is unknown; retrying is safe and cannot charge twice.")
        if e.code == "ORDER_ALREADY_CAPTURED":
            try:
                return _record_capture(conn, tid, r, client.get_order(order_id), p)
            except PayPalError:
                pass
        with tx(conn):
            _set(conn, tid, "FAILED", error_code=e.code, error_message=e.message)
            s.audit(conn, "paypal_capture_failed", {"code": e.code, "http": e.status}, r["intent_id"], tid)
        raise s.ServiceError(502, e.message)
    return _record_capture(conn, tid, r, cap, p)


def _record_capture(conn, tid, r, cap, p):
    """Verify the authoritative capture response, then store it."""
    with tx(conn):
        p = get_payment_row(conn, tid)
        if p["state"] == "COMPLETED":
            return payment_view(p)
        units = cap.get("purchase_units") or []
        caps = (((units[0] if units else {}).get("payments") or {}).get("captures")) or []
        c0 = caps[0] if caps else {}
        problem = None
        if cap.get("id") != p["paypal_order_id"]:
            problem = "capture response is for a different order"
        elif cap.get("status") not in ("COMPLETED", "PENDING") and c0.get("status") not in ("COMPLETED", "PENDING"):
            problem = f"capture was not completed (status {cap.get('status')})"
        elif not c0.get("id"):
            problem = "capture response has no capture id"
        else:
            amt = c0.get("amount") or {}
            try:
                if amt.get("currency_code") != p["currency"] or from_paypal_value(amt.get("value"), p["currency"]) != p["amount_minor"]:
                    problem = "captured amount does not match the approved amount"
            except ValueError:
                problem = "captured amount is unreadable"
        if problem:  # recorded and committed first; the error is raised after the transaction ends
            _set(conn, tid, "FAILED", error_code="capture_mismatch", error_message=problem, capture_id=c0.get("id"))
            s.audit(conn, "paypal_capture_failed", {"reason": problem, "capture_id": c0.get("id")}, r["intent_id"], tid)
        else:
            done = c0.get("status") == "COMPLETED"
            _set(conn, tid, "COMPLETED" if done else "CAPTURE_PENDING", capture_id=c0["id"], capture_status=c0.get("status"),
                 paypal_status=cap.get("status"), error_code=None, error_message=None)
            if done:
                conn.execute("UPDATE transactions SET status='PAID' WHERE id=?", (tid,))
            s.audit(conn, "payment_completed" if done else "payment_capture_pending",
                    {"order_id": p["paypal_order_id"], "capture_id": c0["id"], "amount_minor": p["amount_minor"], "currency": p["currency"], "sandbox": True},
                    r["intent_id"], tid)
    if problem:
        raise s.ServiceError(502, problem + " Check the PayPal Sandbox dashboard before retrying.")
    return payment_view(get_payment_row(conn, tid))


def note_buyer_cancelled(conn, tid):
    """The buyer pressed Cancel on PayPal. The order stays open, so they may try again until their consent expires."""
    with tx(conn):
        r = s._row(conn, "transactions", tid, "transaction")
        p = get_payment_row(conn, tid)
        if p is None:
            raise s.ServiceError(409, "no checkout was started for this transaction")
        s.audit(conn, "paypal_buyer_cancelled", {"order_id": p["paypal_order_id"]}, r["intent_id"], tid)
    return payment_view(get_payment_row(conn, tid))


def abandon_checkout(conn, tid):
    """Customer gives up. Terminal: the unused order is never captured."""
    with tx(conn):
        r = s._row(conn, "transactions", tid, "transaction")
        p = get_payment_row(conn, tid)
        if p is None:
            raise s.ServiceError(409, "no checkout was started for this transaction")
        if p["state"] not in ("ORDER_CREATED", "CREATING"):
            raise s.ServiceError(409, f"payment is {p['state']} and cannot be cancelled")
        if p["state"] == "CREATING":
            _set(conn, tid, "FAILED", error_code="cancelled", error_message="cancelled before an order existed")
        else:
            _set(conn, tid, "CANCELLED", error_code="cancelled", error_message="cancelled by the customer")
        s.audit(conn, "payment_cancelled", {"order_id": p["paypal_order_id"]}, r["intent_id"], tid)
    return payment_view(get_payment_row(conn, tid))


def list_payments(conn, limit=50):
    rows = conn.execute("SELECT * FROM payments ORDER BY created_at DESC, rowid DESC LIMIT ?", (max(1, min(int(limit), 200)),)).fetchall()
    out = []
    for p in rows:
        t = s._summary(conn, s._row(conn, "transactions", p["transaction_id"], "transaction"))
        out.append({**payment_view(p), "merchant": t["merchant"], "synthetic": t["synthetic"]})
    return out
