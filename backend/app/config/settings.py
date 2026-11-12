"""Settings come from environment variables, optionally loaded from backend/.env.
A blank value (KEY=) counts as "not set" so the default is used."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_env():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


_load_env()


def get(name, default=""):
    v = os.environ.get(name, "")
    return v.strip() if v and v.strip() else default


def _int(name, default):
    try:
        return int(get(name, str(default)))
    except ValueError:
        return default


def DB_PATH():
    p = Path(get("DATABASE_PATH", str(ROOT / "intentguard.db"))).expanduser()
    return str(p if p.is_absolute() else ROOT / p)


GEMINI_API_KEY = lambda: get("GEMINI_API_KEY")
GEMINI_MODEL = lambda: get("GEMINI_MODEL", "gemini-2.5-flash")
CORS_ORIGINS = lambda: [o.strip() for o in get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
DEMO_MODE = lambda: get("DEMO_MODE", "true").lower() != "false"
# Requests per minute per client for endpoints that cost money or CPU. 0 turns the limit off.
RATE_LIMIT_PER_MIN = lambda: max(0, _int("RATE_LIMIT_PER_MIN", 30))
INTENTGUARD_API_TOKEN = lambda: get("INTENTGUARD_API_TOKEN")

# ---- PayPal Sandbox (backend only; the secret never reaches the browser) ----
PAYPAL_CLIENT_ID = lambda: get("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = lambda: get("PAYPAL_CLIENT_SECRET")
PAYPAL_BASE_URL = lambda: get("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com").rstrip("/")
PAYPAL_TIMEOUT = lambda: max(1, _int("PAYPAL_TIMEOUT_SECONDS", 20))
# Where PayPal sends the buyer back after approving or cancelling. Must be the FRONTEND address.
PAYPAL_RETURN_URL = lambda: get("PAYPAL_RETURN_URL", "http://localhost:5173/checkout/return")
PAYPAL_CANCEL_URL = lambda: get("PAYPAL_CANCEL_URL", "http://localhost:5173/checkout/cancel")
# Currencies we will send to PayPal. USD is the safe default for a Sandbox demo.
PAYPAL_CURRENCIES = lambda: {c.strip().upper() for c in get("PAYPAL_ALLOWED_CURRENCIES", "USD").split(",") if c.strip()}
# How long a customer approval stays usable. Long enough to log in to a Sandbox buyer account.
CONSENT_TTL_SECONDS = lambda: max(30, _int("CONSENT_TTL_SECONDS", 900))
