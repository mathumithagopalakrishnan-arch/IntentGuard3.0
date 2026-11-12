import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../services/api";
import { useSession } from "../context/Session";
import type { Payment } from "../types";
import { Badge, ErrorBox, Loading, Mono, Page, Panel, Row } from "../components/ui";
import { PAYMENT_LABEL, money, paymentTone } from "../utils/format";

/** PayPal sends the buyer here with ?token=<order id>. The backend re-checks the order with PayPal before capturing. */
export default function CheckoutReturn() {
  const { tid = "" } = useParams();
  const [q] = useSearchParams();
  const { set } = useSession();
  const [pay, setPay] = useState<Payment | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(true);
  const started = useRef(false);
  const token = q.get("token") ?? "";

  const run = () => {
    setBusy(true); setErr("");
    api.capture(tid, token).then(setPay).catch((e: Error) => setErr(e.message)).finally(() => setBusy(false));
  };
  useEffect(() => {
    if (started.current) return; // React dev mode runs effects twice; one capture request only
    started.current = true;
    set({ transactionId: tid });
    if (!token) { setBusy(false); setErr("PayPal did not return an order id."); return; }
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Page title="Finishing your PayPal Sandbox payment" intro="The backend is asking PayPal for the authoritative order, checking the amount, currency and your consent, and only then capturing.">
      {busy && <Loading label="Confirming with PayPal Sandbox…" />}
      <ErrorBox msg={err} />
      {err && <Panel title="Payment was not confirmed"><p className="text-sm text-slate-700">If PayPal could not be reached, retrying is safe: the backend reuses the same request id to prevent a duplicate capture. Check the recorded payment state and Sandbox account before starting a new transaction.</p>
        <div className="mt-3 flex gap-2">{token && <button type="button" className="rounded bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={run} disabled={busy}>{busy ? "Retrying…" : "Try again"}</button>}<Link className="rounded border border-slate-300 px-4 py-2 text-sm font-semibold" to="/checkout">Back to checkout</Link></div></Panel>}
      {pay && <Panel title="Result" action={<Badge tone={paymentTone(pay.state)}>{PAYMENT_LABEL[pay.state] ?? pay.state}</Badge>}>
        <dl><Row k="Amount" v={money(pay.amount_minor, pay.currency)} /><Row k="PayPal Sandbox order" v={<Mono>{pay.paypal_order_id ?? "—"}</Mono>} />{pay.capture_id && <Row k="Capture" v={<Mono>{pay.capture_id}</Mono>} />}</dl>
        <div className="mt-3 flex gap-2"><Link className="rounded bg-navy-900 px-4 py-2 text-sm font-semibold text-white" to="/checkout">View payment and receipt</Link><Link className="rounded border border-slate-300 px-4 py-2 text-sm font-semibold" to="/audit">Audit trail</Link></div>
      </Panel>}
    </Page>
  );
}
