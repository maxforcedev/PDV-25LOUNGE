"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Boxes, CalendarRange, ReceiptText, ShoppingBasket, TrendingDown, TrendingUp, Users } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Select, TableLoading } from "@/components/ui";
import { domainLabel } from "@/lib/domain-labels";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { DashboardData, ReportUserGroup } from "@/types";

interface Period { start: string; end: string }

const pad = (value: number) => String(value).padStart(2, "0");
const localInput = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

function range(days = 0, offset = 0): Period {
  const end = new Date();
  end.setDate(end.getDate() + offset);
  end.setHours(23, 59, 59, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - days);
  start.setHours(0, 0, 0, 0);
  return { start: localInput(start), end: localInput(end) };
}

function Kpi({ label, value, note, icon: Icon, href, tone = "primary" }: { label: string; value: string; note: string; icon: typeof TrendingUp; href: string; tone?: "primary" | "danger" | "warning" | "success" }) {
  const tones = { primary: "bg-primary/10 text-primary", danger: "bg-danger/10 text-red-700", warning: "bg-warning/10 text-amber-700", success: "bg-success/10 text-emerald-700" };
  return <Link href={href} className="card group p-5 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[.14em] text-slate-500">{label}</p><strong className="mt-3 block text-2xl text-dark">{value}</strong><span className="mt-1 block text-[11px] text-slate-500">{note}</span></div><span className={`flex size-10 items-center justify-center rounded-lg ${tones[tone]}`}><Icon className="size-5" /></span></div></Link>;
}

function HorizontalBars({ title, rows, href }: { title: string; rows: Array<{ label: string; value: number; display: string; note?: string; query?: string }>; href: string }) {
  const max = Math.max(...rows.map((row) => row.value), 0);
  return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">{title}</h2><Link className="text-xs font-bold text-primary" href={href}>Ver relatório</Link></div>{rows.length ? <div className="space-y-4 p-5" role="img" aria-label={title}>{rows.map((row) => <Link href={`${href}${row.query || ""}`} key={row.label} title={`${row.label}: ${row.display}`} className="block rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/20"><div className="mb-1.5 flex justify-between gap-3 text-xs"><span className="truncate font-semibold">{row.label}<small className="ml-1 font-normal text-slate-500">{row.note}</small></span><strong>{row.display}</strong></div><div className="h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-primary to-blue-400" style={{ width: `${max ? Math.max(3, row.value / max * 100) : 0}%` }} /></div></Link>)}</div> : <EmptyState title="Sem dados" description="Nenhum registro no período selecionado." />}</section>;
}

function PaymentChart({ rows, href }: { rows: NonNullable<DashboardData["sales"]>["payment_distribution"]; href: string }) {
  const total = rows.reduce((sum, row) => sum + Number(row.amount), 0);
  const colors = ["bg-primary", "bg-blue-400", "bg-emerald-500", "bg-amber-500", "bg-violet-500", "bg-slate-500"];
  return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Formas de pagamento</h2><Link className="text-xs font-bold text-primary" href={href}>Ver relatório</Link></div>{rows.length ? <div className="p-5" role="img" aria-label="Distribuição por forma de pagamento"><div className="mb-5 flex h-5 overflow-hidden rounded-full bg-slate-100">{rows.map((row, index) => <Link key={`${row.code}-${index}`} href={`${href}&payment_method_code=${encodeURIComponent(row.code)}`} title={`${row.name}: ${formatBRL(row.amount)}`} className={`${colors[index % colors.length]} min-w-1 transition hover:brightness-110`} style={{ width: `${total ? Number(row.amount) * 100 / total : 0}%` }} />)}</div><div className="grid gap-3 sm:grid-cols-2">{rows.map((row, index) => <Link key={`${row.name}-${index}`} href={`${href}&payment_method_code=${encodeURIComponent(row.code)}`} className="flex items-center justify-between gap-3 text-xs"><span className="flex min-w-0 items-center gap-2"><i className={`size-2.5 shrink-0 rounded-full ${colors[index % colors.length]}`} /><span className="truncate">{row.name}</span></span><strong>{formatBRL(row.amount)}</strong></Link>)}</div></div> : <EmptyState title="Sem recebimentos" description="Nenhum pagamento no período selecionado." />}</section>;
}

