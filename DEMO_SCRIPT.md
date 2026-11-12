# YouTube demo plan (2:50 maximum)

## Title and description

**Title:** IntentGuard: Protecting AI Shopping with Intent-to-Payment Verification

**Description:** IntentGuard is an independent agentic-commerce security prototype. It turns a customer's request into a confirmed Intent Passport, checks a synthetic merchant offer with deterministic rules, requires one-time human consent, and records the result in a verifiable audit chain. PayPal is Sandbox-only. Sandbox OAuth and synthetic USD order creation were verified on 2026-11-12, but buyer approval and capture were not; no successful payment is claimed. All demo offers are synthetic.

## Recording setup

- Configure the local API token in `backend/.env`, then start the backend and frontend and unlock the UI without recording the token. Use only synthetic offers and PayPal Sandbox accounts.
- Capture the actual application at 1080p, hide unrelated desktop notifications, and do not show `.env`, credentials, personal information, or a real PayPal account.
- Use a fresh browser session and rehearse the flow. Do not edit records or receipts to create a desired outcome.
- Use screen recording and clear narration; no copyrighted music or third-party assets without permission.

## Timestamped storyboard and exact narration

| Time | Screen and cursor actions | Spoken script |
|---|---|---|
| 0:00–0:15 | Home. Point to the Sandbox and synthetic-data labels. | "AI agents can shop for us, but a merchant page or a changed cart can alter what we meant to buy. IntentGuard checks the transaction against the customer's intent." |
| 0:15–0:35 | Open Intent. Enter: "Wireless headphones under 50 US dollars. No subscriptions and no refurbished items." Review, edit if needed, confirm. | "The request becomes an editable Intent Passport. The customer confirms the rules, and IntentGuard fingerprints them with SHA-256." |
| 0:35–0:55 | Open Offers, select the legitimate synthetic offer, set the cart and verify. | "Merchant content is treated as untrusted. The backend recomputes the total and applies deterministic checks. AI does not approve a payment." |
| 0:55–1:10 | Show Integrity, drift rows, verification result and chain. | "Here the price, currency, quantity and other protected terms match. Each stage is bound into the integrity chain." |
| 1:10–1:20 | Open Consent and approve the exact transaction. | "The customer gives explicit consent to this exact transaction. Consent expires and can be used only once." |
| 1:20–1:50 | Open Checkout; show server-calculated amount and Sandbox status. If eligible, choose Pay with PayPal Sandbox, use a Sandbox buyer, and approve. | "Checkout uses the server-calculated amount. After a real Sandbox approval, the backend re-fetches the PayPal order, checks its binding and amount, and only then requests capture." |
| 1:50–2:05 | Branch A: show actual `COMPLETED` state and matching Sandbox activity, then receipt. Branch B if still blocked: show `ORDER_CREATED` and the PayPal-hosted currency rejection without implying approval; return to IntentGuard and show that no capture is recorded. | **A:** "This Sandbox payment is complete; the status is confirmed here and in the Sandbox account. The receipt records the result." **B:** "This Sandbox seller does not accept the transaction currency. The order was created, but approval and capture did not complete. This is an account-side blocker, not a successful payment." |
| 2:05–2:25 | Start a new demo transaction, select Scenario B with the hidden subscription, verify and show BLOCKED plus the subscription drift. | "Now the offer hides a monthly subscription. IntentGuard blocks it before checkout, because the customer did not authorize recurring billing." |
| 2:25–2:42 | Open Attack Simulator; run all eight attacks and show their results. | "The simulator exercises eight synthetic attacks, including price and quantity changes, prompt injection, currency mismatch, post-approval changes and replay. These simulations never call PayPal." |
| 2:42–2:50 | Show audit-chain verification, then Home. | "IntentGuard: verify the intent before an AI agent spends." |

Use Branch A only after a genuine Sandbox capture is confirmed both in the app and in the Sandbox account. Otherwise use Branch B and state plainly that the approval/capture is unavailable. Do not substitute an older receipt or another run as if it belongs to the current transaction.

## Chapters

- 0:00 The agentic-commerce problem
- 0:15 Intent Passport
- 0:35 Deterministic verification
- 1:10 Human consent and Sandbox checkout
- 1:50 Payment status or current Sandbox limitation
- 2:05 Blocking a malicious subscription
- 2:25 Attack Simulator and audit chain

## Thumbnail concept

Use an original screenshot of IntentGuard's integrity chain with a green verified stage and a clearly labelled red blocked subscription stage. Add short title text: **"Did the agent buy what you meant?"** Do not use a fabricated PayPal success screen or unlicensed logos.

## Final recording checklist

- [ ] Duration is below three minutes; narration matches the screens.
- [ ] Any `COMPLETED` claim is confirmed in both IntentGuard and the Sandbox account.
- [ ] If the seller currency error persists, use Branch B and label the payment as unavailable / not captured.
- [ ] No credential, buyer password, private data, real-money payment, or fabricated screenshot is visible.
- [ ] All merchants are identified as synthetic; PayPal is labelled Sandbox-only.
- [ ] Check the event's current video, branding, privacy, and third-party asset rules before publishing.
