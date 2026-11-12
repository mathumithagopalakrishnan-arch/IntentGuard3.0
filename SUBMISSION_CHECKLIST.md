# PayPal AI Hackathon Submission Checklist

Complete and verify these items before submitting. A checked box means the action was actually completed, not merely that the feature exists.

## Sandbox and configuration
- [ ] Configure a random `INTENTGUARD_API_TOKEN` (at least 32 characters) in `backend/.env`; unlock the UI with it and keep it out of frontend env files.
- [ ] Create/use a PayPal **Sandbox** app and Sandbox buyer account only.
- [ ] Put `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` only in `backend/.env`; never paste or commit them.
- [ ] If Sandbox credentials were ever exposed, rotate the app secret in PayPal Developer Dashboard, replace `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` in `backend/.env`, then restart the backend.
- [ ] Confirm `PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com` and the intended `PAYPAL_ALLOWED_CURRENCIES`.
- [ ] Set `PAYPAL_RETURN_URL` and `PAYPAL_CANCEL_URL` to the frontend address used for the demo.
- [ ] Set `CORS_ORIGINS` to the exact local frontend origin(s); do not use a wildcard.
- [ ] Confirm no credentials or private environment files are included in screenshots, logs, or the submission.
- [ ] Unlock the local UI and use **Check Sandbox OAuth** on PayPal Sandbox Checkout; this verifies OAuth only and does not disclose credentials or establish seller currency support.
- [ ] Confirm the Sandbox Business seller accepts the intended currency; successful OAuth does not verify receiving-currency support.

## Verification and tests
- [x] Run `python -m pytest -q -rs` from `backend/`; investigate every skip or failure. Latest local run: 170 passed, 0 skipped.
- [x] Confirm HTTP tests ran. A skipped HTTP test is not a pass; latest local run had 0 skips.
- [x] Run `npm run typecheck` and `npm run build` from `frontend/`; both passed in the latest local run.
- [x] Confirmed direct PayPal Sandbox OAuth and synthetic USD order creation on 2026-11-12; the response included a Sandbox approval link.
- [ ] Complete buyer approval and capture with Sandbox test money, then confirm the result in both IntentGuard and the Sandbox account. Until then, approval and capture are unverified. Mocked tests do not establish that PayPal accepts a real Sandbox request.
- [ ] Confirm a successful Sandbox run shows `COMPLETED`, expected currency and amount in IntentGuard and in the Sandbox account.
- [ ] Exercise a cancelled approval and confirm no capture was recorded.
- [ ] If the PayPal-hosted approval page rejects the seller currency, record it as an account-side blocker; do not change the customer's intent or claim a capture.
- [ ] Run Scenario B and the attack simulator; confirm blocked cases do not create or capture a PayPal order.
- [ ] Check duplicate/retry behavior, the transaction receipt, and audit-chain verification.

## Source control and secrets
- [ ] Confirm `.env` files, local databases, credentials, and generated artifacts are not staged or committed; keep only the sanitized `.env.example`.
- [ ] In the GitHub repository settings, verify secret scanning and push protection are enabled where available.
- [ ] Scan the full Git history before publishing. `.gitignore` does not protect secrets already present in prior commits.
- [ ] If any credential was exposed or committed, revoke/rotate it and follow the approved process to remove it from history before submission.

## Demo and submission
- [ ] Rehearse the [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) and keep the recording within the current event limit.
- [ ] Use only synthetic merchant data and Sandbox accounts; do not make real-money transactions.
- [ ] Capture the actual final UI state. Do not claim a payment succeeded unless it displays as completed and the Sandbox account agrees.
- [ ] Review the current event rules for trademarks, third-party assets, licenses, privacy, eligibility, and required submission fields.
- [ ] Verify the repository, Devpost text, architecture, setup instructions, and demo script agree with what was actually tested.
- [ ] Record any untested steps or known limitations in the submission notes.

## Known prototype limits
- The bearer token is a local single-user gate, not multi-user identity or role-based authorization; do not expose this prototype as a public payment service.
- The audit chain is tamper-evident but not externally anchored; a database owner could rewrite the database and recompute it.
- Sandbox-only test results are not evidence of live payment readiness. Do not switch to PayPal Live for this submission.
