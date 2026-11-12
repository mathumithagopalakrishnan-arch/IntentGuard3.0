"""PayPal Orders v2 client for the SANDBOX only. Standard library only (urllib), so it also runs in tests.

Rules enforced here:
- The base URL must be PayPal's sandbox host. Anything else (including the live host) is refused before any request.
- The client secret is only ever sent to PayPal's OAuth endpoint. It is never logged or returned.
- Every create/capture call carries a PayPal-Request-Id, so a retry after a timeout cannot make a second order or capture.
- The transport is injectable, so tests use scripted responses and never touch the network.
"""
import base64, json, logging, time, urllib.error, urllib.parse, urllib.request
from ..config import settings

log = logging.getLogger("intentguard.paypal")
SANDBOX_HOSTS = {"api-m.sandbox.paypal.com", "api.sandbox.paypal.com"}
LIVE_HOSTS = {"api-m.paypal.com", "api.paypal.com"}


class PayPalError(Exception):
    """`retryable` is True when the outcome is unknown (timeout, 5xx) so the SAME request id may be retried."""
    def __init__(self, message, status=0, code="paypal_error", retryable=False):
        super().__init__(message)
        self.message, self.status, self.code, self.retryable = message, status, code, retryable


def assert_sandbox(base_url: str) -> str:
    u = urllib.parse.urlparse(base_url or "")
    host = (u.hostname or "").lower()
    if u.scheme != "https" or host in LIVE_HOSTS or host not in SANDBOX_HOSTS or u.path not in ("", "/") or u.username or u.password:
        raise PayPalError("Refused: PAYPAL_BASE_URL must be https://api-m.sandbox.paypal.com. IntentGuard never talks to live PayPal.", code="not_sandbox")
    return f"https://{host}"


def _urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except ValueError:
            return e.code, {"message": "non-JSON error body"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PayPalError(f"Could not reach PayPal Sandbox ({type(e).__name__}).", code="network", retryable=True)


class PayPalClient:
    def __init__(self, client_id=None, client_secret=None, base_url=None, transport=None, timeout=None, clock=time.time):
        self.client_id = settings.PAYPAL_CLIENT_ID() if client_id is None else client_id
        self.client_secret = settings.PAYPAL_CLIENT_SECRET() if client_secret is None else client_secret
        self.base = assert_sandbox(settings.PAYPAL_BASE_URL() if base_url is None else base_url)
        self.transport = transport or _urllib_transport
        self.timeout = timeout or settings.PAYPAL_TIMEOUT()
        self.clock = clock
        self._token, self._token_exp = None, 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # ---- OAuth ----
    def _access_token(self) -> str:
        if not self.configured:
            raise PayPalError("PayPal Sandbox credentials are not set (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET in backend/.env).", code="not_configured")
        if self._token and self.clock() < self._token_exp - 30:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        status, data = self.transport("POST", self.base + "/v1/oauth2/token",
                                      {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                                      b"grant_type=client_credentials", self.timeout)
        if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
            raise PayPalError("PayPal Sandbox rejected the credentials or is unavailable." if status < 500 else "PayPal Sandbox is temporarily unavailable.",
                              status=status, code="oauth_failed", retryable=status >= 500)
        self._token = data["access_token"]
        self._token_exp = self.clock() + float(data.get("expires_in", 300))
        return self._token

    def _call(self, method, path, body=None, request_id=None):
        token = self._access_token()
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        raw = json.dumps(body).encode() if body is not None else None
        status, data = self.transport(method, self.base + path, headers, raw, self.timeout)
        if status == 401:  # token may have expired early: drop it so the next attempt re-authenticates
            self._token = None
        if status >= 400 or not isinstance(data, dict):
            name = data.get("name") if isinstance(data, dict) else None
            issue = ""
            if isinstance(data, dict) and data.get("details"):
                issue = str((data["details"][0] or {}).get("issue", ""))
            raise PayPalError(f"PayPal Sandbox returned an error ({status}{' ' + name if name else ''}{': ' + issue if issue else ''}).",
                              status=status, code=issue or name or "paypal_error", retryable=status >= 500 or status == 429)
        return data

    # ---- Orders v2 ----
    def create_order(self, payload: dict, request_id: str) -> dict:
        return self._call("POST", "/v2/checkout/orders", payload, request_id)

    def get_order(self, order_id: str) -> dict:
        return self._call("GET", "/v2/checkout/orders/" + urllib.parse.quote(order_id, safe=""))

    def capture_order(self, order_id: str, request_id: str) -> dict:
        return self._call("POST", "/v2/checkout/orders/" + urllib.parse.quote(order_id, safe="") + "/capture", {}, request_id)

    def probe(self) -> dict:
        """Optional live check used by /api/paypal/status?probe=true. Returns only a yes/no and a message."""
        try:
            self._access_token()
            return {"oauth_ok": True, "message": "PayPal Sandbox accepted the credentials."}
        except PayPalError as e:
            return {"oauth_ok": False, "message": e.message}


def get_client() -> PayPalClient:
    """One place to replace in tests."""
    return PayPalClient()


def status_summary() -> dict:
    """Configuration facts only. Never includes the secret or any part of it."""
    try:
        assert_sandbox(settings.PAYPAL_BASE_URL())
        base_ok = True
    except PayPalError:
        base_ok = False
    configured = bool(settings.PAYPAL_CLIENT_ID() and settings.PAYPAL_CLIENT_SECRET())
    return {"mode": "sandbox", "configured": configured, "base_url_is_sandbox": base_ok, "ready": configured and base_ok,
            "currencies": sorted(settings.PAYPAL_CURRENCIES()), "return_url": settings.PAYPAL_RETURN_URL()}
