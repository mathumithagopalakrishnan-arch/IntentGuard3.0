
# IntentGuard: The Trust Layer for Agentic Commerce

> Independent hackathon prototype for the PayPal AI Hackathon 2026. Not endorsed by or affiliated with PayPal. Payments use the **PayPal Sandbox only (test money)**. All demo merchants are **synthetic**.

## Problem

AI shopping agents can search, choose and buy on a customer's behalf. Between the customer's request and final payment, original instructions can be lost or manipulated:

- Hidden monthly subscriptions
- Changed prices or quantities
- Unexpected fees
- Malicious instructions embedded in product pages

Generic fraud scores do not answer the key question: **Is the transaction being paid the transaction the customer actually intended?**

## Solution: The Intent-to-Payment Integrity Chain

IntentGuard connects eight stages, each protected by hashing and linked to the previous stage:

1. Original customer intent.
2. Intent Passport: AI-interpreted, editable and customer-confirmed rules with a SHA-256 fingerprint.
3. Merchant offer: treated as untrusted data and scanned, never obeyed.
4. Final cart: the server recomputes prices and totals.
5. Deterministic verification: approximately 14 rules decide PASS or BLOCKED without relying on AI.
6. Explicit human consent: bound to the exact transaction fingerprint, short-lived and single-use.
7. PayPal Sandbox order and capture: amount comes from the server; capture happens only after PayPal reports the order as APPROVED.
8. Tamper-evident audit trail and downloadable Intent Integrity Receipt.

If a protected transaction attribute changes, previous consent no longer matches. A new PayPal order is not created, and an existing order is not captured.

**Target audience:** Shoppers using AI shopping agents, agentic-commerce platforms requiring verifiable authorization, and merchants seeking intent-matched checkout protection.

## Key Features

- Intent Passport with Gemini interpretation, clarification questions and rule-based fallback.
- Intent Drift table comparing customer intent with transaction details.
- Merchant Prompt Injection Firewall with Unicode and zero-width normalization.
- Transaction Integrity Gate covering price, total, currency, budget, quantity, category, subscriptions, shipping, disclosures and threats.
- Consent lifecycle with expiry, fingerprint binding, atomic one-time consumption and replay protection.
- PayPal Sandbox Orders v2 integration with OAuth, order creation, retrieval, capture and idempotency.
- Evidence-grounded explanations distinguishing evidence, inferred risk and uncertainty.
- Attack Simulator with eight realistic attacks.
- Hash-chained audit log, downloadable receipt, payment history and chain view.
- Guided demos: Scenario A (trusted purchase) and Scenario B (malicious purchase).

## Technology Stack

- Frontend: React 18, TypeScript, Vite and Tailwind CSS.
- Backend: Python and FastAPI.
- Database: SQLite.
- AI: Gemini API (optional).
- Payments: PayPal REST Orders v2 (Sandbox).
- Integrity: SHA-256 canonical JSON hashing.

The PayPal client uses Python's standard library (`urllib`).

## Repository Structure

```text
IntentGuard3.0/
├── backend/
│   ├── app/
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
├── ARCHITECTURE.md
├── DEMO_SCRIPT.md
├── DEVPOST_DESCRIPTION.md
├── HACKATHON_CHANGES.md
├── LICENSE
├── README.md
├── SECURITY.md
└── SUBMISSION_CHECKLIST.md
```

## Setup on Windows

### Prerequisites

- Python 3.11 or later
- Node.js 20 or later
- npm
- Windows PowerShell

### 1. Backend Setup

Open PowerShell in the repository root folder.

```powershell
cd backend

python -m venv .venv

.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

copy .env.example .env

notepad .env
```

Configure the environment variables in `backend/.env`.

Set `INTENTGUARD_API_TOKEN` to a random value containing at least 32 characters.

Keep PayPal credentials in the backend environment file only.

If PowerShell blocks virtual environment activation, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Then activate the environment again.

Start the backend:

```powershell
uvicorn app.main:app --reload
```

Backend API documentation:

http://127.0.0.1:8000/docs

API requests require the configured bearer token.

### 2. Frontend Setup

Open a **second PowerShell window** in the repository root folder.

```powershell
cd frontend

copy .env.example .env

npm install

npm run dev
```

Open the frontend:

http://localhost:5173

### 3. Environment Variables

Configure these values in `backend/.env`.

