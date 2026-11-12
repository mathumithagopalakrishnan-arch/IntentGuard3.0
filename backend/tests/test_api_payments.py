"""HTTP tests for the payment, receipt, chain, explain and simulator endpoints. Need fastapi + httpx (pip install -r requirements.txt).
Without them every test is SKIPPED, not passed. PayPal is replaced by a scripted double, so these do NOT test real PayPal Sandbox."""
import copy, os, tempfile, unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app.main import app
    HAVE_FASTAPI = True
except (ImportError, RuntimeError):
    HAVE_FASTAPI = False

from app.services import paypal
from app.services.demo_data import DEFAULT_DEMO_INTENT, SCENARIOS
from tests.fakepaypal import FakePayPal


@unittest.skipUnless(HAVE_FASTAPI, "fastapi/httpx not installed: HTTP tests were NOT run")
class PaymentApi(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"DATABASE_PATH": os.path.join(tempfile.mkdtemp(), "a.db"), "GEMINI_API_KEY": "", "RATE_LIMIT_PER_MIN": "0",
                                           "PAYPAL_CLIENT_ID": "cid", "PAYPAL_CLIENT_SECRET": "secret",
                                           "INTENTGUARD_API_TOKEN": "test-intentguard-auth-token-long-enough"})
        env.start(); self.addCleanup(env.stop)
        self.fake = FakePayPal()
        patch = mock.patch.object(paypal, "get_client", lambda: paypal.PayPalClient("cid", "secret", "https://api-m.sandbox.paypal.com", transport=self.fake.transport))
        patch.start(); self.addCleanup(patch.stop)
        cm = TestClient(app, raise_server_exceptions=False, headers={"Authorization": "Bearer test-intentguard-auth-token-long-enough"})
        self.client = cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)

    def tx(self, name="legit"):
        sc = SCENARIOS[name]
        iid = self.client.post("/api/intents", json={"instruction": "demo", "constraints": copy.deepcopy(DEFAULT_DEMO_INTENT), "source": "user_edited"}).json()["id"]
        self.client.post(f"/api/intents/{iid}/confirm")
        oid = self.client.post("/api/offers", json=copy.deepcopy(sc["offer"])).json()["id"]
        return self.client.post("/api/transactions", json={"intent_id": iid, "offer_id": oid, "cart": [{"item_id": "p1", "qty": 1, "unit_price": sc["cart_price"]}]}).json()

    def test_health_reports_sandbox_ready_without_secret(self):
        j = self.client.get("/api/health").json()
        self.assertTrue(j["payments_enabled"]); self.assertNotIn("secret", str(j).lower().replace("client_secret", ""))

    def test_full_flow(self):
        t = self.tx(); tid = t["id"]
        self.assertEqual(self.client.post(f"/api/transactions/{tid}/checkout").status_code, 409)  # no consent yet
        self.assertEqual(self.client.post(f"/api/transactions/{tid}/consent").status_code, 201)
        r = self.client.post(f"/api/transactions/{tid}/checkout"); self.assertEqual(r.status_code, 201, r.text)
        oid = r.json()["paypal_order_id"]
        self.assertEqual(self.client.post(f"/api/transactions/{tid}/capture", json={"order_id": oid}).status_code, 409)  # not approved
        self.fake.approve(oid)
        c = self.client.post(f"/api/transactions/{tid}/capture", json={"order_id": oid}); self.assertEqual(c.status_code, 200, c.text)
        self.assertEqual(c.json()["state"], "COMPLETED")
        self.assertEqual(self.client.get(f"/api/transactions/{tid}/receipt").status_code, 200)
        self.assertTrue(self.client.get(f"/api/transactions/{tid}/chain").json()["intact"])
        self.assertEqual(self.client.get("/api/audit/verify").json()["intact"], True)

    def test_blocked_transaction_has_no_checkout(self):
        t = self.tx("hidden_subscription")
        self.assertEqual(self.client.post(f"/api/transactions/{t['id']}/consent").status_code, 409)
        self.assertEqual(self.client.post(f"/api/transactions/{t['id']}/checkout").status_code, 409)
        self.assertEqual(self.fake.calls, [])

    def test_capture_rejects_extra_fields(self):
        t = self.tx(); self.client.post(f"/api/transactions/{t['id']}/consent")
        self.assertEqual(self.client.post(f"/api/transactions/{t['id']}/capture", json={"order_id": "X", "amount": 1}).status_code, 422)

    def test_simulator_and_explain(self):
        a = self.client.get("/api/attacks").json()["attacks"]; self.assertEqual(len(a), 8)
        for x in a:
            self.assertTrue(self.client.post(f"/api/attacks/{x['key']}/run").json()["blocked"])
        t = self.tx("hidden_subscription")
        self.assertEqual(self.client.post(f"/api/transactions/{t['id']}/explain").json()["decision"], "BLOCKED")

    def test_not_configured_returns_503(self):
        with mock.patch.dict(os.environ, {"PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": ""}):
            with mock.patch.object(paypal, "get_client", lambda: paypal.PayPalClient(transport=self.fake.transport)):
                t = self.tx(); self.client.post(f"/api/transactions/{t['id']}/consent")
                self.assertEqual(self.client.post(f"/api/transactions/{t['id']}/checkout").status_code, 503)
