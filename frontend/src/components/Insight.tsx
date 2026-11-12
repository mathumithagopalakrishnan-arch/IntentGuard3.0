import { useState } from "react";
import { api } from "../services/api";
import { useAction, useLoad } from "../hooks/useAsync";
import type { ChainStage, DriftRow } from "../types";
import { Badge, Btn, ErrorBox, Loading, Panel, type Tone } from "./ui";
import { CHECK_LABEL, shortHash } from "../utils/format";

/** Intent Drift: what the customer asked for, next to what the transaction does. Computed by the backend, not by an AI. */
export function DriftTable({ rows }: { rows: DriftRow[] }) {
  const drifted = rows.filter((r) => r.drifted).length;
  return (
    <Panel title="Intent drift" action={<Badge tone={drifted ? "red" : "green"}>{drifted ? `${drifted} attribute(s) drifted` : "No drift"}</Badge>}>
      <div className="overflow-x-auto"><table className="w-full min-w-[38rem] text-left text-sm">
        <thead><tr className="border-b border-slate-200 text-slate-600"><th className="py-2 pr-3">Attribute</th><th className="pr-3">You asked for</th><th className="pr-3">Transaction has</th><th>Result</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.attribute} className={`border-b border-slate-100 align-top ${r.drifted ? "bg-red-50" : ""}`}>
            <th className="py-2 pr-3 font-medium">{r.attribute}</th><td className="pr-3">{r.intent}</td><td className="pr-3">{r.transaction}</td>
            <td>{r.drifted ? <span><Badge tone="red">DRIFT</Badge><span className="ml-2 text-xs text-red-800">{r.evidence}</span></span> : <Badge tone="green">matches</Badge>}</td></tr>))}</tbody></table></div>
      <p className="mt-2 text-xs text-slate-600">Each row is tied to a backend rule (for example <code>recurring_billing_allowed</code>). The rules decide; this table only shows where they disagree with your intent.</p>
    </Panel>
  );
}

/** Evidence first, then inferred risks, then uncertainty. Gemini (when configured) only writes wording and is labelled as AI. */
export function ExplainPanel({ txId }: { txId: string }) {
  const act = useAction();
  const [ex, setEx] = useState<Awaited<ReturnType<typeof api.explain>> | null>(null);
  return (
    <Panel title="Explanation with evidence" action={<Btn kind="ghost" disabled={act.busy} onClick={() => act.go(async () => setEx(await api.explain(txId)))}>{ex ? "Explain again" : "Explain this result"}</Btn>}>
      <ErrorBox msg={act.error} />{act.busy && <Loading label="Preparing explanation…" />}
      {!ex && !act.busy && <p className="text-sm text-slate-600">Shows which facts triggered the result, what they could mean, and what nobody can know from this data.</p>}
      {ex && <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2"><Badge tone={ex.source === "gemini" ? "blue" : "slate"}>{ex.source === "gemini" ? "AI-generated wording (Gemini)" : "Rule-based text"}</Badge><span className="text-xs text-slate-600">{ex.label}</span></div>
        {ex.fallback_reason && <p className="text-xs text-amber-900">{ex.fallback_reason}</p>}
        <p className="font-medium">{ex.summary}</p>
        <div><h3 className="font-semibold">Detected evidence (deterministic)</h3>
          {ex.evidence.length === 0 ? <p className="text-slate-600">Nothing was flagged.</p> : <ul className="mt-1 space-y-1">{ex.evidence.map((e) => <li key={e.id}><Badge tone={e.kind === "failed_check" ? "red" : "amber"}>{e.kind === "failed_check" ? "FAILED CHECK" : "SCANNER"}</Badge> <span className="font-medium">{CHECK_LABEL[e.id] ?? e.id}</span> <span className="text-slate-600">{e.detail}</span></li>)}</ul>}</div>
        {ex.inferred_risks.length > 0 && <div><h3 className="font-semibold">What this could mean (inference, not proof)</h3><ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700">{ex.inferred_risks.map((r, i) => <li key={i}>{r.text}</li>)}</ul></div>}
        <div><h3 className="font-semibold">What we cannot know</h3><ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700">{ex.uncertainty.map((u, i) => <li key={i}>{u}</li>)}</ul></div>
      </div>}
    </Panel>
  );
}

const STATUS_TONE: Record<ChainStage["status"], Tone> = { ok: "green", warn: "amber", blocked: "red", broken: "red", pending: "slate" };
const STATUS_TEXT: Record<ChainStage["status"], string> = { ok: "bound", warn: "warning", blocked: "stopped", broken: "BROKEN", pending: "not reached" };

/** The Intent-to-Payment Integrity Chain for one transaction: eight stages, each hash linked to the previous one. */
export function ChainView({ txId, refreshKey = "" }: { txId: string; refreshKey?: string }) {
  const ch = useLoad(() => api.chain(txId), [txId, refreshKey]);
  const c = ch.data;
  return (
    <Panel title="Intent-to-Payment Integrity Chain" action={c && <Badge tone={c.intact ? "green" : "red"}>{c.intact ? "All bindings hold" : "BINDING BROKEN"}</Badge>}>
      {ch.loading && !c && <Loading />}<ErrorBox msg={ch.error} />
      {c && <>
        <ol className="space-y-2">{c.stages.map((st) => (
          <li key={st.key} className="flex flex-wrap items-start gap-2 text-sm">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-navy-900 text-xs font-semibold text-white" aria-hidden>{st.n}</span>
            <div className="min-w-0 flex-1"><p><span className="font-medium">{st.title}</span> <Badge tone={STATUS_TONE[st.status]}>{STATUS_TEXT[st.status]}</Badge></p>
              <p className="text-xs text-slate-600">{st.detail}</p>
              <p className="text-xs text-slate-500">stage hash <code>{shortHash(st.hash)}</code> · link <code>{shortHash(st.link)}</code></p></div></li>))}</ol>
        {c.bindings.length > 0 && <ul className="mt-3 space-y-1 text-xs">{c.bindings.map((b) => <li key={b.name}><Badge tone={b.ok ? "green" : "red"}>{b.ok ? "OK" : "BROKEN"}</Badge> {b.name}</li>)}</ul>}
        <p className="mt-2 text-xs text-slate-600">{c.note}</p>
      </>}
    </Panel>
  );
}
