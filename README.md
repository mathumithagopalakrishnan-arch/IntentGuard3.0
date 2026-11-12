# IntentGuard: The Trust Layer for Agentic Commerce

> Independent hackathon prototype for the PayPal AI Hackathon 2026. Not endorsed by or affiliated with PayPal. Payments use the **PayPal Sandbox only (test money)**. All demo merchants are **synthetic**.

## Problem
AI shopping agents can search, choose and buy on a customer's behalf. Between the customer's request and the final payment, the original instructions can be lost or manipulated: a hidden monthly subscription, a changed price or quantity, an unexpected fee, or text inside a product page that tries to give the agent new orders. Generic fraud scores do not answer the real question: *is the transaction being paid the transaction the customer intended?*

## Solution: the Intent-to-Payment Integrity Chain
IntentGuard binds eight stages together, each hashed and linked to the previous one:

1. Original customer intent (the customer's words)
2. Intent Passport (AI-interpreted, editable, customer-confirmed rules + SHA-256 fingerprint)
3. Merchant offer (untrusted data, scanned, never obeyed)
4. Final cart (the server recomputes every price and the total)
5. Deterministic verification (about 14 rules decide PASS or BLOCKED; no AI)
6. Explicit human consent (bound to the exact transaction fingerprint, short-lived, single use)
7. PayPal Sandbox order and capture (amount comes from the server; capture only after PayPal reports the order APPROVED)
8. Tamper-evident audit trail and a downloadable **Intent Integrity Receipt**

If any protected attribute changes, the earlier consent no longer matches: no new PayPal order is created, and an existing order is not captured.

**Target audience:** shoppers who delegate purchases to AI agents, agentic-commerce platforms that need verifiable authorization, and merchants who want provable, intent-matched checkouts.

## Key features
- Intent Passport with Gemini interpretation, clarification questions and a rule-based fallback
- Intent Drift table (what you asked for vs what the transaction does) tied to backend rules
- Merchant Prompt Injection Firewall (Unicode and zero-width normalization, deterministic rules)
- Transaction Integrity Gate (integer minor units; price, total, currency, budget, quantity, category, prohibited terms, subscription, shipping, disclosures, threats)
- Consent lifecycle: expiry, exact-fingerprint binding, atomic one-time consumption, replay protection
- PayPal Sandbox Orders v2 integration (OAuth, create, get, capture, idempotency, persistent state machine)
- Evidence-grounded explanations (evidence vs inferred risk vs uncertainty; AI text is labelled and validated)
- Attack Simulator with 8 realistic attacks and the exact rule that stops each
- Hash-chained audit log, downloadable receipt, payment history, chain view
- One-click guided demos: Scenario A (trusted purchase) and Scenario B (malicious purchase)

## Technology
React 18 + TypeScript + Vite + Tailwind CSS; Python FastAPI; SQLite; Gemini API (optional); PayPal REST Orders v2 (Sandbox); SHA-256 canonical JSON. The PayPal client uses only the Python standard library (`urllib`).

## Architecture (short)
See [ARCHITECTURE.md](ARCHITECTURE.md) and [SECURITY.md](SECURITY.md).

    backend/app/core      fingerprint, validation, threats, verification, drift, money, consent (stdlib only)
    backend/app/services  service.py (SQLite logic, consent, audit chain), paypal.py (Sandbox client), payments.py (state machine),
                          chain.py, receipt.py, attacks.py, ai_explain.py, interpreter.py, demo_data.py (SYNTHETIC)
    backend/app/api       routes.py        backend/app/main.py (CORS, rate limit, security headers)
    backend/tests         stdlib unittest + a scripted PayPal test double
    frontend/src          pages, components, services/api.ts, types

## Setup on Windows (PowerShell, Python 3.11+, Node.js 20+)

### 1. Backend
    cd intentguard\backend
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy ..\.env.example .env
    notepad .env          # configure the local API token and optional service keys
    uvicorn app.main:app --reload
If PowerShell blocks the activation script: `Set-ExecutionPolicy -Scope Process Bypass`.
Set a random `INTENTGUARD_API_TOKEN` of at least 32 characters in `backend/.env`. Enter it on the app's unlock screen; the browser keeps it only in tab-scoped session storage. API endpoints fail closed until it is configured. API docs: http://127.0.0.1:8000/docs (API calls require the bearer token).

### 2. Frontend (second PowerShell window)
    cd intentguard\frontend
    copy .env.example .env
    npm install
    npm run dev
Open http://localhost:5173 .

### 3. Environment variables (`backend/.env`)
| Variable | Purpose |
|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Sandbox app credentials. **Backend only.** Never put them in the frontend. |
| `INTENTGUARD_API_TOKEN` | Required local API access token; use a random value of at least 32 characters. Enter it in the app unlock screen; never put it in `frontend/.env`. |
| `PAYPAL_BASE_URL` | Must be `https://api-m.sandbox.paypal.com`. Anything else is refused. |
| `PAYPAL_RETURN_URL`, `PAYPAL_CANCEL_URL` | Frontend addresses PayPal returns the buyer to (defaults match `npm run dev`). |
| `PAYPAL_ALLOWED_CURRENCIES` | Default `USD`. |
| `CONSENT_TTL_SECONDS` | Approval lifetime, default 900. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Optional. Without a key the rule-based fallback runs. |
| `CORS_ORIGINS` | Comma-separated exact frontend origins; defaults to the two local Vite URLs. Do not use `*` for a deployment. |
| `VITE_API_BASE_URL` | Optional frontend API base URL in `frontend/.env`; never put secrets in frontend variables. |

Without PayPal credentials everything except the final checkout works, and the checkout page says so. Without the API token, the backend rejects API access.

## Testing
    cd intentguard\backend
    python -m pytest -q -rs
The HTTP tests require the declared FastAPI/httpx dependencies and a Python runtime that can import the `pydantic_core` extension. Treat skipped tests as **not run**, not as passes, and resolve their reported reason before submission. PayPal integration tests use a scripted test double, so they prove IntentGuard's behavior, **not** that real PayPal Sandbox accepts the calls.

Frontend: `cd frontend; npm run typecheck; npm run build`.

## Current PayPal verification status
On 2026-11-12, the configured credentials were accepted by PayPal Sandbox OAuth, and PayPal accepted a synthetic USD order-creation request and returned a Sandbox approval link. The buyer did not approve that order, and no capture was performed. This verifies OAuth and order creation only; it is **not** a verified end-to-end payment. The automated payment tests use a scripted double. Do not claim approval, capture, or successful payment until a Sandbox buyer completes checkout and the capture is confirmed in both IntentGuard and the Sandbox account. No PayPal Live endpoint or live payment was used.

## PayPal Sandbox checkout (manual test)
1. Sign in at https://developer.paypal.com/ and open **Apps & Credentials** (Sandbox). Create an app and copy its Client ID and Secret into `backend/.env`. If these values were ever exposed, rotate the Sandbox app secret first and use only the replacement.
2. Under **Sandbox accounts** find (or create) a **Personal** (buyer) account and note its email and password. Never use a real PayPal account for testing.
3. Restart the backend and unlock the UI with the local API token. On PayPal Sandbox Checkout, choose **Check Sandbox OAuth**. This sends an OAuth probe only; it does not verify that the Sandbox seller can receive the chosen currency. Direct API calls require the bearer token.
4. In the app click **Scenario A: trusted purchase**, then **I approve this exact transaction**, then **PayPal Checkout -> Pay with PayPal Sandbox**.
5. Log in with the Sandbox buyer account on PayPal's page and approve. You return to the app, the backend verifies the order with PayPal and captures it. Confirm `COMPLETED` in IntentGuard and the Sandbox account before reporting a successful payment.
6. Open **Audit & Receipt** and download the Intent Integrity Receipt.
Then run **Scenario B: malicious purchase** to see a blocked transaction (no PayPal order is ever created).
You have `CONSENT_TTL_SECONDS` (default 15 minutes) between approving and finishing at PayPal.

## Troubleshooting
- *"Cannot reach the backend"*: start `uvicorn` and check `VITE_API_BASE_URL` in `frontend/.env`.
- *Checkout says credentials are missing*: set both PayPal values in `backend/.env` and restart the backend.
- *`oauth_failed`*: wrong Client ID/Secret, or you used Live instead of Sandbox credentials.
- *"This seller doesn't accept payments in your currency" on PayPal*: if IntentGuard shows `ORDER_CREATED`, order creation succeeded, but the PayPal-hosted approval flow rejected the seller/currency combination. No capture is confirmed. Do not silently change the customer's USD intent or enable a different currency in code. In the PayPal Developer Dashboard, inspect the Sandbox **Business** account's receiving-currency settings; use/configure a Sandbox seller that accepts the intended currency and a Sandbox buyer, then retry with a new transaction. If the setting is unavailable, create another compatible Sandbox Business account or contact PayPal Sandbox support. The exact account-side cause has not been verified from a PayPal REST error response.
- *"currency ... is not enabled" from IntentGuard*: `PAYPAL_ALLOWED_CURRENCIES` is the application's allowlist only; configure it to include the already-intended currency only after confirming the Sandbox seller can accept it.
- *"consent expired"*: approve again (use **Start again with the same cart**).
- *PayPal returns to a blank page*: `PAYPAL_RETURN_URL` must match the address of the running frontend.

## Known limitations
- A PayPal Sandbox order was created for a USD transaction, but the hosted approval page rejected the seller's currency. There is no verified approval or capture. Automated payment tests use a scripted fake and do not establish live Sandbox acceptance.
- A matching hash proves data is unchanged, not that a merchant is honest. Merchant claims are not independently verified.
- Single-user prototype: the local bearer-token gate is not multi-user identity or role-based authorization. Do not expose it publicly with real credentials.
- The audit chain cannot detect removal of the newest events unless its head hash is stored elsewhere.
- Currency support depends on both this app's allowlist and the Sandbox seller account; do not infer acceptance from the allowlist. Gemini output quality was not evaluated.
- Rotate any previously exposed PayPal Sandbox credentials: in PayPal Developer Dashboard, regenerate the Sandbox app secret, replace `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` in `backend/.env`, restart the backend, and never paste credentials into chat, screenshots, logs, or source control. Do not change values in frontend `.env`.
- GitHub secret scanning, push protection, and repository history could not be verified from this workspace because it contains no Git metadata or `.github` configuration. See [SECURITY.md](SECURITY.md) and complete the source-control checks before publishing.

## Hackathon materials
[HACKATHON_CHANGES.md](HACKATHON_CHANGES.md) · [DEVPOST_DESCRIPTION.md](DEVPOST_DESCRIPTION.md) · [DEMO_SCRIPT.md](DEMO_SCRIPT.md) · [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) · License: [MIT](LICENSE)
