"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Eye,
  Plus,
  Search,
  ShoppingBasket,
  SlidersHorizontal,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import {
  Alert,
  Button,
  EmptyState,
  Input,
  Select,
  TableLoading,
} from "@/components/ui";
import { formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import {
  inDatePeriod,
  purchaseStatusLabels,
  purchaseTypeLabels,
} from "@/lib/purchases";
import { useAuth } from "@/providers/auth-provider";
import type { PurchaseOrder, PurchaseOrderStatus, Supplier } from "@/types";

type Filters = {
  supplier: string;
  type: string;
  status: string;
  document: string;
  period: PeriodValue;
};
const emptyFilters = (): Filters => ({
  supplier: "",
  type: "",
  status: "",
  document: "",
  period: { start: "", end: "" },
});

function PurchaseBadge({ status }: { status: PurchaseOrderStatus }) {
  const tone =
    status === "RECEIVED"
      ? "bg-success/10 text-success-strong"
      : status === "CANCELLED"
        ? "bg-danger/10 text-danger-strong"
        : status === "PARTIALLY_RECEIVED"
          ? "bg-warning/15 text-warning-strong"
          : "bg-info-surface text-info-strong";
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${tone}`}
    >
      {purchaseStatusLabels[status]}
    </span>
  );
}

function Purchases() {
  const { currentBranch, currentCompany, hasPermission, supportSession } =
    useAuth();
  const companyId = currentCompany?.id;
  const branchId = currentBranch?.id;
  const canCreate =
    hasPermission(permissions.createPurchase) &&
    supportSession?.mode !== "READ_ONLY";
  const canViewCosts = hasPermission(permissions.viewPurchaseCosts);
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [draft, setDraft] = useState<Filters>(emptyFilters);
  const [applied, setApplied] = useState<Filters>(emptyFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const context = useRef("");
  context.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;

  async function load(selected = applied, key = context.current) {
    if (!currentBranch) {
      setOrders([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (selected.supplier) params.set("supplier", selected.supplier);
    if (selected.type) params.set("order_type", selected.type);
    if (selected.status) params.set("status", selected.status);
    if (selected.document.trim())
      params.set("search", selected.document.trim());
    try {
      const items = await http.getAll<PurchaseOrder>(
        `purchase-orders/?${params}`,
      );
      if (context.current === key)
        setOrders(
          items.filter((item) =>
            inDatePeriod(
              item.created_at,
              selected.period.start,
              selected.period.end,
            ),
          ),
        );
    } catch (caught) {
      if (context.current === key)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar as compras.",
        );
    } finally {
      if (context.current === key) setLoading(false);
    }
  }
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const selected = emptyFilters();
    setDraft(selected);
    setApplied(selected);
    setOrders([]);
    setSuppliers([]);
    setError("");
    const key = context.current;
    if (!branchId || !companyId) {
      setLoading(false);
      return;
    }
    void loadRef.current(selected, key);
    let active = true;
    http
      .getAll<Supplier>(`suppliers/?company=${companyId}&status=active`)
      .then((items) => {
        if (active && context.current === key) setSuppliers(items);
      })
      .catch(() => {
        if (active) setSuppliers([]);
      });
    return () => {
      active = false;
    };
  }, [branchId, companyId]);

  function apply(event: React.FormEvent) {
    event.preventDefault();
    const selected = { ...draft, period: { ...draft.period } };
    setApplied(selected);
    void load(selected);
  }
  function clear() {
    const selected = emptyFilters();
    setDraft(selected);
    setApplied(selected);
    void load(selected);
  }

  return (
    <>
      <PageHeader
        title="Compras"
        description={`${currentBranch?.name || "Selecione uma filial"} · pedidos e entradas diretas.`}
        action={
          <Link
            href="/compras/nova"
            className={`btn btn-primary ${!canCreate || !currentBranch ? "pointer-events-none opacity-50" : ""}`}
            aria-disabled={!canCreate || !currentBranch}
          >
            <Plus className="size-4" />
            Nova compra
          </Link>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        <form
          className="card grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4"
          onSubmit={apply}
        >
          <Select
            aria-label="Fornecedor"
            value={draft.supplier}
            onChange={(event) =>
              setDraft((value) => ({ ...value, supplier: event.target.value }))
            }
          >
            <option value="">Todos os fornecedores</option>
            {suppliers.map((supplier) => (
              <option key={supplier.id} value={supplier.id}>
                {supplier.trade_name}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Tipo"
            value={draft.type}
            onChange={(event) =>
              setDraft((value) => ({ ...value, type: event.target.value }))
            }
          >
            <option value="">Todos os tipos</option>
            {Object.entries(purchaseTypeLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Status"
            value={draft.status}
            onChange={(event) =>
              setDraft((value) => ({ ...value, status: event.target.value }))
            }
          >
            <option value="">Todos os status</option>
            {Object.entries(purchaseStatusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted" />
            <Input
              className="pl-9"
              placeholder="Número ou documento"
              value={draft.document}
              onChange={(event) =>
                setDraft((value) => ({
                  ...value,
                  document: event.target.value,
                }))
              }
            />
          </div>
          <PeriodFilter
            className="md:col-span-2 xl:col-span-4"
            value={draft.period}
            onChange={(period) => setDraft((value) => ({ ...value, period }))}
          />
          <div className="flex justify-end gap-2 md:col-span-2 xl:col-span-4">
            <Button type="button" variant="secondary" onClick={clear}>
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
              <h2 className="text-sm font-bold">Compras da filial</h2>
              <p className="mt-1 text-[11px] text-muted">
                {orders.length} {orders.length === 1 ? "registro" : "registros"}{" "}
                no período
              </p>
            </div>
            <ShoppingBasket className="size-5 text-muted" />
          </div>
          {loading ? (
            <TableLoading columns={canViewCosts ? 7 : 6} />
          ) : orders.length ? (
            <>
              <div className="divide-y divide-subtle md:hidden">
                {orders.map((order) => (
                  <article key={order.id} className="space-y-3 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link
                          className="font-bold text-link"
                          href={`/compras/${order.id}`}
                        >
                          {order.order_number}
                        </Link>
                        <p className="mt-1 text-xs text-muted">
                          {order.supplier_name}
                        </p>
                      </div>
                      <PurchaseBadge status={order.status} />
                    </div>
                    <dl className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <dt className="text-muted">Tipo</dt>
                        <dd className="font-semibold">
                          {purchaseTypeLabels[order.order_type]}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted">Criada em</dt>
                        <dd>{formatDate(order.created_at)}</dd>
                      </div>
                      <div>
                        <dt className="text-muted">Documento</dt>
                        <dd>{order.document_number || "-"}</dd>
                      </div>
                      {canViewCosts && (
                        <div>
                          <dt className="text-muted">Total</dt>
                          <dd className="font-bold">
                            {formatBRL(order.payable_total)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </article>
                ))}
              </div>
              <div className="table-wrap hidden md:block">
                <table className="data-table min-w-225">
                  <thead>
                    <tr>
                      <th>Compra</th>
                      <th>Fornecedor</th>
                      <th>Tipo</th>
                      <th>Documento</th>
                      <th>Data</th>
                      {canViewCosts && <th>Total</th>}
                      <th>Status</th>
                      <th className="text-right">Ação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((order) => (
                      <tr key={order.id}>
                        <td>
                          <strong>{order.order_number}</strong>
                        </td>
                        <td>{order.supplier_name}</td>
                        <td>{purchaseTypeLabels[order.order_type]}</td>
                        <td>{order.document_number || "-"}</td>
                        <td>{formatDate(order.created_at)}</td>
                        {canViewCosts && (
                          <td className="font-bold">
                            {formatBRL(order.payable_total)}
                          </td>
                        )}
                        <td>
                          <PurchaseBadge status={order.status} />
                        </td>
                        <td>
                          <div className="flex justify-end">
                            <Link
                              className="icon-button"
                              href={`/compras/${order.id}`}
                              title="Ver compra"
                            >
                              <Eye className="size-4" />
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <EmptyState
              title="Nenhuma compra encontrada"
              description="Revise os filtros ou crie a primeira compra desta filial."
            />
          )}
        </section>
      </div>
    </>
  );
}

export default function PurchasesPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewPurchase]}>
      <Purchases />
    </AdminGuard>
  );
}
