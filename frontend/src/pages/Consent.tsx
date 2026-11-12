import { api } from "../services/api";
import { Link, useNavigate } from "react-router-dom";
import { useAction, useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import TxPicker from "../components/TxPicker";
import { Badge, Btn, Empty, ErrorBox, Loading, Mono, Need, Page, Panel, Row } from "../components/ui";
import { money, when } from "../utils/format";

export default function Consent() {
  const { transactionId, set } = useSession();
  const nav = useNavigate();
  const tx = useLoad(transactionId ? () => api.getTransaction(transactionId) : null, [transactionId]);
  const t = tx.data;
  const intent = useLoad(t ? () => api.getIntent(t.intent_id) : null, [t?.intent_id]);
  const offer = useLoad(t ? () => api.getOffer(t.offer_id) : null, [t?.offer_id]);
  const hist = useLoad(() => api.consents(50), []);
  const act = useAction();
  const o = offer.data?.offer, line = t?.cart[0];
  const item = o?.items.find((i) => i.id === line?.item_id);
  const verified = t?.verification.decision === "VERIFIED";
  const decide = (grant: boolean) => act.go(async () => { if (!t) return; await (grant ? api.grantConsent(t.id) : api.rejectConsent(t.id)); tx.reload(); hist.reload(); });

  return (
    <Page title="Human Consent" intro="Only you can approve. This step is possible only after the backend verification passes, and the backend checks everything again at the moment you approve. Your approval is short-lived and can be used once. Next comes the PayPal Sandbox checkout (test money only).">
      <TxPicker />
      {!transactionId && <Need what="No transaction yet." to="/offers" label="Choose an offer and cart" />}
      {transactionId && tx.loading && !t && <Loading />}{transactionId && <ErrorBox msg={tx.error} />}<ErrorBox msg={act.error} />
      {t && o && line && item && intent.data && <>
        <Panel title="What you are approving" action={<Badge tone={verified ? "green" : "red"}>Backend verification: {t.verification.decision}</Badge>}>
          <dl>
            <Row k="Product" v={item.name} /><Row k={o.synthetic ? "Seller (synthetic demo)" : "Seller (user-entered, unverified)"} v={o.merchant} /><Row k="Quantity" v={line.qty} />
            <Row k="Price per item" v={money(line.unit_price, o.currency)} /><Row k="Shipping" v={money(o.shipping, o.currency)} /><Row k="Tax" v={money(o.tax, o.currency)} />
            <Row k="Subscription / recurring billing" v={o.recurring_billing || item.recurring ? "YES" : "none declared"} />
            <Row k="Final amount (server calculated)" v={<strong>{money(t.verification.server_total, o.currency)}</strong>} /><Row k="Currency" v={o.currency} />
            <Row k="Intent fingerprint" v={<Mono>{intent.data.fingerprint}</Mono>} /><Row k="Transaction fingerprint" v={<Mono>{t.verification.transaction_fingerprint}</Mono>} />
          </dl>
        </Panel>
        <Panel title="Your decision">
          {!t.consent && <>
            {!verified && <p className="mb-3 text-sm text-red-800">This transaction did not pass verification, so approval is disabled. See the Integrity page for why.</p>}
            <div className="flex flex-wrap gap-2"><Btn disabled={!verified || act.busy} onClick={() => decide(true)}>I approve this exact transaction</Btn>
              <Btn kind="ghost" disabled={act.busy} onClick={() => decide(false)}>Reject</Btn></div></>}
          {t.consent && <div role="status" className="space-y-2 text-sm">
            <Badge tone={t.consent_state === "ACTIVE" || t.consent_state === "CONSUMED" ? "green" : "red"}>
              {t.consent.decision === "REJECTED" ? "You rejected this transaction" : t.consent_state === "EXPIRED" ? "Approval EXPIRED" : !t.consent_valid ? "Consent is NO LONGER VALID: the transaction changed" : t.consent_state === "CONSUMED" ? "Approval used for a payment" : "Consent granted and still valid"}</Badge>
            <p className="text-slate-600">Decision recorded {when(t.consent.created_at)}. A decision cannot be changed or repeated. To change anything, create a new transaction.</p>
            {t.consent_state === "ACTIVE" && t.consent_valid && <><p className="text-slate-600">Expires in {Math.floor((t.consent.seconds_left ?? 0) / 60)} min. It is bound to the fingerprint above.</p>
              <Link className="inline-block rounded bg-navy-900 px-4 py-2 font-semibold text-white" to="/checkout">Next: PayPal Sandbox checkout</Link></>}
            {(t.consent_state === "EXPIRED" || (!t.consent_valid && t.consent.decision === "GRANTED")) && <Btn onClick={() => act.go(async () => { const nt = await api.createTransaction(t.intent_id, t.offer_id, t.cart); set({ transactionId: nt.id }); nav("/integrity"); })}>Start again with the same cart</Btn>}</div>}
        </Panel>
      </>}
      <Panel title="Consent history" action={<Btn kind="ghost" onClick={hist.reload}>Refresh</Btn>}>
        {hist.loading && !hist.data && <Loading />}<ErrorBox msg={hist.error} />
        {hist.data && hist.data.consents.length === 0 && <Empty>No decisions recorded yet.</Empty>}
        {hist.data && hist.data.consents.length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[36rem] text-left text-sm">
          <thead><tr className="border-b border-slate-200 text-slate-600"><th className="py-2 pr-3">When</th><th className="pr-3">Seller</th><th className="pr-3">Amount</th><th className="pr-3">Decision</th><th className="pr-3">Valid today</th><th>&nbsp;</th></tr></thead>
          <tbody>{hist.data.consents.map((c) => (
            <tr key={c.id} className={`border-b border-slate-100 ${c.transaction_id === transactionId ? "bg-brand-50" : ""}`}>
              <td className="py-2 pr-3">{when(c.created_at)}</td><td className="pr-3">{c.merchant}</td><td className="pr-3">{money(c.server_total, c.currency)}</td>
              <td className="pr-3"><Badge tone={c.decision === "GRANTED" ? "green" : "slate"}>{c.decision}</Badge></td>
              <td className="pr-3">{c.decision === "GRANTED" ? (c.still_valid ? "yes" : <Badge tone="red">NO: changed</Badge>) : "n/a"}</td>
              <td><Btn kind="ghost" onClick={() => set({ transactionId: c.transaction_id })}>Open</Btn></td></tr>))}</tbody></table></div>}
        <p className="mt-2 text-xs text-slate-600">"Valid today" is recomputed from stored data on every load. If anything behind a granted consent changes, it turns to NO.</p>
      </Panel>
    </Page>
  );
}
