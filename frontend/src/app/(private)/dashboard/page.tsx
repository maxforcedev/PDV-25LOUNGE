"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Banknote, Boxes, CreditCard, ReceiptText, ShoppingBasket, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, EmptyState, TableLoading } from "@/components/ui";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { useAuth } from "@/providers/auth-provider";
import type { DashboardData } from "@/types";

function today(): PeriodValue {
  const now = new Date(); const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  return { start: `${date}T00:00`, end: `${date}T23:59` };
}
function Kpi({ label, value, note, icon: Icon }: { label: string; value: string | number; note?: string; icon: typeof TrendingUp }) {
  return <article className="card p-5"><div className="flex items-start justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[.14em] text-slate-400">{label}</p><strong className="mt-3 block text-2xl text-dark">{value}</strong>{note && <span className="mt-1 block text-[11px] text-slate-500">{note}</span>}</div><span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span></div></article>;
}

export default function DashboardPage() {
  const { currentBranch } = useAuth(); const context = useRef(""); context.current = String(currentBranch?.id || "");
  const [period, setPeriod] = useState<PeriodValue>(today); const [data, setData] = useState<DashboardData | null>(null); const [error, setError] = useState("");
  async function load(next = period, token = context.current) {
    if (!currentBranch) return; setData(null); setError("");
    const params = new URLSearchParams({ start_datetime: next.start, end_datetime: next.end });
    try { const result = await http.get<DashboardData>(`dashboard/?${params}`); if (context.current === token) setData(result); }
    catch (caught) { if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o painel."); }
  }
  useEffect(() => { const next = today(); setPeriod(next); void load(next, context.current); }, [currentBranch?.id]);
  const cards = data ? [
    ...(data.sales ? [{ label: "Faturamento", value: formatBRL(data.sales.revenue), note: `${data.sales.count} vendas`, icon: TrendingUp }, { label: "Ticket médio", value: formatBRL(data.sales.average), note: `Descontos ${formatBRL(data.sales.total_discount)}`, icon: ReceiptText }] : []),
    ...(data.consumptions ? [{ label: "Consumação cobrada", value: formatBRL(data.consumptions.charged), note: `Referência ${formatBRL(data.consumptions.reference)}`, icon: ShoppingBasket }] : []),
    ...(data.withdrawals ? [{ label: "Sangrias", value: formatBRL(data.withdrawals.amount), note: `${data.withdrawals.count} registros`, icon: Banknote }] : []),
    ...(data.inventory?.inventory_value !== undefined ? [{ label: "Valor em estoque", value: formatBRL(data.inventory.inventory_value), note: "Custo atual", icon: Boxes }] : []),
  ] : [];
  return <><PageHeader title="Visão operacional" description={`Indicadores da filial ${currentBranch?.name || "atual"}.`} />
    <div className="space-y-5 p-4 sm:p-6 lg:p-8"><section className="card p-4"><PeriodFilter value={period} onApply={(next) => { setPeriod(next); void load(next); }} /></section>{error && <Alert message={error} />}
      {!data ? <section className="card"><TableLoading /></section> : <>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{cards.map((card) => <Kpi key={card.label} {...card} />)}</div>
        {data.inventory && <div className="grid gap-4 sm:grid-cols-2"><Kpi label="Produtos zerados" value={data.inventory.zero_count} icon={Boxes} /><Kpi label="Abaixo do mínimo" value={data.inventory.below_minimum_count} icon={Boxes} /></div>}
        <div className="grid gap-5 xl:grid-cols-2">
          {data.sales && <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Distribuição por pagamento</h2><CreditCard className="size-5 text-primary" /></div>{data.sales.payment_distribution.length ? <div className="divide-y divide-slate-100">{data.sales.payment_distribution.map((row) => <div key={row.code} className="flex justify-between px-5 py-3 text-sm"><span>{row.name}</span><strong>{formatBRL(row.amount)}</strong></div>)}</div> : <EmptyState title="Sem pagamentos" description="Nenhuma venda comercial no período." />}</section>}
          {data.current_cash && <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Caixa atual</h2><Banknote className="size-5 text-primary" /></div>{data.current_cash.length ? <div className="divide-y divide-slate-100">{data.current_cash.map((row) => <div key={row.id} className="px-5 py-4"><div className="flex justify-between"><strong>{row.register.name}</strong><span className="text-xs text-success">Aberto</span></div><div className="mt-2 flex justify-between text-xs text-slate-500"><span>Esperado</span><strong className="text-dark">{formatBRL(row.expected)}</strong></div></div>)}</div> : <EmptyState title="Nenhum caixa aberto" description="Não há sessão aberta nesta filial." />}</section>}
        </div>
        {data.sales && <div className="grid gap-5 xl:grid-cols-2"><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Produtos mais vendidos</h2></div><div className="divide-y divide-slate-100">{data.sales.top_products.slice(0, 8).map((row, index) => <div key={`${row.product_name}-${index}`} className="flex justify-between px-5 py-3 text-sm"><span>{row.product_name}</span><span>{formatQuantity(row.quantity)} · <strong>{formatBRL(row.revenue)}</strong></span></div>)}</div></section><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Categorias mais vendidas</h2></div><div className="divide-y divide-slate-100">{data.sales.top_categories.slice(0, 8).map((row, index) => <div key={`${row.category_name}-${index}`} className="flex justify-between px-5 py-3 text-sm"><span>{row.category_name}</span><span>{formatQuantity(row.quantity)} · <strong>{formatBRL(row.revenue)}</strong></span></div>)}</div></section></div>}
        {data.sales && <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Últimas vendas</h2><Link href="/vendas" className="text-xs font-bold text-primary">Ver todas</Link></div><div className="divide-y divide-slate-100">{data.sales.latest_sales.map((sale) => <Link key={sale.id} href={`/vendas/${sale.id}`} className="flex justify-between px-5 py-3 text-sm hover:bg-slate-50"><span><strong>{sale.sale_number}</strong><small className="ml-2 text-slate-400">{formatDate(sale.created_at)}</small></span><strong>{formatBRL(sale.total)}</strong></Link>)}</div></section>}
      </>}
    </div></>;
}
