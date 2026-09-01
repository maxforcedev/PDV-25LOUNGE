"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ExternalLink, Scale, SlidersHorizontal } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Field, Input, Modal, Select, TableLoading, Textarea } from "@/components/ui";
import { fieldError, formatDate, formatDecimalBRL, formatEditableDecimal, formatQuantity } from "@/lib/format";
import { divergenceStatusLabels, inventoryTone, isUnitQuantityValid, quantityInputMode, resolutionTypeLabels } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { StockTransfer, TransferDivergence, TransferResolution, TransferResolutionType } from "@/types";

type Filters = { status: string; product: string; responsible: string; transfer: string; period: PeriodValue };
const empty = (): Filters => ({ status: "PENDING", product: "", responsible: "", transfer: "", period: { start: "", end: "" } });

function Divergences() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const canViewHistory = hasPermission(permissions.viewTransfers);
  const canResolve = hasPermission(permissions.resolveTransfer) && supportSession?.mode !== "READ_ONLY";
  const canLoadDivergences = canViewHistory || hasPermission(permissions.resolveTransfer);
  const [items, setItems] = useState<TransferDivergence[]>([]);
  const [draft, setDraft] = useState<Filters>(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selected, setSelected] = useState<TransferDivergence | null>(null);
  const [selectedTransfer, setSelectedTransfer] = useState<StockTransfer | null>(null);
  const [resolutionType, setResolutionType] = useState<TransferResolutionType>("FOUND_RECEIPT");
  const [quantity, setQuantity] = useState("");
  const [observation, setObservation] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const key = useRef("");
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(filters = draft, token = context.current) {
    if (!currentBranch || !canLoadDivergences) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const query = new URLSearchParams();
    if (filters.status) query.set("status", filters.status);
    if (filters.product) query.set("product", filters.product);
    if (filters.responsible) query.set("responsible", filters.responsible);
    if (filters.transfer.trim()) query.set("transfer", filters.transfer.trim());
    if (filters.period.start) query.set("start_datetime", filters.period.start);
    if (filters.period.end) query.set("end_datetime", filters.period.end);
    try {
      const response = await http.getAll<TransferDivergence>(`transfer-divergences/?${query}`);
      if (context.current === token) setItems(response);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as divergências.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const filters = { ...empty(), status: query.get("status") ?? "PENDING", product: query.get("product") || "", responsible: query.get("responsible") || "", transfer: query.get("transfer") || "", period: { start: query.get("start_datetime") || "", end: query.get("end_datetime") || "" } };
    setDraft(filters);
    setItems([]);
    setSuccess("");
    void loadRef.current(filters, context.current);
  }, [currentBranch?.id]);

  async function openResolution(item: TransferDivergence) {
    setError("");
    setFields({});
    setSelected(item);
    setSelectedTransfer(null);
    setResolutionType("FOUND_RECEIPT");
    setQuantity(formatEditableDecimal(item.pending_quantity));
    setObservation("");
    key.current = crypto.randomUUID();
    try {
      const divergence = await http.get<TransferDivergence>(`transfer-divergences/${item.id}/`);
      setSelected(divergence);
      setQuantity(formatEditableDecimal(divergence.pending_quantity));
      if (canViewHistory) {
        setSelectedTransfer(await http.get<StockTransfer>(`stock-transfers/${item.transfer}/`));
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível validar o escopo da resolução.");
    }
  }

  function changePayload(callback: () => void) {
    callback();
    key.current = crypto.randomUUID();
  }

  async function resolve(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const transferItem = selectedTransfer?.items.find((item) => item.id === selected.transfer_item);
    if (transferItem && !isUnitQuantityValid(quantity, transferItem.product_unit_snapshot)) {
      setFields({ quantity: [transferItem.product_unit_snapshot.toLowerCase() === "un" ? "Informe uma quantidade inteira de unidades." : "Informe uma quantidade positiva com até 3 casas decimais."] });
      setError("Revise a quantidade informada.");
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      const result = await http.post<TransferResolution>(`transfer-divergences/${selected.id}/resolve/`, { idempotency_key: key.current, resolution_type: resolutionType, quantity: quantity.replace(",", "."), observation });
      setSelected(null);
      setSuccess(`${resolutionTypeLabels[result.resolution_type]} registrada com sucesso.`);
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível resolver a divergência.");
    } finally {
      setSaving(false);
    }
  }

  const expectedBranch = resolutionType === "FOUND_RECEIPT" ? selectedTransfer?.destination_branch : selectedTransfer?.origin_branch;
  const physicalScopeMatches = !selectedTransfer || expectedBranch === currentBranch?.id;
  const selectedUnit = selectedTransfer?.items.find((item) => item.id === selected?.transfer_item)?.product_unit_snapshot;

  return <>
    <PageHeader title="Divergências de transferência" description={`${currentBranch?.name || "Selecione uma filial"} · faltas finalizadas e resoluções auditadas.`} />
    <InventoryNav />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !selected && <Alert message={error} />}
      {success && <Alert message={success} type="success" />}
      {canLoadDivergences && <form className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4" onSubmit={(event) => { event.preventDefault(); void load(); }}>
        <Select aria-label="Status" value={draft.status} onChange={(event) => setDraft((value) => ({ ...value, status: event.target.value }))}><option value="">Todos os status</option>{Object.entries(divergenceStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <Input aria-label="Produto" inputMode="numeric" placeholder="ID do produto" value={draft.product} onChange={(event) => setDraft((value) => ({ ...value, product: event.target.value.replace(/\D/g, "") }))} />
        <Input aria-label="Responsável" inputMode="numeric" placeholder="ID do responsável" value={draft.responsible} onChange={(event) => setDraft((value) => ({ ...value, responsible: event.target.value.replace(/\D/g, "") }))} />
        <Input aria-label="Transferência" placeholder="UUID da transferência" value={draft.transfer} onChange={(event) => setDraft((value) => ({ ...value, transfer: event.target.value }))} />
        <PeriodFilter className="sm:col-span-2 xl:col-span-4" value={draft.period} onChange={(period) => setDraft((value) => ({ ...value, period }))} />
        <div className="flex justify-end gap-2 sm:col-span-2 xl:col-span-4"><Button type="button" variant="secondary" onClick={() => { const filters = empty(); setDraft(filters); void load(filters); }}>Limpar</Button><Button type="submit"><SlidersHorizontal className="size-4" />Aplicar</Button></div>
      </form>}
      {!canViewHistory && canResolve && <div className="rounded-md border border-info/30 bg-info-surface p-4 text-xs text-info-strong">Exibindo somente os dados operacionais necessários para resolver divergências. Impactos financeiros e histórico ampliado permanecem ocultos.</div>}
      {canLoadDivergences && <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Divergências finalizadas</h2><p className="mt-1 text-[11px] text-muted">Quantidade faltante encerrada no recebimento; não representa saldo em trânsito.</p></div><AlertTriangle className="size-5 text-muted" /></div>
        {loading ? <TableLoading columns={canViewHistory ? 7 : 6} /> : items.length ? <>
          <div className="divide-y divide-subtle md:hidden">{items.map((item) => <article key={item.id} className="space-y-3 p-4"><div className="flex items-start justify-between gap-3"><div><strong>{item.product_name}</strong>{canViewHistory ? <Link href={`/estoque/transferencias/${item.transfer}`} className="mt-1 block text-xs text-link">Transferência {item.transfer.slice(0, 8).toUpperCase()}</Link> : <span className="mt-1 block text-xs text-muted">Transferência {item.transfer.slice(0, 8).toUpperCase()}</span>}</div><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(item.status)}`}>{divergenceStatusLabels[item.status]}</span></div><dl className="grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted">Divergência inicial</dt><dd>{formatQuantity(item.initial_quantity)}</dd></div><div><dt className="text-muted">Em aberto</dt><dd className="font-bold">{formatQuantity(item.pending_quantity)}</dd></div>{canViewHistory && <div><dt className="text-muted">Venda potencial</dt><dd>{formatDecimalBRL(item.potential_sale_value)}</dd></div>}{canViewHistory && item.cost_impact !== undefined && <div><dt className="text-muted">Impacto de custo</dt><dd>{formatDecimalBRL(item.cost_impact)}</dd></div>}</dl>{item.status === "PENDING" && canResolve && <Button className="w-full" onClick={() => void openResolution(item)}><Scale className="size-4" />Resolver</Button>}</article>)}</div>
          <div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Detectada em</th><th>Produto</th><th>Transferência</th><th>Inicial / resolvida / em aberto</th>{canViewHistory && <th>Impacto</th>}<th>Status</th><th className="text-right">Ação</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{formatDate(item.detected_at)}</td><td className="font-bold">{item.product_name}</td><td>{canViewHistory ? <Link href={`/estoque/transferencias/${item.transfer}`} className="inline-flex items-center gap-1 font-semibold text-link">{item.transfer.slice(0, 8).toUpperCase()}<ExternalLink className="size-3" /></Link> : <span className="font-semibold">{item.transfer.slice(0, 8).toUpperCase()}</span>}</td><td>{formatQuantity(item.initial_quantity)} / {formatQuantity(item.resolved_quantity)} / <strong>{formatQuantity(item.pending_quantity)}</strong></td>{canViewHistory && <td><span className="block">Venda: {formatDecimalBRL(item.potential_sale_value)}</span>{item.cost_impact !== undefined && <small className="text-muted">Custo: {formatDecimalBRL(item.cost_impact)}</small>}</td>}<td><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(item.status)}`}>{divergenceStatusLabels[item.status]}</span></td><td><div className="flex justify-end">{item.status === "PENDING" && canResolve && <Button className="h-8 px-3 text-xs" onClick={() => void openResolution(item)}>Resolver</Button>}</div></td></tr>)}</tbody></table></div>
        </> : <EmptyState title="Nenhuma divergência" description="Não há divergências disponíveis neste escopo." />}
      </section>}
    </div>
    <Modal open={!!selected} title="Resolver divergência" description={selected ? `${selected.product_name} · ${formatQuantity(selected.pending_quantity)} em aberto` : undefined} onClose={() => !saving && setSelected(null)}>
      <form onSubmit={resolve}>
        <div className="space-y-4 p-5 sm:p-6">
          {error && <Alert message={error} />}
          <Field label="Tipo de resolução" error={fieldError(fields, "resolution_type")}><Select value={resolutionType} onChange={(event) => changePayload(() => setResolutionType(event.target.value as TransferResolutionType))}>{Object.entries(resolutionTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
          {selectedTransfer && <div className={`rounded-md p-3 text-xs ${physicalScopeMatches ? "bg-info-surface text-info-strong" : "bg-danger-surface text-danger-strong"}`}>Esta resolução física deve ser feita em <strong>{resolutionType === "FOUND_RECEIPT" ? selectedTransfer.destination_branch_name : selectedTransfer.origin_branch_name}</strong>. Filial atual: <strong>{currentBranch?.name}</strong>.</div>}
          {!selectedTransfer && <div className="rounded-md bg-info-surface p-3 text-xs text-info-strong">A API validará se a filial atual corresponde ao tipo de resolução selecionado, sem expor os demais dados da transferência.</div>}
          <Field label={`Quantidade${selectedUnit ? ` (${selectedUnit.toUpperCase()})` : ""}`} error={fieldError(fields, "quantity")}><Input required inputMode={quantityInputMode(selectedUnit)} step={selectedUnit?.toLowerCase() === "un" ? "1" : "0.001"} min="0.001" value={quantity} onChange={(event) => changePayload(() => setQuantity(event.target.value))} /></Field>
          <Field label="Motivo / observação" error={fieldError(fields, "observation")}><Textarea required minLength={3} value={observation} onChange={(event) => changePayload(() => setObservation(event.target.value))} /></Field>
        </div>
        <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" onClick={() => setSelected(null)} disabled={saving}>Cancelar</Button><Button type="submit" loading={saving} disabled={!physicalScopeMatches}>Confirmar resolução</Button></div>
      </form>
    </Modal>
  </>;
}

export default function DivergencesPage() {
  return <AdminGuard requiredPermissions={[permissions.viewTransfers, permissions.resolveTransfer]}><Divergences /></AdminGuard>;
}