function WeeklyComparison({ comparison, href }: { comparison: NonNullable<DashboardData["sales"]>["weekly_comparison"]; href: string }) {
  const size = Math.max(comparison.current.length, comparison.previous.length);
  const points = Array.from({ length: size }, (_, index) => ({ current: comparison.current[index], previous: comparison.previous[index] }));
  const max = Math.max(...points.flatMap((point) => [Number(point.current?.revenue || 0), Number(point.previous?.revenue || 0)]), 0);
  const hasData = points.some((point) => Number(point.current?.revenue || 0) || Number(point.previous?.revenue || 0));
  return <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Comparativo do período</h2><p className="mt-1 text-[11px] text-slate-500">Atual × período anterior equivalente</p></div><Link className="text-xs font-bold text-primary" href={href}>Ver vendas</Link></div>{hasData ? <div className="p-5"><div className="mb-4 flex gap-4 text-[10px] font-semibold text-slate-500"><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-primary" />Atual</span><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-slate-300" />Anterior</span></div><div className="flex h-52 items-end gap-2 overflow-x-auto" role="img" aria-label="Faturamento atual comparado ao período anterior">{points.map((point, index) => <div key={index} className="flex h-full min-w-12 flex-1 flex-col justify-end"><div className="flex h-42 items-end justify-center gap-1"><div title={`Atual: ${formatBRL(point.current?.revenue || "0")}`} className="w-3 rounded-t bg-primary" style={{ height: `${max ? Math.max(2, Number(point.current?.revenue || 0) * 100 / max) : 0}%` }} /><div title={`Anterior: ${formatBRL(point.previous?.revenue || "0")}`} className="w-3 rounded-t bg-slate-300" style={{ height: `${max ? Math.max(2, Number(point.previous?.revenue || 0) * 100 / max) : 0}%` }} /></div><span className="mt-2 truncate text-center text-[9px] text-slate-500">{point.current ? new Date(`${point.current.date}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : index + 1}</span></div>)}</div></div> : <EmptyState title="Sem comparação" description="Os dois períodos não possuem faturamento." />}</section>;
}

function PeopleTable({ title, rows, seller, query }: { title: string; rows: ReportUserGroup[]; seller: boolean; query: string }) {
  const href = `/relatorios/${seller ? "atendentes" : "operadores"}?${query}`;
  return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">{title}</h2><Link className="text-xs font-bold text-primary" href={href}>Ver relatório</Link></div>{rows.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Pessoa</th><th>Vendas</th><th>Faturamento</th><th>Ticket</th>{seller && rows.some((row) => row.commission !== undefined) && <th>Comissão</th>}</tr></thead><tbody>{rows.slice(0, 6).map((row) => <tr key={row.user.id}><td><Link className="font-bold text-primary" href={`${href}&${seller ? "seller" : "operator"}=${row.user.id}`}>{row.user.name}</Link></td><td>{row.count}</td><td>{formatBRL(row.effective_revenue)}</td><td>{formatBRL(row.average)}</td>{seller && rows.some((item) => item.commission !== undefined) && <td>{row.commission === undefined ? "-" : formatBRL(row.commission)}</td>}</tr>)}</tbody></table></div> : <EmptyState title="Sem desempenho" description="Nenhuma venda atribuída no período." />}</section>;
}

function DashboardPage() {
  const { currentBranch } = useAuth();
  const context = useRef(currentBranch?.id || 0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState<Period>(() => range());
  const [draftPeriod, setDraftPeriod] = useState<Period>(() => range());
  const [category, setCategory] = useState("");
  const [draftCategory, setDraftCategory] = useState("");
  const [categories, setCategories] = useState<Array<{ id: number; name: string }>>([]);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  async function load(next: Period, nextCategory: string, token = context.current) {
    if (!currentBranch) return;
    setData(null);
    setError("");
    const params = new URLSearchParams({ start_datetime: next.start, end_datetime: next.end });
    if (nextCategory) params.set("category", nextCategory);
    try {
      const result = await http.get<DashboardData>(`dashboard/?${params}`);
      if (context.current === token) {
        setData(result);
        setPeriod(next);
        setCategory(nextCategory);
        if (result.filters?.categories) setCategories(result.filters.categories);
      }
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o Dashboard.");
    }
  }

  useEffect(() => {
    const next = range();
    setDraftPeriod(next);
    setDraftCategory("");
    void load(next, "", context.current);
  }, [currentBranch?.id]);

  const query = new URLSearchParams({ start_datetime: period.start, end_datetime: period.end, ...(category ? { category } : {}), ...(currentBranch ? { branch: String(currentBranch.id) } : {}) }).toString();
  const report = (slug: string, extra = "") => `/relatorios/${slug}?${query}${extra}`;
  const sales = data?.sales;
  const weekdays = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  const heatMax = Math.max(...(sales?.heatmap || []).map((row) => Number(row.revenue)), 0);

  return <><PageHeader title="Dashboard Executivo" description={`Visão gerencial organizada de ${currentBranch?.name || "sua filial"}.`} /><div className="space-y-5 p-4 sm:p-6 lg:p-8"><section className="card p-4"><div className="mb-3 flex items-center gap-2 text-xs font-bold"><CalendarRange className="size-4 text-primary" />Filtros globais</div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><Field label="Filial"><Select value={currentBranch?.id || ""} disabled><option value={currentBranch?.id || ""}>{currentBranch?.name || "Selecione uma filial"}</option></Select></Field><Field label="Data/hora inicial"><input className="input" step="1" type="datetime-local" value={draftPeriod.start} onChange={(event) => setDraftPeriod((value) => ({ ...value, start: event.target.value }))} /></Field><Field label="Data/hora final"><input className="input" step="1" type="datetime-local" value={draftPeriod.end} onChange={(event) => setDraftPeriod((value) => ({ ...value, end: event.target.value }))} /></Field><Field label="Categoria"><Select value={draftCategory} onChange={(event) => setDraftCategory(event.target.value)}><option value="">Todas</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field></div><div className="mt-3 flex flex-wrap items-center gap-2">{[["Hoje", range()], ["Ontem", range(0, -1)], ["Últimos 7 dias", range(6)], ["Últimos 15 dias", range(14)], ["Últimos 30 dias", range(29)]].map(([label, value]) => <button type="button" key={String(label)} className="rounded-full bg-slate-100 px-3 py-1.5 text-[11px] font-bold hover:bg-primary/10 hover:text-primary" onClick={() => setDraftPeriod(value as Period)}>{String(label)}</button>)}{data?.current_cash?.[0] && <button type="button" className="rounded-full bg-success/10 px-3 py-1.5 text-[11px] font-bold text-emerald-700" onClick={() => setDraftPeriod({ start: localInput(new Date(data.current_cash![0].opened_at)), end: localInput(new Date()) })}>Sessão atual</button>}<button type="button" className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Personalizado</button><Button className="ml-auto" onClick={() => void load(draftPeriod, draftCategory)}>Aplicar</Button></div></section>
    {error && <Alert message={error} />}{!data ? <section className="card"><TableLoading /></section> : <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{sales && <><Kpi label="Faturamento" value={formatBRL(sales.effective_revenue)} note={`${sales.count} vendas comerciais`} icon={TrendingUp} href={report("vendas")} /><Kpi label="Ticket médio" value={formatBRL(sales.average)} note="Receita efetiva por venda" icon={ReceiptText} href={report("vendas")} /><Kpi label="Cancelamentos / Estornos" value={formatBRL(sales.cancellations.value)} note={`${sales.cancellations.count} operações`} icon={TrendingDown} tone="danger" href={report("cancelamentos")} /><Kpi label="Descontos manuais" value={formatBRL(sales.manual_discount)} note={`${sales.manual_discount_count} vendas · item + conta`} icon={ReceiptText} tone="warning" href={report("descontos")} /></>}{data.consumptions && <Kpi label="Consumação & Cortesias" value={formatBRL(data.consumptions.charged)} note={`${data.consumptions.count} pedidos · referência ${formatBRL(data.consumptions.reference)} · benefício ${formatBRL(data.consumptions.subsidy)}`} icon={ShoppingBasket} href={report("consumacoes")} />}{sales?.commission !== undefined && <Kpi label="Comissão" value={formatBRL(sales.commission)} note="Custo separado do faturamento" icon={Users} href={report("comissoes")} />}</div>
      <div className="grid gap-5 xl:grid-cols-2">{data.inventory && <section className="card p-5"><div className="mb-4 flex justify-between"><h2 className="text-sm font-bold">Estoque físico</h2><Link className="text-xs font-bold text-primary" href="/estoque">Abrir estoque</Link></div><div className="grid grid-cols-2 gap-3">{data.inventory.inventory_value !== undefined && <Kpi label="Valor em estoque" value={formatBRL(data.inventory.inventory_value)} note="Saldos positivos no recorte" icon={Boxes} href="/estoque" />}<Kpi label="Negativos" value={String(data.inventory.negative_count)} note="Produtos físicos" icon={Boxes} tone="danger" href="/estoque?state=negative" /><Kpi label="Abaixo do mínimo" value={String(data.inventory.below_minimum_count)} note="Exigem atenção" icon={Boxes} tone="warning" href="/estoque?state=below_minimum" /><Kpi label="Produtos físicos" value={String(data.inventory.physical_products)} note="Somente estoque direto" icon={Boxes} href="/estoque" /></div></section>}<section className="card p-5"><div className="mb-4 flex justify-between"><h2 className="text-sm font-bold">Caixa e resultado</h2>{data.operational_result && <Link className="text-xs font-bold text-primary" href={report("resultado")}>Ver resultado</Link>}</div>{data.operational_result && <div className="mb-4 rounded-lg border border-dashed border-primary/30 p-4"><span className="text-[10px] font-bold uppercase text-slate-500">Resultado estimado</span><strong className="mt-2 block text-2xl">{formatBRL(data.operational_result.result)}</strong><small className="text-slate-500">Margem {data.operational_result.margin}%</small></div>}{data.current_cash?.length ? data.current_cash.map((item) => <Link key={item.id} href={`/caixas/sessoes/${item.id}`} className="flex justify-between border-t border-slate-100 py-3 text-sm"><span>{item.register.name}</span><strong>{formatBRL(item.expected)} em dinheiro</strong></Link>) : <p className="text-xs text-slate-500">Nenhum caixa aberto.</p>}</section></div>
      {sales && <><section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Mapa de calor · dia × hora</h2><p className="mt-1 text-[11px] text-slate-500">Faturamento efetivo, vendas e ticket no tooltip.</p></div></div>{sales.heatmap.length ? <div className="overflow-x-auto p-5"><div className="grid min-w-240 grid-cols-[42px_repeat(24,minmax(28px,1fr))] gap-1"><span />{Array.from({ length: 24 }, (_, hour) => <span key={hour} className="text-center text-[9px] text-slate-500">{hour}</span>)}{weekdays.map((day, weekday) => <div key={day} className="contents"><span className="self-center text-[10px] font-bold">{day}</span>{Array.from({ length: 24 }, (_, hour) => { const cell = sales.heatmap.find((row) => row.weekday === weekday && row.hour === hour); const strength = cell && heatMax ? Math.max(.08, Number(cell.revenue) / heatMax) : .03; return <Link key={hour} href={report("vendas", `&hour=${hour}&weekday=${weekday}`)} title={cell ? `${formatBRL(cell.revenue)} · ${cell.count} vendas · ticket ${formatBRL(cell.average)}` : "Sem vendas"} className="aspect-square rounded-sm border border-primary/10" style={{ backgroundColor: `color-mix(in srgb, var(--color-primary) ${Math.round(strength * 100)}%, transparent)` }} />; })}</div>)}</div></div> : <EmptyState title="Sem mapa de calor" description="Nenhuma venda no período selecionado." />}</section><div className="grid gap-5 xl:grid-cols-2"><HorizontalBars title="Produtos mais vendidos" href={report("produtos")} rows={sales.top_products.slice(0, 8).map((row) => ({ label: row.product_name, value: Number(row.revenue), display: formatBRL(row.revenue), note: formatQuantity(row.quantity), query: row.product_id ? `&product=${row.product_id}` : "" }))} /><PaymentChart rows={sales.payment_distribution} href={report("recebimentos")} /><HorizontalBars title="Faturamento por atendente" href={report("atendentes")} rows={sales.top_sellers.slice(0, 8).map((row) => ({ label: row.user.name, value: Number(row.effective_revenue), display: formatBRL(row.effective_revenue), note: `${row.count} vendas`, query: `&seller=${row.user.id}` }))} /><WeeklyComparison comparison={sales.weekly_comparison} href={report("vendas")} /></div><div className="grid gap-5 xl:grid-cols-2"><PeopleTable title="Atendentes" rows={sales.top_sellers} seller query={query} /><PeopleTable title="Operadores de caixa" rows={sales.top_operators} seller={false} query={query} /></div><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Últimas vendas do recorte</h2><Link className="text-xs font-bold text-primary" href={report("vendas")}>Ver todas</Link></div>{sales.latest_sales.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Venda</th><th>Data</th><th>Atendente</th><th>Pagamento</th><th>Status</th><th>Total</th></tr></thead><tbody>{sales.latest_sales.map((sale) => <tr key={sale.id}><td><Link className="font-bold text-primary" href={`/vendas/${sale.id}`}>{sale.sale_number}</Link></td><td>{formatDate(sale.created_at)}</td><td>{sale.seller?.name || "-"}</td><td>{sale.payments.map((payment) => String(payment.payment_method_name || "")).filter(Boolean).join(", ") || "-"}</td><td>{domainLabel(sale.status)}</td><td>{formatBRL(sale.total)}</td></tr>)}</tbody></table></div> : <EmptyState title="Sem vendas recentes" description="Nenhuma venda no período." />}</section></>}
    </>}</div></>;
}

export default function DashboardRoute() {
  return <AdminGuard requiredPermissions={[permissions.viewDashboard]}><DashboardPage /></AdminGuard>;
}
