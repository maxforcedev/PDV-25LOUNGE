"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { DollarSign, Heart, Layers3, ListFilter, Pencil, Plus, Power, Search, Trash2, X } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { ProductV26Sections } from "@/components/product-v26-sections";
import { Alert, Button, ConfirmDialog, EmptyState, Field, Input, IntegerInput, Modal, MoneyInput, Pagination, Select, StatusBadge, TableLoading, Textarea } from "@/components/ui";
import { fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Category, InventoryBehavior, Paginated, Product, ProductComponent, ProductFractionComponent } from "@/types";

type ProductForm = { company: number; category: number; name: string; description: string; internal_code: string; sku: string; barcode: string; unit: string; cost?: string; sale_price: string; is_sellable: boolean; is_favorite: boolean; inventory_behavior: InventoryBehavior; image: string; available_counter: boolean; available_table: boolean; available_command: boolean; participates_in_service_fee: boolean; participates_in_commission: boolean };
type ProductFilters = { category: string; status: string; behavior: string; sellable: string; favorite: string };
const emptyFilters: ProductFilters = { category: "", status: "", behavior: "", sellable: "", favorite: "" };
const blank = (company = 0, includeCost = false): ProductForm => ({ company, category: 0, name: "", description: "", internal_code: "", sku: "", barcode: "", unit: "un", ...(includeCost ? { cost: "0.00" } : {}), sale_price: "0.00", is_sellable: true, is_favorite: false, inventory_behavior: "direct", image: "", available_counter: true, available_table: true, available_command: true, participates_in_service_fee: true, participates_in_commission: true });
function behaviorLabel(value: InventoryBehavior) { return value === "direct" ? "Estoque próprio" : value === "none" ? "Sem estoque" : "Por componentes"; }
function scaled(value: string, places: number) { const normalized = value.trim().replace(",", "."); const negative = normalized.startsWith("-"); const [whole = "0", fraction = ""] = normalized.replace("-", "").split("."); const digits = `${whole.replace(/\D/g, "") || "0"}${fraction.replace(/\D/g, "").padEnd(places, "0").slice(0, places)}`; return BigInt(`${negative ? "-" : ""}${digits}`); }
function money(value: bigint) { const negative = value < BigInt(0); const absolute = negative ? -value : value; return `${negative ? "-" : ""}${absolute / BigInt(100)}.${String(absolute % BigInt(100)).padStart(2, "0")}`; }
function componentSuggestion(components: ProductComponent[], candidates: Product[], field: "cost" | "sale_price") { const thousandths = components.reduce((total, component) => { const candidate = candidates.find((item) => item.id === component.component_product); const value = candidate?.[field]; if (!value) return total; return total + scaled(value, 2) * scaled(component.quantity || "0", 3); }, BigInt(0)); return money((thousandths + BigInt(500)) / BigInt(1000)); }
function displayComponent(component: ProductComponent, candidates: Product[]) { if (component.quantity_display) return component.quantity_display; const candidate = candidates.find((item) => item.id === component.component_product); const quantity = component.quantity.replace(/(?:\.0+|(?:(\.\d*?)0+))$/, "$1"); return `${quantity} ${(component.component_unit || candidate?.unit || "").toUpperCase()}`; }
function channelCount(product: Product) { return [product.available_counter, product.available_table, product.available_command].filter(Boolean).length; }

