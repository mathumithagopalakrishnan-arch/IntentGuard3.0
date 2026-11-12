import type * as T from "../types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000/api";

async function call<R>(method: "GET" | "POST", path: string, body?: unknown): Promise<R> {
  let res: Response;
  try {
    const headers: Record<string, string> = {};
    if (body) headers["Content-Type"] = "application/json";
    const token = window.sessionStorage.getItem("intentguard.apiToken");
    if (token) headers.Authorization = `Bearer ${token}`;
    res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new Error(`Cannot reach the backend at ${BASE}. Is it running? (uvicorn app.main:app --reload)`);
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: { loc?: unknown[]; msg: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch { /* keep default message */ }
    throw new Error(msg);
  }
  return res.json() as Promise<R>;
}

export const api = {
  health: () => call<T.Health>("GET", "/health"),
  stats: () => call<T.Stats>("GET", "/stats"),
  scenarios: () => call<T.Scenarios>("GET", "/demo/scenarios"),
  interpret: (text: string) => call<T.Interpretation>("POST", "/intents/interpret", { text }),
  createIntent: (instruction: string, constraints: T.Constraints, source: T.IntentSource) => call<T.Intent>("POST", "/intents", { instruction, constraints, source }),
  getIntent: (id: string) => call<T.Intent>("GET", `/intents/${id}`),
  confirmIntent: (id: string) => call<T.Intent>("POST", `/intents/${id}/confirm`),
  verifyFingerprint: (id: string) => call<T.FingerprintCheck>("POST", `/intents/${id}/verify-fingerprint`),
  createOffer: (offer: T.Offer) => call<T.OfferRecord>("POST", "/offers", offer),
  getOffer: (id: string) => call<T.OfferRecord>("GET", `/offers/${id}`),
  analyze: (text: string) => call<{ findings: T.Threat[] }>("POST", "/threats/analyze", { text }),
  createTransaction: (intent_id: string, offer_id: string, cart: T.CartLine[]) => call<T.Transaction>("POST", "/transactions", { intent_id, offer_id, cart }),
  getTransaction: (id: string) => call<T.Transaction>("GET", `/transactions/${id}`),
  verifyTransaction: (id: string) => call<T.Transaction>("POST", `/transactions/${id}/verify`),
  grantConsent: (id: string) => call<T.Consent>("POST", `/transactions/${id}/consent`),
  rejectConsent: (id: string) => call<T.Consent>("POST", `/transactions/${id}/consent/reject`),
  audit: (limit = 100) => call<T.AuditPage>("GET", `/audit/events?limit=${limit}`),
  auditPage: (q: { limit?: number; offset?: number; type?: string; transaction_id?: string }) => {
    const p = new URLSearchParams();
    if (q.limit) p.set("limit", String(q.limit));
    if (q.offset) p.set("offset", String(q.offset));
    if (q.type) p.set("type", q.type);
    if (q.transaction_id) p.set("transaction_id", q.transaction_id);
    return call<T.AuditPage>("GET", `/audit/events?${p.toString()}`);
  },
  auditTypes: () => call<{ types: string[] }>("GET", "/audit/types"),
  auditVerify: () => call<T.ChainReport>("GET", "/audit/verify"),
  auditFor: (id: string) => call<{ events: T.AuditEvent[] }>("GET", `/audit/transactions/${id}`),
  transactions: (limit = 50) => call<{ transactions: T.TxSummary[] }>("GET", `/transactions?limit=${limit}`),
  intents: (limit = 5) => call<{ intents: T.Intent[] }>("GET", `/intents?limit=${limit}`),
  consents: (limit = 50) => call<{ consents: T.ConsentRecord[] }>("GET", `/consents?limit=${limit}`),
  // ---- PayPal Sandbox checkout (all amounts are computed by the backend; the browser sends only an order id it got back from PayPal) ----
  paypalStatus: (probe = false) => call<T.PayPalStatus>("GET", `/paypal/status${probe ? "?probe=true" : ""}`),
  checkout: (id: string) => call<T.Payment>("POST", `/transactions/${id}/checkout`),
  capture: (id: string, order_id: string) => call<T.Payment>("POST", `/transactions/${id}/capture`, { order_id }),
  checkoutCancelled: (id: string) => call<T.Payment>("POST", `/transactions/${id}/checkout/cancelled`),
  checkoutAbandon: (id: string) => call<T.Payment>("POST", `/transactions/${id}/checkout/abandon`),
  payments: (limit = 50) => call<{ payments: T.PaymentRow[] }>("GET", `/payments?limit=${limit}`),
  chain: (id: string) => call<T.Chain>("GET", `/transactions/${id}/chain`),
  receipt: (id: string) => call<T.Receipt>("GET", `/transactions/${id}/receipt`),
  explain: (id: string) => call<T.Explanation>("POST", `/transactions/${id}/explain`),
  attacks: () => call<{ label: string; attacks: T.AttackInfo[] }>("GET", "/attacks"),
  runAttack: (key: string) => call<T.AttackResult>("POST", `/attacks/${key}/run`),
};
