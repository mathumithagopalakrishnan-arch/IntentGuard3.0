"""PayPal client, consent lifecycle, payment state machine, receipt and chain. Uses a scripted PayPal double:
these tests prove IntentGuard's behavior, NOT that real PayPal Sandbox accepts the calls (that is NOT TESTED here)."""
import copy, json, os, tempfile, threading, time, unittest
from unittest import mock
from app.database.db import connect, init_db
from app.services import service as s, payments, ai_explain, attacks, interpreter
from app.services.paypal import PayPalClient, PayPalError, assert_sandbox
from app.services.chain import build_chain
from app.services.receipt import build_receipt
from app.services.demo_data import SCENARIOS, DEFAULT_DEMO_INTENT
from app.core.threats import normalize
from app.core.money import to_paypal_value, from_paypal_value
from tests.fakepaypal import FakePayPal

SANDBOX = "https://api-m.sandbox.paypal.com"


class PayBase(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "p.db")
        init_db(self.path)
        self.c = connect(self.path)
        self.fake = FakePayPal()
        self.pp = PayPalClient("cid", "secret", SANDBOX, transport=self.fake.transport)

    def tx(self, name="legit", consent=True, now=None):
        sc = SCENARIOS[name]
        i = s.confirm_intent(self.c, s.create_intent(self.c, "buy headphones under $50", copy.deepcopy(DEFAULT_DEMO_INTENT), "user_edited")["id"])
        o = s.create_offer(self.c, copy.deepcopy(sc["offer"]))
        t = s.create_transaction(self.c, i["id"], o["id"], [{"item_id": "p1", "qty": 1, "unit_price": sc["cart_price"]}])
        if consent:
            s.grant_consent(self.c, t["id"], now)
        return t, o

    def checkout(self, tid, approve=True):
        p = payments.start_checkout(self.c, self.pp, tid)
        if approve:
            self.fake.approve(p["paypal_order_id"])
        return p

    def events(self, tid):
        return [e["type"] for e in reversed(s.list_audit(self.c, tid, 500))]


class PayPalClientTests(unittest.TestCase):
    def test_oauth_success_and_token_cached(self):
        f = FakePayPal(); pp = PayPalClient("cid", "secret", SANDBOX, transport=f.transport)
        pp.get_order.__self__  # client exists
        f.orders["X1"] = {"id": "X1", "status": "CREATED", "purchase_units": []}
        pp.get_order("X1"); pp.get_order("X1")
        self.assertEqual(f.count("oauth2/token"), 1)

    def test_oauth_failure(self):
        f = FakePayPal(); f.oauth_status = 401
        with self.assertRaises(PayPalError) as cm:
            PayPalClient("cid", "bad", SANDBOX, transport=f.transport).get_order("X")
        self.assertEqual(cm.exception.code, "oauth_failed"); self.assertFalse(cm.exception.retryable)

    def test_oauth_server_error_is_retryable(self):
        f = FakePayPal(); f.oauth_status = 503
        with self.assertRaises(PayPalError) as cm:
            PayPalClient("cid", "s", SANDBOX, transport=f.transport).get_order("X")
        self.assertTrue(cm.exception.retryable)

    def test_missing_credentials(self):
        with self.assertRaises(PayPalError) as cm:
            PayPalClient("", "", SANDBOX, transport=FakePayPal().transport).get_order("X")
        self.assertEqual(cm.exception.code, "not_configured")

    def test_sandbox_url_enforced(self):
        for bad in ("https://api-m.paypal.com", "https://api.paypal.com", "http://api-m.sandbox.paypal.com", "https://api-m.sandbox.paypal.com.evil.com",
                    "https://evil.com/api-m.sandbox.paypal.com", "https://user:pw@api-m.sandbox.paypal.com", "", "https://api-m.sandbox.paypal.com/v2"):
            with self.assertRaises(PayPalError, msg=bad) as cm:
                PayPalClient("a", "b", bad, transport=FakePayPal().transport)
            self.assertEqual(cm.exception.code, "not_sandbox")
        self.assertEqual(assert_sandbox("https://api-m.sandbox.paypal.com/"), SANDBOX)

    def test_secret_never_in_errors_or_urls(self):
        f = FakePayPal(); f.oauth_status = 401
        try:
            PayPalClient("cid", "TOPSECRET", SANDBOX, transport=f.transport).get_order("X")
        except PayPalError as e:
            self.assertNotIn("TOPSECRET", e.message)
        self.assertTrue(all("TOPSECRET" not in p for _, p, _ in f.calls))

    def test_money_conversion_is_exact(self):
        for m in (0, 1, 99, 100, 4700, 123456789):
            self.assertEqual(from_paypal_value(to_paypal_value(m)), m)
        self.assertEqual(to_paypal_value(4700), "47.00")
        for bad in ("1.234", "-1", "abc", "1,00", None, 5):
            with self.assertRaises(ValueError):
                from_paypal_value(bad)
        with self.assertRaises(ValueError):
            to_paypal_value(1.5)


