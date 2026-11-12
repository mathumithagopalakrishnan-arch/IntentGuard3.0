import { useState } from "react";
import { api } from "../services/api";
import { useAction, useLoad } from "../hooks/useAsync";
import type { AttackResult } from "../types";
import { Badge, Btn, ErrorBox, Loading, Page, Panel } from "../components/ui";
import { CHECK_LABEL, WHY } from "../utils/format";

const RULE_LABEL = (r: string) => CHECK_LABEL[r] ?? ({ consent_fingerprint_binding: "Consent is bound to the exact transaction fingerprint", one_time_consent: "Consent can be decided once and used once" } as Record<string, string>)[r] ?? r;

export default function Simulator() {
  const list = useLoad(() => api.attacks(), []);
  const act = useAction();
  const [results, setResults] = useState<Record<string, AttackResult>>({});
  const [running, setRunning] = useState("");
  const run = (key: string) => act.go(async () => { setRunning(key); try { const r = await api.runAttack(key); setResults((p) => ({ ...p, [key]: r })); } finally { setRunning(""); } });
  const runAll = () => act.go(async () => {
    try {
      for (const a of list.data?.attacks ?? []) {
        setRunning(a.key);
        const r = await api.runAttack(a.key);
        setResults((p) => ({ ...p, [a.key]: r }));
      }
    } finally {
      setRunning("");
    }
  });
  const done = Object.values(results);
  return (
    <Page title="Attack Simulator" intro="Each attack runs through the real verification, consent and payment-gate code on a temporary in-memory database. Nothing is saved, PayPal is never contacted, and every merchant here is synthetic. For each attack you see exactly which rule caught it and why.">
      <ErrorBox msg={list.error} /><ErrorBox msg={act.error} />
      <Panel title="Run the attacks" action={<Btn disabled={act.busy || !list.data} onClick={runAll}>Run all {list.data?.attacks.length ?? ""} attacks</Btn>}>
        {list.loading && <Loading />}
        {done.length > 0 && <p className="mb-2 text-sm" role="status">{done.filter((r) => r.blocked && r.expected_rule_hit).length} of {done.length} attacks run were stopped by the expected rule. Payments captured: {done.filter((r) => r.payment_captured).length}.</p>}
        <ul className="space-y-4">{list.data?.attacks.map((a) => {
          const r = results[a.key];
          return (
            <li key={a.key} className="rounded border border-slate-200 p-4 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{a.title}</h3>
                <div className="flex items-center gap-2">{r && <Badge tone={r.blocked && r.expected_rule_hit ? "green" : "red"}>{r.blocked ? "ATTACK BLOCKED" : "NOT BLOCKED"}</Badge>}
                  <Btn kind="ghost" disabled={act.busy} onClick={() => run(a.key)}>{running === a.key ? "Running…" : r ? "Run again" : "Run attack"}</Btn></div></div>
              <p className="mt-1 text-slate-700">{a.story}</p>
              {r && <div className="mt-3 space-y-2" role="status">
                <p><span className="font-medium">Caught by:</span> {a.expected_rules.map((x) => <span key={x} className="mr-1"><Badge tone="blue">{RULE_LABEL(x)}</Badge></span>)}</p>
                <ul className="space-y-1">{r.detected_by.map((d, i) => <li key={i} className="text-xs"><code className="rounded bg-slate-100 px-1">{d.rule}</code> <span className="text-slate-700">{d.detail}</span></li>)}</ul>
                {r.threats.map((t, i) => <p key={i} className="text-xs text-red-800">Scanner: {WHY[t.rule] ?? t.rule} (matched <code className="rounded bg-slate-100 px-1">{t.evidence}</code>)</p>)}
                <ol className="list-decimal pl-5 text-xs text-slate-600">{r.steps.map((st) => <li key={st}>{st}</li>)}</ol>
                <p className="text-xs"><span className="font-medium">Why it works:</span> {a.why}</p>
                <p className="text-xs font-medium">Payment captured: {r.payment_captured ? "YES" : "no"}</p>
              </div>}
            </li>);
        })}</ul>
      </Panel>
    </Page>
  );
}
