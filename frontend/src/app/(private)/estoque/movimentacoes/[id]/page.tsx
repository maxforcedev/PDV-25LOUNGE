"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, History } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { Alert, Spinner } from "@/components/ui";
import { domainLabel } from "@/lib/domain-labels";
import { formatDate } from "@/lib/format";
import { movementDomainOriginLabel, physicalQuantityDisplay } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import type { Product, StockMovement } from "@/types";

function originHref(movement: StockMovement) {
  const origin = movement.origin;
  if (!origin) return null;
  const paths: Record<string, string> = {
    sale: "/vendas", consumption: "/consumacoes", purchase: "/compras",
    transfer: "/estoque/transferencias", inventory_count: "/estoque/inventarios",
    command: "/comandas", loss: "/estoque/perdas",
  };
  return paths[origin.kind]
    ? origin.kind === "loss" ? paths[origin.kind] : `${paths[origin.kind]}/${origin.id}`
    : null;
}

function MovementDetail() {
  const id = String(useParams<{ id: string }>().id);
  const [movement, setMovement] = useState<StockMovement | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void http.get<StockMovement>(`stock-movements/${id}/`)
      .then(async (response) => { if (active) setMovement(response); if (response.content_quantity != null) { const detail = await http.get<Product>(`products/${response.product}/`).catch(() => null); if (active) setProduct(detail); } })
      .catch((caught) => { if (active) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar a movimentação."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  const packageContent = movement?.package_content || product?.fraction_config?.package_content;
  const contentUnit = movement?.content_unit || product?.fraction_config?.content_unit;
  const previousDisplay = movement ? physicalQuantityDisplay({ quantity: movement.previous_quantity, unit: movement.unit, content: movement.previous_content, packageContent, contentUnit, completePackages: movement.previous_complete_packages, residualContent: movement.previous_residual_content }) : "-";
  const movementDisplay = movement ? physicalQuantityDisplay({ quantity: movement.movement_quantity, unit: movement.unit, content: movement.content_quantity, packageContent, contentUnit, completePackages: movement.movement_complete_packages, residualContent: movement.movement_residual_content }) : "-";
  const finalDisplay = movement ? physicalQuantityDisplay({ quantity: movement.final_quantity, unit: movement.unit, content: movement.final_content, packageContent, contentUnit, completePackages: movement.final_complete_packages, residualContent: movement.final_residual_content }) : "-";
  const originTarget = movement ? originHref(movement) : null;

  return <>
    <PageHeader title={`Movimento #${id}`} description="Registro físico exato associado ao evento de estoque." action={<Link href="/estoque/movimentacoes" className="btn btn-secondary"><ArrowLeft className="size-4" />Movimentações</Link>} />
    <InventoryNav />
    <div className="p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      {loading ? <div className="card flex min-h-64 items-center justify-center text-primary"><Spinner className="size-7" /></div> : movement ? <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">{movement.product_name}</h2><p className="mt-1 text-xs text-muted">{movement.internal_code} · {movement.branch_name}</p></div><History className="size-5 text-muted" /></div>
        <dl className="grid gap-px bg-subtle sm:grid-cols-2 lg:grid-cols-3">
          {[
            ["Registrado em", formatDate(movement.created_at)],
            ["Origem de domínio", movementDomainOriginLabel(movement.domain_origin)],
            ["Natureza", domainLabel(movement.nature)],
            ["Quantidade anterior", previousDisplay],
            ["Movimento", `${movement.content_quantity != null && Number(movement.content_quantity) > 0 ? "+" : ""}${movementDisplay}`],
            ["Quantidade final", finalDisplay],
            ["Responsável", movement.user_name],
            ["Referência da operação", movement.operation_reference || "-"],
            ["Operação", movement.operation_label || "-"],
          ].map(([label, value]) => <div key={label} className="bg-surface p-5"><dt className="text-[11px] font-semibold text-muted">{label}</dt><dd className="mt-1 break-all text-sm font-bold">{value}</dd></div>)}
        </dl>
        {originTarget && movement.origin && <div className="border-t border-subtle p-5"><strong className="text-xs">Origem</strong><Link className="mt-1 block text-sm font-bold text-primary" href={originTarget}>{movement.origin.label}</Link></div>}
        {movement.reason && <div className="border-t border-subtle p-5"><strong className="text-xs">Motivo</strong><p className="mt-2 text-sm text-muted">{movement.reason}</p></div>}
      </section> : !error && <Alert message="Movimentação não encontrada." />}
    </div>
  </>;
}

export default function MovementDetailPage() {
  return <AdminGuard requiredPermissions={[permissions.viewInventoryHistory]}><MovementDetail /></AdminGuard>;
}
