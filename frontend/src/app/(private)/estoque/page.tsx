"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Boxes,
  CircleDollarSign,
  History,
  ListFilter,
  PackageX,
  Plus,
  Search,
  Settings2,
  SlidersHorizontal,
  TriangleAlert,
  X,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  Pagination,
  Select,
  TableLoading,
  Textarea,
} from "@/components/ui";
import { fieldError, formatBRL, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Category, Paginated, Product, Stock } from "@/types";

type Action = "entry" | "exit" | "adjustment" | "minimum";
type Summary = {
  negative_count?: number;
  below_minimum_count?: number;
  zero_count?: number;
  estimated_value?: string;
  allow_negative_stock: boolean;
  legacy_negative_state: boolean;
};
type StockFilters = {
  state: string;
  category: string;
  status: string;
  behavior: string;
};
const emptyFilters: StockFilters = {
  state: "",
  category: "",
  status: "",
  behavior: "",
};
function StateBadge({ state }: { state: Stock["state"] }) {
  const negative = state === "negative";
  const zero = state === "zero";
  const below = state === "below_minimum";
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${negative ? "bg-red-700 text-white" : zero ? "bg-danger/10 text-red-700" : below ? "bg-warning/15 text-amber-700" : "bg-success/10 text-emerald-700"}`}
    >
      {negative ? "Negativo" : zero ? "Zerado" : below ? "Abaixo do mínimo" : "Normal"}
    </span>
  );
}

function Inventory() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const canEntry = hasPermission(permissions.inventoryEntry);
  const canExit = hasPermission(permissions.inventoryExit);
  const canAdjust = hasPermission(permissions.inventoryAdjust);
  const canMove = canEntry || canExit || canAdjust;
  const canMinimum = hasPermission(permissions.changeMinimum);
  const canHistory = hasPermission(permissions.viewInventoryHistory);
  const canViewProducts = hasPermission(permissions.viewProduct);
  const canViewKpis = hasPermission(permissions.viewStockKpis);
  const canViewCosts = hasPermission(permissions.viewStockCosts);
  const canRegularize = hasPermission(permissions.regularizeInventory);
  const [data, setData] = useState<Paginated<Stock> | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [productsLoading, setProductsLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [behavior, setBehavior] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draft, setDraft] = useState<StockFilters>(emptyFilters);
  const [chooser, setChooser] = useState(false);
  const [action, setAction] = useState<Action | null>(null);
  const [selected, setSelected] = useState<Stock | null>(null);
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [nature, setNature] = useState("normal");
  const [reason, setReason] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const showRegularize = canRegularize && !!summary?.allow_negative_stock && (summary?.negative_count ?? 0) > 0;
  const showLegacyRecovery = canRegularize && !!summary?.legacy_negative_state && (summary?.negative_count ?? 0) > 0;
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  function params(
    filters: StockFilters = { state, category, status, behavior },
    searchValue = search,
  ) {
    const value = new URLSearchParams({
      company: String(currentCompany?.id || ""),
      branch: String(currentBranch?.id || ""),
    });
    if (searchValue) value.set("search", searchValue);
    if (filters.state) value.set("state", filters.state);
    if (filters.category) value.set("category", filters.category);
    if (filters.status) value.set("status", filters.status);
    if (filters.behavior) value.set("inventory_behavior", filters.behavior);
    return value;
  }
  function stockRequest(
    path: string | undefined,
    explicitParams: URLSearchParams,
  ) {
    if (!path) {
      const requestParams = new URLSearchParams(explicitParams);
      return { path: `stocks/?${requestParams}`, params: requestParams };
    }
    const url = new URL(path, window.location.origin);
    url.searchParams.set("company", String(currentCompany?.id));
    url.searchParams.set("branch", String(currentBranch?.id));
    return {
      path: /^https?:\/\//.test(path)
        ? url.toString()
        : `${url.pathname.replace(/^\//, "")}${url.search}`,
      params: new URLSearchParams(url.searchParams),
    };
  }
  async function load(
    path?: string,
    explicitParams = params(),
    context = contextRef.current,
  ) {
    if (!currentCompany || !currentBranch) {
      setData(null);
      setSummary(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const request = stockRequest(path, explicitParams);
    try {
      const [stocks, totals] = await Promise.all([
        http.get<Paginated<Stock>>(request.path),
        http.get<Summary>(`stocks/summary/?${request.params}`),
      ]);
      if (contextRef.current === context) {
        setData(stocks);
        setSummary(totals);
      }
    } catch (caught) {
      if (contextRef.current === context) {
        setData(null);
        setSummary(null);
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar o estoque.",
        );
      }
    } finally {
      if (contextRef.current === context) setLoading(false);
    }
  }
  useEffect(() => {
    const requestedState = new URLSearchParams(window.location.search).get("state") || "";
    const initialState = ["normal", "below_minimum", "zero", "negative"].includes(requestedState) ? requestedState : "";
    const initialFilters = { ...emptyFilters, state: initialState };
    setSearch("");
    setState(initialState);
    setCategory("");
    setStatus("");
    setBehavior("");
    setData(null);
    setSummary(null);
    setAction(null);
    const context = contextRef.current;
    if (!currentCompany || !currentBranch) {
      setLoading(false);
      return;
    }
    setDraft(initialFilters);
    void load(undefined, params(initialFilters, ""), context);
    let active = true;
    http
      .getAll<Category>(
        `categories/?company=${currentCompany.id}&status=active`,
      )
      .then(
        (items) =>
          active && contextRef.current === context && setCategories(items),
      )
      .catch(() => active && setCategories([]));
    return () => {
      active = false;
    };
  }, [currentCompany?.id, currentBranch?.id]);
  function resetAction(next: Action, stock: Stock | null) {
    setChooser(false);
    setSelected(stock);
    setAction(next);
    setProductId(stock ? String(stock.product) : "");
    setQuantity(
      next === "minimum" && stock
        ? stock.minimum_quantity
        : next === "adjustment" && stock
          ? stock.current_quantity
          : "",
    );
    setReason("");
    setNature(next === "entry" ? "normal" : next === "exit" ? "loss" : "inventory");
    setFields({});
    setError("");
  }
  async function choose(next: Exclude<Action, "minimum">) {
    resetAction(next, null);
    setProducts([]);
    if (!canViewProducts || !currentCompany || !currentBranch) return;
    const context = contextRef.current;
    setProductsLoading(true);
    try {
      const items = await http.getAll<Product>(
        `products/?company=${currentCompany.id}&branch=${currentBranch.id}&inventory_behavior=direct&status=active`,
      );
      if (contextRef.current === context && items.length) {
        setProducts(items);
        setProductId(String(items[0].id));
      }
    } catch (caught) {
      if (contextRef.current === context)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar os produtos.",
        );
    } finally {
      if (contextRef.current === context) setProductsLoading(false);
    }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!action || !currentBranch) return;
    setSaving(true);
    setError("");
    setFields({});
    try {
      if (action === "minimum" && selected)
        await http.patch(
          `stocks/${selected.id}/minimum/?branch=${currentBranch.id}`,
          { minimum_quantity: quantity },
        );
      else
        await http.post(
          `stock-movements/${action}/?branch=${currentBranch.id}`,
          {
            product: selected?.product || Number(productId),
            branch: currentBranch.id,
            ...(action === "adjustment"
              ? { final_quantity: quantity }
              : { quantity }),
             reason,
             nature,
          },
        );
      setAction(null);
      setSelected(null);
      setSuccess(
        action === "minimum"
          ? "Estoque mínimo atualizado."
          : "Movimentação registrada com sucesso.",
      );
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível concluir a operação.");
    } finally {
      setSaving(false);
    }
  }
  const title =
    action === "entry"
      ? "Entrada de estoque"
      : action === "exit"
        ? "Saída de estoque"
        : action === "adjustment"
          ? "Ajuste de saldo"
          : "Estoque mínimo";
  function openFilters() {
    setDraft({ state, category, status, behavior });
    setFiltersOpen(true);
  }
  function applyFilters() {
    const appliedParams = params(draft);
    setState(draft.state);
    setCategory(draft.category);
    setStatus(draft.status);
    setBehavior(draft.behavior);
    setFiltersOpen(false);
    void load(undefined, appliedParams);
  }
  function clearFilters() {
    const appliedParams = params(emptyFilters);
    setDraft(emptyFilters);
    setState("");
    setCategory("");
    setStatus("");
    setBehavior("");
    setFiltersOpen(false);
    void load(undefined, appliedParams);
  }
  return (
    <>
      <PageHeader
        title="Estoque"
        description={`${currentBranch?.name || "Selecione uma filial"} · posição atual dos produtos.`}
        action={
          <div className="flex flex-wrap gap-2">
            {canEntry && <Link href="/estoque/entrada-em-grupo" className="btn btn-secondary"><Plus className="size-4" />Entrada em grupo</Link>}
            {showRegularize && <Link href="/estoque/regularizar" className="btn btn-secondary"><TriangleAlert className="size-4" />Regularizar negativos</Link>}
            {canMove && (
              <Button
                onClick={() => setChooser(true)}
                disabled={!currentBranch}
              >
                <Plus className="size-4" />
                Movimentação
              </Button>
            )}
            {canHistory && (
              <Link href="/estoque/movimentacoes" className="btn btn-secondary">
                <History className="size-4" />
                Histórico
              </Link>
            )}
          </div>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !action && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        {showLegacyRecovery && <section className="card border-warning/40 bg-warning/10 p-4 text-sm"><strong className="block text-warning-strong">Estado legado incompatível</strong><p className="mt-1 text-muted">A filial bloqueia estoque negativo, mas ainda possui {summary?.negative_count} {summary?.negative_count === 1 ? "produto negativo" : "produtos negativos"}. Use a recuperação administrativa antes de novas saídas.</p><Link href="/estoque/regularizar?legacy=true" className="btn btn-secondary mt-3"><TriangleAlert className="size-4" />Recuperar saldos negativos</Link></section>}
        {(canViewKpis || canViewCosts) && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {canViewKpis && (
              <>
                <button type="button" className="card flex items-center gap-4 p-5 text-left" onClick={() => { const filters = { state: "negative", category, status, behavior }; setState("negative"); setDraft(filters); void load(undefined, params(filters)); }}>
                  <span className="flex size-10 items-center justify-center rounded-lg bg-red-700 text-white">
                    <TriangleAlert className="size-5" />
                  </span>
                  <div>
                    <strong className="text-xl">{loading ? "..." : (summary?.negative_count ?? 0)}</strong>
                    <p className="text-[11px] text-slate-500">Produtos com saldo negativo</p>
                  </div>
                </button>
                <div className="card flex items-center gap-4 p-5">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-warning/15 text-amber-700">
                    <TriangleAlert className="size-5" />
                  </span>
                  <div>
                    <strong className="text-xl">
                      {loading ? "..." : (summary?.below_minimum_count ?? 0)}
                    </strong>
                    <p className="text-[11px] text-slate-500">
                      Produtos abaixo do mínimo
                    </p>
                  </div>
                </div>
                <div className="card flex items-center gap-4 p-5">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-danger/10 text-danger">
                    <PackageX className="size-5" />
                  </span>
                  <div>
                    <strong className="text-xl">
                      {loading ? "..." : (summary?.zero_count ?? 0)}
                    </strong>
                    <p className="text-[11px] text-slate-500">
                      Produtos zerados
                    </p>
                  </div>
                </div>
              </>
            )}
            {canViewCosts && (
              <div className="card flex items-center gap-4 p-5">
                <span className="flex size-10 items-center justify-center rounded-lg bg-success/10 text-success">
                  <CircleDollarSign className="size-5" />
                </span>
                <div>
                  <strong className="text-xl">
                    {loading
                      ? "..."
                      : summary?.estimated_value !== undefined
                        ? formatBRL(summary.estimated_value)
                        : "-"}
                  </strong>
                  <p className="text-[11px] text-slate-500">
                    Valor em estoque pelo custo atual
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
        <form
          className="card relative p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void load();
          }}
        >
          <div className="flex gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-3 top-3 size-4 text-slate-400" />
              <Input
                className="pl-9"
                placeholder="Produto ou código"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <Button type="submit">Buscar</Button>
            <Button type="button" variant="secondary" onClick={openFilters}>
              <ListFilter className="size-4" />
              Filtros
            </Button>
          </div>
          <p className="mt-2 text-[10px] text-slate-400">
            Filial fixa: <strong>{currentBranch?.name || "nenhuma"}</strong>.
            Lista e indicadores usam os mesmos filtros.
          </p>
          {filtersOpen && (
            <>
              <button
                type="button"
                aria-label="Cancelar filtros"
                className="fixed inset-0 z-40 bg-slate-950/45 md:absolute md:bg-transparent"
                onClick={() => setFiltersOpen(false)}
              />
              <div
                role="dialog"
                aria-label="Filtros de estoque"
                className="fixed inset-x-0 bottom-0 z-50 max-h-[90vh] overflow-y-auto rounded-t-xl bg-white p-5 shadow-2xl md:absolute md:inset-auto md:right-4 md:top-15 md:w-96 md:rounded-xl md:border md:border-slate-200"
              >
                <div className="mb-4 flex items-center justify-between">
                  <strong className="text-sm">Filtros</strong>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => setFiltersOpen(false)}
                  >
                    <X className="size-4" />
                  </button>
                </div>
                <div className="space-y-3">
                  <Field label="Filial atual">
                    <Input
                      readOnly
                      value={currentBranch?.name || "Sem filial ativa"}
                    />
                  </Field>
                  <Field label="Categoria">
                    <Select
                      value={draft.category}
                      onChange={(event) =>
                        setDraft((value) => ({
                          ...value,
                          category: event.target.value,
                        }))
                      }
                    >
                      <option value="">Todas</option>
                      {categories.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Estado">
                    <Select
                      value={draft.state}
                      onChange={(event) =>
                        setDraft((value) => ({
                          ...value,
                          state: event.target.value,
                        }))
                      }
                    >
                      <option value="">Todos</option>
                      <option value="normal">Normal</option>
                      <option value="negative">Negativo</option>
                      <option value="below_minimum">Abaixo do mínimo</option>
                      <option value="zero">Zerado</option>
                    </Select>
                  </Field>
                  <Field label="Status">
                    <Select
                      value={draft.status}
                      onChange={(event) =>
                        setDraft((value) => ({
                          ...value,
                          status: event.target.value,
                        }))
                      }
                    >
                      <option value="">Todos</option>
                      <option value="active">Ativos</option>
                      <option value="inactive">Inativos</option>
                    </Select>
                  </Field>
                  <Field label="Comportamento">
                    <Select
                      value={draft.behavior}
                      onChange={(event) =>
                        setDraft((value) => ({
                          ...value,
                          behavior: event.target.value,
                        }))
                      }
                    >
                      <option value="">Todos</option>
                      <option value="direct">Estoque próprio</option>
                      <option value="none">Sem estoque</option>
                      <option value="components">Componentes</option>
                    </Select>
                  </Field>
                </div>
                <div className="mt-5 flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setFiltersOpen(false)}
                  >
                    Cancelar
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={clearFilters}
                  >
                    Limpar
                  </Button>
                  <Button type="button" onClick={applyFilters}>
                    Aplicar
                  </Button>
                </div>
              </div>
            </>
          )}
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Posição de estoque</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Saldo, categoria e custos atuais
              </p>
            </div>
            <Boxes className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading columns={canViewCosts ? 7 : 5} />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th>Categoria</th>
                      <th>Saldo / Mínimo</th>
                      {canViewCosts && (
                        <>
                          <th>Custo unitário</th>
                          <th>Custo total</th>
                        </>
                      )}
                      <th>Estado</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((stock) => (
                      <tr key={stock.id}>
                        <td>
                          <strong className="block">
                            {stock.product_name}
                          </strong>
                          <span className="text-[11px] text-slate-400">
                            {stock.internal_code}
                          </span>
                        </td>
                        <td>{stock.category_name || "-"}</td>
                        <td>
                          <strong>
                            {formatQuantity(stock.current_quantity)}{" "}
                            {stock.unit.toUpperCase()}
                          </strong>
                          <span className="block text-[10px] text-slate-400">
                            Mín. {formatQuantity(stock.minimum_quantity)}
                          </span>
                        </td>
                        {canViewCosts && (
                          <>
                            <td>{formatBRL(stock.unit_cost)}</td>
                            <td>{formatBRL(stock.total_cost)}</td>
                          </>
                        )}
                        <td>
                          <StateBadge state={stock.state} />
                        </td>
                        <td>
                          <div className="flex justify-end gap-1">
                            {canEntry && (
                                 <button
                                  className="icon-button"
                                  title="Entrada"
                                  onClick={() => resetAction("entry", stock)}
                                >
                                  <ArrowDown className="size-4 text-success" />
                                 </button>
                            )}
                            {canExit && (
                                 <button
                                  className="icon-button"
                                  title="Saída"
                                  onClick={() => resetAction("exit", stock)}
                                >
                                  <ArrowUp className="size-4 text-danger" />
                                 </button>
                            )}
                            {canAdjust && (
                                 <button
                                  className="icon-button"
                                  title="Ajustar saldo"
                                  onClick={() =>
                                    resetAction("adjustment", stock)
                                  }
                                >
                                  <Settings2 className="size-4" />
                                 </button>
                            )}
                            {canMinimum && (
                              <button
                                className="icon-button"
                                title="Estoque mínimo"
                                onClick={() => resetAction("minimum", stock)}
                              >
                                <SlidersHorizontal className="size-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={(path) => load(path)}
              />
            </>
          ) : (
            <EmptyState
              title="Nenhum saldo de estoque"
              description="Nenhum produto foi encontrado para os filtros informados."
            />
          )}
        </section>
      </div>
      <Modal
        open={chooser}
        title="Nova movimentação"
        description="Escolha claramente o tipo de operação antes de informar os dados."
        onClose={() => setChooser(false)}
      >
        <div className="grid gap-3 p-5 sm:grid-cols-3">
          {canEntry && <button
            className="rounded-lg border border-slate-200 p-5 text-left hover:border-success hover:bg-success/5"
            onClick={() => void choose("entry")}
          >
            <ArrowDown className="mb-3 size-5 text-success" />
            <strong className="block text-sm">Entrada</strong>
            <span className="text-[10px] text-slate-500">
              Adicionar quantidade
            </span>
          </button>}
          {canExit && <button
            className="rounded-lg border border-slate-200 p-5 text-left hover:border-danger hover:bg-danger/5"
            onClick={() => void choose("exit")}
          >
            <ArrowUp className="mb-3 size-5 text-danger" />
            <strong className="block text-sm">Saída</strong>
            <span className="text-[10px] text-slate-500">
              Retirar quantidade
            </span>
          </button>}
          {canAdjust && <button
            className="rounded-lg border border-slate-200 p-5 text-left hover:border-primary hover:bg-primary/5"
            onClick={() => void choose("adjustment")}
          >
            <Settings2 className="mb-3 size-5 text-primary" />
            <strong className="block text-sm">Ajuste</strong>
            <span className="text-[10px] text-slate-500">
              Definir saldo final
            </span>
          </button>}
        </div>
      </Modal>
      <Modal
        open={!!action}
        title={title}
        description={
          selected
            ? `${selected.product_name} em ${currentBranch?.name}`
            : `Primeira operação em ${currentBranch?.name || "filial atual"}`
        }
        onClose={() => !saving && setAction(null)}
      >
        <form onSubmit={submit}>
          <div className="space-y-5 p-5">
            {error && <Alert message={error} />}
            {!selected && action !== "minimum" && (
              <>
                <Field label="Produto" error={fieldError(fields, "product")}>
                  <Select
                    required
                    value={productId}
                    onChange={(event) => setProductId(event.target.value)}
                    disabled={productsLoading || !canViewProducts}
                  >
                    <option value="">
                      {productsLoading ? "Carregando..." : "Selecione"}
                    </option>
                    {products.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name} ({product.internal_code})
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Filial">
                  <Input
                    value={currentBranch?.name || ""}
                    readOnly
                    className="bg-slate-50 text-slate-500"
                  />
                </Field>
              </>
            )}
            <Field
              label={
                action === "adjustment"
                  ? "Saldo final"
                  : action === "minimum"
                    ? "Quantidade mínima"
                    : "Quantidade"
              }
              error={fieldError(
                fields,
                action === "adjustment"
                  ? "final_quantity"
                  : action === "minimum"
                    ? "minimum_quantity"
                    : "quantity",
              )}
            >
              <Input
                required
                inputMode="decimal"
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
              />
            </Field>
            {action !== "minimum" && (
              <Field label="Natureza" error={fieldError(fields, "nature")}>
                <Select value={nature} onChange={(event) => setNature(event.target.value)}>
                  {action === "entry" ? <><option value="normal">Compra / entrada normal</option><option value="bonus">Bonificada</option><option value="return">Devolução</option><option value="opening_balance">Saldo inicial</option><option value="correction">Correção</option><option value="other">Outros</option></> : action === "exit" ? <><option value="transfer">Transferência</option><option value="damage">Avaria</option><option value="loss">Perda</option><option value="internal_use">Uso interno</option><option value="correction">Correção</option><option value="other">Outros</option></> : <><option value="inventory">Inventário / contagem física</option><option value="balance_correction">Correção de saldo</option><option value="other">Outros</option></>}
                </Select>
              </Field>
            )}
            {action !== "minimum" && (
              <Field
                label="Motivo"
                optional
                error={fieldError(fields, "reason")}
              >
                <Textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </Field>
            )}
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setAction(null)}
              disabled={saving}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              loading={saving}
              disabled={
                !selected && (!canViewProducts || productsLoading || !productId)
              }
            >
              Confirmar
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
export default function InventoryPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewInventory]}>
      <Inventory />
    </AdminGuard>
  );
}
