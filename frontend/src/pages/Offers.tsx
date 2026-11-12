import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";
import { useAction, useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import type { Offer } from "../types";
import { Badge, Btn, Empty, ErrorBox, Loading, Need, Page, Panel, Row } from "../components/ui";
import { money, toMinor } from "../utils/format";

const CURRENCIES = ["USD", "EUR", "GBP", "INR", "AUD", "CAD"];
const DISCLOSURES = ["shipping", "tax", "returns"];
const BLANK = { merchant: "", name: "", category: "", price: "", ship: "0", tax: "0", claimed: "", currency: "USD", recurring: false, disclosures: [...DISCLOSURES], description: "", terms: "" };
const inp = "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm";

/** Money text -> whole minor units, or an error message. */
function minor(text: string, label: string, allowEmpty = false): number | null | string {
  if (allowEmpty && text.trim() === "") return null;
  const n = toMinor(text);
  return Number.isFinite(n) && n >= 0 ? n : `${label} must be a number, zero or more.`;
}

export default function Offers() {
  const { intentId, offerId, set } = useSession();
  const nav = useNavigate();
  const act = useAction();
  const [pick, setPick] = useState("");
  const [cartPrice, setCartPrice] = useState<string | null>(null);
  const [qty, setQty] = useState("1");
  const [f, setF] = useState(BLANK);
  const sc = useLoad(() => api.scenarios(), []);
  const intent = useLoad(intentId ? () => api.getIntent(intentId) : null, [intentId]);
  const rec = useLoad(offerId ? () => api.getOffer(offerId) : null, [offerId]);

  const inspect = () => act.go(async () => {
    const s = sc.data?.scenarios[pick];
    if (!s) throw new Error("Choose a scenario first.");
    const r = await api.createOffer(s.offer);
    set({ offerId: r.id, transactionId: "" });
    setCartPrice((s.cart_price / 100).toFixed(2));
  });

  const inspectCustom = () => act.go(async () => {
    const price = minor(f.price, "Price"), ship = minor(f.ship, "Shipping"), tax = minor(f.tax, "Tax"), claimed = minor(f.claimed, "Stated total", true);
    for (const v of [price, ship, tax, claimed]) if (typeof v === "string") throw new Error(v);
    if (!f.merchant.trim() || !f.name.trim() || !f.category.trim()) throw new Error("Seller, product name and product category are required.");
    const offer: Offer = {
      merchant: f.merchant.trim(), currency: f.currency, shipping: ship as number, tax: tax as number, disclosures: f.disclosures,
      claimed_total: claimed as number | null, recurring_billing: f.recurring, description: f.description.trim(), terms: f.terms.trim(),
      items: [{ id: "p1", name: f.name.trim(), description: "", category: f.category.trim(), unit_price: price as number, recurring: false }],
      synthetic: false, label: "User-entered offer (not verified)",
    };
    const r = await api.createOffer(offer);
    set({ offerId: r.id, transactionId: "" });
    setCartPrice(((price as number) / 100).toFixed(2));
  });

  const o = rec.data?.offer, item = o?.items[0];
  const startTx = () => act.go(async () => {
    if (!o || !item) return;
    const unit = cartPrice === null ? item.unit_price : toMinor(cartPrice), q = Number(qty);
    if (!Number.isFinite(unit) || unit < 0) throw new Error("Cart price must be zero or more.");
    if (!Number.isInteger(q) || q < 1) throw new Error("Quantity must be a whole number, 1 or more.");
    const t = await api.createTransaction(intentId, offerId, [{ item_id: item.id, qty: q, unit_price: unit }]);
    set({ transactionId: t.id });
    nav("/integrity");
  });
  const toggle = (d: string) => setF({ ...f, disclosures: f.disclosures.includes(d) ? f.disclosures.filter((x) => x !== d) : [...f.disclosures, d] });

  return (
    <Page title="Merchant Offer Intelligence" intro="Inspect an offer before anything is verified. Demo offers are SYNTHETIC. An offer you type in yourself is checked against your intent, but nothing here confirms that any real seller is honest.">
      <ErrorBox msg={act.error} />
      <Panel title="Synthetic demo scenarios" action={<Badge tone="amber">SYNTHETIC</Badge>}>
        {sc.loading && <Loading />}<ErrorBox msg={sc.error} />
        {sc.data && <fieldset className="space-y-2"><legend className="mb-1 text-sm text-slate-600">{sc.data.label}</legend>
          <p className="mb-2 text-xs text-slate-500">{sc.data.default_intent_hint}</p>
          {Object.entries(sc.data.scenarios).map(([k, v]) => (
            <label key={k} className="flex flex-wrap items-center gap-2 text-sm"><input type="radio" name="sc" checked={pick === k} onChange={() => setPick(k)} />{v.offer.label}
              <Badge tone={v.expected === "VERIFIED" ? "green" : "red"}>expected: {v.expected}</Badge></label>))}
        </fieldset>}
        <div className="mt-3"><Btn onClick={inspect} disabled={act.busy || !pick}>Inspect this offer</Btn></div>
      </Panel>
      <details className="rounded-lg border border-slate-200 bg-white p-5">
        <summary className="cursor-pointer text-base font-semibold">Or enter your own offer (user-entered, unverified)</summary>
        <p className="mt-2 text-sm text-slate-600">Type in an offer you want checked. The server checks the numbers and scans the text, using the same rules as the demo offers. It does not contact any merchant.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="text-sm">Seller name<input className={inp} value={f.merchant} maxLength={120} onChange={(e) => setF({ ...f, merchant: e.target.value })} /></label>
          <label className="text-sm">Product name<input className={inp} value={f.name} maxLength={200} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
          <label className="text-sm">Product category<input className={inp} value={f.category} maxLength={80} placeholder="wireless headphones" onChange={(e) => setF({ ...f, category: e.target.value })} /></label>
          <label className="text-sm">Currency<select className={inp} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label className="text-sm">Product price<input className={inp} inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></label>
          <label className="text-sm">Shipping<input className={inp} inputMode="decimal" value={f.ship} onChange={(e) => setF({ ...f, ship: e.target.value })} /></label>
          <label className="text-sm">Tax<input className={inp} inputMode="decimal" value={f.tax} onChange={(e) => setF({ ...f, tax: e.target.value })} /></label>
          <label className="text-sm">Total the seller states (optional)<input className={inp} inputMode="decimal" value={f.claimed} onChange={(e) => setF({ ...f, claimed: e.target.value })} /></label>
        </div>
        <fieldset className="mt-3 flex flex-wrap items-center gap-4 text-sm"><legend className="sr-only">Disclosures the seller makes</legend><span className="font-medium">Seller discloses:</span>
          {DISCLOSURES.map((d) => <label key={d} className="flex items-center gap-1"><input type="checkbox" checked={f.disclosures.includes(d)} onChange={() => toggle(d)} />{d}</label>)}
          <label className="flex items-center gap-1"><input type="checkbox" checked={f.recurring} onChange={(e) => setF({ ...f, recurring: e.target.checked })} />Recurring billing</label></fieldset>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="text-sm">Description (seller text)<textarea className={inp} rows={2} maxLength={5000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
          <label className="text-sm">Terms (seller text)<textarea className={inp} rows={2} maxLength={5000} value={f.terms} onChange={(e) => setF({ ...f, terms: e.target.value })} /></label>
        </div>
        <div className="mt-3 flex gap-2"><Btn onClick={inspectCustom} disabled={act.busy}>Inspect my offer</Btn><Btn kind="ghost" onClick={() => setF(BLANK)}>Clear form</Btn></div>
      </details>
      {offerId && rec.loading && <Loading />}
      {offerId && <ErrorBox msg={rec.error} />}
      {!offerId && <Empty>No offer inspected yet. Pick a scenario or enter your own above.</Empty>}
      {o && item && rec.data && <Panel title="Offer details" action={<Badge tone={o.synthetic ? "amber" : "slate"}>{rec.data.data_origin}</Badge>}>
        <dl>
          <Row k="Product" v={item.name} /><Row k="Merchant" v={o.merchant} /><Row k="Product price" v={money(item.unit_price, o.currency)} />
          <Row k="Currency" v={o.currency} /><Row k="Shipping" v={money(o.shipping, o.currency)} /><Row k="Tax" v={money(o.tax, o.currency)} />
          <Row k="Total stated by merchant" v={money(o.claimed_total, o.currency)} />
          <Row k="Recurring billing" v={o.recurring_billing || item.recurring ? <Badge tone="red">Yes</Badge> : "None declared"} />
          <Row k="Disclosures present" v={o.disclosures.join(", ") || "none"} />
          <Row k="Terms" v={o.terms || "none provided"} /><Row k="Description" v={o.description || "none provided"} />
          <Row k="Threat findings" v={rec.data.threats.length === 0 ? "none" : <Badge tone={rec.data.threats.some((t) => t.severity === "high") ? "red" : "amber"}>{rec.data.threats.length} (see Threats page)</Badge>} />
        </dl>
        <p className="mt-2 text-xs text-slate-600">Merchant text is untrusted. It is shown as plain text and never followed as instructions.</p>
        <h3 className="mt-4 text-sm font-semibold">Selected cart</h3>
        <div className="mt-2 grid gap-3 md:grid-cols-3">
          <label className="text-sm">Quantity<input className={inp} inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} /></label>
          <label className="text-sm">Cart unit price ({o.currency})<input className={inp} inputMode="decimal"
            value={cartPrice ?? (item.unit_price / 100).toFixed(2)} onChange={(e) => setCartPrice(e.target.value)} /></label>
        </div>
        <p className="mt-1 text-xs text-slate-600">The cart price starts from the offer. You can change it to see the engine catch a cart price that differs from the offer.</p>
        <div className="mt-3">{!intentId || (intent.data && intent.data.status !== "CONFIRMED")
          ? <Need what="Confirm an Intent Passport first." to="/intent" label="Go to Intent Passport" />
          : <Btn onClick={startTx} disabled={act.busy || intent.loading}>Verify against my intent</Btn>}</div>
      </Panel>}
    </Page>
  );
}
