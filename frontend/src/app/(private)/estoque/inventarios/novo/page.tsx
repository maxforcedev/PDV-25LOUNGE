"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Select, Textarea } from "@/components/ui";
import { contentUnitLabel, isExactContentValid, isUnitQuantityValid, physicalQuantityDisplay, quantityInputMode } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { InventoryCount, InventoryCountMode, InventoryWorkflowOptions, InventoryWorkflowStockOption } from "@/types";

type Row = {
  product: number;
  counted_quantity: string;
  counted_complete_packages: string;
  counted_residual_content: string;
};

function initialRows(stocks: InventoryWorkflowStockOption[]) {
  return Object.fromEntries(stocks.map((stock) => [stock.product, {
    product: stock.product,
    counted_quantity: "",
    counted_complete_packages: "",
    counted_residual_content: "",
  }])) as Record<number, Row>;
}

function NewCount() {
  const router = useRouter();
  const { currentBranch, supportSession } = useAuth();
  const [options, setOptions] = useState<InventoryWorkflowOptions | null>(null);
  const [rows, setRows] = useState<Record<number, Row>>({});
  const [mode, setMode] = useState<InventoryCountMode>("FULL");
  const [query, setQuery] = useState("");
  const [observation, setObservation] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const branchId = currentBranch?.id;
  const readOnly = supportSession?.mode === "READ_ONLY";

  useEffect(() => {
    let active = true;
    setReviewing(false); setError(""); setOptions(null); setRows({});
    if (!branchId) { setLoading(false); return; }
    setLoading(true);
    void http.get<InventoryWorkflowOptions>("inventory-counts/options/")
      .then((response) => {
        if (!active) return;
        setOptions(response);
        setRows(initialRows(response.stocks));
      })
      .catch((caught) => active && setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções do inventário."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [branchId]);

  const selectedStocks = (options?.stocks || []).filter((stock) => mode === "FULL" || rows[stock.product]?.counted_quantity !== "" || rows[stock.product]?.counted_complete_packages !== "");
  const visibleStocks = (options?.stocks || []).filter((stock) => `${stock.product_name} ${stock.internal_code} ${stock.category_name || ""}`.toLowerCase().includes(query.toLowerCase()));

  function update(product: number, value: Partial<Row>) {
    setRows((current) => ({ ...current, [product]: { ...current[product], ...value } }));
  }

  function validate() {
    if (!selectedStocks.length) return "Selecione ao menos um produto para a contagem parcial.";
    for (const stock of selectedStocks) {
      const row = rows[stock.product];
      const tracked = !!stock.package_content && !!stock.content_unit;
      if (tracked) {
        if (!/^\d+$/.test(row.counted_complete_packages)) return `Informe embalagens completas para ${stock.product_name}.`;
        if (!isExactContentValid(row.counted_residual_content || "0", true) || Number((row.counted_residual_content || "0").replace(",", ".")) >= Number(stock.package_content)) return `Informe residual válido para ${stock.product_name}.`;
      } else if (!isUnitQuantityValid(row.counted_quantity, stock.unit, true)) return `Informe quantidade válida para ${stock.product_name}.`;
    }
    return "";
  }

  function beginReview(event: React.FormEvent) {
    event.preventDefault();
    const message = validate();
    if (message) { setError(message); return; }
    setError(""); setReviewing(true);
  }

  async function capture() {
    if (!currentBranch || !options) return;
    setSaving(true); setError("");
    try {
      const count = await http.post<InventoryCount>("inventory-counts/", {
        branch: currentBranch.id,
        mode,
        observation,
        items: selectedStocks.map((stock) => {
          const row = rows[stock.product];
          const tracked = !!stock.package_content && !!stock.content_unit;
          return {
            product: stock.product,
            ...(tracked ? {
              counted_complete_packages: Number(row.counted_complete_packages),
              // Empty residual is canonically zero; users do not need to type it.
              counted_residual_content: (row.counted_residual_content || "0").replace(",", "."),
            } : { counted_quantity: row.counted_quantity.replace(",", ".") }),
          };
        }),
      });
      router.push(`/estoque/inventarios/${count.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível capturar a contagem.");
      setSaving(false);
    }
  }

  function display(stock: InventoryWorkflowStockOption, row: Row) {
    if (stock.package_content && stock.content_unit) return `${row.counted_complete_packages || "0"} embalagens + ${row.counted_residual_content || "0"} ${contentUnitLabel(stock.content_unit)}`;
    return `${row.counted_quantity || "0"} ${stock.unit.toUpperCase()}`;
  }

  return <>
    <PageHeader title="Nova contagem" description={`${currentBranch?.name || "Selecione uma filial"} · preencha, revise e só então capture o snapshot imutável.`} action={<Link href="/estoque" className="btn btn-secondary"><ArrowLeft className="size-4" />Estoque</Link>} />
    <InventoryNav />
    <div className="p-4 sm:p-6 lg:p-8"><form className="mx-auto max-w-6xl space-y-4" onSubmit={beginReview}>
      {error && <Alert message={error} />}
      <section className="card p-5"><div className="grid gap-4 sm:grid-cols-[280px_1fr]"><Field label="Tipo de contagem"><Select value={mode} disabled={reviewing || readOnly} onChange={(event) => setMode(event.target.value as InventoryCountMode)}><option value="FULL">Contagem completa</option><option value="PARTIAL">Contagem parcial</option></Select></Field><p className="self-end text-xs text-muted">{mode === "FULL" ? "Todos os produtos controlados da filial, inclusive saldos zerados." : "Preencha somente os produtos que deseja conferir."}</p></div><div className="mt-4"><Field label="Observação geral" optional><Textarea value={observation} disabled={reviewing || readOnly} onChange={(event) => setObservation(event.target.value)} placeholder="Opcional" /></Field></div></section>
      {!reviewing ? <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Produtos para contagem</h2><p className="mt-1 text-[11px] text-muted">Agrupados por categoria. O saldo teórico é apenas referência operacional.</p></div><div className="relative w-full sm:w-72"><Search className="absolute left-3 top-3 size-4 text-muted" /><Input className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar produto ou código" /></div></div>{loading ? <p className="p-6 text-sm text-muted">Carregando produtos...</p> : visibleStocks.map((stock, index) => { const row = rows[stock.product]; const tracked = !!stock.package_content && !!stock.content_unit; const previousCategory = visibleStocks[index - 1]?.category_name; return <div key={stock.product}>{stock.category_name !== previousCategory && <h3 className="border-y border-subtle bg-surface-muted px-5 py-2 text-xs font-bold">{stock.category_name || "Sem categoria"}</h3>}<article className="grid gap-3 border-b border-subtle p-4 sm:grid-cols-[minmax(0,1fr)_240px]"><div><strong>{stock.product_name}</strong><small className="ml-2 text-muted">{stock.internal_code}</small><p className="mt-1 text-xs text-muted">Teórico: {physicalQuantityDisplay({ quantity: stock.current_quantity, unit: stock.unit, content: stock.current_content, packageContent: stock.package_content, contentUnit: stock.content_unit })}</p></div>{tracked ? <div className="grid grid-cols-2 gap-2"><Input required={mode === "FULL"} inputMode="numeric" min="0" step="1" placeholder="Embalagens" value={row.counted_complete_packages} onChange={(event) => update(stock.product, { counted_complete_packages: event.target.value.replace(/\D/g, "") })} disabled={readOnly} /><Input inputMode="decimal" min="0" step="0.000000001" placeholder={`Residual (${contentUnitLabel(stock.content_unit)})`} value={row.counted_residual_content} onChange={(event) => update(stock.product, { counted_residual_content: event.target.value })} disabled={readOnly} /></div> : <Input required={mode === "FULL"} inputMode={quantityInputMode(stock.unit)} min="0" step={stock.unit.toLowerCase() === "un" ? "1" : "0.001"} placeholder={`Contado (${stock.unit.toUpperCase()})`} value={row.counted_quantity} onChange={(event) => update(stock.product, { counted_quantity: event.target.value })} disabled={readOnly} />}</article></div>; })}</section> : <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Revisão antes da captura</h2><p className="mt-1 text-[11px] text-muted">Ainda não existe snapshot persistido. Voltar permite editar esta contagem.</p></div></div><div className="divide-y divide-subtle">{selectedStocks.map((stock) => <div key={stock.product} className="grid gap-2 p-4 text-sm sm:grid-cols-3"><strong>{stock.product_name}</strong><span>Teórico: {physicalQuantityDisplay({ quantity: stock.current_quantity, unit: stock.unit, content: stock.current_content, packageContent: stock.package_content, contentUnit: stock.content_unit })}</span><span className="font-bold">Contado: {display(stock, rows[stock.product])}</span></div>)}</div></section>}
      <div className="flex justify-end gap-2"><Link href="/estoque" className="btn btn-secondary">Cancelar</Link>{reviewing ? <><Button type="button" variant="secondary" onClick={() => setReviewing(false)} disabled={saving}>Voltar e editar</Button><Button type="button" loading={saving} disabled={readOnly} onClick={() => void capture()}>Capturar inventário</Button></> : <Button type="submit" disabled={readOnly || loading}>Revisar <ArrowRight className="size-4" /></Button>}</div>
    </form></div>
  </>;
}

export default function NewCountPage() {
  return <AdminGuard requiredPermissions={[permissions.performInventoryCount]}><NewCount /></AdminGuard>;
}