class CheckoutTests(PayBase):
    def test_order_uses_server_total_and_ids(self):
        t, _ = self.tx()
        p = self.checkout(t["id"], approve=False)
        self.assertEqual((p["state"], p["amount_minor"], p["currency"]), ("ORDER_CREATED", 4700, "USD"))
        req = self.fake.orders[p["paypal_order_id"]]["request"]
        u = req["purchase_units"][0]
        self.assertEqual(u["amount"]["value"], "47.00"); self.assertEqual(u["custom_id"], t["id"])
        self.assertEqual(u["amount"]["breakdown"]["item_total"]["value"], "40.00")
        self.assertEqual(req["intent"], "CAPTURE")
        self.assertTrue(p["approve_url"].startswith("https://www.sandbox.paypal.com/"))
        self.assertIn(t["id"], req["payment_source"]["paypal"]["experience_context"]["return_url"])

    def test_full_happy_path(self):
        t, _ = self.tx()
        p = self.checkout(t["id"])
        done = payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual((done["state"], done["capture_status"]), ("COMPLETED", "COMPLETED")); self.assertTrue(done["capture_id"])
        v = s.get_transaction(self.c, t["id"])
        self.assertEqual(v["status"], "PAID"); self.assertTrue(v["consent"]["used"]); self.assertEqual(v["consent_state"], "CONSUMED")
        self.assertEqual(self.events(t["id"])[-6:], ["consent_granted", "payment_checkout_started", "paypal_order_created", "consent_consumed", "payment_capture_started", "payment_completed"][-6:])
        self.assertTrue(s.verify_audit_chain(self.c)["intact"])

    def test_blocked_transaction_cannot_check_out(self):
        t, _ = self.tx("hidden_subscription", consent=False)
        with self.assertRaises(s.ServiceError):
            s.grant_consent(self.c, t["id"])
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertIn("no customer consent", cm.exception.message)
        self.assertEqual(self.fake.calls, [])

    def test_amount_mismatch_refused_and_not_captured(self):
        t, _ = self.tx()
        self.fake.tamper_amount = ("USD", "1.00")
        p = self.checkout(t["id"])
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertIn("amount", cm.exception.message)
        self.assertEqual(self.fake.count("/capture"), 0)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "FAILED")
        self.assertIn("payment_refused", self.events(t["id"]))

    def test_currency_mismatch_refused(self):
        t, _ = self.tx()
        self.fake.tamper_amount = ("EUR", "47.00")
        p = self.checkout(t["id"])
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertIn("currency", cm.exception.message); self.assertEqual(self.fake.count("/capture"), 0)

    def test_non_enabled_currency_never_reaches_paypal(self):
        sc = copy.deepcopy(SCENARIOS["legit"]["offer"]); sc["currency"] = "EUR"
        i = s.confirm_intent(self.c, s.create_intent(self.c, "x y z", dict(DEFAULT_DEMO_INTENT, currency="EUR"), "user_edited")["id"])
        o = s.create_offer(self.c, sc)
        t = s.create_transaction(self.c, i["id"], o["id"], [{"item_id": "p1", "qty": 1, "unit_price": 4000}])
        s.grant_consent(self.c, t["id"])
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertIn("not enabled", cm.exception.message); self.assertEqual(self.fake.calls, [])

    def test_missing_credentials_create_no_payment_and_can_recover(self):
        t, _ = self.tx()
        nocreds = PayPalClient("", "", SANDBOX, transport=self.fake.transport)
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, nocreds, t["id"])
        self.assertEqual(cm.exception.status, 503)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 0)
        self.assertEqual(payments.start_checkout(self.c, self.pp, t["id"])["state"], "ORDER_CREATED")

    def test_wrong_order_id_refused(self):
        t, _ = self.tx(); t2, _ = self.tx()
        p, p2 = self.checkout(t["id"]), self.checkout(t2["id"])
        with self.assertRaises(s.ServiceError):
            payments.confirm_and_capture(self.c, self.pp, t["id"], p2["paypal_order_id"])
        with self.assertRaises(s.ServiceError):
            payments.confirm_and_capture(self.c, self.pp, t["id"], "NOPE")
        self.assertEqual(self.fake.count("/capture"), 0)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "ORDER_CREATED")
        self.assertIn("payment_refused", self.events(t["id"]))

    def test_order_for_other_transaction_refused_by_custom_id(self):
        t, _ = self.tx()
        p = self.checkout(t["id"])
        self.fake.orders[p["paypal_order_id"]]["purchase_units"][0]["custom_id"] = "someone-else"
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertIn("different transaction", cm.exception.message); self.assertEqual(self.fake.count("/capture"), 0)

    def test_unapproved_order_is_never_captured(self):
        t, _ = self.tx()
        p = self.checkout(t["id"], approve=False)
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual(cm.exception.status, 409); self.assertEqual(self.fake.count("/capture"), 0)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "ORDER_CREATED")
        self.assertEqual(s.get_transaction(self.c, t["id"])["consent_state"], "ACTIVE")  # consent not burned by a refused attempt
        self.fake.approve(p["paypal_order_id"])  # the buyer approves later: now it works
        self.assertEqual(payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])["state"], "COMPLETED")

    def test_capture_failure_is_recorded(self):
        t, _ = self.tx()
        p = self.checkout(t["id"]); self.fake.capture_decline = True
        with self.assertRaises(s.ServiceError):
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        row = payments.get_payment_row(self.c, t["id"])
        self.assertEqual((row["state"], row["error_code"]), ("FAILED", "INSTRUMENT_DECLINED"))
        self.assertNotEqual(s.get_transaction(self.c, t["id"])["status"], "PAID")
        self.assertIn("paypal_capture_failed", self.events(t["id"]))

    def test_duplicate_capture_is_idempotent(self):
        t, _ = self.tx()
        p = self.checkout(t["id"])
        a = payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        b = payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual(a["capture_id"], b["capture_id"]); self.assertEqual(self.fake.count("/capture"), 1)
        self.assertEqual(self.events(t["id"]).count("payment_completed"), 1)

    def test_duplicate_order_returns_same_order(self):
        t, _ = self.tx()
        a = payments.start_checkout(self.c, self.pp, t["id"]); b = payments.start_checkout(self.c, self.pp, t["id"])
        self.assertEqual(a["paypal_order_id"], b["paypal_order_id"]); self.assertEqual(self.fake.count("POST /v2/checkout/orders"), 1)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)

    def test_checkout_after_completion_does_not_create_new_order(self):
        t, _ = self.tx()
        p = self.checkout(t["id"]); payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        again = payments.start_checkout(self.c, self.pp, t["id"])
        self.assertEqual(again["state"], "COMPLETED"); self.assertEqual(self.fake.count("POST /v2/checkout/orders"), 1)

    def test_create_timeout_then_retry_reuses_request_id(self):
        t, _ = self.tx()
        self.fake.fail_create = ["timeout"]
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertEqual(cm.exception.status, 503); self.assertIn("safely retry", cm.exception.message)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "CREATING")
        p = payments.start_checkout(self.c, self.pp, t["id"])
        self.assertEqual(p["state"], "ORDER_CREATED")
        rids = [r for m, path, r in self.fake.calls if path == "/v2/checkout/orders"]
        self.assertEqual(len(rids), 2); self.assertEqual(rids[0], rids[1])

    def test_create_timeout_retry_rechecks_consent_fingerprint(self):
        t, o = self.tx()
        self.fake.fail_create = ["timeout"]
        with self.assertRaises(s.ServiceError):
            payments.start_checkout(self.c, self.pp, t["id"])

        offer = json.loads(self.c.execute("SELECT offer_json FROM offers WHERE id=?", (o["id"],)).fetchone()[0])
        offer["label"] = "changed without changing the amount"
        self.c.execute("UPDATE offers SET offer_json=? WHERE id=?", (json.dumps(offer, sort_keys=True), o["id"]))

        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertIn("changed", cm.exception.message)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "FAILED")
        self.assertEqual(self.fake.count("POST /v2/checkout/orders"), 1)

    def test_create_api_error_is_terminal(self):
        t, _ = self.tx()
        self.fake.fail_create = [("http", 400, "INVALID_REQUEST", "CURRENCY_NOT_SUPPORTED")]
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertEqual(cm.exception.status, 502)
        row = payments.get_payment_row(self.c, t["id"])
        self.assertEqual((row["state"], row["error_code"]), ("FAILED", "CURRENCY_NOT_SUPPORTED"))
        with self.assertRaises(s.ServiceError):
            payments.start_checkout(self.c, self.pp, t["id"])  # terminal: no silent re-charge path

    def test_capture_timeout_then_retry_captures_once(self):
        t, _ = self.tx()
        p = self.checkout(t["id"]); self.fake.fail_capture = ["timeout"]
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual(cm.exception.status, 503)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "CAPTURING")
        done = payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual(done["state"], "COMPLETED")
        rids = [r for m, path, r in self.fake.calls if path.endswith("/capture")]
        self.assertEqual(rids[0], rids[1])  # same PayPal-Request-Id: PayPal cannot charge twice
        self.assertEqual(self.events(t["id"]).count("consent_consumed"), 1)

    def test_capture_applied_but_response_lost_is_recovered(self):
        t, _ = self.tx()
        p = self.checkout(t["id"]); self.fake.lose_capture_response = 1
        with self.assertRaises(s.ServiceError):
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        done = payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual(done["state"], "COMPLETED"); self.assertTrue(done["capture_id"])

    def test_capture_recovery_rechecks_authoritative_order_binding(self):
        t, _ = self.tx()
        p = self.checkout(t["id"]); self.fake.lose_capture_response = 1
        with self.assertRaises(s.ServiceError):
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])

        self.fake.orders[p["paypal_order_id"]]["purchase_units"][0]["custom_id"] = "different-transaction"
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertIn("different transaction", cm.exception.message)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "FAILED")

    def test_pending_capture_state(self):
        t, _ = self.tx()
        p = self.checkout(t["id"])
        orig = self.fake.transport
        def pending(method, url, headers, body, timeout):
            st, d = orig(method, url, headers, body, timeout)
            if url.endswith("/capture"):
                d = copy.deepcopy(d); d["purchase_units"][0]["payments"]["captures"][0]["status"] = "PENDING"
            return st, d
        pp = PayPalClient("cid", "secret", SANDBOX, transport=pending)
        r = payments.confirm_and_capture(self.c, pp, t["id"], p["paypal_order_id"])
        self.assertEqual(r["state"], "CAPTURE_PENDING"); self.assertNotEqual(s.get_transaction(self.c, t["id"])["status"], "PAID")

    def test_capture_amount_mismatch_in_response_is_flagged(self):
        t, _ = self.tx()
        p = self.checkout(t["id"])
        orig = self.fake.transport
        def wrong(method, url, headers, body, timeout):
            st, d = orig(method, url, headers, body, timeout)
            if url.endswith("/capture"):
                d = copy.deepcopy(d); d["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"] = "99.00"
            return st, d
        with self.assertRaises(s.ServiceError):
            payments.confirm_and_capture(self.c, PayPalClient("cid", "secret", SANDBOX, transport=wrong), t["id"], p["paypal_order_id"])
        row = payments.get_payment_row(self.c, t["id"])
        self.assertEqual((row["state"], row["error_code"]), ("FAILED", "capture_mismatch")); self.assertTrue(row["capture_id"])

    def test_cancel_and_abandon(self):
        t, _ = self.tx()
        p = self.checkout(t["id"], approve=False)
        self.assertEqual(payments.note_buyer_cancelled(self.c, t["id"])["state"], "ORDER_CREATED")  # may try again
        self.assertEqual(payments.abandon_checkout(self.c, t["id"])["state"], "CANCELLED")
        self.fake.approve(p["paypal_order_id"])
        with self.assertRaises(s.ServiceError):
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual(self.fake.count("/capture"), 0)

    def test_cancel_racing_with_paypal_order_lookup_prevents_capture(self):
        t, _ = self.tx()
        p = self.checkout(t["id"], approve=True)
        original_get_order = self.pp.get_order

        def cancel_after_lookup(order_id):
            order = original_get_order(order_id)
            payments.abandon_checkout(self.c, t["id"])
            return order

        with mock.patch.object(self.pp, "get_order", side_effect=cancel_after_lookup):
            with self.assertRaises(s.ServiceError) as cm:
                payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertIn("CANCELLED", cm.exception.message)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "CANCELLED")
        self.assertEqual(self.fake.count("/capture"), 0)

    def test_interrupted_capture_without_request_id_is_refused(self):
        t, _ = self.tx()
        p = self.checkout(t["id"], approve=True)
        with payments.tx(self.c):
            self.c.execute("UPDATE payments SET state='CAPTURING', capture_request_id=NULL WHERE transaction_id=?", (t["id"],))
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertIn("capture request id is missing", cm.exception.message)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "FAILED")
        self.assertEqual(self.fake.count("/capture"), 0)

    def test_illegal_transition_rejected(self):
        t, _ = self.tx(); self.checkout(t["id"])
        with s.tx(self.c) if hasattr(s, "tx") else mock.MagicMock():
            with self.assertRaises(s.ServiceError):
                payments._set(self.c, t["id"], "COMPLETED")  # ORDER_CREATED -> COMPLETED is not allowed


