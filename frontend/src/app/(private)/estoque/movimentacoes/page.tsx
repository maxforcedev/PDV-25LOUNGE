"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, History, Search, SlidersHorizontal } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Input, Pagination, Select, TableLoading } from "@/components/ui";
import { formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, StockMovement } from "@/types";

const labels: Record<string, string> = { entry: "Entrada", exit: "Saída", adjustment: "Ajuste", sale: "Venda", sale_cancellation: "Cancelamento de venda", consumption: "Consumação", consumption_cancellation: "Cancelamento de consumação", cancellation: "Cancelamento" };
const tones: Record<string, string> = { entry: "bg-success/10 text-emerald-700", exit: "bg-danger/10 text-red-700", adjustment: "bg-primary/10 text-primary", sale: "bg-danger/10 text-red-700", consumption: "bg-warning/15 text-amber-700", sale_cancellation: "bg-success/10 text-emerald-700", consumption_cancellation: "bg-success/10 text-emerald-700", cancellation: "bg-success/10 text-emerald-700" };

function signed(movement: StockMovement) {
  if (movement.type === "adjustment") {
    const previous = Number(movement.previous_quantity); const final = Number(movement.final_quantity);
    if (!Number.isFinite(previous) || !Number.isFinite(final)) return "-";
    const difference = final - previous;
    return `${difference > 0 ? "+" : ""}${formatQuantity(difference.toFixed(3))}`;
  }
  const positive = ["entry", "cancellation", "sale_cancellation", "consumption_cancellation"].includes(movement.type);
  return `${positive ? "+" : "-"}${formatQuantity(movement.movement_quantity.replace("-", ""))}`;
}

function Movements() {
  const { currentCompany, currentBranch } = useAuth();
  const [data, setData] = useState<Paginated<StockMovement> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [period, setPeriod] = useState<PeriodValue>({ start: "", end: "" });
  const contextRef = useRef(""); contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;

  function query(selectedPeriod = period) {
    const params = new URLSearchParams({ company: String(currentCompany?.id || ""), branch: String(currentBranch?.id || "") });
    if (search) params.set("search", search); if (type) params.set("type", type);
    if (selectedPeriod.start) params.set("start_datetime", selectedPeriod.start); if (selectedPeriod.end) params.set("end_datetime", selectedPeriod.end);
    return `stock-movements/?${params}`;
  }
  function pagePath(path?: string) { if (!path) return query(); const url = new URL(path, window.location.origin); url.searchParams.set("company", String(currentCompany?.id)); url.searchParams.set("branch", String(currentBranch?.id)); return /^https?:\/\//.test(path) ? url.toString() : `${url.pathname.replace(/^\//, "")}${url.search}`; }
  async function load(path?: string, context = contextRef.current) { if (!currentCompany || !currentBranch) { setData(null); setLoading(false); return; } setLoading(true); setError(""); try { const response = await http.get<Paginated<StockMovement>>(pagePath(path)); if (contextRef.current === context) setData(response); } catch (caught) { if (contextRef.current === context) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as movimentações."); } finally { if (contextRef.current === context) setLoading(false); } }
  useEffect(() => { setSearch(""); setType(""); setPeriod({ start: "", end: "" }); setData(null); void load(`stock-movements/?company=${currentCompany?.id || ""}&branch=${currentBranch?.id || ""}`, contextRef.current); }, [currentCompany?.id, currentBranch?.id]);

  return <><PageHeader title="Movimentações de estoque" description={`Histórico imutável de ${currentBranch?.name || "filial atual"}.`} action={<Link href="/estoque" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar ao estoque</Link>} /><div className="space-y-4 p-4 sm:p-6 lg:p-8">
    {error && <Alert message={error} />}
    <form className="card grid gap-3 p-4 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => { event.preventDefault(); void load(); }}><div className="relative"><Search className="absolute left-3 top-3 size-4 text-slate-400" /><Input className="pl-9" placeholder="Produto, código ou motivo" value={search} onChange={(event) => setSearch(event.target.value)} /></div><Select value={type} onChange={(event) => setType(event.target.value)}><option value="">Todos os tipos</option><option value="entry">Entrada</option><option value="exit">Saída</option><option value="adjustment">Ajuste</option><option value="sale">Venda</option><option value="sale_cancellation">Cancelamento de venda</option><option value="consumption">Consumação</option><option value="consumption_cancellation">Cancelamento de consumação</option></Select><Button type="submit"><SlidersHorizontal className="size-4" />Filtrar</Button><PeriodFilter className="sm:col-span-3" value={period} onApply={(next) => { setPeriod(next); void load(query(next)); }} /></form>
    <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Histórico</h2><p className="mt-1 text-[11px] text-slate-500">Movimento e transição de saldo</p></div><History className="size-5 text-slate-300" /></div>{loading ? <TableLoading /> : data?.results.length ? <><div className="table-wrap"><table className="data-table"><thead><tr><th>Data</th><th>Produto</th><th>Tipo</th><th>Quantidade</th><th>Transição de saldo</th><th>Responsável</th><th>Motivo</th></tr></thead><tbody>{data.results.map((movement) => { const amount = signed(movement); const positive = amount.startsWith("+"); return <tr key={movement.id}><td className="whitespace-nowrap">{formatDate(movement.created_at)}</td><td><strong className="block">{movement.product_name}</strong><span className="text-[11px] text-slate-400">{movement.internal_code}</span></td><td><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${tones[movement.type] || tones.cancellation}`}>{labels[movement.type] || movement.type}</span></td><td className={`font-bold ${positive ? "text-emerald-700" : "text-red-700"}`}>{amount} {movement.unit.toUpperCase()}</td><td>{formatQuantity(movement.previous_quantity)} → {formatQuantity(movement.final_quantity)}</td><td>{movement.user_name}</td><td className="min-w-48">{movement.reason}</td></tr>; })}</tbody></table></div><Pagination count={data.count} next={data.next} previous={data.previous} onPage={load} /></> : <EmptyState title="Nenhuma movimentação" description="Ajuste os filtros ou registre uma operação de estoque." />}</section>
  </div></>;
}

export default function MovementsPage() { return <AdminGuard requiredPermissions={[permissions.viewInventoryHistory]}><Movements /></AdminGuard>; }
