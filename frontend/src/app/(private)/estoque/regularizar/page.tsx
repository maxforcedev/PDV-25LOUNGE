"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Input, TableLoading, Textarea } from "@/components/ui";
import { formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, Stock } from "@/types";

export default function RegularizeStockPage() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [values, setValues] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
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
    setSaving(true); setError(""); setSuccess("");
    try {
      const result = await http.post<{ count: number; operation_reference: string }>(`stocks/regularize-negatives/?branch=${currentBranch.id}`, { branch: currentBranch.id, reason, items: stocks.map((stock) => ({ stock: stock.id, final_quantity: values[stock.id] })) });
      setSuccess(`${result.count} saldos regularizados. Referência ${result.operation_reference}.`);
      await load();
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "A regularização não foi concluída."); }
    finally { setSaving(false); }
  }
  if (!hasPermission(permissions.regularizeInventory)) return <div className="p-6"><Alert message="Seu usuário não possui permissão para regularizar saldos." /></div>;
  return <>
    <PageHeader title="Regularização de negativos" description="Corrija explicitamente todos os saldos negativos antes de desativar essa política." action={<Link href="/estoque" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">{error && <Alert message={error} />}{success && <Alert type="success" message={success} />}{loading ? <TableLoading /> : stocks.length ? <><section className="card p-5"><Field label="Justificativa da regularização"><Textarea required minLength={3} value={reason} onChange={(event) => setReason(event.target.value)} /></Field></section><section className="card overflow-hidden"><div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Saldo atual</th><th>Novo saldo</th></tr></thead><tbody>{stocks.map((stock) => <tr key={stock.id}><td><strong>{stock.product_name}</strong><small className="block text-slate-400">{stock.internal_code}</small></td><td className="font-bold text-red-700">{formatQuantity(stock.current_quantity)} {stock.unit.toUpperCase()}</td><td className="max-w-40"><Input required inputMode="decimal" value={values[stock.id] || ""} onChange={(event) => setValues((current) => ({ ...current, [stock.id]: event.target.value }))} /></td></tr>)}</tbody></table></div><div className="flex justify-end border-t border-slate-100 p-4"><Button loading={saving} disabled={reason.trim().length < 3} onClick={() => void submit()}>Regularizar {stocks.length} produtos</Button></div></section></> : <EmptyState title="Nenhum saldo negativo" description="A filial já está pronta para operar sem estoque negativo." />}</div>
  </>;
}