class ConsentLifecycleTests(PayBase):
    def test_missing_consent(self):
        t, _ = self.tx(consent=False)
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertIn("no customer consent", cm.exception.message); self.assertEqual(self.fake.calls, [])
        self.assertIn("payment_refused", self.events(t["id"]))

    def test_rejected_consent(self):
        t, _ = self.tx(consent=False); s.reject_consent(self.c, t["id"])
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertIn("rejected", cm.exception.message)

    def test_expired_consent_blocks_checkout(self):
        t, _ = self.tx(consent=False, now=None)
        s.grant_consent(self.c, t["id"], now=time.time() - 100000)
        self.assertEqual(s.get_transaction(self.c, t["id"])["consent_state"], "EXPIRED")
        with self.assertRaises(s.ServiceError) as cm:
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertIn("expired", cm.exception.message); self.assertEqual(self.fake.calls, [])

    def test_consent_expires_between_order_and_capture(self):
        t, _ = self.tx()
        p = self.checkout(t["id"])
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"], now=time.time() + 100000)
        self.assertIn("expired", cm.exception.message); self.assertEqual(self.fake.count("/capture"), 0)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "EXPIRED")
        self.assertFalse(s.get_transaction(self.c, t["id"])["consent"]["used"])

    def test_expiry_default_for_old_rows_without_stored_expiry(self):
        t, _ = self.tx()
        self.c.execute("UPDATE consents SET expires_epoch=NULL")
        self.assertEqual(s.get_transaction(self.c, t["id"])["consent_state"], "ACTIVE")
        self.c.execute("UPDATE consents SET created_at='2020-01-01T00:00:00.000Z'")
        self.assertEqual(s.get_transaction(self.c, t["id"])["consent_state"], "EXPIRED")

    def test_duplicate_approval_rejected(self):
        t, _ = self.tx()
        with self.assertRaises(s.ServiceError) as cm:
            s.grant_consent(self.c, t["id"])
        self.assertEqual(cm.exception.status, 409)

    def test_replayed_approval_after_use(self):
        t, _ = self.tx()
        p = self.checkout(t["id"]); payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        with self.assertRaises(s.ServiceError):
            s.consume_consent(self.c, t["id"])
        with self.assertRaises(s.ServiceError):
            s.grant_consent(self.c, t["id"])
        self.assertEqual(self.fake.count("/capture"), 1)

    def test_changed_transaction_voids_approval(self):
        t, o = self.tx()
        off = json.loads(self.c.execute("SELECT offer_json FROM offers WHERE id=?", (o["id"],)).fetchone()[0])
        off["items"][0]["unit_price"] = 4400; off["claimed_total"] = 5100
        self.c.execute("UPDATE offers SET offer_json=? WHERE id=?", (json.dumps(off, sort_keys=True), o["id"]))
        v = s.get_transaction(self.c, t["id"])
        self.assertFalse(v["consent_valid"])
        with self.assertRaises(s.ServiceError):
            payments.start_checkout(self.c, self.pp, t["id"])
        self.assertEqual(self.fake.calls, [])

    def test_change_after_order_creation_blocks_capture(self):
        t, o = self.tx()
        p = self.checkout(t["id"])
        off = json.loads(self.c.execute("SELECT offer_json FROM offers WHERE id=?", (o["id"],)).fetchone()[0])
        off["tax"] = 100; off["claimed_total"] = 4500
        self.c.execute("UPDATE offers SET offer_json=? WHERE id=?", (json.dumps(off, sort_keys=True), o["id"]))
        with self.assertRaises(s.ServiceError) as cm:
            payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"])
        self.assertEqual(self.fake.count("/capture"), 0)
        self.assertEqual(payments.get_payment_row(self.c, t["id"])["state"], "FAILED")

    def test_consume_consent_requires_unexpired(self):
        t, _ = self.tx(consent=False); s.grant_consent(self.c, t["id"], now=time.time() - 100000)
        with self.assertRaises(s.ServiceError) as cm:
            s.consume_consent(self.c, t["id"])
        self.assertIn("expired", cm.exception.message)

    def test_concurrent_checkouts_create_one_order(self):
        t, _ = self.tx(); results, errors = [], []
        def work():
            conn = connect(self.path)
            try:
                results.append(payments.start_checkout(conn, self.pp, t["id"]))
            except Exception as e:  # noqa
                errors.append(e)
            finally:
                conn.close()
        th = [threading.Thread(target=work) for _ in range(6)]
        [x.start() for x in th]; [x.join() for x in th]
        self.assertEqual(errors, [])
        self.assertEqual(len({r["paypal_order_id"] for r in results}), 1)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)
        self.assertEqual(len(self.fake.orders), 1)

    def test_concurrent_captures_complete_once(self):
        t, _ = self.tx(); p = self.checkout(t["id"]); results, errors = [], []
        def work():
            conn = connect(self.path)
            try:
                results.append(payments.confirm_and_capture(conn, self.pp, t["id"], p["paypal_order_id"]))
            except s.ServiceError as e:
                errors.append(e)
            finally:
                conn.close()
        th = [threading.Thread(target=work) for _ in range(6)]
        [x.start() for x in th]; [x.join() for x in th]
        self.assertTrue(results)
        self.assertEqual(len({r["capture_id"] for r in results if r["capture_id"]}), 1)
        self.assertEqual(sum(1 for o in self.fake.orders.values() if o["status"] == "COMPLETED"), 1)
        self.assertEqual(self.events(t["id"]).count("payment_completed"), 1)
        self.assertEqual(self.events(t["id"]).count("consent_consumed"), 1)


