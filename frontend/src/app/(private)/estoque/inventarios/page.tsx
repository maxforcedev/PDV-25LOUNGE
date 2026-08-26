"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ClipboardCheck, Eye, Plus, SlidersHorizontal } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Input, Select, TableLoading } from "@/components/ui";
import { formatDate, formatQuantity } from "@/lib/format";
import { countStatusLabels, inventoryTone } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { InventoryCount } from "@/types";

type Filters = { status: string; product: string; responsible: string; period: PeriodValue };
const empty = (): Filters => ({ status: "", product: "", responsible: "", period: { start: "", end: "" } });
function Counts() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const canView = hasPermission(permissions.viewAdvancedInventory);
  const canCreate = hasPermission(permissions.performInventoryCount) && supportSession?.mode !== "READ_ONLY";
  const [items, setItems] = useState<InventoryCount[]>([]); const [draft, setDraft] = useState<Filters>(empty);
  const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const context = useRef(""); context.current = String(currentBranch?.id || "");
  async function load(filters = draft, token = context.current) {
    if (!currentBranch || !canView) { setItems([]); setLoading(false); return; }
    setLoading(true); setError(""); const query = new URLSearchParams(); if (filters.status) query.set("status", filters.status); if (filters.product) query.set("product", filters.product); if (filters.responsible) query.set("responsible", filters.responsible); if (filters.period.start) query.set("start_datetime", filters.period.start); if (filters.period.end) query.set("end_datetime", filters.period.end);
    try { const response = await http.getAll<InventoryCount>(`inventory-counts/?${query}`); if (context.current === token) setItems(response); }
    catch (caught) { if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os inventários."); }
    finally { if (context.current === token) setLoading(false); }
  }
  useEffect(() => { const query = new URLSearchParams(window.location.search); const filters = { ...empty(), status: query.get("status") || "", product: query.get("product") || "", responsible: query.get("responsible") || "", period: { start: query.get("start_datetime") || "", end: query.get("end_datetime") || "" } }; setDraft(filters); setItems([]); void load(filters, context.current); }, [currentBranch?.id, canView]);
  return <><PageHeader title="Inventários físicos" description={`${currentBranch?.name || "Selecione uma filial"} · contagens, diferenças e ajustes confirmados.`} action={<Link href="/estoque/inventarios/novo" aria-disabled={!canCreate || !currentBranch} className={`btn btn-primary ${!canCreate || !currentBranch ? "pointer-events-none opacity-50" : ""}`}><Plus className="size-4" />Nova contagem</Link>} /><InventoryNav />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">{error && <Alert message={error} />}{canView ? <><form className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3" onSubmit={(e) => { e.preventDefault(); void load(); }}><Select aria-label="Status" value={draft.status} onChange={(e) => setDraft((v) => ({ ...v, status: e.target.value }))}><option value="">Todos os status</option>{Object.entries(countStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select><Input aria-label="Produto" inputMode="numeric" placeholder="ID do produto" value={draft.product} onChange={(e) => setDraft((v) => ({ ...v, product: e.target.value.replace(/\D/g, "") }))} /><Input aria-label="Responsável" inputMode="numeric" placeholder="ID do responsável" value={draft.responsible} onChange={(e) => setDraft((v) => ({ ...v, responsible: e.target.value.replace(/\D/g, "") }))} /><PeriodFilter className="sm:col-span-2 xl:col-span-3" value={draft.period} onChange={(period) => setDraft((v) => ({ ...v, period }))} /><div className="flex justify-end gap-2 sm:col-span-2 xl:col-span-3"><Button type="button" variant="secondary" onClick={() => { const filters = empty(); setDraft(filters); void load(filters); }}>Limpar</Button><Button type="submit"><SlidersHorizontal className="size-4" />Aplicar</Button></div></form><section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Contagens</h2><p className="mt-1 text-[11px] text-muted">O ajuste usa a diferença capturada, preservando movimentos posteriores.</p></div><ClipboardCheck className="size-5 text-muted" /></div>{loading ? <TableLoading columns={6} /> : items.length ? <><div className="divide-y divide-subtle md:hidden">{items.map((item) => <article key={item.id} className="p-4"><div className="flex items-start justify-between gap-3"><Link href={`/estoque/inventarios/${item.id}`} className="font-bold text-link">{item.id.slice(0, 8).toUpperCase()}</Link><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(item.status)}`}>{countStatusLabels[item.status]}</span></div><p className="mt-2 text-xs text-muted">{formatDate(item.created_at)} · {item.items.length} {item.items.length === 1 ? "produto" : "produtos"}</p><p className="mt-2 text-xs">Diferença: <strong>{formatQuantity(String(item.items.reduce((sum, row) => sum + Number(row.difference_quantity), 0)))}</strong></p></article>)}</div><div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Inventário</th><th>Data</th><th>Itens</th><th>Diferença total</th><th>Status</th><th className="text-right">Ação</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td className="font-bold">{item.id.slice(0, 8).toUpperCase()}</td><td>{formatDate(item.created_at)}</td><td>{item.items.length}</td><td className="font-bold">{formatQuantity(String(item.items.reduce((sum, row) => sum + Number(row.difference_quantity), 0)))}</td><td><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(item.status)}`}>{countStatusLabels[item.status]}</span></td><td><div className="flex justify-end"><Link href={`/estoque/inventarios/${item.id}`} className="icon-button"><Eye className="size-4" /></Link></div></td></tr>)}</tbody></table></div></> : <EmptyState title="Nenhum inventário" description="Não há contagens para os filtros aplicados." />}</section></> : <section className="card"><EmptyState title="Histórico restrito" description="Você pode realizar contagens, mas não possui permissão para consultar o estoque avançado." /></section>}</div>
  </>;
}
export default function CountsPage() { return <AdminGuard requiredPermissions={[permissions.viewAdvancedInventory, permissions.performInventoryCount]}><Counts /></AdminGuard>; }
