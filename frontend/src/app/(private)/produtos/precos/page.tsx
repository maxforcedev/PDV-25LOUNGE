"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, DollarSign, RotateCcw, Search } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Input, MoneyInput, TableLoading } from "@/components/ui";
import { formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { BranchProductPrice, ProductPriceComparison } from "@/types";

interface OperationalPriceTable extends ProductPriceComparison {
  overrides: BranchProductPrice[];
}

interface BulkPriceResponse {
  operation_reference: string;
  count: number;
  created: number;
  updated: number;
  results: BranchProductPrice[];
}

type PriceItem = { product: number; sale_price: string };
type LineErrors = Record<number, Record<string, string[]>>;

function BranchPrices() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const canChange = hasPermission(permissions.changeBranchPrice);
  const [comparison, setComparison] = useState<ProductPriceComparison | null>(null);
  const [overrides, setOverrides] = useState<Record<number, BranchProductPrice>>({});
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [savingAll, setSavingAll] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [lineErrors, setLineErrors] = useState<LineErrors>({});
  const branchRef = useRef(currentBranch?.id || 0);
  branchRef.current = currentBranch?.id || 0;

  function mapLineErrors(caught: ApiError, items: PriceItem[]) {
    const mapped: LineErrors = {};
    for (const [path, messages] of Object.entries(caught.fields)) {
      const match = /^items\.(\d+)(?:\.(.+))?$/.exec(path);
      if (!match) continue;
      const item = items[Number(match[1])];
      if (!item) continue;
      const field = match[2] || "non_field_errors";
      mapped[item.product] = { ...mapped[item.product], [field]: messages };
    }
    return mapped;
  }

  function bulkErrorMessage(caught: ApiError) {
    const globalMessages = Object.entries(caught.fields)
      .filter(([path]) => !/^items\.\d+(?:\.|$)/.test(path))
      .flatMap(([, messages]) => messages);
    return [...new Set([caught.message, ...globalMessages])].join(" ");
  }

  async function load() {
    if (!currentCompany || !currentBranch) { setComparison(null); setLoading(false); return; }
    const branchId = currentBranch.id;
    setLoading(true); setError("");
    try {
      const matrix = await http.get<OperationalPriceTable>("branch-prices/table/");
      if (branchRef.current !== branchId) return;
      const byProduct = Object.fromEntries(matrix.overrides.map((price) => [price.product, price]));
      setComparison(matrix);
      setOverrides(byProduct);
      setDrafts(Object.fromEntries(matrix.products.map((product) => [product.id, byProduct[product.id]?.sale_price || product.default_price])));
      setLineErrors({});
    } catch (caught) {
      if (branchRef.current === branchId) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os preços por filial.");
    } finally { if (branchRef.current === branchId) setLoading(false); }
  }

  useEffect(() => { setSearch(""); setSuccess(""); void load(); }, [currentCompany?.id, currentBranch?.id]);

  async function save(productId: number) {
    if (!currentBranch || !canChange) return;
    const branchId = currentBranch.id;
    const salePrice = drafts[productId];
    const items = [{ product: productId, sale_price: salePrice ?? "" }];
    setSaving(productId); setError(""); setSuccess(""); setLineErrors({});
    try {
      await http.post<BulkPriceResponse>("branch-prices/bulk/", { branch: branchId, items });
      if (branchRef.current !== branchId) return;
      setSuccess("Preço específico salvo com sucesso.");
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        const mapped = mapLineErrors(caught, items);
        setLineErrors(mapped);
        setError(bulkErrorMessage(caught));
      } else setError("Não foi possível salvar o preço específico.");
    } finally { setSaving(null); }
  }

  async function saveAll() {
    if (!currentBranch || !canChange || !comparison) return;
    const branchId = currentBranch.id;
    const changed = comparison.products.filter((product) => drafts[product.id] !== undefined && drafts[product.id] !== (overrides[product.id]?.sale_price || product.default_price));
    if (!changed.length) { setSuccess("Nenhuma alteração pendente."); return; }
    const items = changed.map((product) => ({ product: product.id, sale_price: drafts[product.id] }));
    setSavingAll(true); setError(""); setSuccess(""); setLineErrors({});
    try {
      const result = await http.post<BulkPriceResponse>("branch-prices/bulk/", { branch: branchId, items });
      if (branchRef.current !== branchId) return;
      setSuccess(`${result.count} preço(s) salvo(s) em uma única operação.`);
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        const mapped = mapLineErrors(caught, items);
        setLineErrors(mapped);
        setError(bulkErrorMessage(caught));
      } else setError("Não foi possível salvar as alterações em lote.");
    } finally { setSavingAll(false); }
  }

  async function useDefault(productId: number) {
    const existing = overrides[productId];
    if (!existing || !canChange) return;
    setSaving(productId); setError(""); setSuccess("");
    try {
      await http.delete(`branch-prices/${existing.id}/`);
      setSuccess("A filial voltou a usar o preço padrão do produto.");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível restaurar o preço padrão.");
    } finally { setSaving(null); }
  }

  const products = comparison?.products.filter((product) => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    return !term || product.name.toLocaleLowerCase("pt-BR").includes(term) || product.internal_code.toLocaleLowerCase("pt-BR").includes(term);
  }) || [];

  return <>
    <PageHeader title="Preços por filial" description="Compare os preços da empresa e edite em lote a filial ativa sem alterar o preço padrão." action={<Link href="/produtos" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar aos produtos</Link>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      {success && <Alert type="success" message={success} />}
      {!!Object.keys(lineErrors).length && <div role="alert" className="card border-danger/30 p-4"><strong className="text-xs text-danger-strong">Linhas que precisam de correção</strong>{Object.entries(lineErrors).map(([productId, fields]) => <p key={productId} className="mt-2 text-xs text-danger-strong"><span className="font-bold">{comparison?.products.find((product) => product.id === Number(productId))?.name || `Produto ${productId}`}:</span> {Object.values(fields).flat().join(" ")}</p>)}</div>}
      <div className="card grid gap-4 p-4 lg:grid-cols-[1fr_auto] lg:items-center">
        <div className="relative"><Search className="absolute left-3 top-3 size-4 text-slate-400" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar produto ou código" /></div>
        <div className="flex flex-wrap items-center gap-2"><div className="rounded-lg bg-primary/5 px-4 py-2 text-xs text-slate-600"><strong className="text-primary">Filial editável:</strong> {currentBranch?.name || "nenhuma"}</div><Button onClick={() => void saveAll()} loading={savingAll} disabled={!canChange || saving !== null}>Salvar alterações da filial</Button></div>
      </div>
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Comparativo de preços</h2><p className="mt-1 text-[11px] text-slate-500">“Preço padrão” indica que não existe substituição para a filial. “Preço da filial” indica override ativo.</p></div><DollarSign className="size-5 text-slate-300" /></div>
        {loading ? <TableLoading columns={(comparison?.branches.length || 1) + 3} /> : products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Preço padrão</th>{comparison?.branches.map((branch) => <th key={branch.id}>{branch.name}</th>)}<th className="text-right">Ações</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td><strong className="block">{product.name}</strong><span className="text-[11px] text-slate-400">{product.internal_code}</span></td><td>{formatBRL(product.default_price)}</td>{comparison?.branches.map((branch) => { const specific = product.prices[String(branch.id)]; const active = branch.id === currentBranch?.id; const changed = active && drafts[product.id] && drafts[product.id] !== (overrides[product.id]?.sale_price || product.default_price); return <td key={branch.id}>{active ? <div className="min-w-36"><MoneyInput aria-label={`Preço de ${product.name} em ${branch.name}`} value={drafts[product.id] || product.default_price} onValueChange={(value) => setDrafts((current) => ({ ...current, [product.id]: value }))} disabled={!canChange || saving === product.id || savingAll} /><span className={`mt-1 block text-[10px] ${changed ? "font-semibold text-amber-600" : specific === null ? "text-slate-400" : "font-semibold text-primary"}`}>{changed ? "Alterado" : specific === null ? "Preço padrão" : "Preço da filial"}</span></div> : <div><strong className="text-xs">{formatBRL(specific || product.default_price)}</strong><span className="block text-[10px] text-slate-400">{specific === null ? "Preço padrão" : "Preço da filial"}</span></div>}</td>; })}<td><div className="flex justify-end gap-1"><Button variant="secondary" loading={saving === product.id} disabled={!canChange || saving !== null || savingAll} onClick={() => void save(product.id)}><Check className="size-4" />Salvar</Button><button type="button" className="icon-button" title="Usar preço padrão" disabled={!canChange || !overrides[product.id] || saving !== null || savingAll} onClick={() => void useDefault(product.id)}><RotateCcw className="size-4" /></button></div></td></tr>)}</tbody></table></div> : <EmptyState title="Nenhum produto encontrado" description="Ajuste a busca ou cadastre produtos." />}
      </section>
    </div>
  </>;
}

export default function BranchPricesPage() {
  return <AdminGuard requiredPermissions={[permissions.changeBranchPrice]}><BranchPrices /></AdminGuard>;
}