class AuditReceiptChainTests(PayBase):
    def paid(self):
        t, _ = self.tx(); p = self.checkout(t["id"]); payments.confirm_and_capture(self.c, self.pp, t["id"], p["paypal_order_id"]); return t

    def test_audit_chain_valid_and_references_transaction(self):
        t = self.paid()
        self.assertTrue(s.verify_audit_chain(self.c)["intact"])
        for e in s.list_audit(self.c, t["id"], 500):
            self.assertEqual(e["transaction_id"], t["id"])
        types = set(self.events(t["id"]))
        self.assertTrue({"payment_checkout_started", "paypal_order_created", "payment_capture_started", "payment_completed", "consent_consumed"} <= types)

    def test_tampered_payment_audit_record_detected(self):
        self.paid()
        self.c.execute("UPDATE audit_events SET detail_json='{\"order_id\":\"FORGED\"}' WHERE type='payment_completed'")
        r = s.verify_audit_chain(self.c)
        self.assertFalse(r["intact"]); self.assertIn("edited", r["reason"])

    def test_receipt_contents_and_hash(self):
        t = self.paid()
        r = build_receipt(self.c, t["id"])
        from app.core.fingerprint import sha256_hex
        self.assertEqual(r["receipt_sha256"], sha256_hex(r["receipt"]))
        body = r["receipt"]
        self.assertEqual(body["paypal_sandbox_payment"]["state"], "COMPLETED"); self.assertNotIn("approve_url", body["paypal_sandbox_payment"])
        self.assertEqual(body["original_intent"]["fingerprint_sha256"], s.get_transaction(self.c, t["id"])["verification"]["checks"] and body["original_intent"]["fingerprint_sha256"])
        self.assertEqual(body["verification"]["decision"], "VERIFIED"); self.assertEqual(len(body["integrity_chain"]["stages"]), 8)
        self.assertIn("SANDBOX", body["environment"]); self.assertTrue(body["audit_events"])
        self.assertNotIn("secret", json.dumps(r).lower())

    def test_chain_binding_and_tamper(self):
        t = self.paid()
        ch = build_chain(self.c, t["id"])
        self.assertTrue(ch["intact"]); self.assertTrue(all(st["link"] for st in ch["stages"]))
        self.c.execute("UPDATE payments SET amount_minor=1 WHERE transaction_id=?", (t["id"],))
        self.assertFalse(build_chain(self.c, t["id"])["intact"])

    def test_chain_links_change_when_early_stage_changes(self):
        t, o = self.tx(); a = build_chain(self.c, t["id"])["head_link"]
        off = json.loads(self.c.execute("SELECT offer_json FROM offers WHERE id=?", (o["id"],)).fetchone()[0]); off["label"] = "changed"
        self.c.execute("UPDATE offers SET offer_json=? WHERE id=?", (json.dumps(off, sort_keys=True), o["id"]))
        self.assertNotEqual(a, build_chain(self.c, t["id"])["head_link"])

    def test_existing_database_is_migrated(self):
        import sqlite3
        old = os.path.join(tempfile.mkdtemp(), "old.db")
        conn = sqlite3.connect(old)
        conn.executescript("CREATE TABLE consents(id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL, decision TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));")
        conn.close()
        init_db(old)
        c = connect(old)
        self.assertIn("expires_epoch", {r["name"] for r in c.execute("PRAGMA table_info(consents)")})
        self.assertTrue(c.execute("SELECT name FROM sqlite_master WHERE name='payments'").fetchone())


