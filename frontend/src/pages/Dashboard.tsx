import { Link, useNavigate } from "react-router-dom";
import { api } from "../services/api";
import { useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import { Badge, Btn, Empty, ErrorBox, Loading, Page, Panel, Row } from "../components/ui";
import { consentLabel, money, when } from "../utils/format";

export default function Dashboard() {
  const { transactionId, set } = useSession();
  const nav = useNavigate();
  const health = useLoad(() => api.health(), []);
  const stats = useLoad(() => api.stats(), []);
  const events = useLoad(() => api.audit(6), []);
  const txs = useLoad(() => api.transactions(8), []);
  const chain = useLoad(() => api.auditVerify(), []);
  const st = stats.data;
  const tiles: [string, number | undefined, string?][] = [
    ["Intent passports", st?.intents, st ? `${st.intents_confirmed} confirmed` : undefined], ["Offers inspected", st?.offers],
    ["Transactions", st?.transactions], ["Verified", st?.verified, st ? `${st.awaiting_consent} awaiting consent` : undefined],
    ["Blocked", st?.blocked], ["Consents granted", st?.consents_granted, st ? `${st.consents_rejected} rejected` : undefined],
    ["Threat scans", st?.threat_scans], ["Audit events", st?.audit_events],
  ];
  const open = (id: string, intent_id: string, offer_id: string) => { set({ transactionId: id, intentId: intent_id, offerId: offer_id }); nav("/integrity"); };

  return (
    <Page title="Dashboard" intro="Live numbers from the backend database. Nothing here is estimated or pre-filled.">
      <div className="grid gap-5 md:grid-cols-3">
        <Panel title="System health">
          {health.loading && <Loading />}<ErrorBox msg={health.error} />
          {health.data && <dl>
            <Row k="API" v={<Badge tone={health.data.status === "ok" ? "green" : "red"}>{health.data.status}</Badge>} />
            <Row k="Database" v={<Badge tone={health.data.database === "ok" ? "green" : "red"}>{health.data.database}</Badge>} />
            <Row k="Gemini" v={<Badge tone={health.data.gemini_configured ? "green" : "amber"}>{health.data.gemini_configured ? "configured" : "not set (fallback rules)"}</Badge>} />
            <Row k="Demo mode" v={<Badge tone={health.data.demo_mode ? "amber" : "slate"}>{health.data.demo_mode ? "on: synthetic data" : "off"}</Badge>} />
            <Row k="Payments" v={<Badge tone={health.data.payments_enabled ? "green" : "amber"}>{health.data.payments_enabled ? "PayPal Sandbox credentials set" : "Sandbox credentials not set"}</Badge>} />
            <Row k="Audit log" v={chain.loading ? "checking…" : chain.error ? <Badge tone="amber">unknown</Badge>
              : chain.data?.intact ? <Badge tone="green">{chain.data.events} events verified</Badge> : <Badge tone="red">TAMPERING DETECTED</Badge>} /></dl>}
        </Panel>
        <div className="md:col-span-2"><Panel title="Totals">
          {stats.loading && <Loading />}<ErrorBox msg={stats.error} />
          {st && <div className="grid grid-cols-2 gap-4 md:grid-cols-4">{tiles.map(([l, n, sub]) => (
            <div key={l}><p className="text-2xl font-semibold">{n}</p><p className="text-xs text-slate-600">{l}</p>{sub && <p className="text-xs text-slate-500">{sub}</p>}</div>))}</div>}
        </Panel></div>
      </div>
      <Panel title="Recent transactions" action={<Btn kind="ghost" onClick={txs.reload}>Refresh</Btn>}>
        {txs.loading && !txs.data && <Loading />}<ErrorBox msg={txs.error} />
        {txs.data && txs.data.transactions.length === 0 && <Empty>No transactions yet. Start with the <Link className="font-semibold text-brand-600 underline" to="/intent">Intent Passport</Link>.</Empty>}
        {txs.data && txs.data.transactions.length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[40rem] text-left text-sm">
          <thead><tr className="border-b border-slate-200 text-slate-600"><th className="py-2 pr-3">When</th><th className="pr-3">Seller</th><th className="pr-3">Server total</th><th className="pr-3">Decision</th><th className="pr-3">Consent</th><th>&nbsp;</th></tr></thead>
          <tbody>{txs.data.transactions.map((t) => (
            <tr key={t.id} className={`border-b border-slate-100 ${t.id === transactionId ? "bg-brand-50" : ""}`}>
              <td className="py-2 pr-3">{when(t.created_at)}</td><td className="pr-3">{t.merchant}</td><td className="pr-3">{money(t.server_total, t.currency)}</td>
              <td className="pr-3"><Badge tone={t.decision === "VERIFIED" ? "green" : "red"}>{t.decision}</Badge>{t.failed_checks.length > 0 && <span className="ml-2 text-xs text-slate-500">{t.failed_checks.length} check(s) failed</span>}</td>
              <td className="pr-3">{consentLabel(t.consent, t.consent_valid)}</td>
              <td><Btn kind="ghost" onClick={() => open(t.id, t.intent_id, t.offer_id)}>Open</Btn></td></tr>))}</tbody></table></div>}
      </Panel>
      <Panel title="Recent security events" action={<Link className="text-sm text-brand-600 underline" to="/audit">All events</Link>}>
        {events.loading && !events.data && <Loading />}<ErrorBox msg={events.error} />
        {events.data && events.data.events.length === 0 && <Empty>No events yet.</Empty>}
        <ul className="space-y-1 text-sm">{events.data?.events.map((e) => <li key={e.id}><span className="text-slate-500">{when(e.ts)}</span> · {e.type.replace(/_/g, " ")}</li>)}</ul>
      </Panel>
    </Page>
  );
}
