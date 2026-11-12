import { useCallback, useEffect, useRef, useState } from "react";

/** Loads data when `deps` change. A slow old response can never overwrite a newer one. */
export function useLoad<R>(fn: (() => Promise<R>) | null, deps: unknown[]) {
  const [data, setData] = useState<R | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(() => {
    const id = ++seq.current;
    if (!fn) { setData(null); setError(""); setLoading(false); return; }
    setLoading(true); setError("");
    fn()
      .then((d) => { if (id === seq.current) setData(d); })
      .catch((e: Error) => { if (id === seq.current) { setData(null); setError(e.message); } })
      .finally(() => { if (id === seq.current) setLoading(false); });
  }, deps);
  useEffect(run, [run]);
  return { data, error, loading, reload: run };
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const go = async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
    setBusy(true); setError("");
    try { return await fn(); } catch (e) { setError((e as Error).message); return undefined; } finally { setBusy(false); }
  };
  return { busy, error, go };
}
