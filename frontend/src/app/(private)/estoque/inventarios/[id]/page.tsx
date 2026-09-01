"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, Spinner } from "@/components/ui";
import { formatDate, formatDecimalBRL, formatQuantity } from "@/lib/format";
import {
  countStatusLabels,
  inventoryDecimalSign,
  inventoryTone,
  physicalQuantityDisplay,
} from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { InventoryCount } from "@/types";

function countValue(
  item: InventoryCount["items"][number],
  kind: "theoretical" | "counted" | "difference",
) {
  if (
    item.content_unit &&
    (item.theoretical_content != null || item.counted_content != null)
  ) {
    const content =
      kind === "theoretical"
        ? item.theoretical_content
        : kind === "counted"
          ? item.counted_content
          : item.difference_content;
    const display = physicalQuantityDisplay({
      content,
      packageContent: item.package_content_snapshot,
      contentUnit: item.content_unit,
      completePackages:
        kind === "counted"
          ? item.counted_complete_packages
          : kind === "difference"
            ? item.difference_complete_packages
            : undefined,
      residualContent:
        kind === "counted"
          ? item.counted_residual_content
          : kind === "difference"
            ? item.difference_residual_content
            : undefined,
    });
    return `${inventoryDecimalSign(content || "0") === 1 && kind === "difference" ? "+" : ""}${display}`;
  }
  const value =
    kind === "theoretical"
      ? item.theoretical_quantity
      : kind === "counted"
        ? item.counted_quantity
        : item.difference_quantity;
  return `${inventoryDecimalSign(value || "0") === 1 && kind === "difference" ? "+" : ""}${formatQuantity(value)}`;
}

function comparisonTone(item: InventoryCount["items"][number]) {
  const difference = inventoryDecimalSign(
    item.difference_content ?? item.difference_quantity,
  );
  if (difference === -1) return "text-danger-strong";
  if (difference === 1) return "text-warning-strong";
  return "text-success-strong";
}

function comparisonSurface(item: InventoryCount["items"][number]) {
  const difference = inventoryDecimalSign(
    item.difference_content ?? item.difference_quantity,
  );
  if (difference === -1) return "bg-danger/10";
  if (difference === 1) return "bg-warning/15";
  return "bg-success/10";
}

