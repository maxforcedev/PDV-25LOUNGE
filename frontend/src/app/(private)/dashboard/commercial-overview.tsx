"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3, CircleDollarSign, CreditCard, PackageSearch, ReceiptText, ShoppingBasket, TrendingUp, type LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/ui";
import { signedMoneyToCents } from "@/lib/cash";
import { decimalCompare, decimalIsZero, formatDate, formatDecimalBRL as formatBRL, formatPercent, formatQuantity } from "@/lib/format";
import { domainLabel } from "@/lib/domain-labels";
import type { DashboardComparisonDelta, DashboardData } from "@/types";

type Sales = NonNullable<DashboardData["sales"]>;

function positiveMoneyCents(value: unknown) {
  const cents = signedMoneyToCents(value);
  return cents !== null && cents > BigInt(0) ? cents : BigInt(0);
}

function ratioPercent(value: bigint, total: bigint) {
  if (value <= BigInt(0) || total <= BigInt(0)) return 0;
  return Number((value * BigInt(10_000)) / total) / 100;
}

function MetricCard({ label, value, note, icon: Icon, href, tone = "primary", trend }: { label: string; value: string; note: string; icon: LucideIcon; href?: string; tone?: "primary" | "success" | "danger" | "muted"; trend?: DashboardComparisonDelta }) {
  const tones = {
    primary: "bg-primary/10 text-primary",
    success: "bg-success/10 text-success-strong",
    danger: "bg-danger/10 text-danger-strong",
    muted: "bg-surface-muted text-muted",
  };
  const trendLabel = trend?.comparable && trend.percentage !== null ? `${trend.direction === "up" ? "+" : ""}${formatPercent(trend.percentage)} vs. período anterior` : "Comparação preparada para o período anterior";
  const trendTone = trend?.direction === "down" ? "text-danger-strong" : trend?.direction === "up" ? "text-success-strong" : "text-muted";
  const TrendIcon = trend?.direction === "down" ? ArrowDownRight : trend?.direction === "up" ? ArrowUpRight : ArrowRight;
  const content = <div className="flex h-full flex-col"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-muted">{label}</p><strong className="mt-3 block break-words text-[clamp(1.45rem,2.4vw,2rem)] font-bold leading-none tracking-tight text-fg">{value}</strong></div><span className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}><Icon className="size-5" /></span></div><div className="mt-5 border-t border-subtle pt-3"><p className="text-[11px] text-muted">{note}</p><p className={`mt-1 flex items-center gap-1 text-[11px] font-semibold ${trendTone}`}><TrendIcon className="size-3.5" />{trendLabel}</p></div></div>;
  const className = `card min-h-52 p-5 ${href ? "transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25" : ""}`;
  return href ? <Link href={href} className={className}>{content}</Link> : <div className={className}>{content}</div>;
}

