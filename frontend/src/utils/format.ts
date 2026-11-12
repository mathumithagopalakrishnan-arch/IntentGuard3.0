export const money = (minor: number | null | undefined, cur: string) =>
  minor == null ? "—" : new Intl.NumberFormat("en", { style: "currency", currency: cur }).format(minor / 100);
export const when = (iso: string) => new Date(iso).toLocaleString();
export const toMinor = (major: string): number => Math.round(parseFloat(major) * 100);
export const WHY: Record<string, string> = {
  ignore_instructions: "Merchant text tries to override the rules an AI shopping agent follows.",
  role_override: "Merchant text tries to give the AI a new role or hidden instructions.",
  auto_approve: "Merchant text tries to make an AI approve or complete a payment. Only a human may approve.",
  skip_verification: "Merchant text tells the system to skip or switch off safety checks. Real sellers have no reason to.",
  hide_from_user: "Merchant text asks that the user is not told something. Honest sellers do not do this.",
  hidden_renewal: "The offer may charge again later. This is how surprise subscriptions work.",
  free_trial: "A free trial can turn into paid billing. Check what happens when it ends.",
  extra_fee_words: "Extra fees may appear at checkout that are not in the shown price.",
  urgency: "Pressure wording tries to rush your decision.",
};
export const CHECK_LABEL: Record<string, string> = {
  cart_items_exist: "Cart items exist in the offer", cart_price_matches_offer: "Cart prices match the offer",
  claimed_total_matches: "Merchant's stated total matches the server's total", currency_matches: "Currency matches your intent",
  within_budget: "Total is within your budget", quantity_ok: "Quantity is within your limit", category_matches: "Product matches what you asked for",
  no_prohibited_terms: "No prohibited terms", recurring_billing_allowed: "No unapproved recurring billing",
  shipping_within_limit: "Shipping within your limit", required_disclosures_present: "Required disclosures are present",
  no_high_threats: "No high-severity threats", intent_integrity: "Intent Passport is unchanged", intent_confirmed: "You confirmed the Intent Passport",
};
export const shortHash = (h: string | null | undefined) => (h ? `${h.slice(0, 10)}…` : "—");
export const consentLabel = (c: { decision: string } | null, valid: boolean) =>
  !c ? "none" : c.decision === "REJECTED" ? "rejected" : valid ? "granted" : "granted (no longer valid)";
export const PAYMENT_LABEL: Record<string, string> = {
  CREATING: "Creating the PayPal order", ORDER_CREATED: "Waiting for you to approve at PayPal", CAPTURING: "Capturing the payment",
  CAPTURE_PENDING: "Capture pending at PayPal", COMPLETED: "Payment completed (Sandbox)", FAILED: "Payment failed", CANCELLED: "Payment cancelled", EXPIRED: "Approval expired",
};
export const paymentTone = (s: string): "green" | "amber" | "red" | "slate" | "blue" =>
  s === "COMPLETED" ? "green" : s === "FAILED" || s === "EXPIRED" ? "red" : s === "CANCELLED" ? "slate" : "amber";
export const downloadJson = (name: string, data: unknown) => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
};
