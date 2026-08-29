"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, History, Search, SlidersHorizontal } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { InventoryNav } from "@/components/inventory-nav";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { StockOperationDetails } from "@/components/stock-operation-details";
import {
  Alert,
  Button,
  EmptyState,
  Input,
  Pagination,
  Select,
  TableLoading,
} from "@/components/ui";
import { domainLabel } from "@/lib/domain-labels";
import { movementDomainOriginLabel, movementDomainOriginLabels, physicalQuantityDisplay } from "@/lib/inventory";
import { formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, StockMovement } from "@/types";

const labels: Record<string, string> = {
  entry: "Entrada",
  exit: "Saída",
  adjustment: "Ajuste",
  sale: "Venda",
  sale_cancellation: "Cancelamento de venda",
  consumption: "Consumação",
  consumption_cancellation: "Cancelamento de consumação",
  cancellation: "Cancelamento",
};
const tones: Record<string, string> = {
  entry: "bg-success/10 text-emerald-700",
  exit: "bg-danger/10 text-red-700",
  adjustment: "bg-primary/10 text-primary",
  sale: "bg-danger/10 text-red-700",
  consumption: "bg-warning/15 text-amber-700",
  sale_cancellation: "bg-success/10 text-emerald-700",
  consumption_cancellation: "bg-success/10 text-emerald-700",
  cancellation: "bg-success/10 text-emerald-700",
};
interface MovementFilters {
  search: string;
  product: string;
  type: string;
  nature: string;
  domainOrigin: string;
  operationReference: string;
  period: PeriodValue;
}
const emptyFilters = (): MovementFilters => ({
  search: "",
  product: "",
  type: "",
  nature: "",
  domainOrigin: "",
  operationReference: "",
  period: { start: "", end: "" },
});

function signed(movement: StockMovement) {
  if (movement.content_quantity != null) {
    const display = physicalQuantityDisplay({
      content: movement.content_quantity,
      packageContent: movement.package_content,
      contentUnit: movement.content_unit,
      completePackages: movement.movement_complete_packages,
      residualContent: movement.movement_residual_content,
    });
    return `${Number(movement.content_quantity) > 0 ? "+" : ""}${display}`;
  }
  if (movement.type === "adjustment") {
    const difference =
      Number(movement.final_quantity) - Number(movement.previous_quantity);
    return `${difference > 0 ? "+" : ""}${formatQuantity(difference.toFixed(3))} ${movement.unit.toUpperCase()}`;
  }
  const positive = [
    "entry",
    "cancellation",
    "sale_cancellation",
    "consumption_cancellation",
  ].includes(movement.type);
  return `${positive ? "+" : "-"}${formatQuantity(movement.movement_quantity.replace("-", ""))} ${movement.unit.toUpperCase()}`;
}

function balance(movement: StockMovement, final = false) {
  return physicalQuantityDisplay({
    quantity: final ? movement.final_quantity : movement.previous_quantity,
    unit: movement.unit,
    content: final ? movement.final_content : movement.previous_content,
    packageContent: movement.package_content,
    contentUnit: movement.content_unit,
    completePackages: final ? movement.final_complete_packages : movement.previous_complete_packages,
    residualContent: final ? movement.final_residual_content : movement.previous_residual_content,
  });
}

function originHref(movement: StockMovement) {
  const origin = movement.origin;
  if (!origin) return null;
  const paths: Record<string, string> = {
    sale: "/vendas",
    consumption: "/consumacoes",
    purchase: "/compras",
    transfer: "/estoque/transferencias",
    inventory_count: "/estoque/inventarios",
    command: "/comandas",
    loss: "/estoque/perdas",
  };
  const path = paths[origin.kind];
  return path ? origin.kind === "loss" ? path : `${path}/${origin.id}` : null;
}