function SalesEvolution({ sales, href }: { sales: Sales; href?: string }) {
  const rows = sales.weekly_comparison.current;
  const max = rows.reduce((largest, row) => {
    const value = positiveMoneyCents(row.sales_revenue);
    return value > largest ? value : largest;
  }, BigInt(0));
  const hasRevenue = rows.some((row) => !decimalIsZero(row.sales_revenue));
  function dayHref(date: string) {
    if (!href) return "";
    const [pathname, query = ""] = href.split("?");
    const params = new URLSearchParams(query);
    params.set("start_datetime", `${date}T00:00:00`);
    params.set("end_datetime", `${date}T23:59:59`);
    return `${pathname}?${params}`;
  }
  return <section className="card overflow-hidden xl:col-span-2"><div className="card-header"><div><div className="flex items-center gap-2"><BarChart3 className="size-4 text-primary" /><h2 className="text-sm font-bold">Evolução de faturamento</h2></div><p className="mt-1 text-xs text-muted">Faturamento diário de vendas no período selecionado.</p></div>{href && <Link className="text-xs font-bold text-link" href={href}>Ver detalhes</Link>}</div>{hasRevenue ? <div className="overflow-x-auto px-5 pb-5 pt-7"><div className="flex h-64 min-w-150 items-end gap-2" aria-label="Faturamento diário no período">{rows.map((row) => { const style = { height: `${Math.max(4, ratioPercent(positiveMoneyCents(row.sales_revenue), max))}%` }; const label = `${row.date}: ${formatBRL(row.sales_revenue)}, ${row.count} vendas`; const bar = <span className="group relative block w-full rounded-t-md bg-chart-1 transition hover:brightness-110" style={style}><span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-max -translate-x-1/2 rounded-md bg-chart-tooltip px-2 py-1 text-[10px] text-chart-tooltip-fg opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-visible:opacity-100">{formatBRL(row.sales_revenue)} · {row.count} vendas</span></span>; return <div key={row.date} className="flex h-full min-w-10 flex-1 flex-col justify-end"><span className="mb-2 truncate text-center text-[9px] font-semibold text-muted">{formatBRL(row.sales_revenue)}</span>{href ? <Link href={dayHref(row.date)} aria-label={label} className="flex h-52 items-end focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus">{bar}</Link> : <div aria-label={label} className="flex h-52 items-end">{bar}</div>}<span className="mt-2 text-center text-[10px] text-muted">{row.date.slice(8, 10)}/{row.date.slice(5, 7)}</span></div>; })}</div></div> : <EmptyState title="Sem vendas" description="Nenhum faturamento foi registrado no período." />}</section>;
}

function PaymentPanel({ sales, href, available }: { sales: Sales; href?: string; available: DashboardData["availability"]["financial_receipts"] }) {
  const rows = sales.payment_distribution ?? [];
  const scope = sales.payment_distribution_scope === "operational" ? "Recebimentos operacionais" : "Recebimentos vinculados a vendas";
  return <section className="card overflow-hidden"><div className="card-header"><div><div className="flex items-center gap-2"><CreditCard className="size-4 text-primary" /><h2 className="text-sm font-bold">Formas de pagamento</h2></div><p className="mt-1 text-xs text-muted">{scope} no período.</p></div>{href && <Link className="text-xs font-bold text-link" href={href}>Relatório</Link>}</div>{available !== "available" ? <EmptyState title={available === "restricted" ? "Recebimentos sem permissão" : "Recebimentos indisponíveis"} description={available === "restricted" ? "Este perfil não possui acesso aos recebimentos." : "O recurso financeiro não está disponível para esta filial."} /> : rows.length ? <div className="divide-y divide-subtle px-5">{rows.map((row) => { const content = <><span className="min-w-0"><strong className="block truncate text-sm">{row.name}</strong><small className="text-[11px] text-muted">{formatPercent(row.percentage)} do total</small></span><strong className="shrink-0 text-right text-sm">{formatBRL(row.payment_total)}</strong></>; const className = `flex items-center justify-between gap-3 py-3.5 ${href ? "transition hover:text-link focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20" : ""}`; return href ? <Link key={row.code} href={`${href}&payment_method_code=${encodeURIComponent(row.code)}`} className={className}>{content}</Link> : <div key={row.code} className={className}>{content}</div>; })}</div> : <EmptyState title="Sem recebimentos" description="Nenhuma forma de pagamento no período." />}</section>;
}

function ProductPerformance({ sales, productsHref, consumptionAvailability }: { sales: Sales; productsHref?: string; consumptionAvailability: DashboardData["availability"]["consumptions"] }) {
  const [view, setView] = useState<"commercial" | "consumption">("commercial");
  const products = sales.top_products ?? [];
  const commercialUnavailable = sales.top_products === undefined;
  const consumption = sales.product_consumption ?? [];
  const restrictedConsumption = consumptionAvailability !== "available" && view === "consumption";
  return <section className="card overflow-hidden"><div className="card-header"><div><div className="flex items-center gap-2"><PackageSearch className="size-4 text-primary" /><h2 className="text-sm font-bold">Desempenho de produtos</h2></div><p className="mt-1 text-xs text-muted">{view === "commercial" ? "Ranking por faturamento de vendas." : "Quantidade consolidada: venda direta e modificadores."}</p></div>{productsHref && <Link className="text-xs font-bold text-link" href={productsHref}>Ver relatório</Link>}</div><div className="flex gap-1 border-b border-subtle bg-surface-muted/60 px-5 pt-3"><button type="button" className={`rounded-t-md px-3 py-2 text-xs font-bold ${view === "commercial" ? "bg-surface text-primary shadow-[0_-1px_0_var(--border-subtle)]" : "text-muted hover:text-fg"}`} onClick={() => setView("commercial")}>Produtos mais vendidos</button><button type="button" className={`rounded-t-md px-3 py-2 text-xs font-bold ${view === "consumption" ? "bg-surface text-primary shadow-[0_-1px_0_var(--border-subtle)]" : "text-muted hover:text-fg"}`} onClick={() => setView("consumption")}>Consumo consolidado</button></div>{view === "commercial" ? commercialUnavailable ? <EmptyState title="Produtos indisponíveis" description="Este recurso não está disponível para esta filial." /> : products.length ? <ol className="divide-y divide-subtle px-5">{products.slice(0, 5).map((row, index) => { const content = <><span className="flex min-w-0 items-center gap-3"><b className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">{index + 1}</b><span className="min-w-0"><strong className="block truncate text-sm">{row.product_name}</strong><small className="block truncate text-[10px] text-muted">{formatQuantity(row.quantity)} vendidos</small></span></span><strong className="shrink-0 text-right text-sm">{formatBRL(row.sales_revenue)}</strong></>; const className = `flex items-center justify-between gap-4 py-3.5 ${productsHref && row.product_id ? "transition hover:text-link focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20" : ""}`; return <li key={row.product_id || row.product_name}>{productsHref && row.product_id ? <Link href={`${productsHref}&product=${row.product_id}`} className={className}>{content}</Link> : <div className={className}>{content}</div>}</li>; })}</ol> : <EmptyState title="Sem produtos vendidos" description="Nenhum produto compõe o faturamento do período." /> : restrictedConsumption ? <EmptyState title="Consumo indisponível" description="Este perfil não possui acesso ao consumo consolidado de produtos." /> : consumption.length ? <ol className="divide-y divide-subtle px-5">{consumption.slice(0, 5).map((row, index) => <li key={row.product_id} className="flex items-center justify-between gap-4 py-3.5"><span className="flex min-w-0 items-center gap-3"><b className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">{index + 1}</b><span className="min-w-0"><strong className="block truncate text-sm">{row.product_name}</strong><small className="block text-[10px] text-muted">Direta: {formatQuantity(row.direct_quantity, row.unit)} · Modificador: {formatQuantity(row.modifier_quantity, row.unit)}</small></span></span><strong className="shrink-0 text-right text-sm">{formatQuantity(row.consolidated_quantity, row.unit)}</strong></li>)}</ol> : <EmptyState title="Sem consumo consolidado" description="Nenhuma quantidade de produto foi registrada no período." />}</section>;
}

function LatestSales({ sales, canViewSaleDetail, salesHref }: { sales: Sales; canViewSaleDetail: boolean; salesHref?: string }) {
  const results = sales.latest_sales.results.slice(0, 5);
  function SaleNumber({ sale }: { sale: Sales["latest_sales"]["results"][number] }) { return canViewSaleDetail ? <Link className="font-bold text-link" href={`/vendas/${sale.id}`}>{sale.sale_number}</Link> : <strong>{sale.sale_number}</strong>; }
  return <section className="card overflow-hidden"><div className="card-header"><div><div className="flex items-center gap-2"><ReceiptText className="size-4 text-primary" /><h2 className="text-sm font-bold">Últimas vendas</h2></div><p className="mt-1 text-xs text-muted">Operações mais recentes no período selecionado.</p></div>{salesHref && <Link className="text-xs font-bold text-link" href={salesHref}>Ver todas</Link>}</div>{results.length ? <><div className="hidden md:block"><div className="table-wrap"><table className="data-table"><thead><tr><th>Venda</th><th>Data e horário</th><th>Atendente</th><th>Pagamento</th><th>Situação</th><th>Total recebido</th></tr></thead><tbody>{results.map((sale) => <tr key={sale.id}><td><SaleNumber sale={sale} /></td><td>{formatDate(sale.created_at)}</td><td>{sale.seller?.name || "-"}</td><td>{sale.payments.map((payment) => String(payment.payment_method_name || "")).filter(Boolean).join(", ") || "-"}</td><td><span className="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold text-muted">{domainLabel(sale.status)}</span></td><td className="font-semibold">{formatBRL(sale.total_received)}</td></tr>)}</tbody></table></div></div><div className="divide-y divide-subtle md:hidden">{results.map((sale) => <article key={sale.id} className="p-4"><div className="flex items-start justify-between gap-3"><SaleNumber sale={sale} /><strong className="text-sm">{formatBRL(sale.total_received)}</strong></div><p className="mt-1 text-xs text-muted">{formatDate(sale.created_at)} · {sale.seller?.name || "Sem atendente"}</p><div className="mt-3 flex flex-wrap gap-2"><span className="rounded-full bg-surface-muted px-2 py-1 text-[10px] font-semibold text-muted">{sale.payments.map((payment) => String(payment.payment_method_name || "")).filter(Boolean).join(", ") || "-"}</span><span className="rounded-full bg-surface-muted px-2 py-1 text-[10px] font-semibold text-muted">{domainLabel(sale.status)}</span></div></article>)}</div></> : <EmptyState title="Sem vendas recentes" description="Nenhuma venda no período." />}</section>;
}

export function CommercialOverview({ data, salesReportHref, receiptsReportHref, productsReportHref, resultReportHref, canViewSaleDetail }: { data: DashboardData; salesReportHref?: string; receiptsReportHref?: string; productsReportHref?: string; resultReportHref?: string; canViewSaleDetail: boolean }) {
  const sales = data.sales;
  const result = data.operational_result?.result ?? data.operational_result?.estimated_result;
  if (!sales) return <section className="card"><EmptyState title="Indicadores comerciais indisponíveis" description={data.availability.sales === "restricted" ? "Este perfil não possui permissão para visualizar vendas." : "As vendas não estão disponíveis para esta filial."} /></section>;
  return <><section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Faturamento de vendas" value={formatBRL(sales.sales_revenue)} note={`${sales.count} operações realizadas`} icon={TrendingUp} href={salesReportHref} trend={sales.period_comparison.deltas.net_revenue} /><MetricCard label="Quantidade de vendas" value={String(sales.count)} note="Operações registradas no período" icon={ShoppingBasket} href={salesReportHref} trend={sales.period_comparison.deltas.sales_count} /><MetricCard label="Ticket médio" value={formatBRL(sales.ticket_average)} note="Média por operação de venda" icon={ReceiptText} href={salesReportHref} trend={sales.period_comparison.deltas.ticket_average} /><MetricCard label="Resultado operacional estimado" value={result === undefined ? "Sem permissão" : formatBRL(result)} note={result === undefined ? "Disponível com acesso financeiro autorizado" : "Estimativa financeira para o período"} icon={CircleDollarSign} href={result !== undefined ? resultReportHref : undefined} tone={result === undefined ? "muted" : decimalCompare(result, "0") === -1 ? "danger" : decimalCompare(result, "0") === 1 ? "success" : "primary"} trend={sales.period_comparison.deltas.estimated_result} /></section><section className="grid gap-5 xl:grid-cols-3"><SalesEvolution sales={sales} href={salesReportHref} /><PaymentPanel sales={sales} href={receiptsReportHref} available={data.availability.financial_receipts} /></section><ProductPerformance sales={sales} productsHref={productsReportHref} consumptionAvailability={data.availability.consumptions} /><LatestSales sales={sales} canViewSaleDetail={canViewSaleDetail} salesHref={salesReportHref} /></>;
}
