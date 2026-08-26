"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { StockOperationDetails } from "@/components/stock-operation-details";
import { Alert, Button, EmptyState, Field, Input, TableLoading, Textarea } from "@/components/ui";
import { formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { contentUnitLabel, isUnitQuantityValid, physicalQuantityDisplay, quantityInputMode } from "@/lib/inventory";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, Stock } from "@/types";

type OperationSuccess = { label: string; reference: string; count: number };

function RegularizeStock() {
  const { currentCompany, currentBranch } = useAuth();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [values, setValues] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<OperationSuccess | null>(null);
  const [reason, setReason] = useState("Regularização de saldos negativos");
  async function load() {
    if (!currentCompany || !currentBranch) return;
    setLoading(true);
    try {
      const result = await http.get<Paginated<Stock>>(`stocks/?company=${currentCompany.id}&branch=${currentBranch.id}&state=negative&page_size=200`);
      setStocks(result.results);
      setValues(Object.fromEntries(result.results.map((stock) => [stock.id, "0"])));
    } catch { setError("Não foi possível carregar os saldos negativos."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [currentCompany?.id, currentBranch?.id]);
  async function submit() {
    if (!currentBranch || !stocks.length) return;
    const invalid = stocks.find((stock) => {
      const tracked = stock.current_content != null && stock.package_content && stock.content_unit;
      return !isUnitQuantityValid(values[stock.id], tracked ? "un" : stock.unit, true);
    });
    if (invalid) {
      const tracked = invalid.current_content != null && invalid.package_content && invalid.content_unit;
      setError(`${invalid.product_name}: informe ${tracked ? "um número inteiro de embalagens fechadas" : invalid.unit.toLowerCase() === "un" ? "uma quantidade inteira" : "uma quantidade válida com até 3 casas decimais"}.`);
      return;
    }
    setSaving(true); setError(""); setSuccess(null);
    try {
      const result = await http.post<{ count: number; operation_reference: string }>(`stocks/regularize-negatives/?branch=${currentBranch.id}`, { branch: currentBranch.id, reason, items: stocks.map((stock) => ({ stock: stock.id, final_quantity: values[stock.id] })) });
      setSuccess({ label: `Regularização · ${result.count} ${result.count === 1 ? "produto" : "produtos"}`, reference: result.operation_reference, count: result.count });
      await load();
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "A regularização não foi concluída."); }
    finally { setSaving(false); }
  }
  return <>
    <PageHeader title="Regularização de negativos" description="Corrija explicitamente todos os saldos negativos antes de desativar essa política." action={<Link href="/estoque" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">{error && <Alert message={error} />}{success && <section role="status" className="rounded-md border border-success/30 bg-success/10 px-3.5 py-3 text-[13px] text-success-strong"><strong className="block">{success.label}</strong><p className="mt-1">Saldos regularizados com sucesso.</p><StockOperationDetails reference={success.reference} count={success.count} /></section>}{loading ? <TableLoading /> : stocks.length ? <><section className="card p-5"><Field label="Justificativa da regularização"><Textarea required minLength={3} value={reason} onChange={(event) => setReason(event.target.value)} /></Field></section><section className="card overflow-hidden"><div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Saldo atual</th><th>Novo saldo</th></tr></thead><tbody>{stocks.map((stock) => { const tracked = stock.current_content != null && stock.package_content && stock.content_unit; const balance = physicalQuantityDisplay({ quantity: stock.current_quantity, unit: stock.unit, content: stock.current_content, packageContent: stock.package_content, contentUnit: stock.content_unit, completePackages: stock.complete_packages, residualContent: stock.residual_content }); return <tr key={stock.id}><td><strong>{stock.product_name}</strong><small className="block text-slate-400">{stock.internal_code}</small></td><td className="font-bold text-red-700">{balance}</td><td className="max-w-52"><Input required inputMode={quantityInputMode(tracked ? "un" : stock.unit)} pattern={tracked ? "\d+" : undefined} step={tracked || stock.unit.toLowerCase() === "un" ? "1" : "0.001"} min="0" value={values[stock.id] || ""} onChange={(event) => setValues((current) => ({ ...current, [stock.id]: tracked ? event.target.value.replace(/\D/g, "") : event.target.value }))} />{tracked && <span className="mt-1 block text-[10px] text-muted">Novo saldo em embalagens fechadas de {formatQuantity(stock.package_content)} {contentUnitLabel(stock.content_unit)}</span>}</td></tr>; })}</tbody></table></div><div className="flex justify-end border-t border-slate-100 p-4"><Button loading={saving} disabled={reason.trim().length < 3} onClick={() => void submit()}>Regularizar {stocks.length} produtos</Button></div></section></> : <EmptyState title="Nenhum saldo negativo" description="A filial já está pronta para operar sem estoque negativo." />}</div>
  </>;
}

export default function RegularizeStockPage() {
  return <AdminGuard requiredPermissions={[permissions.viewInventory, permissions.regularizeInventory]} requireAll><RegularizeStock /></AdminGuard>;
}
