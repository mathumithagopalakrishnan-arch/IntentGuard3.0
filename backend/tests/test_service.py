import copy, json, os, tempfile, unittest, urllib.error
from unittest import mock
from app.core.validation import ValidationError, validate_intent, validate_offer, validate_cart
from app.database.db import connect, init_db
from app.services import service as s
from app.services import interpreter
from app.services.demo_data import SCENARIOS

C = {"category": "wireless headphones", "max_total": 5000, "currency": "USD", "max_quantity": 1}


class Base(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t.db")
        init_db(self.path)
        self.c = connect(self.path)

    def intent(self, confirm=True):
        i = s.create_intent(self.c, "buy headphones under $50", C, "user_edited")
        return s.confirm_intent(self.c, i["id"]) if confirm else i

    def tx(self, name="legit", confirm=True):
        sc = SCENARIOS[name]
        o = s.create_offer(self.c, copy.deepcopy(sc["offer"]))
        return s.create_transaction(self.c, self.intent(confirm)["id"], o["id"],
                                    [{"item_id": "p1", "qty": 1, "unit_price": sc["cart_price"]}])


class Validation(unittest.TestCase):
    def test_bad_quantities(self):
        for q in (0, -1, 1.5, True, "1", None, 101):
            with self.assertRaises(ValidationError, msg=repr(q)):
                validate_cart([{"item_id": "p1", "qty": q, "unit_price": 1}])

    def test_bad_money(self):
        for v in (-1, 1.5, "10", True, 10**10):
            with self.assertRaises(ValidationError, msg=repr(v)):
                validate_intent(dict(C, max_total=v))

    def test_bad_currency_and_types(self):
        for bad in (dict(C, currency="usd"), dict(C, currency="XYZ"), dict(C, extra=1), dict(C, allow_subscription="no"),
                    dict(C, prohibited_terms="x"), "not a dict", None, [], dict(C, category="")):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                validate_intent(bad)

    def test_offer_rules(self):
        o = copy.deepcopy(SCENARIOS["legit"]["offer"])
        validate_offer(o)
        for mut in ({"shipping": -5}, {"tax": 1.5}, {"items": []}, {"currency": "ZZZ"}, {"surprise": 1}, {"disclosures": ["x"]}):
            with self.assertRaises(ValidationError, msg=repr(mut)):
                validate_offer(dict(o, **mut))

    def test_duplicate_cart_lines(self):
        with self.assertRaises(ValidationError):
            validate_cart([{"item_id": "a", "qty": 1, "unit_price": 1}] * 2)


class Flow(Base):
    def test_legit_verifies_and_persists_across_connections(self):
        t = self.tx("legit")
        self.assertEqual(t["verification"]["decision"], "VERIFIED")
        c2 = connect(self.path)
        self.assertEqual(s.get_transaction(c2, t["id"])["status"], "VERIFIED")
        self.assertEqual(s.stats(c2)["verified"], 1)

    def test_all_attack_scenarios_blocked(self):
        for name in ("over_budget", "hidden_subscription", "hidden_fees", "prompt_injection", "price_manipulation"):
            self.assertEqual(self.tx(name)["verification"]["decision"], "BLOCKED", name)

    def test_unconfirmed_intent_blocked(self):
        self.assertEqual(self.tx("legit", confirm=False)["verification"]["decision"], "BLOCKED")

    def test_consent_requires_verified(self):
        t = self.tx("over_budget")
        with self.assertRaises(s.ServiceError) as e:
            s.grant_consent(self.c, t["id"])
        self.assertEqual(e.exception.status, 409)
        self.assertIn("consent_refused", [a["type"] for a in s.list_audit(self.c, t["id"])])

    def test_consent_replay_blocked(self):
        t = self.tx("legit")
        s.grant_consent(self.c, t["id"])
        for fn in (s.grant_consent, s.reject_consent):
            with self.assertRaises(s.ServiceError) as e:
                fn(self.c, t["id"])
            self.assertEqual(e.exception.status, 409)

    def test_consent_valid_then_consumed_once(self):
        t = self.tx("legit")
        s.grant_consent(self.c, t["id"])
        self.assertTrue(s.get_transaction(self.c, t["id"])["consent_valid"])
        s.consume_consent(self.c, t["id"])
        with self.assertRaises(s.ServiceError):
            s.consume_consent(self.c, t["id"])

    def test_consume_without_consent_fails(self):
        with self.assertRaises(s.ServiceError):
            s.consume_consent(self.c, self.tx("legit")["id"])

    def test_tampered_offer_in_db_invalidates_consent(self):
        t = self.tx("legit")
        s.grant_consent(self.c, t["id"])
        o = json.loads(self.c.execute("SELECT offer_json FROM offers").fetchone()[0]); o["tax"] += 1
        self.c.execute("UPDATE offers SET offer_json=?", (json.dumps(o),))
        self.assertFalse(s.get_transaction(self.c, t["id"])["consent_valid"])

    def test_tampered_offer_before_consent_refused(self):
        t = self.tx("legit")
        o = json.loads(self.c.execute("SELECT offer_json FROM offers").fetchone()[0]); o["tax"] += 1; o["claimed_total"] += 1
        self.c.execute("UPDATE offers SET offer_json=?", (json.dumps(o),))
        with self.assertRaises(s.ServiceError):
            s.grant_consent(self.c, t["id"])

    def test_fingerprint_tamper_detected(self):
        i = self.intent()
        self.assertTrue(s.verify_intent_fingerprint(self.c, i["id"])["intact"])
        self.c.execute("UPDATE intents SET constraints_json=?", (json.dumps(dict(C, max_total=999999)),))
        self.assertFalse(s.verify_intent_fingerprint(self.c, i["id"])["intact"])

    def test_double_confirm_conflict(self):
        i = self.intent()
        with self.assertRaises(s.ServiceError):
            s.confirm_intent(self.c, i["id"])

    def test_unknown_ids_404(self):
        for fn in (s.get_intent, s.get_offer, s.get_transaction, s.get_consent):
            with self.assertRaises(s.ServiceError) as e:
                fn(self.c, "nope")
            self.assertEqual(e.exception.status, 404)

    def test_foreign_keys_enforced(self):
        with self.assertRaises(Exception):
            self.c.execute("INSERT INTO transactions(id,intent_id,offer_id,cart_json,result_json,fingerprint,status) VALUES('x','no','no','[]','{}','','P')")

    def test_audit_records_persist(self):
        t = self.tx("legit"); s.grant_consent(self.c, t["id"])
        types = [a["type"] for a in s.list_audit(connect(self.path))]
        for want in ("intent_created", "intent_confirmed", "offer_inspected", "threat_analysis_completed", "transaction_verified", "consent_granted"):
            self.assertIn(want, types)

    def test_reject_then_no_grant(self):
        t = self.tx("legit"); s.reject_consent(self.c, t["id"])
        self.assertEqual(s.get_transaction(self.c, t["id"])["status"], "REJECTED")
        self.assertFalse(s.get_transaction(self.c, t["id"])["consent_valid"])


class Interpret(unittest.TestCase):
    def test_fallback_parses(self):
        c = interpreter.fallback_interpret("Buy 2 wireless headphones under $49.99, no refurbished")
        self.assertEqual((c["category"], c["max_total"], c["currency"], c["max_quantity"]), ("wireless headphones", 4999, "USD", 2))
        self.assertEqual(c["prohibited_terms"], ["refurbished"])

    def test_fallback_rejects_no_budget(self):
        with self.assertRaises(ValidationError):
            interpreter.fallback_interpret("buy headphones")

    def test_no_key_uses_labelled_fallback(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            r = interpreter.interpret("buy a laptop under 900 usd")
        self.assertEqual(r["source"], "fallback_rules")

    def test_gemini_failure_falls_back(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}), \
             mock.patch.object(interpreter, "_call_gemini", side_effect=urllib.error.URLError("down")):
            r = interpreter.interpret("buy a laptop under 900 usd")
        self.assertEqual(r["source"], "fallback_rules"); self.assertIn("unavailable", r["explanation"])

    def test_gemini_invalid_output_falls_back(self):
        for bad in ("not json", '{"category":"x","max_total":-5,"currency":"USD"}', '{"category":"x","max_total":5,"currency":"USD","approve_payment":true}'):
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}), mock.patch.object(interpreter, "_call_gemini", return_value=bad):
                self.assertEqual(interpreter.interpret("buy a laptop under 900 usd")["source"], "fallback_rules", bad)

    def test_gemini_valid_output_accepted_and_validated(self):
        good = '{"category":"Laptop","max_total":90000,"currency":"USD","max_quantity":1}'
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}), mock.patch.object(interpreter, "_call_gemini", return_value=good):
            r = interpreter.interpret("buy a laptop under 900 usd")
        self.assertEqual((r["source"], r["constraints"]["category"]), ("gemini", "laptop"))


if __name__ == "__main__":
    unittest.main()