function CountDetail() {
  const id = String(useParams<{ id: string }>().id);
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const canViewReport = hasPermission(permissions.viewAdvancedInventory);
  const [count, setCount] = useState<InventoryCount | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const key = useRef("");
  const branchId = currentBranch?.id;

  async function load() {
    if (!canViewReport) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setCount(await http.get<InventoryCount>(`inventory-counts/${id}/`));
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar o inventário.",
      );
    } finally {
      setLoading(false);
    }
  }
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    setCount(null);
    setSuccess("");
    key.current = "";
    void loadRef.current();
  }, [id, branchId]);

  const canConfirm =
    hasPermission(permissions.performInventoryCount) &&
    supportSession?.mode !== "READ_ONLY" &&
    (count
      ? count.status === "OPEN" && count.branch === branchId
      : !canViewReport);

  async function confirm() {
    setSaving(true);
    setError("");
    try {
      const result = await http.post<InventoryCount>(
        `inventory-counts/${id}/confirm/`,
        { idempotency_key: key.current },
      );
      setCount(result);
      setConfirming(false);
      setSuccess(
        "Inventário confirmado. As diferenças foram conciliadas uma única vez.",
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível confirmar o inventário.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading && !count)
    return (
      <div className="flex min-h-96 items-center justify-center text-primary">
        <Spinner className="size-7" />
      </div>
    );

  return (
    <>
      <PageHeader
        title={
          count
            ? `Inventário ${count.id.slice(0, 8).toUpperCase()}`
            : `Inventário ${id.slice(0, 8).toUpperCase()}`
        }
        description={
          count
            ? `${count.branch_name} · capturado em ${formatDate(count.created_at)}`
            : "Ação autorizada sem acesso ao relatório"
        }
        action={
          <div className="flex gap-2">
            <Link href="/estoque/inventarios" className="btn btn-secondary">
              <ArrowLeft className="size-4" />
              Voltar
            </Link>
            {canConfirm && (
              <Button
                onClick={() => {
                  if (!key.current) key.current = crypto.randomUUID();
                  setConfirming(true);
                }}
              >
                <CheckCircle2 className="size-4" />
                Confirmar inventário
              </Button>
            )}
          </div>
        }
      />
      <InventoryNav />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {success && <Alert message={success} type="success" />}
        {!count && !canViewReport && (
          <section className="card p-5">
            <strong className="text-sm">Confirmação independente</strong>
            <p className="mt-1 text-xs text-muted">
              A consulta do relatório permanece oculta. A API validará o
              inventário, o estado e a filial ao confirmar.
            </p>
          </section>
        )}
        {count && (
          <>
            <section className="card p-5 sm:p-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(count.status)}`}
                  >
                    {countStatusLabels[count.status]}
                  </span>
                  <span className="ml-2 text-xs text-muted">
                    {count.mode === "FULL"
                      ? "Contagem completa"
                      : "Contagem parcial"}
                  </span>
                  {count.observation && (
                    <p className="mt-4 text-sm">{count.observation}</p>
                  )}
                  {canViewReport && (
                    <p className="mt-2 text-xs text-muted">
                      Criado por #{count.created_by}
                    </p>
                  )}
                </div>
                {canViewReport && count.confirmed_at && (
                  <div className="text-xs">
                    <span className="text-muted">Confirmado em</span>
                    <strong className="mt-1 block">
                      {formatDate(count.confirmed_at)}
                    </strong>
                    <span className="text-muted">
                      por #{count.confirmed_by}
                    </span>
                  </div>
                )}
              </div>
            </section>
            <section className="card overflow-hidden">
              <div className="card-header">
                <div>
                  <h2 className="text-sm font-bold">Contagem capturada</h2>
                  <p className="mt-1 text-[11px] text-muted">
                    Teórico, físico, horário e diferença usada na confirmação.
                  </p>
                </div>
              </div>
              <div className="divide-y divide-subtle md:hidden">
                {count.items.map((item) => {
                  const sign = inventoryDecimalSign(
                    item.difference_content ?? item.difference_quantity,
                  );
                  return (
                    <article
                      key={item.id}
                      className={`p-4 ${comparisonSurface(item)}`}
                    >
                      <strong>{item.product_name}</strong>
                      <p className="mt-1 text-xs text-muted">
                        Contado em {formatDate(item.counted_at)}
                        {canViewReport ? ` por #${item.counted_by}` : ""}
                      </p>
                      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <dt className="text-muted">Teórico</dt>
                          <dd>{countValue(item, "theoretical")}</dd>
                        </div>
                        <div>
                          <dt className="text-muted">Contado</dt>
                          <dd className={`font-bold ${comparisonTone(item)}`}>
                            {countValue(item, "counted")}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted">Situação</dt>
                          <dd className={`font-bold ${comparisonTone(item)}`}>
                            {sign === -1
                              ? "Falta"
                              : sign === 1
                                ? "Sobra"
                                : "Correto"}
                          </dd>
                        </div>
                      </dl>
                      {item.observation && (
                        <p className="mt-2 text-xs text-muted">
                          {item.observation}
                        </p>
                      )}
                      {canViewReport && item.movement_ids.length > 0 && (
                        <Link
                          href={`/estoque/movimentacoes?operation_reference=${count.id}&domain_origin=INVENTORY_COUNT`}
                          className="mt-3 inline-block text-xs font-semibold text-link"
                        >
                          Ver ajuste
                        </Link>
                      )}
                    </article>
                  );
                })}
              </div>
              <div className="table-wrap hidden md:block">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Produto / horário</th>
                      <th>Teórico</th>
                      <th>Contado</th>
                      <th>Situação</th>
                      {canViewReport && (
                        <>
                          <th>Impactos</th>
                          <th>Ajuste / movimento</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {count.items.map((item) => {
                      const sign = inventoryDecimalSign(
                        item.difference_content ?? item.difference_quantity,
                      );
                      return (
                        <tr key={item.id} className={comparisonSurface(item)}>
                          <td>
                            <strong>{item.product_name}</strong>
                            <small className="block text-muted">
                              {formatDate(item.counted_at)}
                              {canViewReport ? ` · #${item.counted_by}` : ""}
                            </small>
                          </td>
                          <td>{countValue(item, "theoretical")}</td>
                          <td className={`font-bold ${comparisonTone(item)}`}>
                            {countValue(item, "counted")}
                          </td>
                          <td className={`font-bold ${comparisonTone(item)}`}>
                            {sign === -1
                              ? "Falta"
                              : sign === 1
                                ? "Sobra"
                                : "Correto"}
                          </td>
                          {canViewReport && (
                            <>
                              <td>
                                <span className="block">
                                  Venda:{" "}
                                  {formatDecimalBRL(item.potential_sale_value)}
                                </span>
                                {item.cost_impact !== undefined && (
                                  <small className="text-muted">
                                    Custo: {formatDecimalBRL(item.cost_impact)}
                                  </small>
                                )}
                              </td>
                              <td>
                                {item.movement_ids.length ? (
                                  <Link
                                    href={`/estoque/movimentacoes?operation_reference=${count.id}&domain_origin=INVENTORY_COUNT`}
                                    className="font-semibold text-link"
                                  >
                                    Movimento #{item.movement_ids.join(", #")}
                                  </Link>
                                ) : (
                                  <span className="text-muted">
                                    Aguardando confirmação
                                  </span>
                                )}
                              </td>
                            </>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
      <ConfirmDialog
        open={confirming}
        title="Confirmar inventário"
        message="A diferença capturada será aplicada ao saldo atual como ajuste imutável. Repetir esta confirmação usará a mesma chave e não duplicará movimentos."
        confirmLabel="Confirmar e ajustar"
        loading={saving}
        onClose={() => setConfirming(false)}
        onConfirm={() => void confirm()}
      />
    </>
  );
}

export default function CountDetailPage() {
  return (
    <AdminGuard
      requiredPermissions={[
        permissions.viewAdvancedInventory,
        permissions.performInventoryCount,
      ]}
    >
      <CountDetail />
    </AdminGuard>
  );
}
