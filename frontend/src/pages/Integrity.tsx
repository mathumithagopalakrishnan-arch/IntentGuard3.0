import { api } from "../services/api";
import { useAction, useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import { Link } from "react-router-dom";
import TxPicker from "../components/TxPicker";
import { DriftTable, ExplainPanel } from "../components/Insight";
import { Badge, Btn, ErrorBox, Loading, Mono, Need, Page, Panel, Row } from "../components/ui";
import { CHECK_LABEL, money } from "../utils/format";

export default function Integrity() {
  const { transactionId } = useSession();
  const tx = useLoad(transactionId ? () => api.getTransaction(transactionId) : null, [transactionId]);
  const t = tx.data;
  const intent = useLoad(t ? () => api.getIntent(t.intent_id) : null, [t?.intent_id]);
  const offer = useLoad(t ? () => api.getOffer(t.offer_id) : null, [t?.offer_id]);
  const act = useAction();
  const c = intent.data?.constraints, o = offer.data?.offer, line = t?.cart[0];
  const v = t?.verification;
  const warnings = v ? v.threats.filter((x) => x.severity !== "high").length : 0;
  const state = !v ? null : v.decision === "BLOCKED" ? "BLOCKED" : warnings > 0 ? "REVIEW" : "PASS";

  return (
    <Page title="Transaction Integrity Engine" intro="The backend compares your confirmed intent, the offer and the selected cart. Every result below was computed by deterministic code on the server. No AI is involved in this decision.">
      <TxPicker />
      {!transactionId && <Need what="No transaction yet." to="/offers" label="Choose an offer and cart" />}
      {transactionId && tx.loading && <Loading />}{transactionId && <ErrorBox msg={tx.error} />}<ErrorBox msg={act.error} />
      {t && v && c && o && line && <>
        <Panel title="Decision" action={<Btn kind="ghost" disabled={act.busy} onClick={() => act.go(async () => { await api.verifyTransaction(t.id); tx.reload(); })}>Re-run verification</Btn>}>
          <div className="flex flex-wrap items-center gap-3">
            {state === "BLOCKED" && <Badge tone="red">BLOCKED</Badge>}{state === "PASS" && <Badge tone="green">PASS</Badge>}{state === "REVIEW" && <Badge tone="amber">NEEDS REVIEW</Badge>}
            <span className="text-sm">{state === "BLOCKED" ? "At least one required check failed. Payment approval is not possible." : state === "REVIEW" ? "All required checks passed, but there are warnings. Read them on the Threats page." : "All required checks passed."}</span></div>
          <p className="mt-2 text-xs text-slate-600">Transaction fingerprint: <Mono>{v.transaction_fingerprint}</Mono></p>
        </Panel>
        <Panel title="Side by side">
          <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-left text-sm">
            <thead><tr className="border-b border-slate-200 text-slate-600"><th className="py-2 pr-3">&nbsp;</th><th className="pr-3">Your intent</th><th className="pr-3">Merchant offer</th><th>Selected cart</th></tr></thead>
            <tbody className="[&_td]:py-1.5 [&_td]:pr-3 [&_tr]:border-b [&_tr]:border-slate-100">
              <tr><th className="pr-3 font-medium">Product</th><td>{c.category}</td><td>{o.items.find((i) => i.id === line.item_id)?.name}</td><td>{line.item_id}</td></tr>
              <tr><th className="pr-3 font-medium">Quantity</th><td>up to {c.max_quantity}</td><td>n/a</td><td>{line.qty}</td></tr>
              <tr><th className="pr-3 font-medium">Unit price</th><td>n/a</td><td>{money(o.items.find((i) => i.id === line.item_id)?.unit_price, o.currency)}</td><td>{money(line.unit_price, o.currency)}</td></tr>
              <tr><th className="pr-3 font-medium">Shipping</th><td>{c.max_shipping == null ? "no limit" : `up to ${money(c.max_shipping, c.currency)}`}</td><td>{money(o.shipping, o.currency)}</td><td>n/a</td></tr>
              <tr><th className="pr-3 font-medium">Recurring billing</th><td>{c.allow_subscription ? "allowed" : "not allowed"}</td><td>{o.recurring_billing ? "yes" : "no"}</td><td>n/a</td></tr>
              <tr><th className="pr-3 font-medium">Currency</th><td>{c.currency}</td><td>{o.currency}</td><td>n/a</td></tr>
            </tbody></table></div>
          <dl className="mt-4"><Row k="Your maximum total" v={money(c.max_total, c.currency)} /><Row k="Expected total (server recalculated)" v={money(v.server_total, o.currency)} />
            <Row k="Actual proposed total (merchant stated)" v={money(o.claimed_total, o.currency)} /></dl>
        </Panel>
        <DriftTable rows={t.drift} />
        <ExplainPanel txId={t.id} />
        <Panel title="Every check">
          <ul className="space-y-2">{v.checks.map((k) => (
            <li key={k.id} className="flex flex-wrap items-start gap-2 text-sm"><Badge tone={k.passed ? "green" : "red"}>{k.passed ? "PASS" : "BLOCKED"}</Badge>
              <span><span className="font-medium">{CHECK_LABEL[k.id] ?? k.id}.</span> <span className="text-slate-600">{k.detail}</span></span></li>))}</ul>
        </Panel>
        <div><Link className="rounded bg-navy-900 px-4 py-2 text-sm font-semibold text-white" to="/consent">Next: review and consent</Link></div>
      </>}
    </Page>
  );
}
