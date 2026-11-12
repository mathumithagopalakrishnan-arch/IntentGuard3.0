# Architecture

## Components
- **Frontend** (React/TS/Vite/Tailwind): thin client. It stores record IDs plus the local API bearer token in tab-scoped session storage. All decisions, amounts and states live in the backend database.
- **Backend** (FastAPI): `api/routes.py` maps HTTP to services. `services/service.py` holds intent, offer, transaction, consent and audit logic over SQLite. `services/paypal.py` is the PayPal Sandbox client. `services/payments.py` is the payment state machine. `services/chain.py`, `receipt.py`, `attacks.py`, `ai_explain.py`, `interpreter.py` provide the chain view, receipt, simulator and AI features.
- **Core** (`backend/app/core`, stdlib only): fingerprinting, validation, deterministic verification, threat scanner, drift, money conversion.
- **SQLite**: intents, offers, transactions, consents (with `expires_epoch`), payments, hash-chained audit_events. `apply_schema` upgrades older databases in place.

## Data flow
1. `POST /intents/interpret` (Gemini or fallback, untrusted, validated) -> `POST /intents` -> `POST /intents/{id}/confirm`.
2. `POST /offers` scans merchant text. `POST /transactions` stores the cart and runs `verify()`; the server recomputes the total.
3. `POST /transactions/{id}/consent` re-verifies and stores a consent with the transaction fingerprint and an expiry.
4. `POST /transactions/{id}/checkout` re-checks consent and fingerprint, stores a payment row, then creates the PayPal order from stored data. If creation times out, a retry uses the same PayPal request id and re-checks the consent fingerprint and amount before another request.
5. The buyer approves on PayPal and returns to `/checkout/return/{tid}?token=ORDER`. The frontend calls `POST /transactions/{id}/capture` with only the order id.
6. The backend fetches the order from PayPal, checks status, amount, currency and custom_id, atomically consumes the consent, captures, verifies the capture response and records the result. If a capture response is lost, recovery first re-fetches and revalidates the completed order before recording its capture.

## Verification process
`verify(intent, offer, cart)` runs about 14 deterministic checks (items exist, cart price = offer price, stated total = server total, currency, budget, quantity, category, prohibited terms, recurring billing, shipping, disclosures, high-severity threats) plus intent integrity and confirmation. Any failure means BLOCKED. The transaction fingerprint is SHA-256 over canonical JSON of intent fingerprint + offer + cart + total.

## Payment lifecycle
`CREATING -> ORDER_CREATED -> CAPTURING -> COMPLETED`, with `CAPTURE_PENDING`, `FAILED`, `CANCELLED`, `EXPIRED`. Illegal transitions raise. Network calls run outside database transactions. Retries reuse the stored `PayPal-Request-Id`, so PayPal deduplicates. A timeout during capture leaves `CAPTURING`; a retry first reads the order and verifies its transaction binding, amount and currency before recording an already-completed capture or retrying capture.

## Trust boundaries
| Zone | Trust |
|---|---|
| Customer's words, merchant content, cart sent by client | Untrusted data |
| Gemini output | Untrusted until schema-validated; never authorizes |
| Backend verification, consent and payment code | Authority |
| PayPal API responses | Authoritative for payment status, but amount/currency/custom_id are still compared with what we stored |
| Browser | Holds no PayPal credentials; it holds the local bearer token for the current tab and cannot authorize or alter server-calculated amounts |

## Design decisions
- Redirect-based PayPal approval (no JS SDK) so no client id or secret reaches the browser and the whole flow is server-verified.
- Consent is consumed at capture start, not at order creation, so an order that never gets approved does not burn the approval.
- Stdlib `urllib` for PayPal so the integration can be tested with a scripted transport and no extra dependency.
- The Attack Simulator runs on a temporary in-memory database through the real services, so demos never pollute real data.
- CORS allows only the configured frontend origins (`CORS_ORIGINS`); API methods are limited to GET/POST and the required content-type and authorization headers. Credentials are not enabled for cross-origin requests.
- Every `/api` endpoint requires a configured bearer token (`INTENTGUARD_API_TOKEN`, at least 32 characters), compared in constant time. The UI prompts for it and keeps it in `sessionStorage`; it is not placed in a `VITE_` variable. The API fails closed when the token is unset.
- `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` are backend-only. The browser receives only configuration status and the Sandbox approval URL.
