"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Check, DollarSign, RotateCcw, Search } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Input, MoneyInput, TableLoading } from "@/components/ui";
import { formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { BranchProductPrice, ProductPriceComparison } from "@/types";

function BranchPrices() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const canChange = hasPermission(permissions.changeProduct);
  const [comparison, setComparison] = useState<ProductPriceComparison | null>(null);
  const [overrides, setOverrides] = useState<Record<number, BranchProductPrice>>({});
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    if (!currentCompany || !currentBranch) {
      setComparison(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [matrix, prices] = await Promise.all([
        http.get<ProductPriceComparison>("products/price-comparison/"),
        http.getAll<BranchProductPrice>(`branch-prices/?branch=${currentBranch.id}`),
      ]);
      const byProduct = Object.fromEntries(prices.map((price) => [price.product, price]));
      setComparison(matrix);
      setOverrides(byProduct);
      setDrafts(Object.fromEntries(matrix.products.map((product) => [
        product.id,
        byProduct[product.id]?.sale_price || product.default_price,
      ])));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os preços por filial.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setSearch("");
    setSuccess("");
    void load();
  }, [currentCompany?.id, currentBranch?.id]);

  async function save(productId: number) {
    if (!currentBranch || !canChange) return;
    const salePrice = drafts[productId];
    if (!salePrice) return;
    setSaving(productId);
    setError("");
    setSuccess("");
    try {
      const existing = overrides[productId];
      if (existing) await http.patch(`branch-prices/${existing.id}/`, { sale_price: salePrice });
      else await http.post("branch-prices/", { product: productId, branch: currentBranch.id, sale_price: salePrice });
      setSuccess("Preço específico salvo com sucesso.");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível salvar o preço específico.");
    } finally {
      setSaving(null);
    }
  }

  async function useDefault(productId: number) {
    const existing = overrides[productId];
    if (!existing || !canChange) return;
    setSaving(productId);
    setError("");
    setSuccess("");
    try {
      await http.delete(`branch-prices/${existing.id}/`);
      setSuccess("A filial voltou a usar o preço padrão do produto.");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível restaurar o preço padrão.");
    } finally {
      setSaving(null);
    }
  }

  const products = comparison?.products.filter((product) => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    return !term || product.name.toLocaleLowerCase("pt-BR").includes(term) || product.internal_code.toLocaleLowerCase("pt-BR").includes(term);
  }) || [];

  return <>
    <PageHeader title="Preços por filial" description="Compare os preços da empresa e edite a filial ativa sem alterar o preço padrão." action={<Link href="/produtos" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar aos produtos</Link>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      {success && <Alert type="success" message={success} />}
      <div className="card grid gap-4 p-4 lg:grid-cols-[1fr_auto] lg:items-center">
        <div className="relative"><Search className="absolute left-3 top-3 size-4 text-slate-400" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar produto ou código" /></div>
        <div className="rounded-lg bg-primary/5 px-4 py-2 text-xs text-slate-600"><strong className="text-primary">Filial editável:</strong> {currentBranch?.name || "nenhuma"}</div>
      </div>
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Comparativo de preços</h2><p className="mt-1 text-[11px] text-slate-500">“Padrão” indica que não existe substituição para a filial.</p></div><DollarSign className="size-5 text-slate-300" /></div>
        {loading ? <TableLoading columns={(comparison?.branches.length || 1) + 3} /> : products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Preço padrão</th>{comparison?.branches.map((branch) => <th key={branch.id}>{branch.name}</th>)}<th className="text-right">Ações</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td><strong className="block">{product.name}</strong><span className="text-[11px] text-slate-400">{product.internal_code}</span></td><td>{formatBRL(product.default_price)}</td>{comparison?.branches.map((branch) => { const specific = product.prices[String(branch.id)]; const active = branch.id === currentBranch?.id; return <td key={branch.id}>{active ? <div className="min-w-36"><MoneyInput aria-label={`Preço de ${product.name} em ${branch.name}`} value={drafts[product.id] || product.default_price} onValueChange={(value) => setDrafts((current) => ({ ...current, [product.id]: value }))} disabled={!canChange || saving === product.id} /><span className={`mt-1 block text-[10px] ${specific === null ? "text-slate-400" : "font-semibold text-primary"}`}>{specific === null ? "Padrão" : "Específico"}</span></div> : <div><strong className="text-xs">{formatBRL(specific || product.default_price)}</strong><span className="block text-[10px] text-slate-400">{specific === null ? "Padrão" : "Específico"}</span></div>}</td>; })}<td><div className="flex justify-end gap-1"><Button variant="secondary" loading={saving === product.id} disabled={!canChange || saving !== null} onClick={() => void save(product.id)}><Check className="size-4" />Salvar</Button><button type="button" className="icon-button" title="Usar preço padrão" disabled={!canChange || !overrides[product.id] || saving !== null} onClick={() => void useDefault(product.id)}><RotateCcw className="size-4" /></button></div></td></tr>)}</tbody></table></div> : <EmptyState title="Nenhum produto encontrado" description="Ajuste a busca ou cadastre produtos para comparar os preços." />}
      </section>
    </div>
  </>;
}

export default function BranchPricesPage() {
  return <AdminGuard requiredPermissions={[permissions.viewProduct]}><BranchPrices /></AdminGuard>;
}
