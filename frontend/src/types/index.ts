// Mirrors backend/app/services/service.py and schemas/models.py exactly.
export interface Constraints {
  category: string; max_total: number; currency: string; max_quantity: number;
  allow_subscription: boolean; prohibited_terms: string[]; max_shipping: number | null; required_disclosures: string[];
}
export type IntentSource = "gemini" | "fallback_rules" | "user_edited";
export interface Interpretation { constraints: Constraints; source: "gemini" | "fallback_rules"; explanation: string; clarifications?: string[] }
export interface Intent { id: string; instruction: string; constraints: Constraints; fingerprint: string; source: string;
  status: "DRAFT" | "CONFIRMED"; created_at: string; confirmed_at: string | null }
export interface FingerprintCheck { intent_id: string; stored: string; recomputed: string; intact: boolean; note: string }
export interface OfferItem { id: string; name: string; description: string; category: string; unit_price: number; recurring: boolean }
export interface Offer { merchant: string; currency: string; shipping: number; tax: number; disclosures: string[]; claimed_total: number | null;
  recurring_billing: boolean; description: string; terms: string; items: OfferItem[]; synthetic: boolean; label: string }
export interface Threat { category: string; severity: "high" | "medium" | "low"; rule: string; source: string; evidence: string; origin: string }
export interface OfferRecord { id: string; offer: Offer; threats: Threat[]; data_origin: string }
export interface Scenarios { label: string; default_intent_hint: string; scenarios: Record<string, { offer: Offer; cart_price: number; expected: "VERIFIED" | "BLOCKED" }> }
export interface CartLine { item_id: string; qty: number; unit_price: number }
export interface Check { id: string; passed: boolean; severity: string; detail: string }
export interface Verification { decision: "VERIFIED" | "BLOCKED"; checks: Check[]; threats: Threat[]; server_total: number | null; transaction_fingerprint: string }
export interface Consent { id: string; decision: "GRANTED" | "REJECTED"; fingerprint: string; used: boolean; created_at: string;
  expires_epoch?: number | null; state?: ConsentState; seconds_left?: number | null }
export type ConsentState = "NONE" | "REJECTED" | "ACTIVE" | "EXPIRED" | "CONSUMED";
export interface DriftRow { attribute: string; intent: string; transaction: string; drifted: boolean; rule: string; evidence: string }
export type PaymentState = "CREATING" | "ORDER_CREATED" | "CAPTURING" | "CAPTURE_PENDING" | "COMPLETED" | "FAILED" | "CANCELLED" | "EXPIRED";
export interface Payment { id: string; transaction_id: string; state: PaymentState; amount_minor: number; currency: string; paypal_order_id: string | null; paypal_status: string | null;
  capture_id: string | null; capture_status: string | null; approve_url: string | null; error_code: string | null; error_message: string | null; attempts: number;
  created_at: string; updated_at: string; sandbox: boolean }
export interface PaymentRow extends Payment { merchant: string; synthetic: boolean }
export interface Transaction { id: string; intent_id: string; offer_id: string; cart: CartLine[]; status: string; created_at: string;
  verification: Verification; drift: DriftRow[]; consent: Consent | null; consent_valid: boolean; consent_state: ConsentState; payment: Payment | null }
export interface ChainStage { n: number; key: string; title: string; status: "ok" | "warn" | "blocked" | "broken" | "pending"; hash: string | null; link: string | null; detail: string }
export interface Chain { transaction_id: string; stages: ChainStage[]; bindings: { name: string; ok: boolean }[]; intact: boolean; head_link: string | null; note: string }
export interface Explanation { source: "gemini" | "rule_based"; label: string; decision: string; summary: string; fallback_reason?: string;
  evidence: { id: string; kind: string; detail: string }[]; inferred_risks: { evidence_id: string; text: string }[]; uncertainty: string[]; drift: DriftRow[] }
export interface AttackInfo { key: string; title: string; story: string; expected_rules: string[]; why: string }
export interface AttackResult extends AttackInfo { blocked: boolean; expected_rule_hit: boolean; detected_by: { rule: string; detail: string }[]; threats: Threat[];
  steps: string[]; payment_captured: boolean; synthetic: boolean; note: string }
export interface PayPalStatus { mode: string; configured: boolean; base_url_is_sandbox: boolean; ready: boolean; currencies: string[]; return_url: string;
  probe?: { oauth_ok: boolean; message: string } }
export interface Receipt { receipt: Record<string, unknown>; receipt_sha256: string }
export interface AuditEvent { id: number; ts: string; type: string; intent_id: string | null; transaction_id: string | null; detail: Record<string, unknown>; hash: string | null; prev_hash: string | null }
export interface AuditPage { events: AuditEvent[]; total: number; limit: number; offset: number }
export interface ChainReport { intact: boolean; events: number; chained: number; legacy_unchained: number; head: string | null; note?: string; first_broken_id?: number; reason?: string }
export interface TxSummary { id: string; intent_id: string; offer_id: string; created_at: string; status: string; decision: "VERIFIED" | "BLOCKED"; merchant: string; synthetic: boolean;
  currency: string; server_total: number | null; failed_checks: string[]; consent: Consent | null; consent_valid: boolean; consent_state?: ConsentState; payment_state?: PaymentState | null }
export interface ConsentRecord extends Consent { transaction_id: string; merchant: string; currency: string; server_total: number | null; still_valid: boolean }
export interface Health { status: string; database: string; gemini_configured: boolean; payments_enabled: boolean; demo_mode: boolean; paypal?: PayPalStatus; version?: string }
export interface Stats { intents: number; intents_confirmed: number; offers: number; transactions: number; verified: number; blocked: number; awaiting_consent: number;
  consents_granted: number; consents_rejected: number; threat_scans: number; audit_events: number; payments_completed?: number }
