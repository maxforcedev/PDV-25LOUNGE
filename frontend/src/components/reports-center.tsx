"use client";

import Link from "next/link";
import { Banknote, Boxes, ReceiptText } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { phaseOneReportGroups } from "@/lib/report-presentation";
import { useAuth } from "@/providers/auth-provider";

const icons = { Vendas: ReceiptText, Financeiro: Banknote, Estoque: Boxes } as const;

export function ReportsCenter() {
  const { currentBranch, hasPermission } = useAuth();
  return <><PageHeader title="Central de Relatórios" description={`Análises dedicadas de ${currentBranch?.name || "sua filial"}.`} /><div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-2 lg:p-8 xl:grid-cols-3">{phaseOneReportGroups.map((group) => { const reports = group.reports.filter((item) => hasPermission(item.permission)); if (!reports.length) return null; const Icon = icons[group.title]; return <section key={group.title} className="card overflow-hidden"><div className="card-header"><div className="flex items-center gap-3"><span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span><div><h2 className="text-sm font-bold">{group.title}</h2><p className="mt-1 text-[11px] text-slate-500">{group.description}</p></div></div></div><div className="divide-y divide-slate-100">{reports.map((report) => <Link key={report.href} href={report.href} className="flex items-center justify-between gap-4 px-5 py-3.5 text-sm font-semibold transition hover:bg-slate-50"><span>{report.label}</span><span className="shrink-0 text-primary">Ver relatório</span></Link>)}</div></section>; })}</div></>;
}
