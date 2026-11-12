import { api } from "../services/api";
import { useLoad } from "../hooks/useAsync";
import { useSession } from "../context/Session";
import { ErrorBox } from "./ui";
import { when } from "../utils/format";

/** Lets the user switch to any earlier transaction. Everything shown comes from the backend database. */
export default function TxPicker() {
  const { transactionId, set } = useSession();
  const list = useLoad(() => api.transactions(20), []);
  const items = list.data?.transactions ?? [];
  if (list.error) return <ErrorBox msg={list.error} />;
  if (items.length === 0) return null;
  const choose = (id: string) => {
    const t = items.find((x) => x.id === id);
    if (t) set({ transactionId: t.id, intentId: t.intent_id, offerId: t.offer_id });
  };
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor="txpick" className="font-medium">Transaction</label>
      <select id="txpick" className="max-w-full rounded border border-slate-300 bg-white px-2 py-1.5" value={transactionId} onChange={(e) => choose(e.target.value)}>
        {!items.some((t) => t.id === transactionId) && <option value="">Choose a transaction…</option>}
        {items.map((t) => <option key={t.id} value={t.id}>{when(t.created_at)} · {t.merchant} · {t.decision}</option>)}
      </select>
    </div>
  );
}
