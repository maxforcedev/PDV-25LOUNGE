"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { Filter, Ticket, UserRoundCheck } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Field, Input, Modal, Pagination, Select, TableLoading } from "@/components/ui";
import { formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { businessMonthToDate } from "@/lib/period";
import { useAuth } from "@/providers/auth-provider";
import type { ReportResponse } from "@/types";

type Row = Record<string, unknown>;
type Option = { id: string | number; name: string; historical?: boolean };
type Options = { products: Option[]; operators: Option[]; devices: Option[] };

const statusLabels: Record<string, string> = {
  issued: "Emitido",
  partially_used: "Parcialmente usado",
  used: "Usado",
  cancelled: "Cancelado",
};
const methodLabels: Record<string, string> = { scan: "Scanner", manual: "Manual" };

function initialPeriod(): PeriodValue { return businessMonthToDate(); }
function quantity(value: unknown) { return formatQuantity(String(value || "0")); }
function ticketNumber(value: unknown) { return `#${String(value || "").padStart(4, "0")}`; }
function text(value: unknown) { return value == null || value === "" ? "-" : String(value); }
function reportPath(url: string) { const parsed = new URL(url); const marker = "/api/v1/"; const index = parsed.pathname.indexOf(marker); return `${index >= 0 ? parsed.pathname.slice(index + marker.length) : parsed.pathname.replace(/^\//, "")}${parsed.search}`; }
function optionLabel(option: Option) { return `${option.name}${option.historical ? " (Histórico)" : ""}`; }

function Status({ value }: { value: unknown }) {
  const status = String(value || "");
  const tone = status === "cancelled" ? "bg-danger/10 text-danger-strong" : status === "used" ? "bg-slate-200 text-slate-700" : status === "partially_used" ? "bg-warning/10 text-warning-strong" : "bg-success/10 text-emerald-700";
  return <span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-bold uppercase ${tone}`}>{statusLabels[status] || text(value)}</span>;
}

function Kpi({ label, value }: { label: string; value: unknown }) {
  return <section className="card p-4"><span className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</span><strong className="mt-1 block text-xl">{typeof value === "number" ? value : quantity(value)}</strong></section>;
}

export function TicketsReport() {
  const { currentBranch, hasPermission } = useAuth();
  const allowed = hasPermission(permissions.viewTickets);
  const context = useRef(0);
  const requestId = useRef(0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState(initialPeriod);
  const [appliedPeriod, setAppliedPeriod] = useState(initialPeriod);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string>>({});
  const [options, setOptions] = useState<Options>({ products: [], operators: [], devices: [] });
  const [data, setData] = useState<ReportResponse<Row> | null>(null);
  const [detail, setDetail] = useState<Row | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function query(nextPeriod = appliedPeriod, nextFilters = appliedFilters) {
    return new URLSearchParams({ start_datetime: nextPeriod.start, end_datetime: nextPeriod.end, ...Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value)) });
  }

  async function loadOptions(token: number) {
    try {
      const result = await http.get<Options>("reports/ticket-options/");
      if (context.current === token) setOptions(result);
    } catch { if (context.current === token) setOptions({ products: [], operators: [], devices: [] }); }
  }

  async function load(nextPeriod = period, nextFilters = filters, token = context.current) {
    if (!currentBranch || !allowed) return;
    const id = ++requestId.current;
    setLoading(true); setError("");
    const nextQuery = query(nextPeriod, nextFilters);
    try {
      const result = await http.get<ReportResponse<Row>>(`reports/tickets/?${nextQuery}`);
      if (context.current === token && requestId.current === id) {
        setData(result); setAppliedPeriod(nextPeriod); setAppliedFilters(nextFilters);
        window.history.replaceState(null, "", `${window.location.pathname}?${nextQuery}`);
      }
    } catch (caught) {
      if (context.current === token && requestId.current === id) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o relatório de tickets.");
    } finally { if (context.current === token && requestId.current === id) setLoading(false); }
  }

  const resetForBranch = useEffectEvent(() => {
    const current = new URLSearchParams(window.location.search);
    const start = current.get("start_datetime"); const end = current.get("end_datetime");
    const nextPeriod = start && end ? { start, end } : initialPeriod();
    const nextFilters = Object.fromEntries([...current.entries()].filter(([key]) => !["start_datetime", "end_datetime", "branch", "export", "page", "page_size"].includes(key)));
    setPeriod(nextPeriod); setAppliedPeriod(nextPeriod); setFilters(nextFilters); setAppliedFilters(nextFilters); setData(null);
    void load(nextPeriod, nextFilters, context.current); void loadOptions(context.current);
  });

  useEffect(() => {
    resetForBranch();
  }, [currentBranch?.id, allowed]);

  async function openDetail(id: unknown) {
    if (!id) return;
    setDetailLoading(true); setError("");
    try { setDetail(await http.get<Row>(`reports/tickets/${String(id)}/`)); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível abrir o ticket."); }
    finally { setDetailLoading(false); }
  }

  async function loadPage(url: string) {
    const id = ++requestId.current; const token = context.current; setLoading(true);
    try { const result = await http.get<ReportResponse<Row>>(reportPath(url)); if (context.current === token && requestId.current === id) setData(result); }
    catch (caught) { if (context.current === token && requestId.current === id) setError(caught instanceof ApiError ? caught.message : "Não foi possível trocar a página."); }
    finally { if (context.current === token && requestId.current === id) setLoading(false); }
  }

  if (!allowed) return <div className="p-6"><Alert message="Você não possui permissão para este relatório." /></div>;
  const summary = data?.summary || {}; const results = data?.results || [];
  const redemptions = Array.isArray(detail?.redemptions) ? detail.redemptions as Row[] : [];
  const modifiers = Array.isArray(detail?.modifiers) ? detail.modifiers : [];
  return <>
    <PageHeader title="Tickets" description="Acompanhamento operacional de emissões, retiradas e cancelamentos da filial." action={<Link className="btn btn-secondary" href="/relatorios">Central</Link>} />
    <div className="space-y-5 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      <form className="card space-y-4 p-4" onSubmit={(event) => { event.preventDefault(); void load({ ...period }, { ...filters }); }}>
        <div className="flex items-center gap-2 text-xs font-bold"><Filter className="size-4 text-primary" />Filtros</div>
        <PeriodFilter value={period} onChange={setPeriod} onApply={(next) => void load(next, filters)} />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field label="Número do ticket"><Input inputMode="numeric" value={filters.number || ""} onChange={(event) => setFilters((current) => ({ ...current, number: event.target.value.replace(/\D/g, "") }))} placeholder="Ex.: 0048" /></Field>
          <Field label="Situação"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option><option value="issued">Emitidos</option><option value="partially_used">Parcialmente usados</option><option value="used">Usados</option><option value="cancelled">Cancelados</option><option value="validated">Validados</option></Select></Field>
          <Field label="Produto"><Select value={filters.product || ""} onChange={(event) => setFilters((current) => ({ ...current, product: event.target.value }))}><option value="">Todos os produtos</option>{options.products.map((item) => <option key={item.id} value={item.id}>{optionLabel(item)}</option>)}</Select></Field>
          <Field label="Origem"><Select value={filters.origin || ""} onChange={(event) => setFilters((current) => ({ ...current, origin: event.target.value }))}><option value="">Venda e comanda</option><option value="sale">Venda</option><option value="command">Comanda</option></Select></Field>
          <Field label="Operador que retirou"><Select value={filters.operator || ""} onChange={(event) => setFilters((current) => ({ ...current, operator: event.target.value }))}><option value="">Todos os operadores</option>{options.operators.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="Dispositivo"><Select value={filters.device || ""} onChange={(event) => setFilters((current) => ({ ...current, device: event.target.value }))}><option value="">Todos os dispositivos</option>{options.devices.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="Método de validação"><Select value={filters.input_method || ""} onChange={(event) => setFilters((current) => ({ ...current, input_method: event.target.value }))}><option value="">Scanner e manual</option><option value="scan">Scanner</option><option value="manual">Manual</option></Select></Field>
        </div>
        <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => { const next = initialPeriod(); setPeriod(next); setFilters({}); void load(next, {}); }}>Limpar</Button><Button type="submit">Aplicar</Button></div>
      </form>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Kpi label="Tickets emitidos" value={summary.tickets_issued} /><Kpi label="Tickets validados" value={summary.tickets_validated} /><Kpi label="Parcialmente usados" value={summary.tickets_partially_used} /><Kpi label="Totalmente usados" value={summary.tickets_used} /><Kpi label="Unidades emitidas" value={summary.issued_quantity} /><Kpi label="Unidades retiradas" value={summary.redeemed_quantity} /><Kpi label="Unidades disponíveis" value={summary.available_quantity} /><Kpi label="Canceladas sem retirada" value={summary.cancelled_quantity} /></div>
      <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Tickets emitidos</h2><p className="mt-1 text-[11px] text-muted">{data?.count || 0} tickets no recorte aplicado.</p></div><Ticket className="size-5 text-muted" /></div>
        {loading ? <TableLoading columns={10} /> : !results.length ? <EmptyState title="Nenhum ticket encontrado" description="Ajuste o período ou os filtros para consultar este recorte." /> : <div className="table-wrap"><table className="data-table min-w-260"><thead><tr><th>Ticket</th><th>Produto</th><th>Emitido</th><th>Retirado</th><th>Restante</th><th>Status</th><th>Origem</th><th>Última retirada</th><th>Operador</th><th>Dispositivo</th><th /></tr></thead><tbody>{results.map((row) => <tr key={String(row.id)}><td><strong>{ticketNumber(row.number)}</strong></td><td><strong>{text(row.product_name)}</strong><small className="block text-muted">{text(row.unit)}</small></td><td>{quantity(row.issued_quantity)}</td><td>{quantity(row.redeemed_quantity)}</td><td>{String(row.status) === "cancelled" ? <span className="text-danger">Cancelado: {quantity(row.cancelled_quantity)}</span> : quantity(row.remaining_quantity)}</td><td><Status value={row.status} /></td><td>{text(row.origin_label)}</td><td>{row.last_redeemed_at ? formatDate(String(row.last_redeemed_at)) : "-"}</td><td>{text(row.last_operator_name)}</td><td>{text(row.last_device_name)}</td><td><Button type="button" variant="secondary" className="whitespace-nowrap" onClick={() => void openDetail(row.id)}>Detalhes</Button></td></tr>)}</tbody></table></div>}
        <Pagination count={data?.count || 0} next={data?.next || null} previous={data?.previous || null} onPage={loadPage} />
      </section>
    </div>
    <Modal open={!!detail || detailLoading} title={detail ? `Ticket ${ticketNumber(detail.number)}` : "Ticket"} description="Dados operacionais e histórico de retiradas" onClose={() => { if (!detailLoading) setDetail(null); }} size="lg" tall>
      {detailLoading ? <TableLoading columns={3} /> : detail && <div className="space-y-5 p-5 sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><strong className="text-xl">{text(detail.product_name)}</strong><p className="mt-1 text-sm text-muted">{text(detail.origin_label)} · emitido em {formatDate(String(detail.issued_at))}</p></div><Status value={detail.status} /></div><div className="grid grid-cols-2 gap-3 sm:grid-cols-4"><Kpi label="Emitido" value={detail.issued_quantity} /><Kpi label="Retirado" value={detail.redeemed_quantity} /><Kpi label="Restante" value={detail.remaining_quantity} /><Kpi label="Cancelado" value={detail.cancelled_quantity} /></div>{modifiers.length > 0 && <div><h3 className="text-xs font-bold uppercase tracking-wide text-muted">Modificadores</h3><p className="mt-1 text-sm">{modifiers.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join(", ")}</p></div>}{detail.notes ? <div><h3 className="text-xs font-bold uppercase tracking-wide text-muted">Observação</h3><p className="mt-1 whitespace-pre-wrap text-sm">{text(detail.notes)}</p></div> : null}<div><div className="mb-3 flex items-center gap-2"><UserRoundCheck className="size-4 text-primary" /><h3 className="text-sm font-bold">Histórico de retiradas</h3></div>{redemptions.length ? <div className="divide-y divide-subtle rounded-lg border border-subtle">{redemptions.map((redemption) => <article key={String(redemption.id)} className="grid gap-2 p-3 text-sm sm:grid-cols-[1fr_auto]"><div><strong>{text(redemption.operator_name)}</strong><p className="text-muted">{formatDate(String(redemption.redeemed_at))} · {text(redemption.device_name)} · {methodLabels[String(redemption.input_method)] || text(redemption.input_method)}</p></div><strong>{quantity(redemption.quantity)}</strong></article>)}</div> : <EmptyState title="Sem retiradas" description="Este ticket ainda não possui registros de retirada." />}</div>{detail.cancelled_at ? <p className="text-sm text-danger">Ticket cancelado em {formatDate(String(detail.cancelled_at))}.</p> : null}</div>}
    </Modal>
  </>;
}
