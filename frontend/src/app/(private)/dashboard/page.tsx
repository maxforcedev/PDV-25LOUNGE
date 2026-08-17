"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Banknote, Boxes, Clock3, CreditCard, ReceiptText, ShoppingBasket, TrendingUp, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, EmptyState, TableLoading } from "@/components/ui";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { useAuth } from "@/providers/auth-provider";
import type { DashboardData } from "@/types";

function today(): PeriodValue {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  return { start: `${date}T00:00`, end: `${date}T23:59` };
}

function Kpi({ label, value, note, icon: Icon, href }: { label: string; value: string | number; note?: string; icon: typeof TrendingUp; href?: string }) {
  const content = <article className="card h-full p-5 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[.14em] text-slate-400">{label}</p><strong className="mt-3 block text-2xl text-dark">{value}</strong>{note && <span className="mt-1 block text-[11px] text-slate-500">{note}</span>}</div><span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span></div></article>;
  return href ? <Link href={href} className="block h-full">{content}</Link> : content;
}

function BarChart({ title, icon: Icon, rows, empty }: { title: string; icon: typeof TrendingUp; rows: Array<{ label: string; value: number; display: string; note?: string }>; empty: string }) {
  const max = Math.max(...rows.map((row) => row.value), 0);
  return <section className="card overflow-hidden"><div className="card-header"><h2 className="flex items-center gap-2 text-sm font-bold"><Icon className="size-4 text-primary" />{title}</h2></div>{rows.length ? <div className="space-y-4 p-5">{rows.map((row) => <div key={row.label}><div className="mb-1.5 flex items-end justify-between gap-3 text-xs"><span className="min-w-0 truncate font-semibold">{row.label}<small className="ml-1 text-[10px] font-normal text-slate-400">{row.note}</small></span><strong>{row.display}</strong></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-primary to-blue-400 transition-all" style={{ width: `${max ? Math.max(3, row.value / max * 100) : 0}%` }} /></div></div>)}</div> : <EmptyState title="Sem dados" description={empty} />}</section>;
}

export default function DashboardPage() {
  const { currentBranch } = useAuth();
  const context = useRef("");
  context.current = String(currentBranch?.id || "");
  const [period, setPeriod] = useState<PeriodValue>(today);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  async function load(next = period, token = context.current) {
    if (!currentBranch) return;
    setData(null); setError("");
    const params = new URLSearchParams({ start_datetime: next.start, end_datetime: next.end });
    try {
      const result = await http.get<DashboardData>(`dashboard/?${params}`);
      if (context.current === token) setData(result);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o painel.");
    }
  }

  useEffect(() => { const next = today(); setPeriod(next); void load(next, context.current); }, [currentBranch?.id]);
  const periodParams = new URLSearchParams({ start_datetime: period.start, end_datetime: period.end });
  const reportHref = (extra = "") => `/relatorios?${periodParams}${extra}`;
  const sales = data?.sales;
  const cards = data ? [
    ...(sales ? [
      { label: "Valor bruto", value: formatBRL(sales.gross), note: `${sales.count} vendas`, icon: TrendingUp, href: reportHref("&report=sales") },
      { label: "Faturamento efetivo", value: formatBRL(sales.effective_revenue), note: `Descontos ${formatBRL(sales.total_discount)}`, icon: ReceiptText, href: reportHref("&report=sales") },
      { label: "Taxa de serviço", value: formatBRL(sales.service_fee), note: `Cobrado ${formatBRL(sales.customer_total)}`, icon: CreditCard, href: reportHref("&report=sales") },
      { label: "Comissão", value: formatBRL(sales.commission), note: "Vendas finalizadas", icon: Users, href: reportHref("&report=sales") },
    ] : []),
    ...(data.consumptions ? [{ label: "Consumação cobrada", value: formatBRL(data.consumptions.charged), note: `Referência ${formatBRL(data.consumptions.reference)}`, icon: ShoppingBasket, href: "/consumacoes" }] : []),
    ...(data.withdrawals ? [{ label: "Sangrias", value: formatBRL(data.withdrawals.amount), note: `${data.withdrawals.count} registros`, icon: Banknote, href: reportHref("&report=withdrawals") }] : []),
    ...(data.inventory?.inventory_value !== undefined ? [{ label: "Valor em estoque", value: formatBRL(data.inventory.inventory_value), note: "Custo atual", icon: Boxes, href: "/estoque" }] : []),
  ] : [];

  return <><PageHeader title="Visão operacional" description={`Indicadores da filial ${currentBranch?.name || "atual"}.`} />
    <div className="space-y-5 p-4 sm:p-6 lg:p-8">
      <section className="card p-4"><PeriodFilter value={period} onApply={(next) => { setPeriod(next); void load(next); }} /></section>
      {error && <Alert message={error} />}
      {!data ? <section className="card"><TableLoading /></section> : <>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{cards.map((card) => <Kpi key={card.label} {...card} />)}</div>
        {data.inventory && <div className="grid gap-4 sm:grid-cols-3"><Kpi label="Saldo negativo" value={data.inventory.negative_count} icon={Boxes} href="/estoque?state=negative" /><Kpi label="Produtos zerados" value={data.inventory.zero_count} icon={Boxes} href="/estoque?state=zero" /><Kpi label="Abaixo do mínimo" value={data.inventory.below_minimum_count} icon={Boxes} href="/estoque?state=below_minimum" /></div>}
        {sales && <div className="grid gap-5 xl:grid-cols-2">
          <BarChart title="Faturamento e vendas por hora" icon={Clock3} empty="Nenhuma venda no período." rows={sales.hourly_sales.map((row) => ({ label: new Date(row.hour).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }), value: Number(row.customer_total), display: formatBRL(row.customer_total), note: `${row.count} venda${row.count === 1 ? "" : "s"}` }))} />
          <BarChart title="Formas de pagamento" icon={CreditCard} empty="Nenhum pagamento no período." rows={sales.payment_distribution.map((row) => ({ label: row.name, value: Number(row.amount), display: formatBRL(row.amount) }))} />
          <BarChart title="Produtos mais vendidos" icon={ShoppingBasket} empty="Nenhum produto vendido." rows={sales.top_products.slice(0, 8).map((row) => ({ label: row.product_name, value: Number(row.revenue), display: formatBRL(row.revenue), note: formatQuantity(row.quantity) }))} />
          <BarChart title="Atendentes" icon={Users} empty="Nenhuma venda atribuída." rows={sales.top_sellers.slice(0, 8).map((row) => ({ label: row.user.name, value: Number(row.customer_total), display: formatBRL(row.customer_total), note: `${row.count} venda${row.count === 1 ? "" : "s"}` }))} />
        </div>}
        <div className="grid gap-5 xl:grid-cols-2">
          {data.current_cash && <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Caixa atual</h2><Banknote className="size-5 text-primary" /></div>{data.current_cash.length ? <div className="divide-y divide-slate-100">{data.current_cash.map((row) => <div key={row.id} className="px-5 py-4"><div className="flex justify-between"><strong>{row.register.name}</strong><span className="text-xs text-success">Aberto</span></div><div className="mt-2 flex justify-between text-xs text-slate-500"><span>Esperado</span><strong className="text-dark">{formatBRL(row.expected)}</strong></div></div>)}</div> : <EmptyState title="Nenhum caixa aberto" description="Não há sessão aberta nesta filial." />}</section>}
          {sales && <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Últimas vendas</h2><Link href={`/vendas?${periodParams}`} className="text-xs font-bold text-primary">Ver todas</Link></div>{sales.latest_sales.length ? <div className="divide-y divide-slate-100">{sales.latest_sales.map((sale) => <Link key={sale.id} href={`/vendas/${sale.id}`} className="flex justify-between px-5 py-3 text-sm hover:bg-slate-50"><span><strong>{sale.sale_number}</strong><small className="ml-2 text-slate-400">{sale.seller?.name || sale.operator.name} · {formatDate(sale.created_at)}</small></span><strong>{formatBRL(sale.total)}</strong></Link>)}</div> : <EmptyState title="Sem vendas" description="Nenhuma venda comercial no período." />}</section>}
        </div>
      </>}
    </div>
  </>;
}
