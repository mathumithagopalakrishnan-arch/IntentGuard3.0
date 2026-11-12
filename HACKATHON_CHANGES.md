# Changes made for the PayPal AI Hackathon

The project existed before the Submission Period (Oct 1, 2026). The list below describes what was added or changed in the hackathon work, based on the file differences between the uploaded `intentguard-3_0-final.zip` and the current code. **Before submitting, confirm the dates against your own git history; this document does not claim specific commit dates.**

## Existing before (preserved)
Intent Passport and SHA-256 fingerprint, about 14 deterministic checks, threat scanner with Unicode normalization, consent binding, hash-chained audit log, rate limiting, security headers, 10 synthetic scenarios, 7 screens, about 25 endpoints, 95 tests. Payments were disabled (`payments_enabled` hardcoded false).

## Added
- **PayPal Sandbox integration** (`services/paypal.py`): OAuth, Orders v2 create/get/capture, sandbox-only URL enforcement, idempotent request ids, injectable transport.
- **Payment state machine and persistence** (`services/payments.py`, new `payments` table): order creation from the verified server total, authoritative order checks before capture, duplicate and retry handling, cancel/abandon.
- **Consent lifecycle fixes**: real expiry (`expires_epoch`, in-place migration), atomic one-time consumption connected to the payment flow (previously unused), invalidation when the fingerprint changes.
- **Intent-to-Payment Integrity Chain** (`services/chain.py`) and **Intent Integrity Receipt** (`services/receipt.py`).
- **Intent Drift** table (`core/drift.py`).
- **Attack Simulator** (`services/attacks.py`, 8 attacks) and UI.
- **AI**: clarification questions in interpretation, broader fallback parsing, evidence-grounded explanations with schema validation and a labelled Gemini path (`services/ai_explain.py`).
- **Frontend**: Home with guided Scenario A/B, PayPal Checkout, return and cancel pages, drift and explanation panels, chain view, payments table, receipt download, Attack Simulator. Existing pages were extended, not replaced.
- **Health**: `payments_enabled` now reflects Sandbox configuration; `/api/paypal/status`.
- **Tests**: regression coverage for client, payments, consent, concurrency, audit, receipt, chain, AI validation, attacks, migration and authenticated HTTP endpoints. The current suite has 168 passing tests; PayPal network behavior is simulated and no live capture is implied.
- **Docs and license**: README, ARCHITECTURE, SECURITY, DEMO_SCRIPT, DEVPOST_DESCRIPTION, MIT LICENSE, updated `.env.example`.

## Not changed
Original tests were kept. Existing API response shapes were extended with new keys only.
