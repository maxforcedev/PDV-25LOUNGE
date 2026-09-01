"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  GripVertical,
  Pencil,
  Plus,
  Power,
  Search,
  SlidersHorizontal,
  Tags,
  Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  Select,
  StatusBadge,
  TableLoading,
  Textarea,
} from "@/components/ui";
import { fieldError, formatDate, formatDecimalBRL as formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { archivedRecordConflict } from "@/lib/archived-errors";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Category } from "@/types";

interface CategoryFilters {
  search: string;
  status: string;
  hasProducts: string;
}
const emptyFilters = (): CategoryFilters => ({
  search: "",
  status: "",
  hasProducts: "",
});

function Categories() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const router = useRouter();
  const canAdd = hasPermission(permissions.addCategory);
  const canChange = hasPermission(permissions.changeCategory);
  const canStatus = hasPermission(permissions.changeCategoryStatus);
  const [items, setItems] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [orderState, setOrderState] = useState<"" | "saving" | "error">("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Category | null>(null);
  const [form, setForm] = useState({
    company: 0, name: "", description: "",
    available_counter: true, available_table: true, available_command: true,
    participates_in_service_fee: true, participates_in_commission: true,
  });
  const [applyingConfig, setApplyingConfig] = useState<Category | null>(null);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<Category | null>(null);
  const [deleting, setDeleting] = useState<Category | null>(null);
  const [restoreConflict, setRestoreConflict] = useState<{
    id: number;
    name: string;
    archivedAt: string;
  } | null>(null);
  const [draftFilters, setDraftFilters] =
    useState<CategoryFilters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<CategoryFilters>(emptyFilters);
  const dragged = useRef<number | null>(null);
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;

  async function load(
    companyId = currentCompany?.id,
    context = contextRef.current,
    selected = appliedFilters,
  ) {
    if (!companyId || !currentBranch) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ company: String(companyId) });
      if (selected.search.trim()) params.set("search", selected.search.trim());
      if (selected.status) params.set("status", selected.status);
      if (selected.hasProducts)
        params.set("has_products", selected.hasProducts);
      const result = await http.getAll<Category>(`categories/?${params}`);
      if (contextRef.current === context) setItems(result);
    } catch (caught) {
      if (contextRef.current === context)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar as categorias.",
        );
    } finally {
      if (contextRef.current === context) setLoading(false);
    }
  }

  useEffect(() => {
    setItems([]);
    setOpen(false);
    setRestoreConflict(null);
    setOrderState("");
    dragged.current = null;
    const cleared = emptyFilters();
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    void load(currentCompany?.id, contextRef.current, cleared);
  }, [currentCompany?.id, currentBranch?.id]);

  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    setAppliedFilters(draftFilters);
    setOrderState("");
    dragged.current = null;
    void load(currentCompany?.id, contextRef.current, draftFilters);
  }

  function clearFilters() {
    const cleared = emptyFilters();
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    setOrderState("");
    dragged.current = null;
    void load(currentCompany?.id, contextRef.current, cleared);
  }

  async function show(category?: Category) {
    if (category ? !canChange : !canAdd) return;
    setFields({});
    setError("");
    if (!category) {
      setRestoreConflict(null);
      setEditing(null);
      setForm({
        company: currentCompany?.id || 0, name: "", description: "",
        available_counter: true, available_table: true, available_command: true,
        participates_in_service_fee: true, participates_in_commission: true,
      });
      setOpen(true);
      return;
    }
    setSaving(true);
    setOpen(true);
    try {
      const detail = await http.get<Category>(`categories/${category.id}/`);
      setEditing(detail);
      setForm({
        company: detail.company,
        name: detail.name,
        description: detail.description || "",
        available_counter: detail.available_counter,
        available_table: detail.available_table,
        available_command: detail.available_command,
        participates_in_service_fee: detail.participates_in_service_fee,
        participates_in_commission: detail.participates_in_commission,
      });
    } catch (caught) {
      setOpen(false);
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível abrir a categoria.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setFields({});
    try {
      if (editing) await http.patch(`categories/${editing.id}/`, form);
      else await http.post("categories/", form);
      setOpen(false);
      setSuccess(
        editing
          ? "Categoria atualizada com sucesso."
          : "Categoria criada com sucesso.",
      );
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        const conflict = archivedRecordConflict(
          caught,
          "archived_category_exists",
          "category_id",
        );
        if (!editing && conflict) {
          setRestoreConflict(conflict);
          return;
        }
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível salvar a categoria.");
    } finally {
      setSaving(false);
    }
  }

  async function restoreCategory() {
    if (!restoreConflict) return;
    setSaving(true);
    setError("");
    try {
      await http.post(`categories/${restoreConflict.id}/restore/`);
      setRestoreConflict(null);
      setOpen(false);
      setSuccess("Categoria restaurada com sucesso.");
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível restaurar a categoria.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function persistOrder(next: Category[]) {
    const previous = items;
    const companyId = currentCompany?.id;
    const context = contextRef.current;
    if (
      !companyId ||
      !currentBranch ||
      orderState === "saving" ||
      Object.values(appliedFilters).some(Boolean)
    )
      return;
    setItems(next);
    setOrderState("saving");
    try {
      const ordered = await http.post<Category[]>("categories/reorder/", {
        company: companyId,
        category_ids: next.map((item) => item.id),
      });
      if (contextRef.current !== context) return;
      setItems(ordered);
      setOrderState("");
    } catch (caught) {
      if (contextRef.current !== context) return;
      setItems(previous);
      setOrderState("error");
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível salvar a ordem.",
      );
    }
  }

  async function applyConfig() {
    if (!applyingConfig) return;
    setSaving(true);
    setError("");
    try {
      const result = await http.post<{ updated_products: number; total_products: number }>(`categories/${applyingConfig.id}/apply-config/`, {});
      setApplyingConfig(null);
      setSuccess(`${result.updated_products} de ${result.total_products} produto(s) atualizado(s).`);
    } catch (caught) {
      setApplyingConfig(null);
      setError(caught instanceof ApiError ? caught.message : "Não foi possível aplicar a configuração.");
    } finally {
      setSaving(false);
    }
  }

  function move(from: number, to: number) {
    if (
      !canChange ||
      orderState === "saving" ||
      from < 0 ||
      to < 0 ||
      from >= items.length ||
      to >= items.length ||
      from === to
    )
      return;
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    void persistOrder(next);
  }

  function drop(overId: number) {
    if (dragged.current === null) return;
    const from = items.findIndex((item) => item.id === dragged.current);
    const to = items.findIndex((item) => item.id === overId);
    dragged.current = null;
    move(from, to);
  }

  async function changeStatus() {
    if (!confirming) return;
    setSaving(true);
    const action = confirming.status === "active" ? "deactivate" : "activate";
    try {
      await http.post(`categories/${confirming.id}/${action}/`);
      setConfirming(null);
      setSuccess(
        `Categoria ${action === "activate" ? "ativada" : "inativada"}.`,
      );
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível alterar o status.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function deleteCategory() {
    if (!deleting || !canChange) return;
    setSaving(true);
    setError("");
    try {
      await http.delete(`categories/${deleting.id}/`);
      setDeleting(null);
      setSuccess("Categoria excluída com sucesso.");
      await load();
    } catch (caught) {
      setDeleting(null);
      setError(caught instanceof ApiError ? caught.message : "Não foi possível excluir a categoria.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Categorias"
        description={`Ordem do catálogo de ${currentCompany?.trade_name || "sua empresa"}.`}
        action={
          <Button onClick={() => show()} disabled={!canAdd || !currentBranch}>
            <Plus className="size-4" />
            Nova categoria
          </Button>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !open && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        <form
          className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-[1fr_180px_220px_auto_auto]"
          onSubmit={applyFilters}
        >
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 size-4 text-slate-400" />
            <Input
              className="pl-9"
              placeholder="Nome ou descrição"
              value={draftFilters.search}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  search: event.target.value,
                }))
              }
            />
          </div>
          <Select
            aria-label="Status da categoria"
            value={draftFilters.status}
            onChange={(event) =>
              setDraftFilters((current) => ({
                ...current,
                status: event.target.value,
              }))
            }
          >
            <option value="">Todos os status</option>
            <option value="active">Ativas</option>
            <option value="inactive">Inativas</option>
          </Select>
          <Select
            aria-label="Presença de produtos"
            value={draftFilters.hasProducts}
            onChange={(event) =>
              setDraftFilters((current) => ({
                ...current,
                hasProducts: event.target.value,
              }))
            }
          >
            <option value="">Com ou sem produtos</option>
            <option value="true">Com produtos</option>
            <option value="false">Sem produtos</option>
          </Select>
          <Button type="button" variant="secondary" onClick={clearFilters}>
            Limpar
          </Button>
          <Button type="submit">
            <SlidersHorizontal className="size-4" />
            Aplicar
          </Button>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Categorias cadastradas</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                {orderState === "saving"
                  ? "Salvando nova ordem..."
                  : orderState === "error"
                    ? "A ordem anterior foi restaurada"
                    : Object.values(appliedFilters).some(Boolean)
                      ? "Limpe os filtros para reordenar o catálogo"
                      : canChange
                      ? "Arraste ou use os botões para reordenar"
                      : "Ordem do catálogo"}
              </p>
            </div>
            <Tags className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading />
          ) : items.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ordem</th>
                    <th>Nome</th>
                    <th>Descrição</th>
                    <th>Produtos</th>
                    <th>Status</th>
                    <th className="text-right">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, index) => (
                    <tr
                      key={item.id}
                      draggable={
                        canChange &&
                        orderState !== "saving" &&
                        !Object.values(appliedFilters).some(Boolean)
                      }
                      onDragStart={() => {
                        dragged.current = item.id;
                      }}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={() => drop(item.id)}
                      className="transition hover:bg-slate-50"
                    >
                      <td>
                        <div className="flex items-center gap-1">
                          <GripVertical
                            className={`size-4 ${canChange && !Object.values(appliedFilters).some(Boolean) ? "cursor-grab text-slate-400" : "text-slate-200"}`}
                          />
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Mover ${item.name} para cima`}
                            title="Mover para cima"
                            disabled={
                              !canChange ||
                              Object.values(appliedFilters).some(Boolean) ||
                              orderState === "saving" ||
                              index === 0
                            }
                            onClick={() => move(index, index - 1)}
                          >
                            <ArrowUp className="size-4" />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Mover ${item.name} para baixo`}
                            title="Mover para baixo"
                            disabled={
                              !canChange ||
                              Object.values(appliedFilters).some(Boolean) ||
                              orderState === "saving" ||
                              index === items.length - 1
                            }
                            onClick={() => move(index, index + 1)}
                          >
                            <ArrowDown className="size-4" />
                          </button>
                        </div>
                      </td>
                      <td className="font-semibold">{item.name}</td>
                      <td className="max-w-96 truncate text-slate-500">
                        {item.description || "-"}
                      </td>
                      <td>{item.product_count}</td>
                      <td>
                        <StatusBadge active={item.status === "active"} />
                      </td>
                      <td>
                        <div className="flex justify-end gap-1">
                          <button
                            className="icon-button"
                            disabled={!canChange}
                            onClick={() => void show(item)}
                          >
                            <Pencil className="size-4" />
                          </button>
                          {item.product_count > 0 && (
                            <button
                              className="icon-button"
                              disabled={!canChange}
                              title="Aplicar configuração aos produtos"
                              onClick={() => setApplyingConfig(item)}
                            >
                              <SlidersHorizontal className="size-4" />
                            </button>
                          )}
                          <button
                            className="icon-button"
                            disabled={!canStatus}
                            onClick={() => setConfirming(item)}
                          >
                            <Power className="size-4" />
                          </button>
                          <button
                            className="icon-button text-danger-strong"
                            disabled={!canChange}
                            title="Excluir categoria"
                            onClick={() => setDeleting(item)}
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={
                Object.values(appliedFilters).some(Boolean)
                  ? "Nenhuma categoria encontrada"
                  : "Nenhuma categoria cadastrada"
              }
              description={
                Object.values(appliedFilters).some(Boolean)
                  ? "Nenhuma categoria corresponde aos filtros aplicados."
                  : "Cadastre categorias para organizar o catálogo."
              }
            />
          )}
        </section>
      </div>
      <Modal
        open={open}
        title={editing ? "Editar categoria" : "Nova categoria"}
        onClose={() => !saving && setOpen(false)}
        size={editing ? "xl" : undefined}
      >
        <form onSubmit={submit}>
          <div className="space-y-5 p-5 sm:p-6">
            {error && <Alert message={error} />}
            <Field label="Nome" error={fieldError(fields, "name")}>
              <Input
                required
                value={form.name}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
              />
            </Field>
            <Field
              label="Descrição"
              optional
              error={fieldError(fields, "description")}
            >
              <Textarea
                value={form.description}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
              />
            </Field>
            {editing && (
              <fieldset className="rounded-lg border border-slate-200 p-4">
                <h3 className="text-xs font-bold">Padrões da categoria</h3>
                <p className="mt-1 text-[11px] text-slate-500">Novos produtos herdam estes valores. Use &ldquo;Aplicar config&rdquo; para propagar aos produtos existentes.</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={form.available_counter} onChange={(e) => setForm((c) => ({ ...c, available_counter: e.target.checked }))} />
                    Vende em balcão
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={form.available_table} onChange={(e) => setForm((c) => ({ ...c, available_table: e.target.checked }))} />
                    Vende em mesa
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={form.available_command} onChange={(e) => setForm((c) => ({ ...c, available_command: e.target.checked }))} />
                    Vende em comanda
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={form.participates_in_service_fee} onChange={(e) => setForm((c) => ({ ...c, participates_in_service_fee: e.target.checked }))} />
                    Participa da taxa de serviço
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={form.participates_in_commission} onChange={(e) => setForm((c) => ({ ...c, participates_in_commission: e.target.checked }))} />
                    Participa da comissão
                  </label>
                </div>
              </fieldset>
            )}
            {editing && (
              <section className="rounded-lg border border-slate-200">
                <div className="border-b border-slate-100 px-4 py-3">
                  <h3 className="text-xs font-bold">Produtos relacionados</h3>
                </div>
                {editing.related_products.length ? (
                  <div className="divide-y divide-slate-100">
                    {editing.related_products.map((product) => (
                      <button
                        type="button"
                        key={product.id}
                        className="grid w-full gap-1 px-4 py-3 text-left hover:bg-slate-50 sm:grid-cols-[1fr_9rem_8rem_auto] sm:items-center"
                        onClick={() =>
                          router.push(`/produtos?edit=${product.id}`)
                        }
                      >
                        <strong className="text-xs">{product.name}</strong>
                        <span className="text-[11px] text-slate-500">
                          {product.internal_code}
                        </span>
                        <span className="text-xs">
                          {formatBRL(product.sale_price)}
                        </span>
                        <StatusBadge active={product.status === "active"} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="p-4 text-xs text-slate-400">
                    Nenhum produto nesta categoria.
                  </p>
                )}
              </section>
            )}
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setOpen(false)}
              disabled={saving}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={saving}>
              Salvar categoria
            </Button>
          </div>
        </form>
      </Modal>
      <ConfirmDialog
        open={!!confirming}
        title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} categoria`}
        message={`Confirma a alteração de status de “${confirming?.name || ""}”?`}
        confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"}
        danger={confirming?.status === "active"}
        loading={saving}
        onClose={() => setConfirming(null)}
        onConfirm={changeStatus}
      />
      <ConfirmDialog
        open={!!applyingConfig}
        title="Aplicar configuração aos produtos"
        message={`Propagar os padrões de canais e participação financeira de "${applyingConfig?.name || ""}" para ${applyingConfig?.product_count || 0} produto(s)? Esta ação é auditada e não pode ser desfeita.`}
        confirmLabel="Aplicar"
        loading={saving}
        onClose={() => setApplyingConfig(null)}
        onConfirm={applyConfig}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Excluir categoria"
        message={`Excluir “${deleting?.name || ""}”? A exclusão é permitida somente sem produtos operacionais ativos vinculados.`}
        confirmLabel="Excluir"
        danger
        loading={saving}
        onClose={() => setDeleting(null)}
        onConfirm={deleteCategory}
      />
      <Modal
        open={!!restoreConflict}
        title="Restaurar categoria"
        description={`Já existiu uma categoria chamada “${restoreConflict?.name || ""}” nesta filial.`}
        onClose={() => !saving && setRestoreConflict(null)}
      >
        <div className="space-y-4 p-5">
          {error && <Alert message={error} />}
          <p className="text-sm text-muted">
            Excluída em: {restoreConflict ? formatDate(restoreConflict.archivedAt) : ""}
          </p>
          <p className="text-sm text-muted">
            A restauração preserva o mesmo ID e o histórico da categoria.
          </p>
          <div className="flex justify-end gap-2 border-t border-subtle pt-4">
            <Button variant="secondary" disabled={saving} onClick={() => setRestoreConflict(null)}>Cancelar</Button>
            <Button loading={saving} onClick={() => void restoreCategory()}>Restaurar categoria</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

export default function CategoriesPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewCategory]}>
      <Categories />
    </AdminGuard>
  );
}
