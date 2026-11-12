import { createContext, useContext, useState, type ReactNode } from "react";

// Only record IDs live in the browser. All data and decisions live in the backend database.
interface Ids { intentId: string; offerId: string; transactionId: string }
interface Ctx extends Ids { set: (p: Partial<Ids>) => void; clear: () => void }
const KEY = "intentguard.ids";
const EMPTY: Ids = { intentId: "", offerId: "", transactionId: "" };
const Session = createContext<Ctx>({ ...EMPTY, set: () => {}, clear: () => {} });

function load(): Ids {
  try { return { ...EMPTY, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; } catch { return EMPTY; }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<Ids>(load);
  const save = (n: Ids) => { setIds(n); try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } };
  return <Session.Provider value={{ ...ids, set: (p: Partial<Ids>) => save({ ...ids, ...p }), clear: () => save(EMPTY) }}>{children}</Session.Provider>;
}
export const useSession = () => useContext(Session);
