from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from ..config import settings
from ..core.validation import ValidationError
from ..database.db import connect
from ..schemas.models import InterpretIn, IntentIn, TransactionIn, ThreatIn, CaptureIn
from ..services import service as s
from ..services import payments, paypal, attacks, ai_explain
from ..services.chain import build_chain
from ..services.receipt import build_receipt
from ..services.demo_data import SCENARIOS
from ..services.interpreter import interpret

router = APIRouter(prefix="/api")


def get_conn():
    conn = connect(settings.DB_PATH())
    try:
        yield conn
    finally:
        conn.close()


def _run(fn, *a):
    try:
        return fn(*a)
    except s.ServiceError as e:
        raise HTTPException(e.status, e.message)
    except ValidationError as e:
        raise HTTPException(422, str(e))


@router.get("/health")
def health(c=Depends(get_conn)):
    c.execute("SELECT 1")
    pp = paypal.status_summary()
    # payments_enabled is true only when Sandbox credentials are present AND the base URL is the sandbox host.
    # It does not prove PayPal accepts them: use /api/paypal/status?probe=true for that.
    return {"status": "ok", "database": "ok", "gemini_configured": bool(settings.GEMINI_API_KEY()),
            "payments_enabled": pp["ready"], "paypal": pp, "demo_mode": settings.DEMO_MODE(), "version": "3.1.0"}


@router.get("/paypal/status")
def paypal_status(probe: bool = Query(False)):
    out = paypal.status_summary()
    if probe and out["ready"]:
        out["probe"] = paypal.get_client().probe()
    return out


@router.get("/stats")
def stats(c=Depends(get_conn)):
    return s.stats(c)


@router.post("/intents/interpret")
def interpret_ep(body: InterpretIn):
    return _run(interpret, body.text)


@router.post("/intents", status_code=201)
def create_intent(body: IntentIn, c=Depends(get_conn)):
    return _run(s.create_intent, c, body.instruction, body.constraints, body.source)


@router.get("/intents")
def list_intents(limit: int = Query(50, ge=1, le=200), c=Depends(get_conn)):
    return {"intents": s.list_intents(c, limit)}


@router.get("/intents/{iid}")
def get_intent(iid: str, c=Depends(get_conn)):
    return _run(s.get_intent, c, iid)


@router.post("/intents/{iid}/confirm")
def confirm(iid: str, c=Depends(get_conn)):
    return _run(s.confirm_intent, c, iid)


@router.get("/intents/{iid}/fingerprint")
def fingerprint(iid: str, c=Depends(get_conn)):
    i = _run(s.get_intent, c, iid)
    return {"intent_id": iid, "fingerprint": i["fingerprint"], "algorithm": "SHA-256 over canonical JSON"}


@router.post("/intents/{iid}/verify-fingerprint")
def verify_fp(iid: str, c=Depends(get_conn)):
    return _run(s.verify_intent_fingerprint, c, iid)


@router.get("/demo/scenarios")
def scenarios():
    return {"label": "SYNTHETIC demo offers. None are real merchants.",
            "default_intent_hint": "Expected outcomes assume the intent: Buy wireless headphones under $50, no refurbished.",
            "scenarios": {k: {"offer": v["offer"], "cart_price": v["cart_price"], "expected": v["expected"]} for k, v in SCENARIOS.items()}}


@router.post("/offers", status_code=201)
def create_offer(body: dict, c=Depends(get_conn)):
    return _run(s.create_offer, c, body)


@router.get("/offers/{oid}")
def get_offer(oid: str, c=Depends(get_conn)):
    return _run(s.get_offer, c, oid)


@router.post("/threats/analyze")
def analyze(body: ThreatIn, c=Depends(get_conn)):
    return {"findings": s.analyze_text(c, body.text)}


@router.post("/transactions", status_code=201)
def create_tx(body: TransactionIn, c=Depends(get_conn)):
    return _run(s.create_transaction, c, body.intent_id, body.offer_id, [l.model_dump() for l in body.cart])


@router.get("/transactions")
def list_tx(limit: int = Query(50, ge=1, le=200), status: Optional[str] = Query(None, pattern="^(PENDING|VERIFIED|BLOCKED|CONSENTED|REJECTED|PAID)$"),
            c=Depends(get_conn)):
    return {"transactions": s.list_transactions(c, limit, status)}


@router.get("/consents")
def list_consents(limit: int = Query(50, ge=1, le=200), c=Depends(get_conn)):
    return {"consents": s.list_consents(c, limit)}


