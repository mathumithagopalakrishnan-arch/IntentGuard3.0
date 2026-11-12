import { useState } from "react";
import { Link } from "react-router-dom";
import { Copy } from "lucide-react";
import { api } from "../services/api";
import { useAction, useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import type { Constraints, FingerprintCheck, Interpretation } from "../types";
import { Badge, Btn, ErrorBox, Loading, Mono, Page, Panel, Row } from "../components/ui";
import { money, toMinor } from "../utils/format";

const EXAMPLES = ["Buy wireless headphones under $50", "Buy wireless headphones under $50, no refurbished", "Buy headphones under 60 dollars", "Buy 2 usb cables under $15"];
const norm = (c: Constraints) => JSON.stringify({ ...c, prohibited_terms: [...c.prohibited_terms].sort() });
const CURRENCIES = ["USD", "EUR", "GBP", "INR", "AUD", "CAD"];

export default function IntentPassport() {
  const { intentId, set, clear } = useSession();
  const [text, setText] = useState("");
  const [interp, setInterp] = useState<Interpretation | null>(null);
  const [f, setF] = useState({ category: "", budget: "", currency: "USD", qty: "1", sub: false, terms: "", ship: "" });
  const [check, setCheck] = useState<FingerprintCheck | null>(null);
  const [copied, setCopied] = useState(false);
  const act = useAction();
  const intent = useLoad(intentId ? () => api.getIntent(intentId) : null, [intentId]);
  const recent = useLoad(() => api.intents(5), [intentId]);

  const interpret = () => act.go(async () => {
    const r = await api.interpret(text);
    setInterp(r);
    const c = r.constraints;
    setF({ category: c.category, budget: (c.max_total / 100).toFixed(2), currency: c.currency, qty: String(c.max_quantity), sub: c.allow_subscription,
      terms: c.prohibited_terms.join(", "), ship: c.max_shipping == null ? "" : (c.max_shipping / 100).toFixed(2) });
  });

  const build = (): Constraints | string => {
    const total = toMinor(f.budget), qty = Number(f.qty), ship = f.ship.trim() === "" ? null : toMinor(f.ship);
    if (!f.category.trim()) return "Product is required.";
    if (!Number.isFinite(total) || total <= 0) return "Maximum budget must be a number above zero.";
    if (!Number.isInteger(qty) || qty < 1) return "Quantity must be a whole number, 1 or more.";
    if (ship !== null && (!Number.isFinite(ship) || ship < 0)) return "Maximum shipping must be zero or more, or empty.";
    return { category: f.category.trim(), max_total: total, currency: f.currency, max_quantity: qty, allow_subscription: f.sub,
      prohibited_terms: f.terms.split(",").map((t) => t.trim()).filter(Boolean), max_shipping: ship, required_disclosures: interp?.constraints.required_disclosures ?? ["returns", "shipping", "tax"] };
  };

  const save = () => act.go(async () => {
    const c = build();
    if (typeof c === "string") throw new Error(c);
    const source = interp && norm(interp.constraints) === norm(c) ? interp.source : "user_edited";
    const created = await api.createIntent(text, c, source);
    set({ intentId: created.id, offerId: "", transactionId: "" });
    setInterp(null); setCheck(null);
  });
  const confirm = () => act.go(async () => { await api.confirmIntent(intentId); intent.reload(); });
  const verifyFp = () => act.go(async () => setCheck(await api.verifyFingerprint(intentId)));
  const copy = async (s: string) => { try { await navigator.clipboard.writeText(s); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ } };
  const inp = "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm";
  const d = intent.data;

  return (
    <Page title="Intent Passport" intro="Say what you want to buy. The system turns it into rules you can edit and confirm. The rules get a SHA-256 fingerprint, so any later change is detectable.">
      <ErrorBox msg={act.error} />
      {!d && <Panel title="1. Describe your purchase">
        <label className="text-sm font-medium" htmlFor="instr">Purchase instruction</label>
        <textarea id="instr" className={inp} rows={2} maxLength={500} value={text} onChange={(e) => setText(e.target.value)} placeholder="Buy wireless headphones under $50" />
        <div className="mt-2 flex flex-wrap gap-2">{EXAMPLES.map((x) => <button key={x} type="button" className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50" onClick={() => setText(x)}>{x}</button>)}</div>
        <div className="mt-3"><Btn onClick={interpret} disabled={act.busy || text.trim().length < 3}>Interpret</Btn></div>
        {act.busy && <div className="mt-2"><Loading /></div>}
      </Panel>}
      {!d && recent.data && recent.data.intents.length > 0 && <Panel title="Or reopen an earlier passport">
        <ul className="space-y-2 text-sm">{recent.data.intents.map((i) => (
          <li key={i.id} className="flex flex-wrap items-center justify-between gap-2"><span>{i.constraints.category} · up to {money(i.constraints.max_total, i.constraints.currency)} <Badge tone={i.status === "CONFIRMED" ? "green" : "amber"}>{i.status}</Badge></span>
            <Btn kind="ghost" onClick={() => set({ intentId: i.id, offerId: "", transactionId: "" })}>Open</Btn></li>))}</ul>
      </Panel>}
      {!d && interp && <Panel title="2. Check what the system understood" action={<Badge tone={interp.source === "gemini" ? "blue" : "amber"}>{interp.source === "gemini" ? "AI interpretation (Gemini)" : "Fallback rules"}</Badge>}>
        <p className="mb-3 text-sm text-slate-600">{interp.explanation}</p>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">Product<input className={inp} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} /></label>
          <label className="text-sm">Maximum total budget<input className={inp} inputMode="decimal" value={f.budget} onChange={(e) => setF({ ...f, budget: e.target.value })} /></label>
          <label className="text-sm">Currency<select className={inp} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label className="text-sm">Maximum quantity<input className={inp} inputMode="numeric" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} /></label>
          <label className="text-sm">Maximum shipping (optional)<input className={inp} inputMode="decimal" value={f.ship} onChange={(e) => setF({ ...f, ship: e.target.value })} /></label>
          <label className="text-sm">Prohibited words (comma separated)<input className={inp} value={f.terms} onChange={(e) => setF({ ...f, terms: e.target.value })} /></label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={f.sub} onChange={(e) => setF({ ...f, sub: e.target.checked })} />Allow subscriptions / recurring billing</label>
        <div className="mt-3"><Btn onClick={save} disabled={act.busy}>Create Intent Passport</Btn></div>
      </Panel>}
      {intentId && intent.loading && <Loading />}
      {intentId && <ErrorBox msg={intent.error} />}
      {d && <Panel title="Your Intent Passport" action={<Badge tone={d.status === "CONFIRMED" ? "green" : "amber"}>{d.status === "CONFIRMED" ? "Confirmed by you" : "Draft: not confirmed"}</Badge>}>
        <dl>
          <Row k="Instruction (your words)" v={d.instruction} />
          <Row k="Interpreted by" v={d.source === "gemini" ? "Gemini (AI)" : d.source === "fallback_rules" ? "Built-in rules" : "You (edited)"} />
          <Row k="Product" v={d.constraints.category} /><Row k="Maximum total" v={money(d.constraints.max_total, d.constraints.currency)} />
          <Row k="Maximum quantity" v={d.constraints.max_quantity} /><Row k="Maximum shipping" v={d.constraints.max_shipping == null ? "no limit set" : money(d.constraints.max_shipping, d.constraints.currency)} />
          <Row k="Subscriptions allowed" v={d.constraints.allow_subscription ? "yes" : "no"} /><Row k="Prohibited words" v={d.constraints.prohibited_terms.join(", ") || "none"} />
          <Row k="Fingerprint (SHA-256)" v={<span className="flex items-center gap-2"><Mono>{d.fingerprint}</Mono><button type="button" aria-label="Copy fingerprint" onClick={() => copy(d.fingerprint)}><Copy className="h-4 w-4" /></button>{copied && <span className="text-xs">Copied</span>}</span>} />
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          {d.status === "DRAFT" && <Btn onClick={confirm} disabled={act.busy}>I confirm these rules</Btn>}
          <Btn kind="ghost" onClick={verifyFp} disabled={act.busy}>Verify fingerprint integrity</Btn>
          <Btn kind="ghost" onClick={() => { clear(); setCheck(null); }}>Start a new intent</Btn>
          {d.status === "CONFIRMED" && <Link className="rounded bg-navy-900 px-4 py-2 text-sm font-semibold text-white" to="/offers">Next: inspect an offer</Link>}
        </div>
        {check && <div className="mt-3" role="status"><Badge tone={check.intact ? "green" : "red"}>{check.intact ? "Fingerprint matches the stored data" : "MISMATCH: stored data changed"}</Badge><p className="mt-1 text-xs text-slate-600">{check.note}</p></div>}
      </Panel>}
    </Page>
  );
}
