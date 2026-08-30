"use client";

import { useEffect, useRef, useState } from "react";
import { GripVertical, Plus, Pencil, Trash2 } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  ConfirmDialog,
  Field,
  Input,
  Modal,
  Spinner,
  TableLoading,
  Select,
} from "@/components/ui";
import { fieldError, formatBRL } from "@/lib/format";
import { ApiError, friendlyError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { ModifierGroup, ModifierOption, Product } from "@/types";

interface OptionForm {
  name: string;
  option_type: ModifierOption["option_type"];
  additional_price: string;
  stock_product: string;
}

function ModifiersPage() {
  const { currentCompany, hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canChange = hasPermission(permissions.changeModifiers) && !readOnly;
  const [groups, setGroups] = useState<ModifierGroup[]>([]);
  const [stockProducts, setStockProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModifierGroup | null>(null);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    is_required: false,
    min_selections: "0",
    max_selections: "",
    allow_option_quantity: false,
    substitution_component: "",
  });
  const [options, setOptions] = useState<OptionForm[]>([]);
  const [optionsModalOpen, setOptionsModalOpen] = useState(false);
  const [viewingGroup, setViewingGroup] = useState<ModifierGroup | null>(null);
  const [groupOptions, setGroupOptions] = useState<ModifierOption[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [optionForm, setOptionForm] = useState<OptionForm>({
    name: "",
    option_type: "add",
    additional_price: "0",
    stock_product: "",
  });
  const [optionEditing, setOptionEditing] = useState<ModifierOption | null>(
    null,
  );
  const [deletingGroup, setDeletingGroup] = useState<ModifierGroup | null>(null);
  const [deletingOption, setDeletingOption] = useState<ModifierOption | null>(null);
  const [reordering, setReordering] = useState(false);
  const [draggedGroupId, setDraggedGroupId] = useState<number | null>(null);
  const [draggedOptionId, setDraggedOptionId] = useState<number | null>(null);
  const context = useRef("");

  context.current = String(currentCompany?.id || "");

  async function load(token: string) {
    if (!currentCompany) {
      setGroups([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await http.getAll<ModifierGroup>(
        `modifier-groups/?company=${currentCompany.id}`,
      );
      if (context.current === token) setGroups(response);
    } catch (caught) {
      if (context.current === token)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar os modificadores.",
        );
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    setGroups([]);
    void loadRef.current(String(currentCompany?.id || ""));
  }, [currentCompany?.id]);

  useEffect(() => {
    if (!currentCompany) {
      setStockProducts([]);
      return;
    }
    void http
      .getAll<Product>(
        `products/?company=${currentCompany.id}&lifecycle=active&status=active&inventory_behavior=direct`,
      )
      .then(setStockProducts)
      .catch(() => setStockProducts([]));
  }, [currentCompany?.id]);

  function openCreate() {
    setEditing(null);
    setForm({
      name: "",
      is_required: false,
      min_selections: "0",
      max_selections: "",
      allow_option_quantity: false,
      substitution_component: "",
    });
    setOptions([]);
    setFields({});
    setModalOpen(true);
  }

  function openEdit(group: ModifierGroup) {
    setEditing(group);
    setForm({
      name: group.name,
      is_required: group.is_required,
      min_selections: String(group.min_selections),
      max_selections:
        group.max_selections != null ? String(group.max_selections) : "",
      allow_option_quantity: group.allow_option_quantity,
      substitution_component: group.substitution_component
        ? String(group.substitution_component)
        : "",
    });
    setFields({});
    setModalOpen(true);
  }

  async function save() {
    if (!currentCompany) return;
    const minimum = Number(form.min_selections) || 0;
    const maximum = form.max_selections ? Number(form.max_selections) : null;
    if (form.is_required && minimum < 1) {
      setError("Grupo obrigatório exige pelo menos uma seleção.");
      return;
    }
    if (maximum !== null && minimum > maximum) {
      setError("A seleção máxima não pode ser menor que a mínima.");
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    const payload = {
      company: currentCompany.id,
      name: form.name.trim(),
      is_required: form.is_required,
      min_selections: minimum,
      max_selections: maximum,
      allow_option_quantity: form.allow_option_quantity,
      substitution_component: form.substitution_component
        ? Number(form.substitution_component)
        : null,
    };
    try {
      if (editing) {
        await http.patch(`modifier-groups/${editing.id}/`, payload);
      } else {
        await http.post("modifier-groups/", payload);
      }
      setModalOpen(false);
      await load(String(currentCompany.id));
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields || {});
      } else {
        setError("Não foi possível salvar o modificador.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function deleteGroup() {
    if (!canChange || !currentCompany || !deletingGroup) return;
    setSaving(true);
    try {
      await http.delete(`modifier-groups/${deletingGroup.id}/`);
      if (viewingGroup?.id === deletingGroup.id) {
        setOptionsModalOpen(false);
        setViewingGroup(null);
      }
      setDeletingGroup(null);
      await load(String(currentCompany.id));
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível excluir o grupo.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function openOptions(group: ModifierGroup) {
    setViewingGroup(group);
    setOptionsModalOpen(true);
    setLoadingOptions(true);
    try {
      const detail = await http.get<ModifierGroup>(
        `modifier-groups/${group.id}/`,
      );
      setGroupOptions(detail.options || []);
    } catch {
      setGroupOptions([]);
    } finally {
      setLoadingOptions(false);
    }
  }

  function openCreateOption() {
    setOptionEditing(null);
    setOptionForm({
      name: "",
      option_type: "add",
      additional_price: "0",
      stock_product: "",
    });
  }

  function openEditOption(opt: ModifierOption) {
    setOptionEditing(opt);
    setOptionForm({
      name: opt.name,
      option_type: opt.option_type === "text" ? "add" : opt.option_type,
      additional_price: opt.additional_price,
      stock_product: opt.stock_product ? String(opt.stock_product) : "",
    });
  }

  async function saveOption() {
    if (!viewingGroup || !currentCompany) return;
    setSaving(true);
    setError("");
    try {
      const payload = {
        modifier_group: viewingGroup.id,
        name: optionForm.name.trim(),
        option_type: optionForm.option_type,
        additional_price: optionForm.additional_price,
        stock_product: optionForm.stock_product
          ? Number(optionForm.stock_product)
          : null,
      };
      if (optionEditing) {
        await http.patch(`modifier-options/${optionEditing.id}/`, payload);
      } else {
        await http.post("modifier-options/", payload);
      }
      setOptionEditing(null);
      setOptionForm({
        name: "",
        option_type: "add",
        additional_price: "0",
        stock_product: "",
      });
      await openOptions(viewingGroup);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível salvar a opção.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function deleteOption() {
    if (!canChange || !deletingOption) return;
    setSaving(true);
    try {
      await http.delete(`modifier-options/${deletingOption.id}/`);
      if (optionEditing?.id === deletingOption.id) openCreateOption();
      setDeletingOption(null);
      if (viewingGroup) await openOptions(viewingGroup);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível remover a opção.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function reorderGroups(sourceId: number, targetId: number) {
    if (reordering || sourceId === targetId) return;
    const previous = groups;
    const next = [...groups];
    const source = next.findIndex((item) => item.id === sourceId);
    const target = next.findIndex((item) => item.id === targetId);
    next.splice(target, 0, next.splice(source, 1)[0]);
    setGroups(next);
    setReordering(true);
    try {
      await http.post("modifier-groups/reorder/", {
        group_ids: next.map((item) => item.id),
      });
    } catch (caught) {
      setGroups(previous);
      setError(
        friendlyError(caught, "Não foi possível ordenar os grupos.").message,
      );
    } finally {
      setReordering(false);
      setDraggedGroupId(null);
    }
  }

  async function reorderOptions(sourceId: number, targetId: number) {
    if (!viewingGroup || reordering || sourceId === targetId) return;
    const previous = groupOptions;
    const next = [...groupOptions];
    const source = next.findIndex((item) => item.id === sourceId);
    const target = next.findIndex((item) => item.id === targetId);
    next.splice(target, 0, next.splice(source, 1)[0]);
    setGroupOptions(next);
    setReordering(true);
    try {
      await http.post("modifier-options/reorder/", {
        modifier_group: viewingGroup.id,
        option_ids: next.map((item) => item.id),
      });
    } catch (caught) {
      setGroupOptions(previous);
      setError(
        friendlyError(caught, "Não foi possível ordenar as opções.").message,
      );
    } finally {
      setReordering(false);
      setDraggedOptionId(null);
    }
  }

  if (!currentCompany)
    return (
      <div className="p-6">
        <Alert message="Selecione uma empresa." />
      </div>
    );

  return (
    <>
      <PageHeader
        title="Modificadores"
        description="Grupos de modificadores (adicionais, observações) vinculados a produtos."
        action={
          canChange ? (
            <Button onClick={openCreate}>
              <Plus className="size-4" />
              Novo grupo
            </Button>
          ) : undefined
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {loading ? (
          <TableLoading />
        ) : groups.length ? (
          <section className="card overflow-hidden">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th aria-label="Ordenação" />
                  <th>Grupo</th>
                  <th>Obrigatório</th>
                  <th>Min/Max</th>
                  <th>Qtd. opção</th>
                  {canChange && <th>Ações</th>}
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <tr
                    key={group.id}
                    draggable={canChange && !reordering}
                    onDragStart={() => setDraggedGroupId(group.id)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() =>
                      draggedGroupId &&
                      void reorderGroups(draggedGroupId, group.id)
                    }
                    className={draggedGroupId === group.id ? "opacity-40" : ""}
                  >
                    <td>
                      <span
                        className="cursor-grab touch-none active:cursor-grabbing"
                        role="button"
                        aria-label={`Arrastar ${group.name}`}
                        tabIndex={0}
                      >
                        <GripVertical className="size-4 text-muted" />
                      </span>
                    </td>
                    <td>
                      <strong>{group.name}</strong>
                    </td>
                    <td>{group.is_required ? "Sim" : "Não"}</td>
                    <td>
                      {group.min_selections}
                      {group.max_selections != null
                        ? ` / ${group.max_selections}`
                        : " / ∞"}
                    </td>
                    <td>{group.allow_option_quantity ? "Sim" : "Não"}</td>
                    {canChange && (
                      <td>
                        <div className="flex gap-1">
                          <button
                            className="icon-button"
                            title="Editar"
                            onClick={() => openEdit(group)}
                          >
                            <Pencil className="size-4" />
                          </button>
                          <button
                            className="icon-button"
                            title="Opções"
                            onClick={() => void openOptions(group)}
                          >
                            <Plus className="size-4" />
                          </button>
                          <button
                            className="icon-button text-danger"
                            title="Excluir"
                            onClick={() => setDeletingGroup(group)}
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </section>
        ) : (
          <Alert message="Nenhum grupo de modificador cadastrado." />
        )}
      </div>

      <Modal
        open={modalOpen}
        title={editing ? "Editar grupo" : "Novo grupo de modificador"}
        onClose={() => setModalOpen(false)}
      >
        <div className="space-y-4 p-5">
          <Field label="Nome do grupo" error={fieldError(fields, "name")}>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              disabled={saving}
              placeholder="Ex.: Adicionais do hambúrguer"
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Seleção mínima"
              error={fieldError(fields, "min_selections")}
            >
              <Input
                type="number"
                min="0"
                value={form.min_selections}
                onChange={(e) =>
                  setForm({ ...form, min_selections: e.target.value })
                }
                disabled={saving}
              />
            </Field>
            <Field
              label="Seleção máxima (vazio = ilimitado)"
              error={fieldError(fields, "max_selections")}
            >
              <Input
                type="number"
                min="0"
                value={form.max_selections}
                onChange={(e) =>
                  setForm({ ...form, max_selections: e.target.value })
                }
                disabled={saving}
              />
            </Field>
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={form.is_required}
                onChange={(e) =>
                  setForm({ ...form, is_required: e.target.checked })
                }
                disabled={saving}
              />
              Obrigatório
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={form.allow_option_quantity}
                onChange={(e) =>
                  setForm({ ...form, allow_option_quantity: e.target.checked })
                }
                disabled={saving}
              />
              Permitir quantidade por opção
            </label>
          </div>
          <Field
            label="Componente substituído"
            optional
            error={fieldError(fields, "substitution_component")}
          >
            <Select
              value={form.substitution_component}
              onChange={(e) =>
                setForm({ ...form, substitution_component: e.target.value })
              }
              disabled={saving}
            >
              <option value="">Grupo de texto ou adicional</option>
              {stockProducts.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name} ({product.unit.toUpperCase()})
                </option>
              ))}
            </Select>
            <span className="mt-1 block text-[10px] text-muted">
              Para substituição, a quantidade é herdada automaticamente do
              produto avulso ou da composição.
            </span>
          </Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button loading={saving} onClick={() => void save()}>
              {editing ? "Salvar" : "Criar"}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={optionsModalOpen}
        title={`Opções de "${viewingGroup?.name || ""}"`}
        onClose={() => setOptionsModalOpen(false)}
        size="xl"
      >
        <div className="space-y-4 p-5">
          {loadingOptions ? (
            <Spinner />
          ) : (
            <>
              {groupOptions.length > 0 && (
                <div className="divide-y divide-subtle">
                  {groupOptions.map((opt) => (
                    <div
                      key={opt.id}
                      draggable={canChange && !reordering}
                      onDragStart={() => setDraggedOptionId(opt.id)}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={() =>
                        draggedOptionId &&
                        void reorderOptions(draggedOptionId, opt.id)
                      }
                      className={`flex items-center justify-between py-3 ${draggedOptionId === opt.id ? "opacity-40" : ""}`}
                    >
                      <span
                        className="mr-2 cursor-grab touch-none active:cursor-grabbing"
                        role="button"
                        aria-label={`Arrastar ${opt.name}`}
                        tabIndex={0}
                      >
                        <GripVertical className="size-4 text-muted" />
                      </span>
                      <div>
                        <strong className="text-sm">{opt.name}</strong>
                        <div className="text-[11px] text-muted">
                          {opt.option_type === "product_input"
                            ? "Produto ou insumo"
                            : opt.option_type === "component_substitution"
                              ? "Substituição de componente"
                              : opt.option_type === "text"
                                ? "Adicionar sem estoque (legado)"
                                : opt.option_type === "add"
                                  ? "Adicionar sem estoque"
                                  : opt.option_type === "remove"
                                    ? "Remover componente"
                                    : "Observação"}
                          {opt.stock_product_name &&
                            ` · ${opt.stock_product_name}`}
                          {opt.additional_price !== "0" &&
                            ` · ${formatBRL(opt.additional_price)}`}
                        </div>
                      </div>
                      {canChange && (
                        <div className="flex gap-1">
                          <button
                            className="icon-button"
                            title="Editar"
                            onClick={() => openEditOption(opt)}
                          >
                            <Pencil className="size-4" />
                          </button>
                          <button
                            className="icon-button text-danger"
                            title="Excluir"
                            onClick={() => setDeletingOption(opt)}
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {canChange && (
                <fieldset className="rounded-lg border border-slate-200 p-4">
                  <h3 className="text-xs font-bold">
                    {optionEditing ? "Editar opção" : "Nova opção"}
                  </h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Field label="Nome">
                      <Input
                        value={optionForm.name}
                        onChange={(e) =>
                          setOptionForm({ ...optionForm, name: e.target.value })
                        }
                        disabled={saving}
                        placeholder="Ex.: Bacon extra"
                      />
                    </Field>
                    <Field label="Tipo">
                      <Select
                        value={optionForm.option_type}
                        onChange={(e) =>
                          setOptionForm({
                            ...optionForm,
                            option_type: e.target
                              .value as ModifierOption["option_type"],
                            stock_product: "",
                          })
                        }
                        disabled={saving}
                      >
                        <option value="product_input">Produto ou insumo</option>
                        <option
                          value="component_substitution"
                          disabled={!viewingGroup?.substitution_component}
                        >
                          Substituição de componente
                        </option>
                        <option value="add">Adicionar sem estoque</option>
                        <option value="remove">Remover componente</option>
                        <option value="observation">Observação</option>
                      </Select>
                    </Field>
                    <Field label="Preço adicional">
                      <Input
                        inputMode="decimal"
                        min="0"
                        value={optionForm.additional_price}
                        onChange={(e) =>
                          setOptionForm({
                            ...optionForm,
                            additional_price: e.target.value,
                          })
                        }
                        disabled={saving}
                      />
                    </Field>
                    {(optionForm.option_type === "product_input" ||
                      optionForm.option_type === "component_substitution") && (
                      <Field label="Produto ou insumo real">
                        <Select
                          required
                          value={optionForm.stock_product}
                          onChange={(e) =>
                            setOptionForm({
                              ...optionForm,
                              stock_product: e.target.value,
                            })
                          }
                          disabled={saving}
                        >
                          <option value="">Selecione</option>
                          {stockProducts
                            .filter(
                              (product) =>
                                optionForm.option_type !==
                                  "component_substitution" ||
                                product.id !==
                                  viewingGroup?.substitution_component,
                            )
                            .map((product) => (
                              <option key={product.id} value={product.id}>
                                {product.name} ({product.unit.toUpperCase()})
                              </option>
                            ))}
                        </Select>
                      </Field>
                    )}
                  </div>
                  <div className="mt-3 flex justify-end gap-2">
                    {optionEditing && (
                      <Button
                        variant="secondary"
                        onClick={() => openCreateOption()}
                      >
                        Cancelar edição
                      </Button>
                    )}
                    <Button
                      loading={saving}
                      onClick={() => void saveOption()}
                      disabled={!optionForm.name.trim()}
                    >
                      {optionEditing ? "Salvar opção" : "Adicionar opção"}
                    </Button>
                  </div>
                </fieldset>
              )}
            </>
          )}
        </div>
      </Modal>
      <ConfirmDialog
        open={Boolean(deletingGroup)}
        title="Excluir grupo de modificador"
        message={`Excluir “${deletingGroup?.name || ""}”? O histórico de vendas e comandas será preservado.`}
        confirmLabel="Excluir grupo"
        danger
        loading={saving}
        onClose={() => setDeletingGroup(null)}
        onConfirm={() => void deleteGroup()}
      />
      <ConfirmDialog
        open={Boolean(deletingOption)}
        title="Excluir opção de modificador"
        message={`Excluir “${deletingOption?.name || ""}”? O histórico continuará preservado.`}
        confirmLabel="Excluir opção"
        danger
        loading={saving}
        onClose={() => setDeletingOption(null)}
        onConfirm={() => void deleteOption()}
      />
    </>
  );
}

export default function ModifiersPageWrapper() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewModifiers]}>
      <ModifiersPage />
    </AdminGuard>
  );
}
