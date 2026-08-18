"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Input, Select, Spinner, Textarea } from "@/components/ui";
import { formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
type EntryCategory = { id: number; name: string };
type EntryProduct = { id: number; name: string; internal_code: string; unit: string; current_quantity: string };
type EntryOptions = { branch: { id: number; name: string }; categories: EntryCategory[]; products: EntryProduct[] };

export default function GroupedEntryPage() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const [categories, setCategories] = useState<EntryCategory[]>([]);
  const [products, setProducts] = useState<EntryProduct[]>([]);
  const [category, setCategory] = useState("");
  const [nature, setNature] = useState("normal");
  const [reason, setReason] = useState("");
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const idempotencyKey = useRef("");

  function rotateIdempotencyKey() {
    idempotencyKey.current = crypto.randomUUID();
  }

  useEffect(() => {
    if (!currentCompany || !currentBranch) return;
    setCategory(""); setProducts([]); setQuantities({}); rotateIdempotencyKey();
    void http.get<EntryOptions>("stock-movements/entry-options/")
      .then((options) => setCategories(options.categories))
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções de entrada."));
  }, [currentCompany?.id, currentBranch?.id]);

  async function selectCategory(value: string) {
    setCategory(value); setProducts([]); setQuantities({}); setError(""); rotateIdempotencyKey();
    if (!value) return;
    setLoadingProducts(true);
    try {
      const options = await http.get<EntryOptions>(`stock-movements/entry-options/?category=${value}`);
      setCategories(options.categories);
      setProducts(options.products);
      setQuantities(Object.fromEntries(options.products.map((product) => [product.id, ""])));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os produtos elegíveis.");
    } finally { setLoadingProducts(false); }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch) return;
    setSaving(true); setError(""); setSuccess("");
    try {
      const result = await http.post<{ count: number; operation_reference: string }>(`stock-movements/group-entry/?branch=${currentBranch.id}`, {
        branch: currentBranch.id,
        category: Number(category),
        idempotency_key: idempotencyKey.current,
        nature,
        reason,
        items: products.map((product) => ({ product: product.id, quantity: quantities[product.id]?.trim() || "0" })),
      });
      setSuccess(`${result.count} entradas concluídas. Referência ${result.operation_reference}.`);
      setQuantities(Object.fromEntries(products.map((product) => [product.id, ""])));
      setReason("");
      rotateIdempotencyKey();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "A operação não foi concluída; nenhuma entrada foi registrada.");
    } finally { setSaving(false); }
  }

  if (!hasPermission(permissions.inventoryEntry)) return <div className="p-6"><Alert message="Seu usuário não possui permissão para entradas de estoque." /></div>;
  return <>
    <PageHeader title="Entrada agrupada" description={`Uma única operação atômica em ${currentBranch?.name || "filial atual"}.`} action={<Link href="/estoque" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
    <form className="space-y-4 p-4 sm:p-6 lg:p-8" onSubmit={submit}>
      {error && <Alert message={error} />}{success && <Alert type="success" message={success} />}
      <section className="card grid gap-4 p-5 sm:grid-cols-3">
        <Field label="Categoria para agrupar"><Select required value={category} onChange={(event) => void selectCategory(event.target.value)}><option value="">Selecione</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
        <Field label="Natureza"><Select value={nature} onChange={(event) => setNature(event.target.value)}><option value="normal">Compra / entrada normal</option><option value="bonus">Bonificada</option><option value="return">Devolução</option><option value="opening_balance">Saldo inicial</option><option value="correction">Correção</option><option value="other">Outros</option></Select></Field>
        <Field label="Motivo" optional><Textarea rows={1} value={reason} onChange={(event) => setReason(event.target.value)} /></Field>
      </section>
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Grade completa da categoria</h2><p className="mt-1 text-[11px] text-muted">Preencha somente o que foi recebido. Campos vazios ou zero não geram movimento.</p></div>{loadingProducts && <Spinner />}</div>
        {products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Saldo atual</th><th>Entrada</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td><strong className="block">{product.name}</strong><small className="text-muted">{product.internal_code}</small></td><td>{formatQuantity(product.current_quantity)} {product.unit.toUpperCase()}</td><td className="max-w-48"><Input inputMode="decimal" min="0" placeholder="0" value={quantities[product.id] || ""} onChange={(event) => setQuantities((current) => ({ ...current, [product.id]: event.target.value }))} /></td></tr>)}</tbody></table></div> : !loadingProducts && category ? <EmptyState title="Categoria sem produtos elegíveis" description="Não há produtos ativos com estoque próprio nesta categoria." /> : null}
        <div className="flex justify-end border-t border-subtle p-4"><Button type="submit" loading={saving} disabled={!category || !products.length || !products.some((product) => Number((quantities[product.id] || "0").replace(",", ".")) > 0)}>Confirmar entrada agrupada</Button></div>
      </section>
    </form>
  </>;
}
