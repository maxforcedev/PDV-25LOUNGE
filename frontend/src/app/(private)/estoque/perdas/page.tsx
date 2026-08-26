"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { SlidersHorizontal, Trash2 } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Input, Select, TableLoading } from "@/components/ui";
import { formatDate, formatDecimalBRL } from "@/lib/format";
import { lossReasonLabels, physicalQuantityDisplay } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { LossRecord } from "@/types";

type Filters = { reason: string; product: string; responsible: string; period: PeriodValue };
const empty = (): Filters => ({ reason: "", product: "", responsible: "", period: { start: "", end: "" } });

function Losses() {
  const { currentBranch, hasPermission } = useAuth();
  const canView = hasPermission(permissions.viewAdvancedInventory);
  const [items, setItems] = useState<LossRecord[]>([]);
  const [draft, setDraft] = useState<Filters>(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const context = useRef("");
  context.current = String(currentBranch?.id || "");
  const lossQuantity = (item: LossRecord) => physicalQuantityDisplay({ quantity: item.quantity, content: item.content_quantity, packageContent: item.package_content_snapshot, contentUnit: item.content_unit, completePackages: item.complete_packages, residualContent: item.residual_content });

  async function load(filters = draft, token = context.current) {
    if (!currentBranch || !canView) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const query = new URLSearchParams();
    if (filters.reason) query.set("reason", filters.reason);
    if (filters.product) query.set("product", filters.product);
    if (filters.responsible) query.set("responsible", filters.responsible);
    if (filters.period.start) query.set("start_datetime", filters.period.start);
    if (filters.period.end) query.set("end_datetime", filters.period.end);
    try {
      const response = await http.getAll<LossRecord>(`loss-records/?${query}`);
      if (context.current === token) setItems(response);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as perdas.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const filters = { ...empty(), reason: query.get("reason") || "", product: query.get("product") || "", responsible: query.get("responsible") || "", period: { start: query.get("start_datetime") || "", end: query.get("end_datetime") || "" } };
    setDraft(filters);
    setItems([]);
    setSuccess("");
    const token = context.current;
    void loadRef.current(filters, token);
  }, [currentBranch, canView]);

  return <>
    <PageHeader title="Registros de perda" description={`${currentBranch?.name || "Selecione uma filial"} · perdas registradas por Saída, com baixa conhecida e auditada.`} />
    <InventoryNav />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      {success && <Alert message={success} type="success" />}
      {canView ? <>
        <form className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3" onSubmit={(event) => { event.preventDefault(); void load(); }}>
          <Select aria-label="Motivo" value={draft.reason} onChange={(event) => setDraft((value) => ({ ...value, reason: event.target.value }))}><option value="">Todos os motivos</option>{Object.entries(lossReasonLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
          <Input aria-label="Produto" inputMode="numeric" placeholder="ID do produto" value={draft.product} onChange={(event) => setDraft((value) => ({ ...value, product: event.target.value.replace(/\D/g, "") }))} />
          <Input aria-label="Responsável" inputMode="numeric" placeholder="ID do responsável" value={draft.responsible} onChange={(event) => setDraft((value) => ({ ...value, responsible: event.target.value.replace(/\D/g, "") }))} />
          <PeriodFilter className="sm:col-span-2 xl:col-span-3" value={draft.period} onChange={(period) => setDraft((value) => ({ ...value, period }))} />
          <div className="flex justify-end gap-2 sm:col-span-2 xl:col-span-3"><Button type="button" variant="secondary" onClick={() => { const filters = empty(); setDraft(filters); void load(filters); }}>Limpar</Button><Button type="submit"><SlidersHorizontal className="size-4" />Aplicar</Button></div>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Registros de perda</h2><p className="mt-1 text-[11px] text-muted">Snapshots de custo permanecem ocultos sem a permissão correspondente.</p></div><Trash2 className="size-5 text-muted" /></div>
          {loading ? <TableLoading columns={7} /> : items.length ? <>
            <div className="divide-y divide-subtle md:hidden">{items.map((item) => <article key={item.id} className="p-4"><div className="flex justify-between gap-3"><div><strong>{item.product_name}</strong><p className="mt-1 text-xs text-muted">{lossReasonLabels[item.reason]} · {formatDate(item.recorded_at)}</p></div><strong>{lossQuantity(item)}</strong></div><p className="mt-3 text-xs text-muted">{item.observation}</p><dl className="mt-3 grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted">Venda potencial</dt><dd>{formatDecimalBRL(item.potential_sale_value)}</dd></div>{item.cost_impact !== undefined && <div><dt className="text-muted">Impacto de custo</dt><dd>{formatDecimalBRL(item.cost_impact)}</dd></div>}</dl><Link href={`/estoque/movimentacoes?operation_reference=${item.id}&domain_origin=LOSS`} className="mt-3 inline-block text-xs font-semibold text-link">Ver movimentação de perda</Link></article>)}</div>
            <div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Data do evento</th><th>Produto</th><th>Quantidade exata</th><th>Motivo</th><th>Responsável</th><th>Impactos</th><th>Movimento</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{formatDate(item.recorded_at)}</td><td><strong>{item.product_name}</strong><small className="block max-w-72 text-muted">{item.observation}</small></td><td className="font-bold">{lossQuantity(item)}</td><td>{lossReasonLabels[item.reason]}</td><td>#{item.recorded_by}</td><td><span className="block">Venda: {formatDecimalBRL(item.potential_sale_value)}</span>{item.cost_impact !== undefined && <small className="text-muted">Custo: {formatDecimalBRL(item.cost_impact)}</small>}</td><td><Link href={`/estoque/movimentacoes?operation_reference=${item.id}&domain_origin=LOSS`} className="font-semibold text-link">Abrir</Link></td></tr>)}</tbody></table></div>
          </> : <EmptyState title="Nenhuma perda" description="Não há registros para os filtros aplicados." />}
        </section>
      </> : <section className="card"><EmptyState title="Histórico restrito" description="Sua permissão não permite consultar o histórico ou seus impactos." /></section>}
    </div>
  </>;
}

export default function LossesPage() {
  return <AdminGuard requiredPermissions={[permissions.viewAdvancedInventory, permissions.recordLoss]}><Losses /></AdminGuard>;
}
