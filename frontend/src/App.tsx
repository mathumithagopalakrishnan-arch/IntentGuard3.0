import { useEffect, useState, type FormEvent } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { api } from "./services/api";
import { ErrorBox, Loading } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import Home from "./pages/Home";
import Checkout from "./pages/Checkout";
import CheckoutReturn from "./pages/CheckoutReturn";
import CheckoutCancel from "./pages/CheckoutCancel";
import Simulator from "./pages/Simulator";
import IntentPassport from "./pages/IntentPassport";
import Offers from "./pages/Offers";
import Threats from "./pages/Threats";
import Integrity from "./pages/Integrity";
import Consent from "./pages/Consent";
import Audit from "./pages/Audit";

const NAV: [string, string][] = [["/", "Home"], ["/intent", "Intent"], ["/offers", "Offer"], ["/integrity", "Verify"], ["/consent", "Consent"], ["/checkout", "PayPal Checkout"], ["/audit", "Audit & Receipt"], ["/simulator", "Attack Simulator"], ["/threats", "Scanner"], ["/dashboard", "Dashboard"]];

export default function App() {
  const [authorized, setAuthorized] = useState(false);
  const [checking, setChecking] = useState(true);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const saved = window.sessionStorage.getItem("intentguard.apiToken");
    if (!saved) { setChecking(false); return; }
    setToken(saved);
    api.health().then(() => setAuthorized(true)).catch((e: Error) => {
      if (e.message === "A valid Bearer token is required.") {
        window.sessionStorage.removeItem("intentguard.apiToken");
        setToken("");
      }
      setError(e.message);
    }).finally(() => setChecking(false));
  }, []);

  const unlock = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setChecking(true);
    setError("");
    window.sessionStorage.setItem("intentguard.apiToken", token);
    try {
      await api.health();
      setAuthorized(true);
    } catch (e) {
      window.sessionStorage.removeItem("intentguard.apiToken");
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  };

  const lock = () => {
    window.sessionStorage.removeItem("intentguard.apiToken");
    setAuthorized(false);
    setToken("");
  };

  if (!authorized) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md items-center px-4">
        <section className="w-full space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 text-lg font-semibold"><ShieldCheck className="h-6 w-6 text-brand-600" aria-hidden />IntentGuard</div>
          <p className="text-sm text-slate-600">Enter the local API access token configured in backend/.env. It is kept only for this browser tab session.</p>
          <ErrorBox msg={error} />
          {checking && <Loading label="Checking API access…" />}
          <form onSubmit={unlock} className="space-y-3">
            <label htmlFor="api-token" className="block text-sm font-medium">API access token</label>
            <input id="api-token" type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm" required minLength={32} />
            <button type="submit" disabled={checking || token.length < 32} className="rounded bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Unlock local app</button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only">Skip to content</a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-6 w-6 text-brand-600" aria-hidden />IntentGuard
            <span className="ml-2 rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900 ring-1 ring-amber-600/30">Hackathon prototype · PayPal Sandbox (test money) · demo data is synthetic</span></div>
          <div className="flex items-center gap-2">
            <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto">
              {NAV.map(([to, label]) => (
                <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `whitespace-nowrap rounded px-3 py-1.5 text-sm font-medium ${isActive ? "bg-navy-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}>{label}</NavLink>))}
            </nav>
            <button type="button" onClick={lock} className="shrink-0 rounded border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50">Lock</button>
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Home />} /><Route path="/dashboard" element={<Dashboard />} /><Route path="/checkout" element={<Checkout />} /><Route path="/checkout/return/:tid" element={<CheckoutReturn />} /><Route path="/checkout/cancel/:tid" element={<CheckoutCancel />} /><Route path="/simulator" element={<Simulator />} /><Route path="/intent" element={<IntentPassport />} /><Route path="/offers" element={<Offers />} />
          <Route path="/threats" element={<Threats />} /><Route path="/integrity" element={<Integrity />} /><Route path="/consent" element={<Consent />} />
          <Route path="/audit" element={<Audit />} /><Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-500">
        IntentGuard is an independent hackathon prototype, not endorsed by PayPal. Payments use the PayPal Sandbox only (test money). It contacts no real merchant. Demo offers are synthetic. A matching hash proves data is unchanged, not that a seller is honest.
      </footer>
    </div>
  );
}
