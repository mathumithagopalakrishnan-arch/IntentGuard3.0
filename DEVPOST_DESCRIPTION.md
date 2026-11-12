# IntentGuard: The Trust Layer for Agentic Commerce

*Independent hackathon prototype. PayPal Sandbox only (test money). All merchants are synthetic. Not endorsed by PayPal.*

## Inspiration
AI shopping agents are starting to buy for people. But the customer's instructions pass through many hands: the agent, a merchant's product page, a generated cart. A hidden subscription or a line of text aimed at the agent can change what gets paid. Fraud scores do not ask the key question: is this the transaction the customer meant?

## What it does
IntentGuard builds an **Intent-to-Payment Integrity Chain**. The customer's request becomes an editable, confirmed Intent Passport (SHA-256 fingerprint). The merchant offer is treated as untrusted data. The server recomputes the cart total and runs deterministic checks (price, quantity, currency, budget, subscriptions, shipping, disclosures, prompt injection). Only a verified transaction can be approved by the customer, and the approval is bound to the exact transaction fingerprint, expires and works once. Then a PayPal Sandbox order is created from the verified total and captured only after PayPal reports it approved. Every step lands in a hash-chained audit log and a downloadable Intent Integrity Receipt. An Attack Simulator lets anyone try eight attacks and see which rule stops each.

## How we built it
React + TypeScript + Vite + Tailwind; FastAPI; SQLite; Gemini; PayPal Orders v2. A persistent payment state machine handles retries, timeouts, cancellations and duplicate requests. The PayPal client is dependency-free and testable with a scripted transport.

## How PayPal is integrated
PayPal is the last, gated stage of the chain, not a decorative button: OAuth, order creation from the server-computed total, buyer approval on PayPal Sandbox, re-fetching the authoritative order, checking status/amount/currency/transaction id and consent, capture with idempotency keys, and verification of the capture response. Live endpoints are refused in code.

## How AI is used
Gemini interprets the customer's sentence into structured constraints and clarification questions, and can write evidence-grounded explanations. Its output is untrusted: schema-validated, capped, and required to cite real evidence ids. A rule-based fallback keeps everything working without Gemini. No AI model can approve or capture a payment.

## Innovation
The difference from a risk dashboard is the binding: intent, offer, cart, verification, consent and payment are hashed and linked, so a change anywhere voids authorization before money moves.

## Impact
For shoppers: delegation without surprise charges. For agentic-commerce platforms: verifiable proof of what was authorized. For merchants: provable, intent-matched checkouts.

## Challenges
Making consent truly single-use and safe under concurrency; keeping refusals in the audit log; handling PayPal timeouts without double capture; keeping AI helpful but never authoritative.

## What makes it different
Deterministic authority, an end-to-end verifiable chain, and a simulator that reproducibly blocks malicious changes. PayPal Sandbox approval and capture are implemented and covered with a scripted test double, but the current seller/currency account combination has not completed a live Sandbox capture; no successful payment is claimed.

## Updates after Oct 1, 2026
See HACKATHON_CHANGES.md in the repository.

## Run and test (for judges)
Setup, local API-token configuration, Sandbox buyer instructions, current currency limitation and troubleshooting are in [README.md](README.md). Automated payment tests use a fake PayPal transport and are not a live payment test.
