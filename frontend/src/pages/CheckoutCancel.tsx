import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../services/api";
import { useSession } from "../context/Session";
import { ErrorBox, Page, Panel } from "../components/ui";

export default function CheckoutCancel() {
  const { tid = "" } = useParams();
  const { set } = useSession();
  const [err, setErr] = useState("");
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    set({ transactionId: tid });
    api.checkoutCancelled(tid).catch((e: Error) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Page title="PayPal approval cancelled" intro="You left PayPal without approving. No money was captured.">
      <ErrorBox msg={err} />
      <Panel title="What next?"><p className="text-sm text-slate-700">The order is still open until your approval expires, so you can try PayPal again, or cancel the payment for good.</p>
        <div className="mt-3"><Link className="rounded bg-navy-900 px-4 py-2 text-sm font-semibold text-white" to="/checkout">Back to checkout</Link></div></Panel>
    </Page>
  );
}
