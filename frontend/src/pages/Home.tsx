import { useNavigate, Link } from "react-router-dom";
import { ShieldCheck, ShieldAlert } from "lucide-react";
import { api } from "../services/api";
import { useAction } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import { Btn, ErrorBox, Loading, Panel } from "../components/ui";

const STAGES: [string, string][] = [
  ["Customer intent", "What you actually asked your AI shopping agent for."], ["Intent Passport", "Your words as editable rules with a SHA-256 fingerprint."],
  ["Merchant offer", "Untrusted data. Never treated as instructions."], ["Final cart", "The server recomputes every price and total itself."],
  ["Verification", "Deterministic rules decide PASS or BLOCKED. No AI."], ["Human consent", "You approve the exact fingerprint. Short-lived, single use."],
  ["PayPal Sandbox", "The order is created from the verified total, and captured only after PayPal confirms approval."], ["Audit trail", "Hash-chained events and a downloadable receipt."],
];

export default function Home() {
  const nav = useNavigate();
  const { set } = useSession();
  const act = useAction();

  /** One click: runs the same API calls a user would make by hand, with the SYNTHETIC demo data. */
  const demo = (scenario: "legit" | "hidden_subscription") => act.go(async () => {
    const sc = (await api.scenarios()).scenarios[scenario];
    const text = "Buy wireless headphones under $50, no refurbished";
    const interp = await api.interpret(text);
    const intent = await api.confirmIntent((await api.createIntent(text, interp.constraints, interp.source)).id);
    const offer = await api.createOffer(sc.offer);
    const tx = await api.createTransaction(intent.id, offer.id, [{ item_id: "p1", qty: 1, unit_price: sc.cart_price }]);
    set({ intentId: intent.id, offerId: offer.id, transactionId: tx.id });
    nav(scenario === "legit" ? "/consent" : "/integrity");
  });

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-navy-900 px-6 py-8 text-white">
        <p className="text-sm font-medium text-blue-200">IntentGuard · independent hackathon prototype</p>
        <h1 className="mt-1 text-3xl font-semibold">The Trust Layer for Agentic Commerce</h1>
        <p className="mt-3 max-w-3xl text-slate-200">AI shopping agents can search, choose and pay for you. Between your request and the final payment, the instructions can be lost or manipulated: a hidden subscription, a changed price, or text in a product page that tries to give the agent new orders. IntentGuard checks that <strong>the transaction being paid is the transaction you intended</strong>, and keeps that proof attached all the way to PayPal.</p>
        <div className="mt-5 flex flex-wrap gap-3">
          <button type="button" disabled={act.busy} onClick={() => demo("legit")} className="flex items-center gap-2 rounded bg-white px-4 py-2 text-sm font-semibold text-navy-900 hover:bg-slate-100 disabled:opacity-50"><ShieldCheck className="h-4 w-4" aria-hidden />Scenario A: trusted purchase</button>
          <button type="button" disabled={act.busy} onClick={() => demo("hidden_subscription")} className="flex items-center gap-2 rounded border border-white/60 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 disabled:opacity-50"><ShieldAlert className="h-4 w-4" aria-hidden />Scenario B: malicious purchase</button>
          <Link to="/intent" className="rounded border border-white/30 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-white/10">Start from my own request</Link>
        </div>
        <div className="mt-3 text-sm">{act.busy && <Loading label="Setting up the synthetic demo…" />}<ErrorBox msg={act.error} /></div>
        <p className="mt-2 text-xs text-slate-300">Both scenarios use clearly labelled SYNTHETIC merchants. Payment uses the PayPal Sandbox with test money only.</p>
      </section>
      <Panel title="The Intent-to-Payment Integrity Chain">
        <ol className="grid gap-3 md:grid-cols-4">{STAGES.map(([t, d], i) => (
          <li key={t} className="rounded border border-slate-200 p-3 text-sm"><p className="font-semibold"><span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-navy-900 text-xs text-white">{i + 1}</span>{t}</p><p className="mt-1 text-xs text-slate-600">{d}</p></li>))}</ol>
        <p className="mt-3 text-sm text-slate-700">Every stage is hashed and linked to the one before it. If any protected attribute changes, the earlier approval stops being valid and PayPal is never asked to take the money.</p>
      </Panel>
      <div className="grid gap-5 md:grid-cols-3">
        <Panel title="What IntentGuard verifies"><ul className="list-disc space-y-1 pl-5 text-sm text-slate-700"><li>Product, budget, quantity, currency</li><li>No unapproved subscription or recurring billing</li><li>Shipping, fees and the merchant's stated total</li><li>Merchant text that tries to command an AI</li><li>That consent matches this exact transaction</li></ul></Panel>
        <Panel title="What it does not claim"><ul className="list-disc space-y-1 pl-5 text-sm text-slate-700"><li>It cannot prove a merchant is honest</li><li>An AI never approves or captures a payment</li><li>Sandbox payments move no real money</li><li>Not endorsed by PayPal</li></ul></Panel>
        <Panel title="Explore"><ul className="space-y-1 text-sm"><li><Link className="text-brand-600 underline" to="/simulator">Attack Simulator</Link>: try 8 realistic attacks</li><li><Link className="text-brand-600 underline" to="/dashboard">Dashboard</Link>: live system numbers</li><li><Link className="text-brand-600 underline" to="/audit">Audit and receipts</Link></li><li><Btn kind="ghost" onClick={() => nav("/threats")}>Threat text scanner</Btn></li></ul></Panel>
      </div>
    </div>
  );
}
