import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import { useAction, useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import TxPicker from "../components/TxPicker";
import { ChainView } from "../components/Insight";
import { Badge, Btn, ErrorBox, Loading, Mono, Need, Page, Panel, Row } from "../components/ui";
import { PAYMENT_LABEL, downloadJson, money, paymentTone } from "../utils/format";

export default function Checkout() {
  const { transactionId } = useSession();
  const tx = useLoad(transactionId ? () => api.getTransaction(transactionId) : null, [transactionId]);
  const pp = useLoad(() => api.paypalStatus(), []);
  const act = useAction();
  const [oauthProbe, setOauthProbe] = useState<{ ok: boolean; message: string } | null>(null);
  const t = tx.data, p = t?.payment ?? null;
  const offer = useLoad(t ? () => api.getOffer(t.offer_id) : null, [t?.offer_id]);
  const cur = offer.data?.offer.currency ?? "USD";
  const canStart = !!t && t.consent_state === "ACTIVE" && t.consent_valid && t.verification.decision === "VERIFIED" && !p && !!pp.data?.ready && oauthProbe?.ok !== false;

  const start = () => act.go(async () => {
    if (!t) return;
    const pay = await api.checkout(t.id);
    if (pay.approve_url) window.location.assign(pay.approve_url); // PayPal Sandbox approval page
    else tx.reload();
  });
  const resume = () => { if (p?.approve_url) window.location.assign(p.approve_url); };
  const abandon = () => act.go(async () => { if (t) { await api.checkoutAbandon(t.id); tx.reload(); } });
  const receipt = () => act.go(async () => { if (t) { const r = await api.receipt(t.id); downloadJson(`intentguard-receipt-${t.id.slice(0, 8)}.json`, r); } });
  const checkSandbox = () => act.go(async () => {
    const status = await api.paypalStatus(true);
    setOauthProbe({ ok: status.probe?.oauth_ok ?? false, message: status.probe?.message ?? "PayPal Sandbox returned no OAuth result." });
  });

  return (
    <Page title="PayPal Sandbox Checkout" intro="The PayPal order is created on the server from the verified total. You approve it on PayPal's Sandbox page with a Sandbox buyer account. Only after PayPal itself reports the order as approved does the backend capture it. Test money only: no real payment is made.">
      <TxPicker />
      {!transactionId && <Need what="No transaction yet." to="/offers" label="Choose an offer and cart" />}
      {transactionId && tx.loading && !t && <Loading />}{transactionId && <ErrorBox msg={tx.error} />}<ErrorBox msg={act.error} />
      <Panel title="PayPal Sandbox status" action={<Badge tone={oauthProbe?.ok ? "green" : "amber"}>{oauthProbe?.ok ? "Sandbox OAuth verified" : pp.data?.ready ? "credentials configured; not verified" : "not configured"}</Badge>}>
        {pp.loading && <Loading />}<ErrorBox msg={pp.error} />
        {pp.data && !pp.data.ready && <p className="text-sm text-amber-900">Sandbox credentials are missing. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to backend/.env and restart the backend (see README). Verification and consent still work without them.</p>}
        {pp.data?.ready && <p className="text-sm text-slate-600">Mode: Sandbox only. Enabled currencies: {pp.data.currencies.join(", ")}. Credentials stay in the backend. Configured credentials do not confirm seller currency acceptance; the PayPal approval page may still reject an account/currency combination.</p>}
        {oauthProbe && !oauthProbe.ok && <p className="text-sm text-red-800" role="status">{oauthProbe.message} Check the Sandbox app credentials in backend/.env; no payment was attempted.</p>}
        {pp.data?.ready && <Btn kind="ghost" onClick={checkSandbox} disabled={act.busy}>{act.busy ? "Checking…" : "Check Sandbox OAuth"}</Btn>}
      </Panel>
      {t && <Panel title="Payment" action={p ? <Badge tone={paymentTone(p.state)}>{PAYMENT_LABEL[p.state] ?? p.state}</Badge> : <Badge tone="slate">not started</Badge>}>
        <dl>
          <Row k="Amount (server calculated)" v={<strong>{money(t.verification.server_total, cur)}</strong>} /><Row k="Verification" v={t.verification.decision} />
          <Row k="Consent" v={t.consent_state} />
          {t.consent?.seconds_left != null && t.consent_state === "ACTIVE" && <Row k="Approval expires in" v={`${Math.floor(t.consent.seconds_left / 60)} min ${t.consent.seconds_left % 60} s`} />}
          {p?.paypal_order_id && <Row k="PayPal Sandbox order" v={<Mono>{p.paypal_order_id}</Mono>} />}
          {p?.capture_id && <Row k="PayPal Sandbox capture" v={<Mono>{p.capture_id}</Mono>} />}
          {p?.error_message && <Row k="Problem" v={<span className="text-red-800">{p.error_message}</span>} />}
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          {!p && <Btn onClick={start} disabled={act.busy || !canStart}>Pay with PayPal Sandbox</Btn>}
          {p?.state === "ORDER_CREATED" && <><Btn onClick={resume} disabled={act.busy}>Continue to PayPal</Btn><Btn kind="ghost" onClick={abandon} disabled={act.busy}>Cancel this payment</Btn></>}
          {p?.state === "COMPLETED" && <Btn onClick={receipt} disabled={act.busy}>Download Intent Integrity Receipt</Btn>}
          {p && ["FAILED", "EXPIRED", "CANCELLED"].includes(p.state) && <Link className="rounded bg-navy-900 px-4 py-2 text-sm font-semibold text-white" to="/offers">Start a new transaction</Link>}
          <Btn kind="ghost" onClick={() => { tx.reload(); pp.reload(); }}>Refresh</Btn>
        </div>
        {!p && !canStart && t && <p className="mt-2 text-sm text-slate-600">{t.consent_state === "NONE" ? "Approve the transaction on the Consent page first." : t.consent_state === "EXPIRED" ? "Your approval expired. Start again from the Consent page." : t.consent_state === "CONSUMED" ? "This approval was already used." : !pp.data?.ready ? "Configure PayPal Sandbox credentials to enable checkout." : "This transaction is not eligible for payment."}</p>}
      </Panel>}
      {t && <ChainView txId={t.id} refreshKey={`${p?.state ?? ""}${p?.updated_at ?? ""}${t.consent_state}`} />}
    </Page>
  );
}
