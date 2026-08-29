import { formatBRL } from "@/lib/format";
import { signedMoneyToCents } from "@/lib/cash";

export function CashStatus({ status }: { status: "open" | "closed" | "cancelled" }) {
  const label = status === "open" ? "Aberta" : status === "cancelled" ? "Anulada" : "Fechada";
  const tone = status === "open" ? "bg-success/10 text-emerald-700" : status === "cancelled" ? "bg-danger/10 text-danger" : "bg-slate-100 text-slate-500";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${tone}`}>{label}</span>;
}

export function DifferenceBadge({ value }: { value: string }) {
  const cents = signedMoneyToCents(value) || BigInt(0);
  const state = cents > BigInt(0) ? "Sobra" : cents < BigInt(0) ? "Falta" : "Conferido";
  const colors = cents > BigInt(0) ? "bg-success/10 text-emerald-700" : cents < BigInt(0) ? "bg-danger/10 text-red-700" : "bg-primary/10 text-primary";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${colors}`}>{state}: {formatBRL(value)}</span>;
}

export function MoneyKpi({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "success" | "danger" | "primary" }) {
  const tones = { default: "text-dark", success: "text-emerald-700", danger: "text-red-700", primary: "text-primary" };
  return <div className="card p-5"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p><p className={`mt-2 text-xl font-bold ${tones[tone]}`}>{formatBRL(value)}</p></div>;
}
