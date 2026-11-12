import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Loader2, AlertCircle } from "lucide-react";

export type Tone = "green" | "amber" | "red" | "blue" | "slate";
const TONES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-600/30", amber: "bg-amber-50 text-amber-900 ring-amber-600/30",
  red: "bg-red-50 text-red-800 ring-red-600/30", blue: "bg-brand-50 text-brand-600 ring-brand-600/30", slate: "bg-slate-100 text-slate-700 ring-slate-400/30",
};
export const Badge = ({ tone, children }: { tone: Tone; children: ReactNode }) =>
  <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${TONES[tone]}`}>{children}</span>;

export const Panel = ({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) => (
  <section className="rounded-lg border border-slate-200 bg-white p-5">
    <div className="mb-3 flex items-center justify-between gap-3"><h2 className="text-base font-semibold">{title}</h2>{action}</div>{children}
  </section>
);
export const Page = ({ title, intro, children }: { title: string; intro: string; children: ReactNode }) => (
  <div className="space-y-5"><header><h1 className="text-xl font-semibold">{title}</h1><p className="mt-1 max-w-3xl text-sm text-slate-600">{intro}</p></header>{children}</div>
);
export const Loading = ({ label = "Loading…" }: { label?: string }) =>
  <p role="status" className="flex items-center gap-2 text-sm text-slate-600"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{label}</p>;
export const ErrorBox = ({ msg }: { msg: string }) => msg ? (
  <p role="alert" className="flex items-start gap-2 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{msg}</p>) : null;
export const Empty = ({ children }: { children: ReactNode }) => <p className="rounded border border-dashed border-slate-300 p-4 text-sm text-slate-600">{children}</p>;
export const Need = ({ what, to, label }: { what: string; to: string; label: string }) =>
  <Empty>{what} <Link className="font-semibold text-brand-600 underline" to={to}>{label}</Link></Empty>;
export const Btn = ({ children, onClick, disabled, kind = "primary" }: { children: ReactNode; onClick: () => void; disabled?: boolean; kind?: "primary" | "ghost" | "danger" }) => (
  <button type="button" onClick={onClick} disabled={disabled}
    className={`rounded px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${kind === "primary" ? "bg-brand-600 text-white hover:bg-blue-700" : kind === "danger" ? "bg-red-700 text-white hover:bg-red-800" : "border border-slate-300 bg-white hover:bg-slate-50"}`}>{children}</button>);
export const Row = ({ k, v }: { k: string; v: ReactNode }) =>
  <div className="flex justify-between gap-4 border-b border-slate-100 py-1.5 text-sm last:border-0"><dt className="text-slate-600">{k}</dt><dd className="text-right font-medium break-all">{v}</dd></div>;
export const Mono = ({ children }: { children: ReactNode }) => <code className="break-all rounded bg-slate-100 px-1.5 py-0.5 text-xs">{children}</code>;
