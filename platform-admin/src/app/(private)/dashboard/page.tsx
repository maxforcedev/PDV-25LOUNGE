"use client";

import Link from "next/link";
import { ArrowUpRight, Building2, CalendarClock, CircleDollarSign, ClockAlert, FlaskConical, ShieldAlert, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorBlock, LoadingBlock } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import type { DashboardMetrics } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

export default function DashboardPage() {
  const { can } = useAuth();
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => { let active = true; api.get<DashboardMetrics>("platform/dashboard/").then((value) => { if (active) setData(value); }).catch((value) => { if (active) setError(value); }); return () => { active = false; }; }, [reload]);
  if (!can("platform.dashboard.view")) return <ErrorBlock error={new Error("Seu perfil nao possui acesso ao painel operacional.")} />;
  if (error) return <ErrorBlock error={error} retry={() => { setError(null); setReload((value) => value + 1); }} />;
  if (!data) return <LoadingBlock label="Consolidando indicadores da plataforma" />;
  const cards = [
    { label: "Tenants ativos", value: data.active_tenants, icon: Building2, tone: "bg-ink text-white" },
    { label: "Clientes pagantes", value: data.paying_customers, icon: Users },
    { label: "MRR contratado", value: money(data.contracted_mrr), icon: CircleDollarSign, wide: true },
    { label: "Novos no mes", value: data.new_tenants, icon: ArrowUpRight },
  ];
  return <div className="enter space-y-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Leitura consolidada</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Estado da plataforma</h1><p className="mt-2 text-sm text-steel/65">Indicadores correntes de operacao, receita e risco.</p></div><p className="font-mono text-[10px] uppercase tracking-wider text-steel/55">Atualizado nesta consulta</p></div>
    <section className="grid gap-px border border-line bg-line sm:grid-cols-2 xl:grid-cols-4">{cards.map(({ label, value, icon: Icon, tone }) => <div key={label} className={`min-h-40 p-5 ${tone || "bg-paper"}`}><div className="flex items-start justify-between"><p className={`font-mono text-[10px] font-bold uppercase tracking-[.12em] ${tone ? "text-white/55" : "text-steel/55"}`}>{label}</p><Icon size={19} className={tone ? "text-signal" : "text-steel/45"} /></div><p className="mt-10 text-3xl font-black tracking-tight">{value}</p></div>)}</section>
    <div className="grid gap-6 xl:grid-cols-[1.4fr_.6fr]"><section className="panel"><div className="panel-head"><div><p className="eyebrow">Composicao da base</p><h2 className="mt-1 font-bold">Distribuicao comercial</h2></div></div><div className="grid gap-px bg-line sm:grid-cols-3"><Metric label="Pago" value={data.paying_customers} /><Metric label="Gratuito" value={data.free} /><Metric label="Interno" value={data.internal} /></div><div className="grid gap-px border-t border-line bg-line sm:grid-cols-3"><Metric label="Trials ativos" value={data.active_trials} icon={<FlaskConical size={16} />} /><Metric label="Trials expirados" value={data.expired_trials} icon={<ClockAlert size={16} />} warning={data.expired_trials > 0} /><Metric label="Cancelamentos agendados" value={data.scheduled_cancellations} icon={<CalendarClock size={16} />} warning={data.scheduled_cancellations > 0} /></div></section>
      <section className="border border-ink bg-ink p-5 text-white"><p className="eyebrow !text-white/45">Fila de atencao</p><div className="mt-8 flex items-end justify-between"><div><p className="text-5xl font-black text-signal">{data.past_due}</p><p className="mt-2 text-sm text-white/60">tenants em risco financeiro</p></div><ShieldAlert size={28} className="text-white/30" /></div>{can("platform.tenants.manage") && <Link href="/tenants" className="mt-8 flex h-11 items-center justify-between border-t border-white/15 pt-4 text-xs font-bold uppercase tracking-wider hover:text-signal">Revisar tenants <ArrowUpRight size={16} /></Link>}</section></div>
  </div>;
}

function Metric({ label, value, icon, warning }: { label: string; value: number; icon?: React.ReactNode; warning?: boolean }) {
  return <div className="bg-paper p-5"><div className="flex items-center justify-between text-steel/50"><p className="eyebrow">{label}</p>{icon}</div><p className={`mt-5 text-2xl font-black ${warning ? "text-alert" : ""}`}>{value}</p></div>;
}