| Variable | Purpose |
|---|---|
| `INTENTGUARD_API_TOKEN` | Required local API access token. Use a random value of at least 32 characters. |
| `PAYPAL_CLIENT_ID` | PayPal Sandbox Client ID. |
| `PAYPAL_CLIENT_SECRET` | PayPal Sandbox Secret. |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` |
| `PAYPAL_RETURN_URL` | Frontend checkout return URL. |
| `PAYPAL_CANCEL_URL` | Frontend checkout cancellation URL. |
| `PAYPAL_ALLOWED_CURRENCIES` | Application currency allowlist. Default: USD. |
| `CONSENT_TTL_SECONDS` | Consent validity period. Default: 900 seconds. |
| `GEMINI_API_KEY` | Optional Gemini API key. |
| `GEMINI_MODEL` | Optional Gemini model identifier. |
| `CORS_ORIGINS` | Allowed frontend origins. |
| `VITE_API_BASE_URL` | Optional frontend API base URL. |

**Gemini is optional.** Without a Gemini API key, the application uses its rule-based fallback.

Never place PayPal credentials or the API token in frontend environment variables.

Without PayPal credentials, features other than final checkout can still work. Without the required API token, protected backend API requests are rejected.

### 4. Testing

Open PowerShell in the repository root.

Backend tests:

```powershell
cd backend

python -m pytest -q -rs
```

Frontend type checking:

```powershell
cd ..\frontend

npm run typecheck
```

Frontend production build:

```powershell
npm run build
```

Skipped tests must not be treated as passed tests. Resolve any skipped-test reasons before submission.

PayPal integration tests use a scripted test double. They demonstrate application behavior but do not independently establish successful real Sandbox checkout.

## Current PayPal Verification Status

As of November 12, 2026:

- PayPal Sandbox OAuth credentials were accepted.
- PayPal accepted a synthetic USD order-creation request.
- A Sandbox approval link was returned.
- The buyer did not approve that order.
- No payment capture was performed.

Therefore, OAuth and order creation have been tested, but **end-to-end payment has not been verified**.

Do not claim successful payment until a Sandbox buyer completes checkout and capture is confirmed in both IntentGuard and the Sandbox account.

No PayPal Live endpoint or live payment was used.

## PayPal Sandbox Manual Checkout

1. Visit https://developer.paypal.com/.
2. Open Apps & Credentials and select Sandbox.
3. Create or select a Sandbox app.
4. Copy its Client ID and Secret into `backend/.env`.
5. Locate or create a Sandbox Personal buyer account.
6. Restart the backend.
7. Unlock the application using the local API token.
8. Open PayPal Sandbox Checkout and select **Check Sandbox OAuth**.
9. Run **Scenario A: trusted purchase**.
10. Select **I approve this exact transaction**.
11. Open PayPal Checkout and select **Pay with PayPal Sandbox**.
12. Sign in using the Sandbox buyer account and approve the transaction.
13. Confirm `COMPLETED` in IntentGuard and the Sandbox account.
14. Open Audit & Receipt and download the Intent Integrity Receipt.
15. Run **Scenario B: malicious purchase** to demonstrate a blocked transaction.

The consent validity period defaults to 15 minutes.

Use Sandbox accounts only. Never use real customer payment details for testing.

## Troubleshooting

**Cannot reach the backend**

- Confirm that the backend server is running.
- Check the frontend API base URL.
- Verify that the backend is listening on port 8000.

**Checkout says credentials are missing**

- Configure both PayPal Sandbox credentials in `backend/.env`.
- Restart the backend.

**oauth_failed**

- Verify the Client ID and Secret.
- Ensure Sandbox credentials are used instead of Live credentials.

**Seller does not accept payments in the selected currency**

- Check the Sandbox Business seller's receiving-currency settings.
- Confirm that the seller supports the intended currency.
- Do not silently change the customer's intended currency.
- Retry using a compatible Sandbox seller and buyer.

**Currency is not enabled**

`PAYPAL_ALLOWED_CURRENCIES` is only the application's allowlist. It does not guarantee that the PayPal Sandbox seller accepts that currency.

**Consent expired**

Approve the same transaction again using the application's restart flow.

**PayPal returns to a blank page**

Check that `PAYPAL_RETURN_URL` matches the running frontend address.

## Security

- PayPal credentials must remain backend-only.
- Never commit real API keys, tokens or secrets.
- Rotate any previously exposed PayPal Sandbox Secret.
- Use a random API token of at least 32 characters.
- Do not expose this single-user prototype publicly with real credentials.
- Do not use PayPal Live credentials for testing.

For additional security information, see [SECURITY.md](SECURITY.md).

## Known Limitations

- PayPal Sandbox order creation was verified, but approval and capture were not completed.
- Automated payment tests use a scripted fake.
- Hash matching proves data integrity, not merchant honesty.
- Merchant claims are not independently verified.
- The prototype uses a local single-user bearer-token gate, not multi-user identity management.
- The audit chain cannot independently detect removal of the newest events unless its head hash is stored externally.
- Currency support depends on both the application allowlist and the Sandbox seller account.
- Gemini output quality has not been independently evaluated.

## Hackathon Materials

- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Demo Script](DEMO_SCRIPT.md)
- [Devpost Description](DEVPOST_DESCRIPTION.md)
- [Hackathon Changes](HACKATHON_CHANGES.md)
- [Submission Checklist](SUBMISSION_CHECKLIST.md)
- [MIT License](LICENSE)

---

**IntentGuard — Protecting the integrity of every AI-assisted purchase.**