@router.get("/transactions/{tid}")
def get_tx(tid: str, c=Depends(get_conn)):
    return _run(s.get_transaction, c, tid)


@router.post("/transactions/{tid}/verify")
def verify_tx(tid: str, c=Depends(get_conn)):
    return _run(s.reverify_transaction, c, tid)


@router.post("/transactions/{tid}/consent", status_code=201)
def grant(tid: str, c=Depends(get_conn)):
    return _run(s.grant_consent, c, tid)


@router.post("/transactions/{tid}/consent/reject", status_code=201)
def reject(tid: str, c=Depends(get_conn)):
    return _run(s.reject_consent, c, tid)


@router.get("/transactions/{tid}/consent")
def get_consent(tid: str, c=Depends(get_conn)):
    return _run(s.get_consent, c, tid)


def _client():
    return paypal.get_client()


def _run_pay(fn, *a):
    try:
        return fn(*a)
    except paypal.PayPalError as e:  # e.g. missing credentials or a refused non-sandbox URL
        raise HTTPException(503 if e.code in ("not_configured", "not_sandbox") else 502, e.message)
    except s.ServiceError as e:
        raise HTTPException(e.status, e.message)


@router.post("/transactions/{tid}/checkout", status_code=201)
def checkout(tid: str, c=Depends(get_conn)):
    """Create the PayPal Sandbox order for the verified, consented transaction. The amount is computed on the server."""
    return _run_pay(lambda: payments.start_checkout(c, _client(), tid))


@router.post("/transactions/{tid}/capture")
def capture(tid: str, body: CaptureIn, c=Depends(get_conn)):
    """Called after the buyer returns from PayPal. The backend re-fetches the order from PayPal and checks everything."""
    return _run_pay(lambda: payments.confirm_and_capture(c, _client(), tid, body.order_id))


@router.post("/transactions/{tid}/checkout/cancelled")
def checkout_cancelled(tid: str, c=Depends(get_conn)):
    return _run(payments.note_buyer_cancelled, c, tid)


@router.post("/transactions/{tid}/checkout/abandon")
def checkout_abandon(tid: str, c=Depends(get_conn)):
    return _run(payments.abandon_checkout, c, tid)


@router.get("/transactions/{tid}/payment")
def get_payment(tid: str, c=Depends(get_conn)):
    _run(s.get_transaction, c, tid)
    p = payments.payment_view(payments.get_payment_row(c, tid))
    if p is None:
        raise HTTPException(404, "no payment started for this transaction")
    return p


@router.get("/payments")
def list_payments(limit: int = Query(50, ge=1, le=200), c=Depends(get_conn)):
    return {"payments": payments.list_payments(c, limit)}


@router.get("/transactions/{tid}/chain")
def chain(tid: str, c=Depends(get_conn)):
    return _run(build_chain, c, tid)


@router.get("/transactions/{tid}/receipt")
def receipt(tid: str, c=Depends(get_conn)):
    return _run(build_receipt, c, tid)


@router.post("/transactions/{tid}/explain")
def explain(tid: str, c=Depends(get_conn)):
    """Evidence-grounded explanation. Gemini (if configured) writes wording only; rules decide."""
    t = _run(s.get_transaction, c, tid)
    return ai_explain.explain_transaction(t, s.get_intent(c, t["intent_id"])["constraints"], s.get_offer(c, t["offer_id"])["offer"])


@router.get("/attacks")
def attack_list():
    return {"label": "SYNTHETIC attacks run on a temporary in-memory database. Nothing is saved and PayPal is never contacted.", "attacks": attacks.list_attacks()}


@router.post("/attacks/{key}/run")
def attack_run(key: str):
    return _run(attacks.run_attack, key)


@router.get("/audit/events")
def audit_events(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), type: Optional[str] = Query(None, max_length=60),
                 intent_id: Optional[str] = Query(None, max_length=64), transaction_id: Optional[str] = Query(None, max_length=64),
                 c=Depends(get_conn)):
    return s.audit_page(c, tid=transaction_id, intent_id=intent_id, type_=type, limit=limit, offset=offset)


@router.get("/audit/types")
def audit_types(c=Depends(get_conn)):
    return {"types": s.audit_types(c)}


@router.get("/audit/verify")
def audit_verify(c=Depends(get_conn)):
    return s.verify_audit_chain(c)


@router.get("/audit/transactions/{tid}")
def audit_tx(tid: str, c=Depends(get_conn)):
    _run(s.get_transaction, c, tid)
    return {"events": s.list_audit(c, tid)}