function Products() {
  const { user, currentCompany, currentBranch, hasPermission } = useAuth();
  const canAdd = hasPermission(permissions.addProduct);
  const canChange = hasPermission(permissions.changeProduct);
  const canStatus = hasPermission(permissions.changeProductStatus);
  const canCompose = hasPermission(permissions.configureComposition);
  const canViewCosts = hasPermission(permissions.viewStockCosts);
  const canChangeCost = hasPermission(permissions.changeProductCost);
  const canChangePrice = hasPermission(permissions.changeProductPrice);
  const canConfigureBranch = hasPermission(permissions.configureProductBranch);
  const canConfigureFraction = hasPermission(permissions.configureProductFraction);
  const canConfigureDestinations = hasPermission(permissions.configureProductDestinations);
  const canDuplicate = hasPermission(permissions.duplicateProduct);
  const canViewSuppliers = hasPermission(permissions.viewSupplier);
  const canChangeSuppliers = hasPermission(permissions.changeSupplier);
  const companyIdRef = useRef(currentCompany?.id);
  companyIdRef.current = currentCompany?.id;
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [data, setData] = useState<Paginated<Product> | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [candidates, setCandidates] = useState<Product[]>([]);
  const [fractionCandidates, setFractionCandidates] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [behavior, setBehavior] = useState("");
  const [sellable, setSellable] = useState("");
  const [favorite, setFavorite] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false); const [draft, setDraft] = useState<ProductFilters>(emptyFilters);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [form, setForm] = useState<ProductForm>(blank());
  const [components, setComponents] = useState<ProductComponent[]>([]);
  const [fractionComponents, setFractionComponents] = useState<ProductFractionComponent[]>([]);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<Product | null>(null);
  const touched = useRef({ cost: false, sale_price: false });
  const openedQuery = useRef("");
  const suggestionCost = canViewCosts ? componentSuggestion(components, candidates, "cost") : undefined;
  const suggestionSale = componentSuggestion(components, candidates, "sale_price");

  function query(filters: ProductFilters = { category, status, behavior, sellable, favorite }) {
    const params = new URLSearchParams({ company: String(currentCompany?.id || "") });
    if (search) params.set("search", search);
    if (filters.category) params.set("category", filters.category);
    if (filters.status) params.set("status", filters.status);
    if (filters.behavior) params.set("inventory_behavior", filters.behavior);
    if (filters.sellable) params.set("is_sellable", filters.sellable);
    if (filters.favorite) params.set("is_favorite", filters.favorite);
    return `products/?${params}`;
  }

  async function load(path?: string, requestedCompanyId = currentCompany?.id) {
    if (!requestedCompanyId) return;
    setLoading(true);
    setError("");
    try {
      const response = await http.get<Paginated<Product>>(path || query());
      if (companyIdRef.current === requestedCompanyId) setData(response);
    } catch (caught) {
      if (companyIdRef.current === requestedCompanyId) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os produtos.");
    } finally {
      if (companyIdRef.current === requestedCompanyId) setLoading(false);
    }
  }

  useEffect(() => {
    const companyId = currentCompany?.id;
    setSearch(""); setCategory(""); setStatus(""); setBehavior(""); setSellable(""); setFavorite(""); setDraft(emptyFilters); setFiltersOpen(false); setOpen(false); openedQuery.current = "";
    setData(null); setCategories([]); setCandidates([]);
    if (!companyId) return;
    void load(`products/?company=${companyId}`, companyId);
    let active = true;
    Promise.all([
      http.getAll<Category>(`categories/?company=${companyId}&status=active`),
      http.getAll<Product>(`products/?company=${companyId}&status=active&inventory_behavior=direct`),
    ]).then(([categoryData, productData]) => {
      if (active && companyIdRef.current === companyId) { setCategories(categoryData); setCandidates(productData); }
    }).catch((caught) => {
      if (active && companyIdRef.current === companyId) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os dados do formulário.");
    });
    return () => { active = false; };
  }, [currentCompany?.id, currentBranch?.id]);

  useEffect(() => {
    if (!currentCompany || !currentBranch || openedQuery.current === `${currentCompany.id}:${currentBranch.id}`) return;
    const id = Number(new URLSearchParams(window.location.search).get("edit"));
    if (!id) return;
    const context = `${currentCompany.id}:${currentBranch.id}`;
    openedQuery.current = context;
    http.get<Product>(`products/${id}/`).then((product) => {
      if (contextRef.current === context && product.company === currentCompany.id) show(product);
    }).catch((caught) => {
      if (contextRef.current === context) setError(caught instanceof ApiError ? caught.message : "Não foi possível abrir o produto informado.");
    });
  }, [currentCompany?.id, currentBranch?.id]);

  async function show(product?: Product) {
    if (!product && !canAdd) return;
    setSaving(!!product);
    setOpen(true);
    setError("");
    let detail = product;
    try {
      if (product) detail = await http.get<Product>(`products/${product.id}/`);
      setEditing(detail || null);
      setForm(detail ? { company: detail.company, category: detail.category, name: detail.name, description: detail.description || "", internal_code: detail.internal_code, sku: detail.sku || "", barcode: detail.barcode || "", unit: detail.unit, ...(canViewCosts && typeof detail.cost === "string" ? { cost: detail.cost } : {}), sale_price: detail.sale_price, is_sellable: detail.is_sellable, is_favorite: detail.is_favorite, inventory_behavior: detail.inventory_behavior, image: detail.image || "", available_counter: detail.available_counter, available_table: detail.available_table, available_command: detail.available_command, participates_in_service_fee: detail.participates_in_service_fee, participates_in_commission: detail.participates_in_commission } : blank(currentCompany?.id, canViewCosts));
      setComponents(detail?.components || []);
      setFractionComponents(detail?.fraction_components || []);
      if (detail?.inventory_behavior === "components") {
        const details = await Promise.all(candidates.map((candidate) => http.get<Product>(`products/${candidate.id}/`).catch(() => candidate)));
        setFractionCandidates(details.filter((candidate) => !!candidate.fraction_config));
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os detalhes do produto.");
      if (product) setOpen(false);
    } finally {
      setSaving(false);
    }
    touched.current = { cost: !!product, sale_price: !!product };
    setFields({});
  }
  function update<K extends keyof ProductForm>(key: K, value: ProductForm[K]) { setForm((current) => ({ ...current, [key]: value })); }
  function addComponent() { if (canCompose) setComponents((current) => [...current, { component_product: 0, component_name: "", component_internal_code: "", component_unit: "", quantity: "1.000", quantity_display: "" }]); }
  function updateComponent(index: number, key: "component_product" | "quantity", value: number | string) { if (!canCompose) return; setComponents((current) => { const next = current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value, quantity_display: "" } : item); const sale = componentSuggestion(next, candidates, "sale_price"); setForm((formValue) => ({ ...formValue, ...(canViewCosts && !touched.current.cost ? { cost: componentSuggestion(next, candidates, "cost") } : {}), sale_price: touched.current.sale_price ? formValue.sale_price : sale })); return next; }); }
  function removeComponent(index: number) { if (!canCompose) return; setComponents((current) => { const next = current.filter((_, itemIndex) => itemIndex !== index); const sale = componentSuggestion(next, candidates, "sale_price"); setForm((formValue) => ({ ...formValue, ...(canViewCosts && !touched.current.cost ? { cost: componentSuggestion(next, candidates, "cost") } : {}), sale_price: touched.current.sale_price ? formValue.sale_price : sale })); return next; }); }
  function addFractionComponent() { if (canCompose) setFractionComponents((current) => [...current, { component_product: 0, component_name: "", component_internal_code: "", content_quantity: "", content_unit: "ml" }]); }
  function updateFractionComponent(index: number, key: "component_product" | "content_quantity", value: number | string) { if (!canCompose) return; setFractionComponents((current) => current.map((item, position) => position === index ? { ...item, [key]: value, ...(key === "component_product" ? { content_unit: fractionCandidates.find((candidate) => candidate.id === Number(value))?.fraction_config?.content_unit || "ml" } : {}) } : item)); }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (editing && !canChange) return;
    setSaving(true); setFields({}); setError(""); setSuccess("");
    try {
      const composition = components.map(({ component_product, quantity }) => ({ component_product, quantity }));
      const exactComposition = fractionComponents.map(({ component_product, content_quantity }) => ({ component_product, content_quantity: content_quantity.replace(",", ".") }));
      if (form.inventory_behavior === "components" && !canCompose && !editing) throw new ApiError("Você não possui permissão para configurar composição de produtos.", 403);
      if (editing) {
        const commonFields = { ...form, inventory_behavior: undefined };
        await http.patch(`products/${editing.id}/`, {
          ...commonFields,
          image: form.image || null,
          ...(editing.inventory_behavior === "components" && canCompose ? { components: composition, fraction_components: exactComposition } : {}),
        });
      } else {
        await http.post<Product>("products/", {
          ...form,
          image: form.image || null,
          ...(form.inventory_behavior === "components" ? { components: composition, fraction_components: exactComposition } : {}),
        });
      }
      setOpen(false);
      setSuccess(editing ? editing.inventory_behavior === "components" && !canCompose ? "Produto atualizado. A composição permaneceu inalterada por falta de permissão." : "Produto atualizado com sucesso." : "Produto criado com sucesso.");
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) { setError(`${caught.message} ${Object.values(caught.fields).flat().join(" ")}`.trim()); setFields(caught.fields); }
      else setError("Não foi possível salvar o produto.");
    } finally { setSaving(false); }
  }

  async function changeStatus() {
    if (!confirming || !canStatus) return;
    setSaving(true);
    const action = confirming.status === "active" ? "deactivate" : "activate";
    try { await http.post(`products/${confirming.id}/${action}/`); setConfirming(null); setSuccess(`Produto ${action === "activate" ? "ativado" : "inativado"}.`); await load(); }
    catch (caught) { setConfirming(null); setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar o status."); }
    finally { setSaving(false); }
  }

  function openFilters() { setDraft({ category, status, behavior, sellable, favorite }); setFiltersOpen(true); }
  function applyFilters() { setCategory(draft.category); setStatus(draft.status); setBehavior(draft.behavior); setSellable(draft.sellable); setFavorite(draft.favorite); setFiltersOpen(false); void load(query(draft)); }
  function clearFilters() { setDraft(emptyFilters); setCategory(""); setStatus(""); setBehavior(""); setSellable(""); setFavorite(""); setFiltersOpen(false); void load(query(emptyFilters)); }

  return <>
    <PageHeader title="Produtos" description={`Catálogo, preços e composição de ${currentCompany?.trade_name || "sua empresa"}.`} action={<div className="flex flex-wrap gap-2">{user?.is_superuser && <Link href="/produtos/lote" className="btn btn-secondary"><Plus className="size-4" />Cadastro em lote</Link>}<Link href="/produtos/precos" className="btn btn-secondary"><DollarSign className="size-4" />Preços por filial</Link><Button onClick={() => show()} disabled={!canAdd}><Plus className="size-4" />Novo produto</Button></div>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !open && <Alert message={error} />}{success && <Alert type="success" message={success} />}
      <form className="card relative flex gap-2 p-4" onSubmit={(event) => { event.preventDefault(); void load(); }}>
        <div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-3 size-4 text-slate-400" /><Input className="pl-9" placeholder="Nome, código, SKU ou código de barras" value={search} onChange={(event) => setSearch(event.target.value)} /></div><Button type="submit">Buscar</Button><Button type="button" variant="secondary" onClick={openFilters}><ListFilter className="size-4" />Filtros{Object.values({ category, status, behavior, sellable, favorite }).filter(Boolean).length ? ` (${Object.values({ category, status, behavior, sellable, favorite }).filter(Boolean).length})` : ""}</Button>
        {filtersOpen && <><button type="button" aria-label="Cancelar filtros" className="fixed inset-0 z-40 bg-slate-950/45 md:absolute md:bg-transparent" onClick={() => setFiltersOpen(false)} /><div role="dialog" aria-label="Filtros de produtos" className="fixed inset-x-0 bottom-0 z-50 max-h-[90vh] overflow-y-auto rounded-t-xl bg-white p-5 shadow-2xl md:absolute md:inset-auto md:right-4 md:top-15 md:w-96 md:rounded-xl md:border md:border-slate-200"><div className="mb-4 flex items-center justify-between"><strong className="text-sm">Filtros</strong><button type="button" className="icon-button" onClick={() => setFiltersOpen(false)}><X className="size-4" /></button></div><div className="space-y-3"><Field label="Categoria"><Select value={draft.category} onChange={(event) => setDraft((value) => ({ ...value, category: event.target.value }))}><option value="">Todas as categorias</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><Field label="Comportamento"><Select value={draft.behavior} onChange={(event) => setDraft((value) => ({ ...value, behavior: event.target.value }))}><option value="">Todos</option><option value="direct">Estoque próprio</option><option value="none">Sem estoque</option><option value="components">Componentes</option></Select></Field><Field label="Status"><Select value={draft.status} onChange={(event) => setDraft((value) => ({ ...value, status: event.target.value }))}><option value="">Todos</option><option value="active">Ativos</option><option value="inactive">Inativos</option></Select></Field><Field label="Venda"><Select value={draft.sellable} onChange={(event) => setDraft((value) => ({ ...value, sellable: event.target.value }))}><option value="">Venda e insumos</option><option value="true">Vendável</option><option value="false">Insumo</option></Select></Field><Field label="Favoritos"><Select value={draft.favorite} onChange={(event) => setDraft((value) => ({ ...value, favorite: event.target.value }))}><option value="">Todos</option><option value="true">Favoritos</option><option value="false">Não favoritos</option></Select></Field></div><div className="mt-5 flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setFiltersOpen(false)}>Cancelar</Button><Button type="button" variant="secondary" onClick={clearFilters}>Limpar</Button><Button type="button" onClick={applyFilters}>Aplicar</Button></div></div></>}
      </form>
      <section className="card overflow-hidden">
         {loading ? <TableLoading /> : data?.results.length ? <><div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Categoria</th><th>Comportamento</th><th>Canais</th><th>Preço</th><th>Status</th><th className="text-right">Ações</th></tr></thead><tbody>{data.results.map((product) => <tr key={product.id}><td><strong className="flex items-center gap-1.5">{product.is_favorite && <Heart className="size-3.5 fill-primary text-primary" />}{product.name}</strong><span className="text-[11px] text-slate-400">{product.internal_code}{product.sku ? ` · SKU ${product.sku}` : ""}</span></td><td>{product.category_name || "-"}</td><td>{behaviorLabel(product.inventory_behavior)}</td><td><strong>{channelCount(product)}/3</strong><span className="block text-[10px] text-muted">globais ativos</span></td><td>R$ {product.sale_price}</td><td><StatusBadge active={product.status === "active"} /></td><td><div className="flex justify-end gap-1"><button className="icon-button" title={canChange ? "Editar e configurar" : "Ver detalhes"} onClick={() => void show(product)}><Pencil className="size-4" /></button><button className="icon-button" disabled={!canStatus} onClick={() => setConfirming(product)}><Power className="size-4" /></button></div></td></tr>)}</tbody></table></div><Pagination count={data.count} next={data.next} previous={data.previous} onPage={load} /></> : <EmptyState title="Nenhum produto cadastrado" description="Crie produtos para montar o catálogo da empresa." />}
      </section>
    </div>
    <Modal open={open} title={editing ? "Produto e configuração" : "Novo produto"} onClose={() => !saving && setOpen(false)} size="xl">
      <form onSubmit={submit}>
        <fieldset disabled={!!editing && !canChange} className="grid gap-5 p-5 disabled:opacity-75 sm:grid-cols-2 lg:grid-cols-3 sm:p-6">
          <div className="sm:col-span-2 lg:col-span-3">{error && <Alert message={error} />}</div>
          <Field label="Nome" error={fieldError(fields, "name")}><Input required value={form.name} onChange={(event) => update("name", event.target.value)} /></Field>
           <Field label="Código interno" optional={!editing} error={fieldError(fields, "internal_code")}><Input required={!!editing} value={form.internal_code} onChange={(event) => update("internal_code", event.target.value)} placeholder={editing ? "Código obrigatório" : "Gerado automaticamente"} /></Field>
           <Field label="SKU" optional error={fieldError(fields, "sku")}><Input value={form.sku} onChange={(event) => update("sku", event.target.value)} placeholder="Identificador comercial" /></Field>
           <Field label="Código de barras" optional error={fieldError(fields, "barcode")}><Input value={form.barcode} onChange={(event) => update("barcode", event.target.value)} /></Field>
           <Field label="Categoria" error={fieldError(fields, "category")}><Select required value={form.category || ""} onChange={(event) => update("category", Number(event.target.value))}><option value="">Selecione uma categoria</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
           <Field label="Unidade"><Select required value={form.unit} onChange={(event) => update("unit", event.target.value)}><option value="un">UN</option><option value="kg">KG</option><option value="g">G</option><option value="l">L</option><option value="ml">ML</option></Select></Field>
          <Field label="Comportamento de estoque"><Select value={form.inventory_behavior} onChange={(event) => update("inventory_behavior", event.target.value as InventoryBehavior)} disabled={!!editing}><option value="direct">Controla estoque próprio</option><option value="none">Não controla estoque</option><option value="components" disabled={!canCompose}>Baixa componentes</option></Select><span className="mt-1 block text-[10px] leading-4 text-slate-400">{editing ? "Definido no cadastro e não pode ser alterado." : !canCompose ? "Produtos por componentes exigem permissão para configurar composição." : "Define como o estoque será controlado."}</span></Field>
{canViewCosts && <Field label="Custo"><MoneyInput required disabled={!canChangeCost} value={form.cost || ""} onValueChange={(next) => { touched.current.cost = true; update("cost", next); }} />{form.inventory_behavior === "components" && <span className="mt-1 flex items-center justify-between text-[10px] text-slate-400">Sugestão local: R$ {suggestionCost}{canChangeCost && <button type="button" className="font-bold text-primary" onClick={() => { touched.current.cost = true; update("cost", suggestionCost); }}>Usar sugestão</button>}</span>}{editing?.suggested_cost && <small className="text-[10px] text-slate-400">Sugestão salva pela API: R$ {editing.suggested_cost}</small>}</Field>}
            <Field label="Preço de venda"><MoneyInput required disabled={!canChangePrice} value={form.sale_price} onValueChange={(next) => { touched.current.sale_price = true; update("sale_price", next); }} />{form.inventory_behavior === "components" && <span className="mt-1 flex items-center justify-between text-[10px] text-slate-400">Sugestão local: R$ {suggestionSale}{canChangePrice && <button type="button" className="font-bold text-primary" onClick={() => { touched.current.sale_price = true; update("sale_price", suggestionSale); }}>Usar sugestão</button>}</span>}{editing?.suggested_sale_price && <small className="text-[10px] text-slate-400">Sugestão salva pela API: R$ {editing.suggested_sale_price}</small>}</Field>
          <Field label="Imagem (URL)" optional><Input value={form.image} onChange={(event) => update("image", event.target.value)} /></Field>
          <Field label="Descrição" optional><Textarea value={form.description} onChange={(event) => update("description", event.target.value)} /></Field>
           <label className="flex items-center gap-3 self-end pb-3 text-xs font-semibold"><input type="checkbox" className="size-4 accent-primary" checked={form.is_sellable} onChange={(event) => update("is_sellable", event.target.checked)} />Disponível para venda</label>
           <label className="flex items-center gap-3 self-end pb-3 text-xs font-semibold"><input type="checkbox" className="size-4 accent-primary" checked={form.is_favorite} onChange={(event) => update("is_favorite", event.target.checked)} />Produto favorito</label>
           <fieldset className="sm:col-span-2 lg:col-span-3 rounded-lg border border-subtle p-4"><legend className="px-1 text-xs font-bold">Canais globais de venda</legend><p className="mb-3 text-[10px] text-muted">A filial pode herdar ou sobrescrever cada canal.</p><div className="grid gap-3 sm:grid-cols-3"><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={form.available_counter} onChange={(event) => update("available_counter", event.target.checked)} />Balcão</label><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={form.available_table} onChange={(event) => update("available_table", event.target.checked)} />Mesa</label><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={form.available_command} onChange={(event) => update("available_command", event.target.checked)} />Comanda</label></div></fieldset>
           <fieldset className="sm:col-span-2 lg:col-span-3 rounded-lg border border-subtle p-4"><legend className="px-1 text-xs font-bold">Participação financeira</legend><div className="grid gap-3 sm:grid-cols-2"><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={form.participates_in_service_fee} onChange={(event) => update("participates_in_service_fee", event.target.checked)} />Participa da taxa de serviço</label><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={form.participates_in_commission} onChange={(event) => update("participates_in_commission", event.target.checked)} />Participa da comissão</label></div></fieldset>
          {form.inventory_behavior === "components" && <div className="sm:col-span-2 lg:col-span-3 rounded-lg border border-slate-200 p-4">
             <div className="mb-3 flex items-center justify-between gap-3"><div><h3 className="flex items-center gap-2 text-xs font-bold"><Layers3 className="size-4 text-primary" />Composição</h3>{!canCompose && <p className="mt-1 text-[10px] text-danger">Sem permissão para configurar composição, esta seção é somente leitura.</p>}</div><Button type="button" variant="secondary" onClick={addComponent} disabled={!canCompose}><Plus className="size-4" />Componente</Button></div>
             <div className="space-y-3">{components.map((component, index) => { const candidate = candidates.find((item) => item.id === component.component_product); return <div key={`${component.component_product}-${index}`} className="grid gap-2 sm:grid-cols-[1fr_10rem_auto]"><Select required value={component.component_product || ""} onChange={(event) => updateComponent(index, "component_product", Number(event.target.value))} disabled={!canCompose}><option value="">Selecione o insumo</option>{candidates.filter((item) => item.id !== editing?.id).map((item) => <option key={item.id} value={item.id}>{item.name} ({item.internal_code})</option>)}</Select><div>{candidate?.unit === "un" ? <IntegerInput required min={1} step={1} value={component.quantity} onValueChange={(next) => updateComponent(index, "quantity", next)} disabled={!canCompose} /> : <MoneyInput required min="0.001" step="0.001" value={component.quantity} onValueChange={(next) => updateComponent(index, "quantity", next)} disabled={!canCompose} />}<span className="mt-1 block text-[10px] text-slate-400">{displayComponent(component, candidates)}</span></div><button type="button" className="icon-button" aria-label="Remover componente" disabled={!canCompose} onClick={() => removeComponent(index)}><Trash2 className="size-4" /></button></div>; })}</div>
             <div className="mt-5 border-t border-subtle pt-4"><div className="mb-3 flex items-center justify-between gap-3"><div><h4 className="text-xs font-bold">Consumo exato de conteúdo</h4><p className="mt-1 text-[10px] text-muted">Somente insumos fracionáveis, sempre em mL ou g. Nunca em UN fracionária.</p></div><Button type="button" variant="secondary" onClick={addFractionComponent} disabled={!canCompose}><Plus className="size-4" />Conteúdo</Button></div><div className="space-y-3">{fractionComponents.map((component, index) => { const candidate = fractionCandidates.find((item) => item.id === component.component_product); const unit = candidate?.fraction_config?.content_unit || component.content_unit; return <div key={`fraction-${component.component_product}-${index}`} className="grid gap-2 sm:grid-cols-[1fr_10rem_auto]"><Select required value={component.component_product || ""} disabled={!canCompose} onChange={(event) => updateFractionComponent(index, "component_product", Number(event.target.value))}><option value="">Selecione o insumo fracionável</option>{fractionCandidates.filter((item) => item.id !== editing?.id && !components.some((normal) => normal.component_product === item.id)).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.fraction_config?.package_content} {item.fraction_config?.content_unit}</option>)}</Select><div><Input required inputMode="decimal" min="0.000000001" step="0.000000001" value={component.content_quantity} disabled={!canCompose} onChange={(event) => updateFractionComponent(index, "content_quantity", event.target.value)} /><span className="mt-1 block text-[10px] text-muted">Conteúdo por venda: {component.content_quantity || "0"} {unit === "ml" ? "mL" : "g"}</span></div><button type="button" className="icon-button" aria-label="Remover consumo exato" disabled={!canCompose} onClick={() => setFractionComponents((value) => value.filter((_, position) => position !== index))}><Trash2 className="size-4" /></button></div>; })}</div></div>
           </div>}
        </fieldset>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4"><Button type="button" variant="secondary" onClick={() => setOpen(false)} disabled={saving}>{editing ? "Fechar" : "Cancelar"}</Button>{(!editing || canChange) && <Button type="submit" loading={saving}>{editing ? "Salvar dados gerais" : "Salvar produto"}</Button>}</div>
      </form>
      {editing && currentCompany && currentBranch && <ProductV26Sections product={editing} companyId={currentCompany.id} currentBranchId={currentBranch.id} branches={(user?.branches || []).filter((branch) => branch.company_id === currentCompany.id && branch.status === "active" && (user?.is_superuser || branch.permissions.includes(permissions.configureProductBranch)))} permissions={{ branch: canConfigureBranch, fraction: canConfigureFraction, destinations: canConfigureDestinations, duplicate: canDuplicate, viewModifiers: hasPermission(permissions.viewModifiers), changeModifiers: hasPermission(permissions.changeModifiers), viewSuppliers: canViewSuppliers, changeSuppliers: canChangeSuppliers }} onReload={async () => { const refreshed = await http.get<Product>(`products/${editing.id}/`); setEditing(refreshed); }} onDuplicated={(created) => { setOpen(false); setSuccess(`Produto duplicado como “${created.name}” (${created.internal_code}). SKU e código de barras foram regenerados com segurança.`); void load(); }} />}
    </Modal>
    <ConfirmDialog open={!!confirming} title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} produto`} message={`Confirma a alteração de status de “${confirming?.name || ""}”?`} confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"} danger={confirming?.status === "active"} loading={saving} onClose={() => setConfirming(null)} onConfirm={changeStatus} />
  </>;
}

export default function ProductsPage() { return <AdminGuard requiredPermissions={[permissions.viewProduct]}><Products /></AdminGuard>; }
