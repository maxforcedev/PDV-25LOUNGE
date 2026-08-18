"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Select, Textarea } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Category, Product } from "@/types";

type Item = { key: number; product: string; quantity: string };
let nextKey = 1;

export default function GroupedEntryPage() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [category, setCategory] = useState("");
  const [nature, setNature] = useState("normal");
  const [reason, setReason] = useState("");
  const [items, setItems] = useState<Item[]>([{ key: nextKey++, product: "", quantity: "" }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!currentCompany || !currentBranch) return;
    void Promise.all([
      http.getAll<Category>(`categories/?company=${currentCompany.id}&status=active`),
      http.getAll<Product>(`products/?company=${currentCompany.id}&branch=${currentBranch.id}&inventory_behavior=direct&status=active`),
    ]).then(([nextCategories, nextProducts]) => {
      setCategories(nextCategories);
      setProducts(nextProducts);
    }).catch(() => setError("Não foi possível carregar o catálogo."));
  }, [currentCompany?.id, currentBranch?.id]);

  const available = products.filter((product) => !category || String(product.category) === category);
  function update(key: number, field: "product" | "quantity", value: string) {
    setItems((rows) => rows.map((row) => row.key === key ? { ...row, [field]: value } : row));
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch) return;
    setSaving(true); setError(""); setSuccess("");
    try {
      const result = await http.post<{ count: number; operation_reference: string }>(`stock-movements/group-entry/?branch=${currentBranch.id}`, {
        branch: currentBranch.id,
        category: Number(category),
        nature,
        reason,
        items: items.map(({ product, quantity }) => ({ product: Number(product), quantity })),
      });
      setSuccess(`${result.count} entradas concluídas. Referência ${result.operation_reference}.`);
      setItems([{ key: nextKey++, product: "", quantity: "" }]);
      setReason("");
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
        <Field label="Categoria para agrupar"><Select required value={category} onChange={(event) => { setCategory(event.target.value); setItems([{ key: nextKey++, product: "", quantity: "" }]); }}><option value="">Selecione</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
        <Field label="Natureza"><Select value={nature} onChange={(event) => setNature(event.target.value)}><option value="normal">Compra / entrada normal</option><option value="bonus">Bonificada</option><option value="return">Devolução</option><option value="opening_balance">Saldo inicial</option><option value="correction">Correção</option><option value="other">Outros</option></Select></Field>
        <Field label="Motivo" optional><Textarea rows={1} value={reason} onChange={(event) => setReason(event.target.value)} /></Field>
      </section>
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Itens da operação</h2><p className="mt-1 text-[11px] text-slate-500">Todos os itens são validados e gravados juntos.</p></div><Button type="button" variant="secondary" onClick={() => setItems((rows) => [...rows, { key: nextKey++, product: "", quantity: "" }])}><Plus className="size-4" />Adicionar</Button></div>
        <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Quantidade</th><th></th></tr></thead><tbody>{items.map((item) => <tr key={item.key}><td><Select required value={item.product} onChange={(event) => update(item.key, "product", event.target.value)}><option value="">Selecione</option>{available.map((product) => <option key={product.id} value={product.id}>{product.name} ({product.internal_code})</option>)}</Select></td><td><Input required inputMode="decimal" value={item.quantity} onChange={(event) => update(item.key, "quantity", event.target.value)} /></td><td><button type="button" className="icon-button" disabled={items.length === 1} onClick={() => setItems((rows) => rows.filter((row) => row.key !== item.key))}><Trash2 className="size-4" /></button></td></tr>)}</tbody></table></div>
        <div className="flex justify-end border-t border-slate-100 p-4"><Button type="submit" loading={saving} disabled={!category || items.some((item) => !item.product || !item.quantity)}>Confirmar entrada agrupada</Button></div>
      </section>
    </form>
  </>;
}
