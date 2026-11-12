# Security

IntentGuard is an independent hackathon prototype. It has had no external security review or certification.

## Threat model
Attackers considered: a malicious merchant (hidden subscription, fees, text that commands an AI agent), a manipulated or buggy shopping agent (changed price, quantity, currency), and a party that replays or alters an approval.
Not covered: a compromised backend host or database owner, stolen Sandbox credentials, multi-user authentication, denial of service beyond simple rate limits, and merchant honesty.

## Controls
- **Verification is deterministic.** No AI decides PASS/BLOCK. Money is integer minor units; the server recomputes totals.
- **Prompt-injection firewall.** Merchant text is normalized (NFKC, zero-width removal, whitespace collapse) and scanned by fixed rules; high-severity findings block.
- **Consent.** Bound to the transaction fingerprint, expires (`CONSENT_TTL_SECONDS`), decided once (UNIQUE per transaction) and consumed once (atomic `UPDATE ... WHERE used=0` in the same write transaction that starts capture). A changed offer, cart or intent changes the fingerprint and voids consent.
- **Payment authorization.** The backend never trusts a client amount. It re-fetches the order from PayPal and requires APPROVED, matching amount, currency and `custom_id`, and a still-verified transaction.
- **PayPal safety.** Only `api-m.sandbox.paypal.com` / `api.sandbox.paypal.com` over HTTPS is accepted; live hosts and look-alikes are refused. Secrets are read from backend environment variables and are never logged or returned. `PayPal-Request-Id` gives idempotent retries. A unique index prevents one order being attached to two payments.
- **Audit.** Hash-chained events; `/api/audit/verify` recomputes the chain. Refusals are recorded.
- **HTTP.** Strict Pydantic models (`extra=forbid`), rate limits on costly endpoints, security headers, `Cache-Control: no-store` on the API.

## Limitations
- Anyone who can write the SQLite file and recompute hashes can rewrite history; store the audit head hash elsewhere for stronger guarantees.
- The API requires a single-user bearer token configured as `INTENTGUARD_API_TOKEN` (at least 32 characters); requests are compared in constant time. The UI holds it in tab-scoped `sessionStorage`, and the backend fails closed if it is unset. This is local single-user protection, not multi-user identity, role-based access, or a substitute for HTTPS on a remote deployment. Bind the backend to localhost and do not expose it publicly.
- Gemini may mis-extract an intent; that is why the customer edits and confirms the Passport, and why rules, not the model, enforce it.
- Scanner rules can miss novel wording; numeric checks do not depend on wording.
- Sandbox only. Moving to live PayPal needs a security review, authentication, webhook handling and a different threat model.

## Credential rotation and Sandbox setup
- If a Sandbox credential may have been exposed, rotate/regenerate the secret for the Sandbox app in the PayPal Developer Dashboard before further checkout testing.
- Replace `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` only in `backend/.env`, then restart the backend. Do not paste credentials into chat or put them in frontend `VITE_` variables.
- Configure a separate random `INTENTGUARD_API_TOKEN` of at least 32 characters in `backend/.env`; enter it only in the local app unlock screen. The browser stores it in session storage for the current tab.
- The `/api/paypal/status?probe=true` OAuth probe reports credential acceptance, not the seller account's ability to receive a particular currency.
- A PayPal-hosted message that the seller does not accept USD occurs after order creation and does not prove a capture. Check the Sandbox Business account's receiving-currency settings or use a compatible Sandbox seller. Keep the customer's currency intent unchanged; do not report success without a verified `COMPLETED` capture.
- The audit chain is not anchored to an independent external service. A party able to rewrite the SQLite database can recompute its hashes; choose and configure a trusted append-only anchor before relying on it as independent evidence.

## GitHub and repository secret protection
- The local `.gitignore` excludes `.env` files (except `.env.example`), database files, virtual environments, build output, and dependency directories. This is a local safeguard; it does not remove a secret already committed to Git history.
- The workspace used for this readiness check has no `.git` metadata or `.github` configuration. Remote GitHub secret-scanning settings, push protection, repository history, and any remote secrets could not be inspected or verified here.
- Before publishing, verify that GitHub secret scanning and push protection are enabled where available, and scan the complete repository history with an approved secret scanner. Never treat a clean working tree or `.gitignore` as proof that history is clean.
- If a credential was committed or exposed, revoke/rotate it first, remove it from repository history using the repository's approved process, and verify the replacement remains outside source control.

Report issues by opening an issue in the repository.