function Movements() {
  const { currentCompany, currentBranch } = useAuth();
  const [data, setData] = useState<Paginated<StockMovement> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [product, setProduct] = useState("");
  const [type, setType] = useState("");
  const [nature, setNature] = useState("");
  const [domainOrigin, setDomainOrigin] = useState("");
  const [operationReference, setOperationReference] = useState("");
  const [period, setPeriod] = useState<PeriodValue>({ start: "", end: "" });
  const [appliedFilters, setAppliedFilters] =
    useState<MovementFilters>(emptyFilters);
  const contextRef = useRef("");
  const requestRef = useRef(0);
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;

  function query(selected: MovementFilters) {
    const params = new URLSearchParams({
      company: String(currentCompany?.id || ""),
      branch: String(currentBranch?.id || ""),
    });
    if (selected.search.trim()) params.set("search", selected.search.trim());
    if (selected.product) params.set("product", selected.product);
    if (selected.type) params.set("type", selected.type);
    if (selected.nature) params.set("nature", selected.nature);
    if (selected.domainOrigin) params.set("domain_origin", selected.domainOrigin);
    if (selected.operationReference)
      params.set("operation_reference", selected.operationReference);
    if (selected.period.start)
      params.set("start_datetime", selected.period.start);
    if (selected.period.end)
      params.set("end_datetime", selected.period.end);
    return `stock-movements/?${params}`;
  }
  function pagePath(path: string | undefined, selected: MovementFilters) {
    if (!path) return query(selected);
    const url = new URL(path, window.location.origin);
    url.searchParams.set("company", String(currentCompany?.id));
    url.searchParams.set("branch", String(currentBranch?.id));
    return /^https?:\/\//.test(path)
      ? url.toString()
      : `${url.pathname.replace(/^\//, "")}${url.search}`;
  }
  function syncUrl(selected: MovementFilters) {
    const params = new URLSearchParams();
    if (selected.search.trim()) params.set("search", selected.search.trim());
    if (selected.product) params.set("product", selected.product);
    if (selected.type) params.set("type", selected.type);
    if (selected.nature) params.set("nature", selected.nature);
    if (selected.domainOrigin) params.set("domain_origin", selected.domainOrigin);
    if (selected.operationReference)
      params.set("operation_reference", selected.operationReference);
    if (selected.period.start)
      params.set("start_datetime", selected.period.start);
    if (selected.period.end)
      params.set("end_datetime", selected.period.end);
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${params.size ? `?${params}` : ""}`,
    );
  }
  async function load(
    path?: string,
    context = contextRef.current,
    selected = appliedFilters,
  ) {
    const requestId = ++requestRef.current;
    if (!currentCompany || !currentBranch) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    setData(null);
    if (!path) {
      setAppliedFilters(selected);
      syncUrl(selected);
    }
    try {
      const response = await http.get<Paginated<StockMovement>>(
        pagePath(path, selected),
      );
      if (contextRef.current === context && requestRef.current === requestId)
        setData(response);
    } catch (caught) {
      if (contextRef.current === context && requestRef.current === requestId)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar as movimentações.",
        );
    } finally {
      if (contextRef.current === context && requestRef.current === requestId)
        setLoading(false);
    }
  }
  useEffect(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const selected = {
      search: queryParams.get("search") || "",
      product: queryParams.get("product") || "",
      type: queryParams.get("type") || "",
      nature: queryParams.get("nature") || "",
      domainOrigin: queryParams.get("domain_origin") || "",
      operationReference: queryParams.get("operation_reference") || "",
      period: {
        start: queryParams.get("start_datetime") || "",
        end: queryParams.get("end_datetime") || "",
      },
    };
    setSearch(selected.search);
    setProduct(selected.product);
    setType(selected.type);
    setNature(selected.nature);
    setDomainOrigin(selected.domainOrigin);
    setPeriod(selected.period);
    setData(null);
    setOperationReference(selected.operationReference);
    setAppliedFilters(selected);
    void load(undefined, contextRef.current, selected);
  }, [currentCompany?.id, currentBranch?.id]);

  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    const selected = { search, product, type, nature, domainOrigin, operationReference, period };
    void load(undefined, contextRef.current, selected);
  }

  function clearFilters() {
    const selected = emptyFilters();
    setSearch("");
    setProduct("");
    setType("");
    setNature("");
    setDomainOrigin("");
    setOperationReference("");
    setPeriod(selected.period);
    void load(undefined, contextRef.current, selected);
  }

  return (
    <>
      <PageHeader
        title="Movimentações de estoque"
        description={`Histórico imutável de ${currentBranch?.name || "filial atual"}.`}
        action={
          <Link href="/estoque" className="btn btn-secondary">
            <ArrowLeft className="size-4" />
            Voltar ao estoque
          </Link>
        }
      />
      <InventoryNav />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {operationReference && (
          <section className="card p-4 text-sm">
            <div>
              <div>
                <strong className="block">
                  {data?.results[0]?.operation_label || "Operação de estoque"}
                </strong>
                <p className="mt-1 text-xs text-muted">
                  Exibindo somente os movimentos desta operação.
                </p>
              </div>
            </div>
            <StockOperationDetails
              reference={operationReference}
              count={data?.results[0]?.operation_count || data?.count || 0}
            />
          </section>
        )}
        <form
          className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-5"
          onSubmit={applyFilters}
        >
          <div className="relative">
            <Search className="absolute left-3 top-3 size-4 text-slate-400" />
            <Input
              className="pl-9"
              placeholder="Produto, código ou motivo"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <Input
            inputMode="numeric"
            placeholder="ID do produto"
            aria-label="Produto"
            value={product}
            onChange={(event) => setProduct(event.target.value.replace(/\D/g, ""))}
          />
          <Select
            value={type}
            onChange={(event) => setType(event.target.value)}
          >
            <option value="">Todos os tipos</option>
            {Object.entries(labels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          <Select
            value={nature}
            onChange={(event) => setNature(event.target.value)}
          >
            <option value="">Todas as naturezas</option>
            <option value="normal">Entrada normal</option>
            <option value="bonus">Bonificada</option>
            <option value="return">Devolução</option>
            <option value="opening_balance">Saldo inicial</option>
            <option value="loss">Perda</option>
            <option value="damage">Avaria</option>
            <option value="internal_use">Uso interno</option>
            <option value="transfer">Transferência</option>
            <option value="inventory">Inventário</option>
            <option value="regularization">Regularização</option>
            <option value="balance_correction">Correção de saldo</option>
            <option value="correction">Correção</option>
            <option value="other">Outros</option>
          </Select>
          <Select
            aria-label="Origem de domínio"
            value={domainOrigin}
            onChange={(event) => setDomainOrigin(event.target.value)}
          >
            <option value="">Todas as origens</option>
            {Object.entries(movementDomainOriginLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </Select>
          <PeriodFilter
            className="sm:col-span-2 xl:col-span-5"
            value={period}
            onChange={setPeriod}
            onApply={(next) => {
              const selected = { ...appliedFilters, period: next };
              setPeriod(next);
              void load(undefined, contextRef.current, selected);
            }}
            showActions={false}
          />
          <div className="flex flex-wrap justify-end gap-2 sm:col-span-2 xl:col-span-5">
            <Button type="button" variant="secondary" onClick={clearFilters}>
              Limpar
            </Button>
            <Button type="submit">
              <SlidersHorizontal className="size-4" />
              Aplicar
            </Button>
          </div>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Histórico</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Movimento, natureza, operação e transição de saldo.
              </p>
            </div>
            <History className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Produto</th>
                      <th>Tipo / natureza</th>
                      <th>Quantidade</th>
                      <th>Transição</th>
                      <th>Responsável</th>
                      <th>Origem / detalhes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((movement) => {
                      const amount = signed(movement);
                      const target = originHref(movement);
                      return (
                        <tr key={movement.id}>
                          <td className="whitespace-nowrap">
                            {formatDate(movement.created_at)}
                          </td>
                          <td>
                            <strong className="block">
                              {movement.product_name}
                            </strong>
                            <span className="text-[11px] text-slate-400">
                              {movement.internal_code}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${tones[movement.type] || tones.cancellation}`}
                            >
                              {labels[movement.type] || movement.type}
                            </span>
                             <small className="mt-1 block text-slate-400">
                               {domainLabel(movement.nature)}
                             </small>
                             <small className="mt-1 block font-semibold text-muted">
                               {movementDomainOriginLabel(movement.domain_origin)}
                             </small>
                          </td>
                          <td
                            className={`font-bold ${amount.startsWith("+") ? "text-emerald-700" : "text-red-700"}`}
                          >
                            {amount}
                          </td>
                          <td>
                            {balance(movement)} → {balance(movement, true)}
                          </td>
                          <td>{movement.user_name}</td>
                          <td className="min-w-52">
                            {target ? (
                              <Link
                                className="font-bold text-primary"
                                href={target}
                              >
                                {movement.origin?.label}
                              </Link>
                            ) : (
                              <Link
                                className="font-bold text-primary"
                                href={`/estoque/movimentacoes/${movement.id}`}
                              >
                                {movement.operation_label}
                              </Link>
                            )}
                            {movement.reason && (
                              <span className="mt-1 block text-slate-500">
                                {movement.reason}
                              </span>
                            )}
                            <StockOperationDetails
                              reference={movement.operation_reference}
                              count={movement.operation_count}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={load}
              />
            </>
          ) : (
            <EmptyState
              title="Nenhuma movimentação"
              description="Não há movimentos para os filtros aplicados."
            />
          )}
        </section>
      </div>
    </>
  );
}

export default function MovementsPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewInventoryHistory]}>
      <Movements />
    </AdminGuard>
  );
}
