"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight, BarChart3, Boxes, ClipboardCheck, PackageCheck, Scale, SlidersHorizontal, Trash2, Truck } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { ReportExportAction } from "@/components/report-export-action";
import { Alert, Button, EmptyState, Input, Select, Spinner } from "@/components/ui";
import { formatDate, formatDecimalBRL } from "@/lib/format";
import { countStatusLabels, divergenceStatusLabels, lossReasonLabels, normalizeQuantityGroups, physicalQuantityDisplay, resolutionTypeLabels, transferStatusLabels } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { AdvancedInventoryReceiptRow, AdvancedInventoryReport, InventoryQuantityGroups } from "@/types";

type Filters = { transferStatus: string; divergenceStatus: string; inventoryStatus: string; lossReason: string; resolutionType: string; product: string; responsible: string; period: PeriodValue };
const empty = (): Filters => ({ transferStatus: "", divergenceStatus: "", inventoryStatus: "", lossReason: "", resolutionType: "", product: "", responsible: "", period: { start: "", end: "" } });

function QuantityGroups({ groups }: { groups?: InventoryQuantityGroups }) {
  const values = normalizeQuantityGroups(groups);
  if (!values.length) return <span>-</span>;
  return <span className="flex flex-wrap gap-1.5">{values.map((item, index) => <span key={`${item.unit}-${index}`} className="rounded-full bg-surface-muted px-2 py-1 text-xs font-bold">{physicalQuantityDisplay({ ...item, content: item.content_quantity, packageContent: item.package_content, contentUnit: item.content_unit, completePackages: item.complete_packages, residualContent: item.residual_content })}</span>)}</span>;
}

type DetailRow = { key: string; eventAt?: string; title: string; resource: string; detail?: string; quantityDisplay?: string; movementIds?: number[] };

function advancedQuantity(row: object, quantityKey: string, contentKeys = ["content_quantity"], prefix = "") {
  const values = row as Record<string, unknown>;
  const first = (...keys: string[]) => {
    const key = keys.find((candidate) => values[candidate] !== undefined && values[candidate] !== null);
    return key ? values[key] as string | number : undefined;
  };
  return physicalQuantityDisplay({
    quantity: first(quantityKey),
    unit: String(first("unit") || ""),
    content: first(...contentKeys),
    packageContent: first("package_content"),
    contentUnit: String(first("content_unit") || ""),
    completePackages: first(...(prefix ? [`${prefix}_complete_packages`, "complete_packages"] : ["complete_packages"])),
    residualContent: first(...(prefix ? [`${prefix}_residual_content`, "residual_content"] : ["residual_content"])),
  });
}

