import { useState } from "react";
import { api } from "../services/api";
import { useAction, useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import type { ChainReport } from "../types";
import { Badge, Btn, Empty, ErrorBox, Loading, Mono, Page, Panel } from "../components/ui";
import { ChainView } from "../components/Insight";
import { PAYMENT_LABEL, downloadJson, money, paymentTone, shortHash, when } from "../utils/format";

const PAGE = 50;

export default function Audit() {
  const { transactionId } = useSession();
  const [mine, setMine] = useState(false);
  const [type, setType] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [report, setReport] = useState<ChainReport | null>(null);
  const act = useAction();
  const scoped = mine && !!transactionId;
  const types = useLoad(() => api.auditTypes(), []);
  const ev = useLoad(() => api.auditPage({ limit, type: type || undefined, transaction_id: scoped ? transactionId : undefined }), [limit, type, scoped, transactionId]);
  const pays = useLoad(() => api.payments(20), []);
  const receipt = (id: string) => act.go(async () => downloadJson(`intentguard-receipt-${id.slice(0, 8)}.json`, await api.receipt(id)));
  const shown = ev.data?.events.length ?? 0;
  const total = ev.data?.total ?? 0;
  const reset = (fn: () => void) => { fn(); setLimit(PAGE); };

  return (
    <Page title="Audit Timeline" intro="Every important step is stored in the database, so this history survives a page refresh. Events are written by the backend, never by this page. Each event is chained to the one before it by a SHA-256 hash, so editing or deleting an old event can be detected.">
      <Panel title="Log integrity" action={<Btn kind="ghost" disabled={act.busy} onClick={() => act.go(async () => setReport(await api.auditVerify()))}>Verify audit log</Btn>}>
        <ErrorBox msg={act.error} />
        {!report && <p className="text-sm text-slate-600">Press the button to recompute every hash in the log.</p>}
        {report && <div role="status" className="space-y-1 text-sm">
          <Badge tone={report.intact ? "green" : "red"}>{report.intact ? `Intact: ${report.chained} chained events verified` : "BROKEN: the log was changed"}</Badge>
          {!report.intact && <p className="text-red-800">First problem at event #{report.first_broken_id}: {report.reason}</p>}
          {report.intact && report.head && <p className="text-slate-600">Head hash: <Mono>{report.head}</Mono></p>}
          {report.legacy_unchained > 0 && <p className="text-slate-600">{report.legacy_unchained} older event(s) were written before chaining existed and are not covered.</p>}
          {report.note && <p className="text-xs text-slate-600">{report.note}</p>}</div>}
      </Panel>
      {transactionId && <ChainView txId={transactionId} />}
      <Panel title="Payments (PayPal Sandbox)" action={<Btn kind="ghost" onClick={pays.reload}>Refresh</Btn>}>
        {pays.loading && !pays.data && <Loading />}<ErrorBox msg={pays.error} />
        {pays.data && pays.data.payments.length === 0 && <Empty>No payments yet.</Empty>}
        {pays.data && pays.data.payments.length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-left text-sm"><thead><tr className="border-b border-slate-200 text-slate-600"><th className="py-2 pr-3">When</th><th className="pr-3">Seller</th><th className="pr-3">Amount</th><th className="pr-3">State</th><th>Receipt</th></tr></thead>
          <tbody>{pays.data.payments.map((p) => <tr key={p.id} className="border-b border-slate-100"><td className="py-2 pr-3">{when(p.created_at)}</td><td className="pr-3">{p.merchant}</td><td className="pr-3">{money(p.amount_minor, p.currency)}</td>
            <td className="pr-3"><Badge tone={paymentTone(p.state)}>{PAYMENT_LABEL[p.state] ?? p.state}</Badge></td><td><Btn kind="ghost" onClick={() => receipt(p.transaction_id)}>Download</Btn></td></tr>)}</tbody></table></div>}
      </Panel>
      <Panel title={scoped ? "Events for the current transaction" : "Events"}
        action={<div className="flex flex-wrap items-center gap-2">
          <label htmlFor="atype" className="sr-only">Event type</label>
          <select id="atype" className="rounded border border-slate-300 bg-white px-2 py-1.5 text-sm" value={type} onChange={(e) => reset(() => setType(e.target.value))}>
            <option value="">All event types</option>{types.data?.types.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select>
          <Btn kind="ghost" onClick={() => reset(() => setMine(!mine))} disabled={!transactionId}>{mine ? "Show all transactions" : "Current transaction only"}</Btn>
          <Btn kind="ghost" onClick={() => { ev.reload(); types.reload(); }}>Refresh</Btn></div>}>
        {ev.loading && !ev.data && <Loading />}<ErrorBox msg={ev.error} />
        {ev.data && total === 0 && <Empty>{type || scoped ? "No events match these filters." : "No events yet. Create an Intent Passport to start the timeline."}</Empty>}
        {ev.data && total > 0 && <p className="mb-2 text-xs text-slate-600">Showing {shown} of {total} events, newest first.</p>}
        <ol className="space-y-3 border-l-2 border-slate-200 pl-4">{ev.data?.events.map((e) => (
          <li key={e.id} className="text-sm"><p className="font-medium">{e.type.replace(/_/g, " ")}</p>
            <p className="text-xs text-slate-500">{when(e.ts)} · event #{e.id} · hash {shortHash(e.hash)}</p>
            {Object.keys(e.detail).length > 0 && <p className="text-xs text-slate-600">{Object.entries(e.detail).map(([k, val]) => `${k}: ${Array.isArray(val) ? val.join(", ") || "none" : String(val)}`).join(" · ")}</p>}</li>))}</ol>
        {ev.data && shown < total && <div className="mt-3"><Btn kind="ghost" disabled={ev.loading} onClick={() => setLimit(limit + PAGE)}>Load {Math.min(PAGE, total - shown)} more</Btn></div>}
      </Panel>
    </Page>
  );
}