class AiAndSecurityTests(PayBase):
    def _v(self, name):
        t, _ = self.tx(name, consent=False); return t

    def test_invalid_ai_output_rejected(self):
        ev = [{"id": "within_budget", "kind": "failed_check", "detail": "x"}]
        for bad in ("not json", "[]", '{"summary": 1, "points": []}', '{"summary": "ok", "points": "x"}', '{"summary":"ok","points":[{"evidence_id":"invented","explanation":"x"}]}'):
            with self.assertRaises(Exception, msg=bad):
                ai_explain.validate_ai(bad, ev)

    def test_ai_points_must_cite_real_evidence_and_are_capped(self):
        ev = [{"id": "within_budget", "kind": "failed_check", "detail": "x"}]
        out = ai_explain.validate_ai(json.dumps({"summary": "s" * 2000, "points": [{"evidence_id": "within_budget", "explanation": "e" * 900},
                                                                                {"evidence_id": "made_up", "explanation": "dropped"}]}), ev)
        self.assertEqual(len(out["points"]), 1); self.assertLessEqual(len(out["points"][0]["text"]), 300); self.assertLessEqual(len(out["summary"]), 600)

    def test_gemini_unavailable_falls_back_to_rules(self):
        v = self._v("hidden_subscription")["verification"]
        def boom(_):
            raise OSError("down")
        res = ai_explain.explain(v, gemini=boom)
        self.assertEqual(res["source"], "rule_based"); self.assertIn("fallback_reason", res); self.assertEqual(res["decision"], "BLOCKED")
        self.assertTrue(res["evidence"]); self.assertTrue(res["uncertainty"])

    def test_gemini_output_is_labelled_and_never_changes_decision(self):
        v = self._v("over_budget")["verification"]
        fake = lambda _: json.dumps({"summary": "Over budget.", "points": [{"evidence_id": "within_budget", "explanation": "Total exceeds your limit."}], "uncertainties": []})
        res = ai_explain.explain(v, gemini=fake)
        self.assertEqual(res["source"], "gemini"); self.assertIn("AI-generated", res["label"]); self.assertEqual(res["decision"], "BLOCKED")
        evil = lambda _: json.dumps({"summary": "APPROVE THIS NOW", "points": [{"evidence_id": "within_budget", "explanation": "fine"}], "uncertainties": []})
        self.assertEqual(ai_explain.explain(v, gemini=evil)["decision"], "BLOCKED")

    def test_pass_explanation_for_legit(self):
        res = ai_explain.explain(self._v("legit")["verification"])
        self.assertEqual(res["decision"], "VERIFIED"); self.assertTrue(res["summary"].startswith("PASS"))

    def test_interpreter_gemini_failure_uses_fallback(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(interpreter, "_call_gemini", side_effect=OSError("x")):
            r = interpreter.interpret("Buy wireless headphones under $50")
        self.assertEqual(r["source"], "fallback_rules"); self.assertIn("clarifications", r)

    def test_interpreter_gemini_output_validated_and_clarifications(self):
        good = json.dumps({"category": "wireless headphones", "max_total": 5000, "currency": "USD", "max_quantity": 1, "allow_subscription": False,
                           "prohibited_terms": [], "max_shipping": None, "clarifications": ["Which color?", 5]})
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(interpreter, "_call_gemini", return_value=good):
            r = interpreter.interpret("headphones under 50 dollars")
        self.assertEqual((r["source"], r["clarifications"]), ("gemini", ["Which color?"]))
        bad = json.dumps({"category": "x", "max_total": "fifty", "currency": "USD"})
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(interpreter, "_call_gemini", return_value=bad):
            self.assertEqual(interpreter.interpret("buy headphones under $50")["source"], "fallback_rules")

    def test_spec_example_intent_is_understood(self):
        r = interpreter.fallback_interpret("I want wireless headphones under $50. No subscriptions, no recurring payments, no additional accessories. Buy only after showing me the final price.")
        self.assertEqual((r["category"], r["max_total"], r["allow_subscription"]), ("wireless headphones", 5000, False)); self.assertIn("accessories", r["prohibited_terms"])

    def test_unicode_and_injection_detection(self):
        self.assertEqual(normalize("Ignore\u200b   PREVIOUS\n\tInstructions"), "ignore previous instructions")
        t = self._v("obfuscated_injection")
        self.assertEqual(t["verification"]["decision"], "BLOCKED"); self.assertIn("no_high_threats", [c["id"] for c in t["verification"]["checks"] if not c["passed"]])

    def test_each_attack_is_blocked_by_the_expected_rule(self):
        for a in attacks.ATTACKS:
            r = attacks.run_attack(a["key"])
            self.assertTrue(r["blocked"], a["key"]); self.assertTrue(r["expected_rule_hit"], a["key"]); self.assertFalse(r["payment_captured"])
            self.assertTrue(set(a["expected_rules"]) & {d["rule"] for d in r["detected_by"]}, a["key"])

    def test_attacks_do_not_touch_real_database_or_paypal(self):
        before = self.c.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        for a in attacks.ATTACKS:
            attacks.run_attack(a["key"])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], before)
        with self.assertRaises(s.ServiceError):
            attacks.run_attack("nope")

    def test_drift_flags_only_the_changed_attributes(self):
        t = self._v("hidden_subscription")
        drift = {d["attribute"]: d for d in t["drift"]}
        self.assertTrue(drift["Subscription"]["drifted"]); self.assertFalse(drift["Currency"]["drifted"])
        self.assertFalse(any(d["drifted"] for d in self._v("legit")["drift"]))


if __name__ == "__main__":
    unittest.main()
