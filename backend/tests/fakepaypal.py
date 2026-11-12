"""A scripted stand-in for PayPal Sandbox used by the tests. It is a TEST DOUBLE: it proves how IntentGuard reacts to PayPal
responses, not that real PayPal accepts our requests. Real Sandbox testing is a separate manual step (see README)."""
import itertools, threading
from app.services.paypal import PayPalError


class FakePayPal:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = []                  # (method, path, request_id)
        self.orders = {}                 # id -> dict
        self.by_request = {}             # request id -> response (PayPal idempotency)
        self.captures_by_request = {}
        self.ids = itertools.count(1)
        self.oauth_status = 200
        self.fail_create = []            # queue of ("timeout" | ("http", status, name, issue))
        self.fail_capture = []           # same, applied BEFORE capture happens
        self.lose_capture_response = 0   # capture is applied, then the response is lost (timeout)
        self.tamper_amount = None        # (currency, value) overrides the amount PayPal reports for the order
        self.capture_decline = False

    def count(self, what):
        """Counts calls. 'POST /v2/checkout/orders' matches that exact path only; other strings match as substrings."""
        if what == "POST /v2/checkout/orders":
            return sum(1 for m, p, _ in self.calls if (m, p) == ("POST", "/v2/checkout/orders"))
        return sum(1 for m, p, _ in self.calls if what in f"{m} {p}")

    def approve(self, order_id):
        self.orders[order_id]["status"] = "APPROVED"

    def transport(self, method, url, headers, body, timeout):
        import json
        path = url.split("paypal.com", 1)[1]
        with self.lock:
            self.calls.append((method, path, headers.get("PayPal-Request-Id")))
            if path == "/v1/oauth2/token":
                if self.oauth_status != 200:
                    return self.oauth_status, {"error": "invalid_client"}
                return 200, {"access_token": "TEST-TOKEN", "expires_in": 3600}
            if headers.get("Authorization") != "Bearer TEST-TOKEN":
                return 401, {"name": "AUTHENTICATION_FAILURE"}
            if method == "POST" and path == "/v2/checkout/orders":
                rid = headers["PayPal-Request-Id"]
                if rid in self.by_request:
                    return 200, self.by_request[rid]
                if self.fail_create:
                    f = self.fail_create.pop(0)
                    if f == "timeout":
                        raise PayPalError("Could not reach PayPal Sandbox (TimeoutError).", code="network", retryable=True)
                    return f[1], {"name": f[2], "details": [{"issue": f[3]}]}
                oid = f"ORDER{next(self.ids):04d}"
                req = json.loads(body)
                unit = req["purchase_units"][0]
                amount = dict(unit["amount"])
                if self.tamper_amount:
                    amount["currency_code"], amount["value"] = self.tamper_amount
                self.orders[oid] = {"id": oid, "status": "PAYER_ACTION_REQUIRED", "purchase_units": [{"custom_id": unit["custom_id"], "amount": amount}], "request": req}
                resp = {"id": oid, "status": "PAYER_ACTION_REQUIRED", "links": [{"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"}]}
                self.by_request[rid] = resp
                return 201, resp
            if method == "GET" and path.startswith("/v2/checkout/orders/"):
                oid = path.rsplit("/", 1)[1]
                if oid not in self.orders:
                    return 404, {"name": "RESOURCE_NOT_FOUND"}
                o = self.orders[oid]
                return 200, {k: v for k, v in o.items() if k != "request"}
            if method == "POST" and path.endswith("/capture"):
                oid = path.split("/")[-2]
                rid = headers["PayPal-Request-Id"]
                if rid in self.captures_by_request:
                    return 201, self.captures_by_request[rid]
                if self.fail_capture:
                    f = self.fail_capture.pop(0)
                    if f == "timeout":
                        raise PayPalError("Could not reach PayPal Sandbox (TimeoutError).", code="network", retryable=True)
                    return f[1], {"name": f[2], "details": [{"issue": f[3]}]}
                o = self.orders.get(oid)
                if not o:
                    return 404, {"name": "RESOURCE_NOT_FOUND"}
                if o["status"] == "COMPLETED":
                    return 422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]}
                if o["status"] != "APPROVED":
                    return 422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "ORDER_NOT_APPROVED"}]}
                if self.capture_decline:
                    return 422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSTRUMENT_DECLINED"}]}
                o["status"] = "COMPLETED"
                amt = o["purchase_units"][0]["amount"]
                o["purchase_units"][0]["payments"] = {"captures": [{"id": f"CAP{next(self.ids):04d}", "status": "COMPLETED",
                                                                    "amount": {"currency_code": amt["currency_code"], "value": amt["value"]}}]}
                resp = {"id": oid, "status": "COMPLETED", "purchase_units": o["purchase_units"]}
                self.captures_by_request[rid] = resp
                if self.lose_capture_response:
                    self.lose_capture_response -= 1
                    raise PayPalError("Could not reach PayPal Sandbox (TimeoutError).", code="network", retryable=True)
                return 201, resp
            return 404, {"name": "NOT_FOUND"}
