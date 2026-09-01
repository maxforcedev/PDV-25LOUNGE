"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Eye, Plus, SlidersHorizontal, Truck } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Input, Select, TableLoading } from "@/components/ui";
import { formatDate, formatQuantity } from "@/lib/format";
import { inventoryTone, sumInventoryDecimals, transferStatusLabels } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { StockTransfer } from "@/types";

type Filters = { status: string; product: string; responsible: string; period: PeriodValue };
const empty = (): Filters => ({ status: "", product: "", responsible: "", period: { start: "", end: "" } });

function Transfers() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const canViewHistory = hasPermission(permissions.viewTransfers);
  const canCreate = hasPermission(permissions.createTransfer) && supportSession?.mode !== "READ_ONLY";
  const canLoadTransfers = canViewHistory
    || hasPermission(permissions.createTransfer)
    || hasPermission(permissions.dispatchTransfer)
    || hasPermission(permissions.receiveTransfer);
  const [items, setItems] = useState<StockTransfer[]>([]);
  const [draft, setDraft] = useState<Filters>(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(filters: Filters, key = context.current) {
    if (!currentBranch || !canLoadTransfers) { setItems([]); setLoading(false); return; }
    setLoading(true); setError("");
    const query = new URLSearchParams();
    if (filters.status) query.set("status", filters.status);
    if (filters.product) query.set("product", filters.product);
    if (filters.responsible) query.set("responsible", filters.responsible);
    if (filters.period.start) query.set("start_datetime", filters.period.start);
    if (filters.period.end) query.set("end_datetime", filters.period.end);
    try {
      const response = await http.getAll<StockTransfer>(`stock-transfers/?${query}`);
      if (context.current === key) setItems(response);
    } catch (caught) {
      if (context.current === key) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as transferências.");
    } finally { if (context.current === key) setLoading(false); }
  }
  useEffect(() => { const query = new URLSearchParams(window.location.search); const filters = { ...empty(), status: query.get("status") || "", product: query.get("product") || "", responsible: query.get("responsible") || "", period: { start: query.get("start_datetime") || "", end: query.get("end_datetime") || "" } }; setDraft(filters); setItems([]); void load(filters, context.current); }, [currentBranch?.id]);
  function apply(event: React.FormEvent) { event.preventDefault(); void load(draft); }
  function clear() { const filters = empty(); setDraft(filters); void load(filters); }

  return <>
    <PageHeader title="Transferências" description={`${currentBranch?.name || "Selecione uma filial"} · saídas e recebimentos entre filiais.`} action={canCreate ?
      <Link href="/estoque/transferencias/nova" aria-disabled={!canCreate || !currentBranch} className={`btn btn-primary ${!canCreate || !currentBranch ? "pointer-events-none opacity-50" : ""}`}><Plus className="size-4" />Nova transferência</Link>
      : undefined} />
    <InventoryNav />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      {canLoadTransfers ? <><form className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3" onSubmit={apply}>
        <Select aria-label="Status" value={draft.status} onChange={(e) => setDraft((v) => ({ ...v, status: e.target.value }))}><option value="">Todos os status</option>{Object.entries(transferStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <Input aria-label="Produto" inputMode="numeric" placeholder="ID do produto" value={draft.product} onChange={(e) => setDraft((v) => ({ ...v, product: e.target.value.replace(/\D/g, "") }))} />
        <Input aria-label="Responsável" inputMode="numeric" placeholder="ID do responsável" value={draft.responsible} onChange={(e) => setDraft((v) => ({ ...v, responsible: e.target.value.replace(/\D/g, "") }))} />
        <PeriodFilter className="sm:col-span-2 xl:col-span-3" value={draft.period} onChange={(period) => setDraft((v) => ({ ...v, period }))} />
        <div className="flex justify-end gap-2 sm:col-span-2 xl:col-span-3"><Button type="button" variant="secondary" onClick={clear}>Limpar</Button><Button type="submit"><SlidersHorizontal className="size-4" />Aplicar</Button></div>
      </form>
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Transferências da filial</h2><p className="mt-1 text-[11px] text-muted">A filial atual participa como origem ou destino.</p></div><Truck className="size-5 text-muted" /></div>
        {loading ? <TableLoading columns={6} /> : items.length ? <>
          <div className="divide-y divide-subtle md:hidden">{items.map((transfer) => <article key={transfer.id} className="space-y-3 p-4"><div className="flex items-start justify-between gap-3"><div><Link href={`/estoque/transferencias/${transfer.id}`} className="font-bold text-link">{transfer.id.slice(0, 8).toUpperCase()}</Link><p className="mt-1 text-xs text-muted">{transfer.origin_branch_name} → {transfer.destination_branch_name}</p></div><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(transfer.status)}`}>{transferStatusLabels[transfer.status]}</span></div><dl className="grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted">Criada em</dt><dd>{formatDate(transfer.created_at)}</dd></div><div><dt className="text-muted">Itens</dt><dd>{transfer.items.length}</dd></div><div><dt className="text-muted">Solicitado</dt><dd>{formatQuantity(sumInventoryDecimals(transfer.items.map((item) => item.requested_quantity)) ?? "")}</dd></div><div><dt className="text-muted">Pendente</dt><dd>{formatQuantity(sumInventoryDecimals(transfer.items.map((item) => item.pending_quantity || "0")) ?? "")}</dd></div></dl></article>)}</div>
          <div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Transferência</th><th>Origem → destino</th><th>Data</th><th>Itens</th><th>Status</th><th className="text-right">Ação</th></tr></thead><tbody>{items.map((transfer) => <tr key={transfer.id}><td className="font-bold">{transfer.id.slice(0, 8).toUpperCase()}</td><td>{transfer.origin_branch_name} → {transfer.destination_branch_name}</td><td>{formatDate(transfer.created_at)}</td><td>{transfer.items.length}</td><td><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(transfer.status)}`}>{transferStatusLabels[transfer.status]}</span></td><td><div className="flex justify-end"><Link href={`/estoque/transferencias/${transfer.id}`} className="icon-button" title="Ver transferência"><Eye className="size-4" /></Link></div></td></tr>)}</tbody></table></div>
        </> : <EmptyState title="Nenhuma transferência" description="Não há transferências para os filtros e a filial selecionada." />}
      </section></> : <section className="card"><EmptyState title="Transferências indisponíveis" description="Seu perfil não possui permissão para consultar ou executar este fluxo." /></section>}
    </div>
  </>;
}
export default function TransfersPage() { return <AdminGuard requiredPermissions={[permissions.viewTransfers, permissions.createTransfer, permissions.dispatchTransfer, permissions.receiveTransfer]}><Transfers /></AdminGuard>; }
