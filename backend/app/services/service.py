"""Business logic over SQLite. Every decision is deterministic and re-derived from stored data."""
import json, time, uuid
from datetime import datetime, timezone
from ..config import settings
from ..core.fingerprint import intent_fingerprint, sha256_hex
from ..core.threats import scan_text, scan_offer
from ..core.validation import validate_intent, validate_offer, validate_cart
from ..core.verification import verify
from ..database.db import tx


class ServiceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _now_iso():
    d = datetime.now(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def _audit_hash(prev, ts, type_, intent_id, transaction_id, detail_json):
    return sha256_hex({"prev": prev, "ts": ts, "type": type_, "intent_id": intent_id,
                       "transaction_id": transaction_id, "detail": detail_json})


def audit(conn, type_, detail, intent_id=None, transaction_id=None):
    """Append one event. Each event stores the hash of the previous one (a hash chain), so editing or
    deleting an old event is detectable. Must run inside tx() so concurrent writers cannot fork the chain."""
    if not conn.in_transaction:
        raise RuntimeError("audit() must be called inside tx()")
    last = conn.execute("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
    prev = last["hash"] if last and last["hash"] else ""
    ts, detail_json = _now_iso(), json.dumps(detail, sort_keys=True)
    conn.execute("INSERT INTO audit_events(ts,type,intent_id,transaction_id,detail_json,prev_hash,hash) VALUES(?,?,?,?,?,?,?)",
                 (ts, type_, intent_id, transaction_id, detail_json, prev,
                  _audit_hash(prev, ts, type_, intent_id, transaction_id, detail_json)))


def verify_audit_chain(conn):
    """Recompute every hash from the stored rows. Detects edited, removed (middle) or reordered events.
    It cannot detect removal of the newest events, or a full rewrite by someone who can recompute the chain,
    unless the head hash was recorded somewhere else."""
    prev, chained, legacy, seen = "", 0, 0, False
    rows = conn.execute("SELECT * FROM audit_events ORDER BY id ASC").fetchall()

    def broken(row, why):
        return {"intact": False, "events": len(rows), "chained": chained, "legacy_unchained": legacy,
                "first_broken_id": row["id"], "reason": why, "head": None}

    for r in rows:
        if r["hash"] is None:
            if seen:
                return broken(r, "an event without a hash appears after hashed events")
            legacy += 1
            continue
        seen = True
        if r["prev_hash"] != prev:
            return broken(r, "link to the previous event does not match (an event was removed, reordered or replaced)")
        if _audit_hash(r["prev_hash"], r["ts"], r["type"], r["intent_id"], r["transaction_id"], r["detail_json"]) != r["hash"]:
            return broken(r, "event content does not match its hash (it was edited)")
        prev, chained = r["hash"], chained + 1
    return {"intact": True, "events": len(rows), "chained": chained, "legacy_unchained": legacy, "head": prev or None,
            "note": "Every event hash was recomputed. This detects edits and deletions in the middle of the log. "
                    "It cannot detect removal of the newest events unless the head hash was saved elsewhere."}


def _new_id():
    return uuid.uuid4().hex


def _row(conn, table, id_, what):
    r = conn.execute(f"SELECT * FROM {table} WHERE id=?", (id_,)).fetchone()
    if not r:
        raise ServiceError(404, f"{what} not found")
    return r


def _intent_view(r):
    return {"id": r["id"], "instruction": r["instruction"], "constraints": json.loads(r["constraints_json"]),
            "fingerprint": r["fingerprint"], "source": r["source"], "status": r["status"],
            "created_at": r["created_at"], "confirmed_at": r["confirmed_at"]}


def create_intent(conn, instruction, constraints, source):
    c = validate_intent(constraints)
    if source not in ("gemini", "fallback_rules", "user_edited"):
        raise ServiceError(422, "invalid interpretation source")
    iid, fp = _new_id(), intent_fingerprint(c)
    with tx(conn):
        conn.execute("INSERT INTO intents(id,instruction,constraints_json,fingerprint,source) VALUES(?,?,?,?,?)",
                     (iid, instruction[:500], json.dumps(c, sort_keys=True), fp, source))
        audit(conn, "intent_created", {"source": source}, intent_id=iid)
    return _intent_view(_row(conn, "intents", iid, "intent"))


def get_intent(conn, iid):
    return _intent_view(_row(conn, "intents", iid, "intent"))


def confirm_intent(conn, iid):
    with tx(conn):
        r = _row(conn, "intents", iid, "intent")
        if r["status"] != "DRAFT":
            raise ServiceError(409, "intent is already confirmed")
        conn.execute("UPDATE intents SET status='CONFIRMED', confirmed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (iid,))
        audit(conn, "intent_confirmed", {"fingerprint": r["fingerprint"]}, intent_id=iid)
    return get_intent(conn, iid)


def verify_intent_fingerprint(conn, iid):
    """Recompute the hash from stored constraints; a mismatch means the stored data changed."""
    r = _row(conn, "intents", iid, "intent")
    fresh = intent_fingerprint(json.loads(r["constraints_json"]))
    ok = fresh == r["fingerprint"]
    with tx(conn):
        audit(conn, "fingerprint_checked", {"intact": ok}, intent_id=iid)
    return {"intent_id": iid, "stored": r["fingerprint"], "recomputed": fresh, "intact": ok,
            "note": "A matching hash proves the data is unchanged. It does not prove any merchant claim is true."}


def create_offer(conn, offer):
    o = validate_offer(offer)
    threats = scan_offer(o)
    oid = _new_id()
    with tx(conn):
        conn.execute("INSERT INTO offers(id,offer_json,synthetic) VALUES(?,?,?)", (oid, json.dumps(o, sort_keys=True), int(o["synthetic"])))
        audit(conn, "offer_inspected", {"offer_id": oid, "synthetic": o["synthetic"]})
        audit(conn, "threat_analysis_completed", {"offer_id": oid, "findings": len(threats),
                                                 "high": sum(t["severity"] == "high" for t in threats)})
    return {"id": oid, "offer": o, "threats": threats,
            "data_origin": "SYNTHETIC demo data, not a real merchant" if o["synthetic"] else "provided by the user; not verified"}


def get_offer(conn, oid):
    r = _row(conn, "offers", oid, "offer")
    o = json.loads(r["offer_json"])
    return {"id": oid, "offer": o, "threats": scan_offer(o),
            "data_origin": "SYNTHETIC demo data, not a real merchant" if r["synthetic"] else "provided by the user; not verified"}


def analyze_text(conn, text):
    findings = scan_text(text, "user_supplied_text")
    with tx(conn):
        audit(conn, "threat_analysis_completed", {"findings": len(findings), "high": sum(f["severity"] == "high" for f in findings), "source": "text"})
    return findings


def _evaluate(conn, tr):
    """Re-derive the verification from stored rows. Never trusts the stored decision."""
    ir, orow = _row(conn, "intents", tr["intent_id"], "intent"), _row(conn, "offers", tr["offer_id"], "offer")
    res = verify(json.loads(ir["constraints_json"]), json.loads(orow["offer_json"]), json.loads(tr["cart_json"]))
    intact = intent_fingerprint(json.loads(ir["constraints_json"])) == ir["fingerprint"]
    res["checks"].append({"id": "intent_integrity", "passed": intact, "severity": "block",
                          "detail": "intent fingerprint matches" if intact else "stored intent no longer matches its fingerprint"})
    confirmed = ir["status"] == "CONFIRMED"
    res["checks"].append({"id": "intent_confirmed", "passed": confirmed, "severity": "block",
                          "detail": "user confirmed the Intent Passport" if confirmed else "intent not confirmed"})
    if not (intact and confirmed):
        res["decision"] = "BLOCKED"
    return res


def _tx_view(conn, r):
    consent = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (r["id"],)).fetchone()
    fresh = _evaluate(conn, r)
    # consent_valid is recomputed on every read, so the UI can never show stale approval as valid.
    valid = bool(consent and consent["decision"] == "GRANTED" and fresh["decision"] == "VERIFIED"
                 and fresh["transaction_fingerprint"] == consent["fingerprint"])
    from ..core.drift import compute_drift
    from . import payments as _pay
    ir, orow = _row(conn, "intents", r["intent_id"], "intent"), _row(conn, "offers", r["offer_id"], "offer")
    drift = compute_drift(json.loads(ir["constraints_json"]), json.loads(orow["offer_json"]), json.loads(r["cart_json"]), fresh)
    return {"id": r["id"], "intent_id": r["intent_id"], "offer_id": r["offer_id"], "cart": json.loads(r["cart_json"]),
            "status": r["status"], "created_at": r["created_at"], "verification": fresh, "drift": drift,
            "consent": _consent_view(consent), "consent_valid": valid, "consent_state": consent_state(consent),
            "payment": _pay.payment_view(_pay.get_payment_row(conn, r["id"]))}


def consent_expiry(c) -> float:
    """Epoch seconds when a consent stops being usable. Older rows without a stored expiry use created_at + the configured lifetime."""
    if c["expires_epoch"] is not None:
        return float(c["expires_epoch"])
    created = datetime.strptime(c["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()
    return created + settings.CONSENT_TTL_SECONDS()


def consent_state(c, now=None) -> str:
    """NONE | REJECTED | ACTIVE | EXPIRED | CONSUMED. CONSUMED means a payment already used this approval (one-time use)."""
    now = time.time() if now is None else now
    if c is None:
        return "NONE"
    if c["decision"] == "REJECTED":
        return "REJECTED"
    if c["used"]:
        return "CONSUMED"
    return "EXPIRED" if now >= consent_expiry(c) else "ACTIVE"


def _consent_view(c, now=None):
    if c is None:
        return None
    exp = consent_expiry(c) if c["decision"] == "GRANTED" else None
    return {"id": c["id"], "decision": c["decision"], "fingerprint": c["fingerprint"], "used": bool(c["used"]),
            "created_at": c["created_at"], "expires_epoch": exp, "state": consent_state(c, now),
            "seconds_left": None if exp is None else max(0, int(exp - (time.time() if now is None else now)))}


def create_transaction(conn, intent_id, offer_id, cart):
    cart = validate_cart(cart)
    _row(conn, "intents", intent_id, "intent"), _row(conn, "offers", offer_id, "offer")
    tid = _new_id()
    with tx(conn):
        conn.execute("INSERT INTO transactions(id,intent_id,offer_id,cart_json,result_json,fingerprint,status) VALUES(?,?,?,?,?,?,?)",
                     (tid, intent_id, offer_id, json.dumps(cart, sort_keys=True), "{}", "", "PENDING"))
        audit(conn, "transaction_created", {"offer_id": offer_id, "cart_lines": len(cart)}, intent_id, tid)
    return reverify_transaction(conn, tid)


def get_transaction(conn, tid):
    return _tx_view(conn, _row(conn, "transactions", tid, "transaction"))


def reverify_transaction(conn, tid):
    with tx(conn):
        r = _row(conn, "transactions", tid, "transaction")
        if conn.execute("SELECT 1 FROM consents WHERE transaction_id=?", (tid,)).fetchone():
            raise ServiceError(409, "transaction already has a consent decision; create a new transaction to change anything")
        res = _evaluate(conn, r)
        status = "VERIFIED" if res["decision"] == "VERIFIED" else "BLOCKED"
        conn.execute("UPDATE transactions SET result_json=?, fingerprint=?, status=? WHERE id=?",
                     (json.dumps(res), res["transaction_fingerprint"], status, tid))
        audit(conn, "transaction_verified", {"decision": res["decision"], "failed": [c["id"] for c in res["checks"] if not c["passed"]]},
              r["intent_id"], tid)
    return get_transaction(conn, tid)


def decide_consent(conn, tid, grant: bool, now=None):
    """Atomic: re-verify, compare fingerprint, insert once (UNIQUE) — all in one write lock."""
    with tx(conn):
        r = _row(conn, "transactions", tid, "transaction")
        if conn.execute("SELECT 1 FROM consents WHERE transaction_id=?", (tid,)).fetchone():
            raise ServiceError(409, "a consent decision already exists for this transaction (replay blocked)")
        if not grant:
            conn.execute("INSERT INTO consents(id,transaction_id,fingerprint,decision) VALUES(?,?,?,'REJECTED')", (_new_id(), tid, r["fingerprint"]))
            conn.execute("UPDATE transactions SET status='REJECTED' WHERE id=?", (tid,))
            audit(conn, "consent_rejected", {}, r["intent_id"], tid)
            return None
        fresh = _evaluate(conn, r)
        if fresh["decision"] != "VERIFIED":
            audit(conn, "consent_refused", {"reason": "transaction does not verify"}, r["intent_id"], tid)
            problem = (409, "consent refused: the transaction does not pass verification")
        elif fresh["transaction_fingerprint"] != r["fingerprint"]:
            audit(conn, "consent_refused", {"reason": "transaction changed since it was verified"}, r["intent_id"], tid)
            problem = (409, "consent refused: transaction changed since it was verified")
        else:
            now = time.time() if now is None else now
            exp = now + settings.CONSENT_TTL_SECONDS()
            conn.execute("INSERT INTO consents(id,transaction_id,fingerprint,decision,expires_epoch) VALUES(?,?,?,'GRANTED',?)", (_new_id(), tid, r["fingerprint"], exp))
            conn.execute("UPDATE transactions SET status='CONSENTED' WHERE id=?", (tid,))
            audit(conn, "consent_granted", {"fingerprint": r["fingerprint"], "expires_in_seconds": settings.CONSENT_TTL_SECONDS()}, r["intent_id"], tid)
            problem = None
    if problem:  # raised after COMMIT so the refusal audit row is kept
        raise ServiceError(*problem)


def grant_consent(conn, tid, now=None):
    decide_consent(conn, tid, True, now)
    return get_transaction(conn, tid)["consent"]


def reject_consent(conn, tid):
    decide_consent(conn, tid, False)
    return get_transaction(conn, tid)["consent"]


def get_consent(conn, tid):
    _row(conn, "transactions", tid, "transaction")
    c = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (tid,)).fetchone()
    if not c:
        raise ServiceError(404, "no consent decision yet")
    return _consent_view(c)


def consume_consent(conn, tid, now=None):
    """A granted, unexpired consent can be used exactly once (atomic UPDATE inside one write lock)."""
    with tx(conn):
        consume_consent_in_tx(conn, tid, now)


def consume_consent_in_tx(conn, tid, now=None):
    """Same as consume_consent but joins the caller's open transaction, so payment state and consent use commit together."""
    c = conn.execute("SELECT * FROM consents WHERE transaction_id=?", (tid,)).fetchone()
    if c is not None and c["decision"] == "GRANTED" and not c["used"] and consent_state(c, now) == "EXPIRED":
        raise ServiceError(409, "consent expired: the approval is too old, please approve the transaction again")
    n = conn.execute("UPDATE consents SET used=1 WHERE transaction_id=? AND decision='GRANTED' AND used=0", (tid,)).rowcount
    if n != 1:
        raise ServiceError(409, "consent missing, not granted, or already used")
    audit(conn, "consent_consumed", {}, transaction_id=tid)


def _audit_where(tid, intent_id, type_):
    where, args = [], []
    for col, val in (("transaction_id", tid), ("intent_id", intent_id), ("type", type_)):
        if val:
            where.append(f"{col}=?")
            args.append(val)
    return (" WHERE " + " AND ".join(where)) if where else "", args


def audit_page(conn, tid=None, intent_id=None, type_=None, limit=100, offset=0):
    """Newest first. Filters are exact matches. Returns the events plus the total that match."""
    clause, args = _audit_where(tid, intent_id, type_)
    limit, offset = max(1, min(int(limit), 500)), max(0, int(offset))
    total = conn.execute("SELECT COUNT(*) FROM audit_events" + clause, args).fetchone()[0]
    rows = conn.execute("SELECT * FROM audit_events" + clause + " ORDER BY id DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    events = [{"id": r["id"], "ts": r["ts"], "type": r["type"], "intent_id": r["intent_id"],
               "transaction_id": r["transaction_id"], "detail": json.loads(r["detail_json"]),
               "hash": r["hash"], "prev_hash": r["prev_hash"]} for r in rows]
    return {"events": events, "total": total, "limit": limit, "offset": offset}


def list_audit(conn, tid=None, limit=100):
    return audit_page(conn, tid=tid, limit=limit)["events"]


def audit_types(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT type FROM audit_events ORDER BY type")]


def _summary(conn, r):
    """One compact row per transaction, always re-derived from stored data."""
    v = _tx_view(conn, r)
    o = json.loads(_row(conn, "offers", r["offer_id"], "offer")["offer_json"])
    ver = v["verification"]
    return {"id": r["id"], "intent_id": r["intent_id"], "offer_id": r["offer_id"], "created_at": r["created_at"],
            "status": r["status"], "decision": ver["decision"], "merchant": o["merchant"], "synthetic": o["synthetic"],
            "currency": o["currency"], "server_total": ver["server_total"],
            "failed_checks": [c["id"] for c in ver["checks"] if not c["passed"]],
            "consent": v["consent"], "consent_valid": v["consent_valid"], "consent_state": v["consent_state"],
            "payment_state": (v["payment"] or {}).get("state")}


def list_transactions(conn, limit=50, status=None):
    limit = max(1, min(int(limit), 200))
    if status:
        rows = conn.execute("SELECT * FROM transactions WHERE status=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (status, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM transactions ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
    return [_summary(conn, r) for r in rows]


def list_intents(conn, limit=50):
    rows = conn.execute("SELECT * FROM intents ORDER BY created_at DESC, rowid DESC LIMIT ?", (max(1, min(int(limit), 200)),)).fetchall()
    return [_intent_view(r) for r in rows]


def list_consents(conn, limit=50):
    """Consent history: every decision with the transaction it belongs to and whether it is still valid today."""
    out = []
    for c in conn.execute("SELECT * FROM consents ORDER BY created_at DESC, rowid DESC LIMIT ?", (max(1, min(int(limit), 200)),)):
        t = _summary(conn, _row(conn, "transactions", c["transaction_id"], "transaction"))
        out.append({**_consent_view(c), "transaction_id": c["transaction_id"], "merchant": t["merchant"], "currency": t["currency"],
                    "server_total": t["server_total"], "still_valid": t["consent_valid"]})
    return out


def stats(conn):
    n = lambda sql: conn.execute(sql).fetchone()[0]
    return {"intents": n("SELECT COUNT(*) FROM intents"), "intents_confirmed": n("SELECT COUNT(*) FROM intents WHERE status='CONFIRMED'"),
            "offers": n("SELECT COUNT(*) FROM offers"), "transactions": n("SELECT COUNT(*) FROM transactions"),
            "verified": n("SELECT COUNT(*) FROM transactions WHERE status IN ('VERIFIED','CONSENTED','PAID')"),
            "payments_completed": n("SELECT COUNT(*) FROM payments WHERE state='COMPLETED'"),
            "blocked": n("SELECT COUNT(*) FROM transactions WHERE status='BLOCKED'"),
            "awaiting_consent": n("SELECT COUNT(*) FROM transactions WHERE status='VERIFIED'"),
            "consents_granted": n("SELECT COUNT(*) FROM consents WHERE decision='GRANTED'"),
            "consents_rejected": n("SELECT COUNT(*) FROM consents WHERE decision='REJECTED'"),
            "threat_scans": n("SELECT COUNT(*) FROM audit_events WHERE type='threat_analysis_completed'"),
            "audit_events": n("SELECT COUNT(*) FROM audit_events")}