function MovementLinks({ ids, available }: { ids: number[] | undefined; available: Map<number, string> }) {
  const { hasPermission } = useAuth();
  const canOpen = hasPermission(permissions.viewInventoryHistory);
  if (!ids?.length) return <span className="text-muted">Sem movimento associado</span>;
  return <span className="flex flex-wrap gap-1.5">{ids.map((id) => available.has(id) && canOpen ? <Link key={id} href={`/estoque/movimentacoes/${id}`} title={available.get(id)} className="rounded-full bg-info-surface px-2 py-1 text-[11px] font-bold text-link">Movimento #{id}</Link> : <span key={id} className="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-bold">Movimento #{id}</span>)}</span>;
}

function DetailRows({ id, title, description, rows, movements }: { id: string; title: string; description: string; rows: DetailRow[]; movements: Map<number, string> }) {
  return <section id={id} className="card scroll-mt-24 overflow-hidden">
    <div className="card-header"><div><h3 className="text-sm font-bold">{title}</h3><p className="mt-1 text-[11px] text-muted">{description}</p></div><span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-bold">{rows.length}</span></div>
    {rows.length ? <>
      <div className="divide-y divide-subtle md:hidden">{rows.map((row) => <article key={row.key} className="space-y-3 p-4"><div className="flex items-start justify-between gap-3"><div><strong className="text-sm">{row.title}</strong><p className="mt-1 break-all text-[11px] text-muted">{row.resource}</p></div>{row.eventAt && <time className="shrink-0 text-[11px] text-muted">{formatDate(row.eventAt)}</time>}</div>{row.detail && <p className="text-xs text-muted">{row.detail}</p>}{row.quantityDisplay !== undefined && <p className="text-xs"><span className="text-muted">Quantidade: </span><strong>{row.quantityDisplay}</strong></p>}<MovementLinks ids={row.movementIds} available={movements} /></article>)}</div>
      <div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Evento / estado</th><th>Data de referência</th><th>Recurso exato</th><th>Quantidade</th><th>Movimentos associados</th></tr></thead><tbody>{rows.map((row) => <tr key={row.key}><td><strong>{row.title}</strong>{row.detail && <small className="block text-muted">{row.detail}</small>}</td><td>{row.eventAt ? formatDate(row.eventAt) : "-"}</td><td className="max-w-64 break-all font-mono text-xs">{row.resource}</td><td>{row.quantityDisplay || "-"}</td><td><MovementLinks ids={row.movementIds} available={movements} /></td></tr>)}</tbody></table></div>
    </> : <EmptyState title="Nenhuma linha neste escopo" description="O backend não retornou eventos ou estados deste tipo para os filtros aplicados." />}
  </section>;
}

function ReceiptEventRows({ rows, movements }: { rows: AdvancedInventoryReceiptRow[]; movements: Map<number, string> }) {
  return <section id="event-receipts" className="card scroll-mt-24 overflow-hidden">
    <div className="card-header"><div><h3 className="text-sm font-bold">Recebimentos</h3><p className="mt-1 text-[11px] text-muted">Uma linha por evento de recebimento, com itens conferidos aninhados.</p></div><span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-bold">{rows.length}</span></div>
    {rows.length ? <>
      <div className="divide-y divide-subtle md:hidden">{rows.map((row) => <article key={row.receipt} className="space-y-3 p-4"><div className="flex items-start justify-between gap-3"><div><strong className="text-sm">{row.finalize ? row.items.length ? "Recebimento final" : "Recebimento zero finalizado" : "Recebimento parcial"}</strong><p className="mt-1 break-all text-[11px] text-muted">Recebimento {row.receipt} · transferência {row.transfer}</p></div><time className="shrink-0 text-[11px] text-muted">{formatDate(row.event_at)}</time></div><p className="text-xs text-muted">Responsável #{row.received_by}</p>{row.items.length ? <div className="space-y-2">{row.items.map((item) => <div key={item.transfer_item} className="rounded-md bg-surface-muted p-3"><div className="flex items-start justify-between gap-3"><div><strong className="text-xs">{item.product_name}</strong><p className="mt-1 text-[10px] text-muted">Produto #{item.product} · item {item.transfer_item}</p></div><strong className="text-xs">{advancedQuantity(item, "quantity")}</strong></div><div className="mt-2"><MovementLinks ids={item.movement_ids} available={movements} /></div></div>)}</div> : <div className="rounded-md border border-warning/30 bg-warning-surface p-3 text-xs text-warning-strong"><strong className="block">Recebimento zero</strong>Nenhum item ou quantidade foi recebido neste evento final.</div>}<div><small className="mb-1 block text-[10px] text-muted">Todos os movimentos do recebimento</small><MovementLinks ids={row.movement_ids} available={movements} /></div></article>)}</div>
      <div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Recebimento</th><th>Recebido em / por</th><th>Transferência</th><th>Tipo</th><th>Itens conferidos</th><th>Movimentos associados</th></tr></thead><tbody>{rows.map((row) => <tr key={row.receipt}><td className="max-w-56 break-all font-mono text-xs">{row.receipt}</td><td>{formatDate(row.event_at)}<small className="block text-muted">Responsável #{row.received_by}</small></td><td className="max-w-56 break-all font-mono text-xs">{row.transfer}</td><td>{row.finalize ? row.items.length ? "Final" : "Zero finalizado" : "Parcial"}</td><td>{row.items.length ? <div className="space-y-2">{row.items.map((item) => <div key={item.transfer_item} className="rounded-md bg-surface-muted p-2.5"><div className="flex justify-between gap-3"><span><strong className="block text-xs">{item.product_name}</strong><small className="text-muted">Produto #{item.product} · item {item.transfer_item}</small></span><strong className="shrink-0 text-xs">{advancedQuantity(item, "quantity")}</strong></div><div className="mt-2"><MovementLinks ids={item.movement_ids} available={movements} /></div></div>)}</div> : <div className="rounded-md bg-warning-surface p-3 text-xs text-warning-strong"><strong className="block">Recebimento zero</strong>Sem itens recebidos.</div>}</td><td><MovementLinks ids={row.movement_ids} available={movements} /></td></tr>)}</tbody></table></div>
    </> : <EmptyState title="Nenhum recebimento neste escopo" description="O backend não retornou eventos de recebimento para os filtros aplicados." />}
  </section>;
}

function AdvancedReport() {
  const { currentBranch } = useAuth();
  const [draft, setDraft] = useState<Filters>(empty);
  const [applied, setApplied] = useState<Filters>(empty);
  const [report, setReport] = useState<AdvancedInventoryReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  function queryFor(filters: Filters) {
    const query = new URLSearchParams();
    if (filters.transferStatus) query.set("transfer_status", filters.transferStatus);
    if (filters.divergenceStatus) query.set("divergence_status", filters.divergenceStatus);
    if (filters.inventoryStatus) query.set("inventory_status", filters.inventoryStatus);
    if (filters.lossReason) query.set("loss_reason", filters.lossReason);
    if (filters.resolutionType) query.set("resolution_type", filters.resolutionType);
    if (filters.product) query.set("product", filters.product);
    if (filters.responsible) query.set("responsible", filters.responsible);
    if (filters.period.start) query.set("start_datetime", filters.period.start);
    if (filters.period.end) query.set("end_datetime", filters.period.end);
    return query;
  }

  async function load(filters: Filters, token = context.current) {
    if (!currentBranch) { setReport(null); setLoading(false); return; }
    setLoading(true); setError(""); setApplied(filters);
    try {
      const response = await http.get<AdvancedInventoryReport>(`advanced-inventory-reports/?${queryFor(filters)}`);
      if (context.current === token) setReport(response);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o relatório avançado.");
    } finally { if (context.current === token) setLoading(false); }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    const filters = empty();
    const token = context.current;
    setDraft(filters); setApplied(filters); setReport(null);
    void loadRef.current(filters, token);
  }, [currentBranch]);

  const card = (label: string, value: number, quantity: InventoryQuantityGroups | undefined, quantityLabel: string, href: string, icon: ReactNode) => <Link href={href} className="card group p-5 transition hover:border-focus/40"><div className="flex items-start justify-between gap-3"><span className="flex size-10 items-center justify-center rounded-lg bg-info-surface text-info-strong">{icon}</span><ArrowRight className="size-4 text-muted transition group-hover:translate-x-1" /></div><strong className="mt-4 block text-xl">{value}</strong><span className="mt-1 block text-xs font-semibold">{label}</span>{quantity && <span className="mt-3 block"><small className="mb-1 block text-[10px] text-muted">{quantityLabel}</small><QuantityGroups groups={quantity} /></span>}</Link>;
  const quantities = report?.quantities_by_unit;
  const financials = report?.financials;
  const hasPeriodSnapshot = report?.state_basis.mode === "as_of_period_end";
  const snapshotAt = report?.state_basis.as_of;
  const snapshotSuffix = hasPeriodSnapshot ? "no fim do período" : "no snapshot atual";
  const details = report?.drill_down;
  const movementLinks = new Map((details?.resource_ids.movements ?? []).map((id, index) => [id, details?.links.movements[index] || ""]));
  const dispatchRows: DetailRow[] = details?.event_rows.dispatches.map((row) => ({ key: `dispatch-${row.transfer_item}`, eventAt: row.event_at, title: row.product_name, resource: `Transferência ${row.transfer} · item ${row.transfer_item}`, detail: `Produto #${row.product} · despacho`, quantityDisplay: advancedQuantity(row, "quantity"), movementIds: row.movement_ids })) ?? [];
  const resolutionRows: DetailRow[] = details?.event_rows.resolutions.map((row) => ({ key: `resolution-${row.resolution}`, eventAt: row.event_at, title: row.product_name, resource: `Resolução ${row.resolution} · divergência ${row.divergence} · transferência ${row.transfer}`, detail: resolutionTypeLabels[row.resolution_type], quantityDisplay: advancedQuantity(row, "quantity"), movementIds: row.movement_ids })) ?? [];
  const divergenceRows: DetailRow[] = details?.event_rows.divergences.map((row) => ({ key: `divergence-${row.divergence}`, eventAt: row.event_at, title: row.product_name, resource: `Divergência ${row.divergence} · transferência ${row.transfer} · item ${row.transfer_item}`, detail: `Produto #${row.product} · detecção`, quantityDisplay: advancedQuantity(row, "initial_quantity", ["initial_content", "content_quantity"], "initial") })) ?? [];
  const lossRows: DetailRow[] = details?.event_rows.losses.map((row) => ({ key: `loss-${row.loss}`, eventAt: row.event_at, title: row.product_name, resource: `Perda ${row.loss}`, detail: lossReasonLabels[row.reason], quantityDisplay: advancedQuantity(row, "quantity"), movementIds: row.movement_ids })) ?? [];
  const countRows: DetailRow[] = details?.event_rows.inventory_counts.map((row) => { const quantity = advancedQuantity(row, "difference_quantity", ["difference_content", "content_quantity"], "difference"); return { key: `count-${row.inventory_count_item}`, eventAt: row.event_at, title: `Diferença · ${row.product_name}`, resource: `Inventário ${row.inventory_count} · item ${row.inventory_count_item}`, detail: `${countStatusLabels[row.status]} · produto #${row.product}`, quantityDisplay: Number(row.difference_content ?? row.difference_quantity) > 0 ? `+${quantity}` : quantity, movementIds: row.movement_ids }; }) ?? [];
  const transferStateRows: DetailRow[] = details?.state_rows.transfers.map((row) => ({ key: `state-transfer-${row.transfer}`, eventAt: snapshotAt, title: transferStatusLabels[row.status], resource: `Transferência ${row.transfer}`, detail: `Origem #${row.origin_branch} → destino #${row.destination_branch} · despachada em ${formatDate(row.dispatched_at)}` })) ?? [];
  const divergenceStateRows: DetailRow[] = details?.state_rows.divergences.map((row) => ({ key: `state-divergence-${row.divergence}`, eventAt: snapshotAt, title: divergenceStatusLabels[row.status], resource: `Divergência ${row.divergence} · transferência ${row.transfer} · item ${row.transfer_item}`, detail: `Produto #${row.product}`, quantityDisplay: advancedQuantity(row, "pending_quantity", ["pending_content", "content_quantity"], "pending") })) ?? [];
  const transitStateRows: DetailRow[] = details?.state_rows.in_transit.map((row) => ({ key: `state-transit-${row.transfer_item}`, eventAt: snapshotAt, title: "Em trânsito", resource: `Transferência ${row.transfer} · item ${row.transfer_item}`, detail: `Produto #${row.product}`, quantityDisplay: advancedQuantity(row, "pending_quantity", ["pending_content", "content_quantity"], "pending") })) ?? [];

  return <>
    <PageHeader title="Estoque avançado" description={`${currentBranch?.name || "Selecione uma filial"} · eventos de transferência, divergência, perda e inventário.`} action={<ReportExportAction path="advanced-inventory-reports/" query={queryFor(applied)} />} />
    <InventoryNav />
    <div className="space-y-5 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      <form className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4" onSubmit={(event) => { event.preventDefault(); void load({ ...draft, period: { ...draft.period } }); }}>
        <Select aria-label="Status da transferência" value={draft.transferStatus} onChange={(event) => setDraft((value) => ({ ...value, transferStatus: event.target.value }))}><option value="">Transferências: todos</option>{Object.entries(transferStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <Select aria-label="Status da divergência" value={draft.divergenceStatus} onChange={(event) => setDraft((value) => ({ ...value, divergenceStatus: event.target.value }))}><option value="">Divergências: todas</option>{Object.entries(divergenceStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <Select aria-label="Status do inventário" value={draft.inventoryStatus} onChange={(event) => setDraft((value) => ({ ...value, inventoryStatus: event.target.value }))}><option value="">Inventários: todos</option>{Object.entries(countStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <Select aria-label="Motivo da perda" value={draft.lossReason} onChange={(event) => setDraft((value) => ({ ...value, lossReason: event.target.value }))}><option value="">Perdas: todos os motivos</option>{Object.entries(lossReasonLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <Select aria-label="Tipo de resolução" value={draft.resolutionType} onChange={(event) => setDraft((value) => ({ ...value, resolutionType: event.target.value }))}><option value="">Resoluções: todos os tipos</option>{Object.entries(resolutionTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <Input aria-label="ID do produto" type="number" min="1" step="1" placeholder="ID do produto" value={draft.product} onChange={(event) => setDraft((value) => ({ ...value, product: event.target.value }))} />
        <Input aria-label="ID do responsável" type="number" min="1" step="1" placeholder="ID do responsável" value={draft.responsible} onChange={(event) => setDraft((value) => ({ ...value, responsible: event.target.value }))} />
        <div className="rounded-md bg-surface-muted px-3 py-2 text-[11px] text-muted"><strong className="block text-fg">Filtros por domínio</strong>Cada status afeta somente seu próprio fluxo.</div>
        <div className="sm:col-span-2 xl:col-span-4"><p className="mb-2 text-xs font-semibold">Período dos eventos</p><p className="mb-3 text-[11px] text-muted">Usa despacho, recebimento, detecção, resolução, registro da perda e captura/confirmação do inventário, conforme o evento consolidado.</p><PeriodFilter value={draft.period} onChange={(period) => setDraft((value) => ({ ...value, period }))} /></div>
        <div className="flex justify-end gap-2 sm:col-span-2 xl:col-span-4"><Button type="button" variant="secondary" onClick={() => { const filters = empty(); setDraft(filters); void load(filters); }}>Limpar</Button><Button type="submit"><SlidersHorizontal className="size-4" />Aplicar</Button></div>
      </form>
      {loading ? <div className="card flex min-h-64 items-center justify-center text-primary"><Spinner className="size-7" /></div> : report ? <>
        <section className="rounded-md border border-info/30 bg-info-surface p-4 text-xs text-info-strong">
          <strong className="block">{hasPeriodSnapshot ? "Posição as-of no fim do período" : "Posição do snapshot atual"}</strong>
          <span className="mt-1 block">{hasPeriodSnapshot ? `Em trânsito, status e divergências pendentes representam a posição na data de corte${snapshotAt ? ` (${formatDate(snapshotAt)})` : " do período"}, não o estado atual.` : "Sem período aplicado, em trânsito, status e divergências pendentes representam o estado corrente."}</span>
        </section>
        <section>
          <div className="mb-3 flex items-center gap-2"><Truck className="size-4 text-primary" /><h2 className="text-sm font-bold">Eventos entre filiais</h2></div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {card("Transferências despachadas (eventos)", report.events.transfer_dispatches, quantities?.transfer_dispatched, "Quantidade despachada no período", "#event-dispatches", <Truck className="size-5" />)}
            {card("Recebimentos (eventos)", report.events.transfer_receipts, quantities?.transfer_received, "Quantidade recebida no período", "#event-receipts", <PackageCheck className="size-5" />)}
            {card(`Em trânsito ${snapshotSuffix}`, report.transfer_statuses.IN_TRANSIT || 0, quantities?.transfer_in_transit, `Quantidade ${snapshotSuffix}`, "#state-in-transit", <Boxes className="size-5" />)}
            {card("Divergências detectadas (eventos)", report.events.divergences, quantities?.divergence_pending, `Quantidade ainda pendente ${snapshotSuffix}`, "#event-divergences", <Scale className="size-5" />)}
            {card("Resoluções de divergência (eventos)", report.events.divergence_resolutions, undefined, "", "#event-resolutions", <Scale className="size-5" />)}
          </div>
          <p className="mt-3 text-[11px] text-muted">Em trânsito é mercadoria ainda aguardando conferência {snapshotSuffix}. Divergência é uma falta já detectada no recebimento finalizado na mesma posição temporal.</p>
        </section>
        <section>
          <div className="mb-3 flex items-center gap-2"><ClipboardCheck className="size-4 text-primary" /><h2 className="text-sm font-bold">Perdas e contagens</h2></div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {card("Registros de perda (eventos)", report.events.losses, quantities?.loss, "Quantidade registrada no período", "#event-losses", <Trash2 className="size-5" />)}
            {card("Inventários (eventos)", report.events.inventory_counts, quantities?.inventory_difference, "Diferença capturada no período", "#event-counts", <ClipboardCheck className="size-5" />)}
          </div>
        </section>
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Valor potencial e impacto</h2><p className="mt-1 text-[11px] text-muted">Custos aparecem somente quando a API autoriza sua visualização.</p></div><BarChart3 className="size-5 text-muted" /></div>
          <div className="grid gap-px bg-subtle sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: `Em trânsito ${snapshotSuffix}`, potential: financials?.in_transit_potential_sale_value, cost: financials?.in_transit_cost_value },
              { label: `Divergência pendente ${snapshotSuffix}`, potential: financials?.pending_divergence_potential_sale_value, cost: financials?.pending_divergence_cost_impact },
              { label: "Perdas", potential: financials?.loss_potential_sale_value, cost: financials?.loss_cost_impact },
              { label: "Diferença de inventário", potential: financials?.inventory_potential_sale_value, cost: financials?.inventory_cost_impact },
            ].map((item) => <div key={item.label} className="bg-surface p-5"><strong className="text-sm">{item.label}</strong><p className="mt-3 text-xs text-muted">Venda potencial: <span className="font-semibold text-fg">{item.potential !== undefined ? formatDecimalBRL(item.potential) : "-"}</span></p>{item.cost !== undefined && <p className="mt-1 text-xs text-muted">Impacto de custo: <span className="font-semibold text-fg">{formatDecimalBRL(item.cost)}</span></p>}</div>)}
          </div>
        </section>
        <section id="event-details" className="scroll-mt-24"><h2 className="text-sm font-bold">Detalhes exatos por horário do evento</h2><p className="mt-1 text-xs text-muted">Linhas fornecidas pelo backend após aplicar o timestamp próprio de cada domínio. IDs e movimentos não são reconstruídos por filtros de listagem.</p></section>
        <DetailRows id="event-dispatches" title="Despachos" description="Horário de despacho da transferência." rows={dispatchRows} movements={movementLinks} />
        <ReceiptEventRows rows={details?.event_rows.receipts ?? []} movements={movementLinks} />
        <DetailRows id="event-divergences" title="Divergências detectadas" description="Horário em que a falta foi detectada e finalizada no destino." rows={divergenceRows} movements={movementLinks} />
        <DetailRows id="event-resolutions" title="Resoluções" description="Horário efetivo de cada resolução de divergência." rows={resolutionRows} movements={movementLinks} />
        <DetailRows id="event-losses" title="Perdas" description="Horário em que cada perda foi registrada." rows={lossRows} movements={movementLinks} />
        <DetailRows id="event-counts" title="Itens de inventário" description="Captura ou confirmação usada como evento pelo contrato do relatório." rows={countRows} movements={movementLinks} />
        <section id="state-details" className="scroll-mt-24"><h2 className="text-sm font-bold">Posição {snapshotSuffix}</h2><p className="mt-1 text-xs text-muted">Estados derivados pelo backend em {snapshotAt ? formatDate(snapshotAt) : "sua data de corte"}; não usam o status atual das telas operacionais.</p></section>
        <DetailRows id="state-transfers" title="Status das transferências" description={`Status derivado ${snapshotSuffix}.`} rows={transferStateRows} movements={movementLinks} />
        <DetailRows id="state-divergences" title="Divergências na posição" description={`Pendências e status ${snapshotSuffix}.`} rows={divergenceStateRows} movements={movementLinks} />
        <DetailRows id="state-in-transit" title="Itens em trânsito" description={`Quantidades ainda em trânsito ${snapshotSuffix}.`} rows={transitStateRows} movements={movementLinks} />
      </> : <section className="card"><EmptyState title="Sem dados consolidados" description="Não há eventos para o escopo selecionado." /></section>}
    </div>
  </>;
}

export default function AdvancedInventoryReportPage() { return <AdminGuard requiredPermissions={[permissions.viewAdvancedInventory]}><AdvancedReport /></AdminGuard>; }
