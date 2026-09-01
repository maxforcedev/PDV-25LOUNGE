"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ProductAutocomplete } from "@/components/product-autocomplete";
import { StockOperationDetails } from "@/components/stock-operation-details";
import { Alert, Button, EmptyState, Field, Input, Modal, Select, Spinner, Textarea } from "@/components/ui";
import { formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { contentUnitLabel, inventoryDecimalSign, isExactContentValid, isUnitQuantityValid, physicalQuantityDisplay, quantityInputMode } from "@/lib/inventory";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Product } from "@/types";

type EntryCategory = { id: number; name: string };
type EntryProduct = {
  id: number; name: string; internal_code: string; unit: string; current_quantity: string;
  barcode?: string; sku?: string | null; category_id: number; category_name: string;
  fraction_config?: { tracking_active: boolean; package_content: string; content_unit: string } | null;
};
type EntryOptions = { branch: { id: number; name: string }; categories: EntryCategory[]; products: EntryProduct[] };
type EntryRow = { mode: "packages" | "content"; value: string };
type OperationSuccess = { label: string; reference: string; count: number };

export default function EntryPage() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const [categories, setCategories] = useState<EntryCategory[]>([]);
  const [products, setProducts] = useState<EntryProduct[]>([]);
  const [rows, setRows] = useState<Record<number, EntryRow>>({});
  const [nature, setNature] = useState("normal");
  const [reason, setReason] = useState("");
  const [productModal, setProductModal] = useState(false);
  const [categoryModal, setCategoryModal] = useState(false);
  const [category, setCategory] = useState("");
  const [draftSearch, setDraftSearch] = useState("");
  const [draftCategory, setDraftCategory] = useState("");
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<OperationSuccess | null>(null);
  const idempotencyKey = useRef("");

  function rotateIdempotencyKey() {
    idempotencyKey.current = crypto.randomUUID();
  }

  function addProducts(incoming: EntryProduct[]) {
    setProducts((current) => {
      const known = new Set(current.map((product) => product.id));
      return [...current, ...incoming.filter((product) => !known.has(product.id))];
    });
    setRows((current) => {
      const next = { ...current };
      incoming.forEach((product) => {
        if (!next[product.id]) next[product.id] = { mode: "packages", value: "" };
      });
      return next;
    });
    rotateIdempotencyKey();
  }

  function fromProduct(product: Product): EntryProduct {
    return {
      id: product.id,
      name: product.name,
      internal_code: product.internal_code,
      barcode: product.barcode,
      sku: product.sku,
      unit: product.unit,
      category_id: product.category,
      category_name: product.category_name,
      current_quantity: product.branch_stock?.current_quantity || "0",
      fraction_config: product.fraction_config
        ? {
            tracking_active: product.fraction_config.tracking_active,
            package_content: product.fraction_config.package_content,
            content_unit: product.fraction_config.content_unit,
          }
        : null,
    };
  }

  useEffect(() => {
    if (!currentCompany || !currentBranch) return;
    setCategories([]); setProducts([]); setRows({}); setDraftSearch(""); setDraftCategory(""); setError(""); setSuccess(null); rotateIdempotencyKey();
    void http.get<EntryOptions>("stock-movements/entry-options/")
      .then((options) => setCategories(options.categories))
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções de entrada."));
  }, [currentCompany?.id, currentBranch?.id]);

  async function addAllProducts() {
    setLoadingProducts(true); setError("");
    try {
      const options = await http.get<EntryOptions>("stock-movements/entry-options/?all=true");
      addProducts(options.products);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os produtos elegíveis.");
    } finally { setLoadingProducts(false); }
  }

  async function addCategory() {
    if (!category) return;
    setLoadingProducts(true); setError("");
    try {
      const options = await http.get<EntryOptions>(`stock-movements/entry-options/?category=${category}`);
      addProducts(options.products);
      setCategoryModal(false); setCategory("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os produtos da categoria.");
    } finally { setLoadingProducts(false); }
  }

  function updateRow(product: EntryProduct, update: Partial<EntryRow>) {
    setRows((current) => ({ ...current, [product.id]: { ...current[product.id], ...update } }));
    rotateIdempotencyKey();
  }

  function removeProduct(id: number) {
    setProducts((current) => current.filter((product) => product.id !== id));
    setRows((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
    rotateIdempotencyKey();
  }

  function isPositive(product: EntryProduct) {
    return inventoryDecimalSign(rows[product.id]?.value || "0") === 1;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch) return;
    const selected = products.filter(isPositive);
    const invalid = selected.find((product) => {
      const row = rows[product.id];
      return row.mode === "content"
        ? !isExactContentValid(row.value)
        : !isUnitQuantityValid(row.value, product.fraction_config?.tracking_active ? "un" : product.unit);
    });
    if (invalid) {
      setError(`${invalid.name}: informe uma quantidade válida para a unidade selecionada.`);
      return;
    }
    setSaving(true); setError(""); setSuccess(null);
    try {
      const result = await http.post<{ count: number; operation_reference: string }>(`stock-movements/group-entry/?branch=${currentBranch.id}`, {
        branch: currentBranch.id,
        idempotency_key: idempotencyKey.current,
        nature,
        reason,
        items: selected.map((product) => {
          const row = rows[product.id];
          return { product: product.id, ...(row.mode === "content" ? { content_quantity: row.value.replace(",", ".") } : { quantity: row.value.replace(",", ".") }) };
        }),
      });
      setSuccess({ label: `Entrada registrada para ${result.count} ${result.count === 1 ? "produto" : "produtos"}.`, reference: result.operation_reference, count: result.count });
      setRows(Object.fromEntries(products.map((product) => [product.id, { mode: "packages", value: "" }])));
      setReason(""); rotateIdempotencyKey();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "A operação não foi concluída; nenhuma entrada foi registrada.");
    } finally { setSaving(false); }
  }

  if (!hasPermission(permissions.inventoryEntry)) return <div className="p-6"><Alert message="Seu usuário não possui permissão para entradas de estoque." /></div>;
  const visibleProducts = products.filter((product) => {
    const query = draftSearch.trim().toLowerCase();
    const matchesSearch = !query || `${product.name} ${product.internal_code} ${product.sku || ""} ${product.barcode || ""}`.toLowerCase().includes(query);
    return matchesSearch && (!draftCategory || String(product.category_id) === draftCategory);
  });
  return <>
    <PageHeader title="Entrada de estoque" description={`Uma única operação atômica em ${currentBranch?.name || "filial atual"}.`} action={<Link href="/estoque" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
    <form className="space-y-4 p-4 sm:p-6 lg:p-8" onSubmit={submit}>
      {error && <Alert message={error} />}{success && <section role="status" className="rounded-md border border-success/30 bg-success/10 px-3.5 py-3 text-[13px] text-success-strong"><strong className="block">{success.label}</strong><p className="mt-1">Entrada concluída com sucesso.</p><StockOperationDetails reference={success.reference} count={success.count} /></section>}
      <section className="card grid gap-4 p-5 sm:grid-cols-2">
        <Field label="Natureza"><Select value={nature} onChange={(event) => { setNature(event.target.value); rotateIdempotencyKey(); }}><option value="normal">Compra / entrada normal</option><option value="bonus">Bonificada</option><option value="return">Devolução</option><option value="opening_balance">Saldo inicial</option><option value="correction">Correção</option><option value="other">Outros</option></Select></Field>
        <Field label="Motivo" optional><Textarea rows={1} value={reason} onChange={(event) => { setReason(event.target.value); rotateIdempotencyKey(); }} /></Field>
      </section>
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Produtos da entrada</h2><p className="mt-1 text-[11px] text-muted">Adicione somente os produtos desta operação. Itens vazios ou zero não são enviados.</p></div><div className="flex flex-wrap gap-2"><Button type="button" onClick={() => { setError(""); setProductModal(true); }}><Plus className="size-4" />Adicionar produto</Button>{products.length > 0 && <><Button type="button" variant="secondary" onClick={() => { setCategory(""); setCategoryModal(true); }}><Plus className="size-4" />Adicionar por categoria</Button><Button type="button" variant="secondary" onClick={() => void addAllProducts()} disabled={loadingProducts}><Plus className="size-4" />Adicionar todos os produtos</Button></>}</div></div>
        {products.length > 0 && <div className="grid gap-3 border-t border-subtle p-4 sm:grid-cols-2"><Input aria-label="Buscar produto" value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} placeholder="Filtrar itens adicionados" /><Select aria-label="Filtrar por categoria" value={draftCategory} onChange={(event) => setDraftCategory(event.target.value)}><option value="">Todas as categorias</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></div>}
        {loadingProducts && <div className="flex justify-center p-5"><Spinner /></div>}
        {products.length ? visibleProducts.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Saldo atual</th><th>Unidade</th><th>Entrada</th><th></th></tr></thead><tbody>{visibleProducts.map((product) => { const row = rows[product.id]; const tracked = !!product.fraction_config?.tracking_active; return <tr key={product.id}><td><strong className="block">{product.name}</strong><small className="text-muted">{product.internal_code}{product.sku ? ` · ${product.sku}` : ""}{product.barcode ? ` · ${product.barcode}` : ""}</small></td><td>{physicalQuantityDisplay({ quantity: product.current_quantity, unit: product.unit })}</td><td>{product.unit.toUpperCase()}</td><td className="min-w-60">{tracked && <div className="mb-2 flex gap-3 text-xs"><label><input className="mr-1" type="radio" checked={row.mode === "packages"} onChange={() => updateRow(product, { mode: "packages", value: "" })} />Embalagens</label><label><input className="mr-1" type="radio" checked={row.mode === "content"} onChange={() => updateRow(product, { mode: "content", value: "" })} />Conteúdo exato</label></div>}<Input inputMode={row.mode === "content" ? "decimal" : quantityInputMode(tracked ? "un" : product.unit)} step={row.mode === "content" ? "0.000000001" : tracked || product.unit.toLowerCase() === "un" ? "1" : "0.001"} min="0" placeholder="0" value={row.value} onChange={(event) => updateRow(product, { value: tracked && row.mode === "packages" ? event.target.value.replace(/\D/g, "") : event.target.value })} />{tracked && <span className="mt-1 block text-[10px] text-muted">{row.mode === "content" ? `Conteúdo em ${contentUnitLabel(product.fraction_config!.content_unit)}` : `Embalagens de ${formatQuantity(product.fraction_config!.package_content)} ${contentUnitLabel(product.fraction_config!.content_unit)}`}</span>}</td><td><button type="button" className="icon-button" title="Remover produto" onClick={() => removeProduct(product.id)}><Trash2 className="size-4" /></button></td></tr>; })}</tbody></table></div> : <EmptyState title="Nenhum produto encontrado" description="Limpe ou altere os filtros para ver os itens do draft." /> : !loadingProducts && <EmptyState title="Nenhum produto adicionado" description="Adicione produtos individualmente, por categoria ou todos os produtos." />}
        <div className="flex justify-end border-t border-subtle p-4"><Button type="submit" loading={saving} disabled={!products.some(isPositive)}>Confirmar entrada</Button></div>
      </section>
    </form>
    <Modal open={productModal} title="Adicionar produto" description="Pesquise um produto elegível para a filial atual." onClose={() => setProductModal(false)} size="xl" tall><div className="p-5"><ProductAutocomplete companyId={currentCompany?.id} branchId={currentBranch?.id} optionsEndpoint="stock-movements/entry-options/" value={null} onError={setError} onChange={(product) => { if (product) { addProducts([fromProduct(product)]); setProductModal(false); } }} /></div></Modal>
    <Modal open={categoryModal} title="Adicionar por categoria" description="Todos os produtos elegíveis da categoria serão adicionados à mesma entrada." onClose={() => setCategoryModal(false)}><div className="space-y-4 p-5"><Field label="Categoria"><Select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">Selecione</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><div className="flex justify-end"><Button type="button" onClick={() => void addCategory()} disabled={!category || loadingProducts}>Adicionar produtos</Button></div></div></Modal>
  </>;
}
