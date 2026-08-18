"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, GripVertical, Pencil, Plus, Power, Tags } from "lucide-react";
import { useRouter } from "next/navigation";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, EmptyState, Field, Input, Modal, StatusBadge, TableLoading, Textarea } from "@/components/ui";
import { fieldError, formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Category } from "@/types";

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
  const [form, setForm] = useState({ company: 0, name: "", description: "" });
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<Category | null>(null);
  const dragged = useRef<number | null>(null);
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;

  async function load(companyId = currentCompany?.id, context = contextRef.current) {
    if (!companyId || !currentBranch) { setItems([]); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const result = await http.getAll<Category>(`categories/?company=${companyId}`);
      if (contextRef.current === context) setItems(result);
    } catch (caught) {
      if (contextRef.current === context) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as categorias.");
    } finally {
      if (contextRef.current === context) setLoading(false);
    }
  }

  useEffect(() => {
    setItems([]); setOpen(false); setOrderState(""); dragged.current = null;
    void load(currentCompany?.id, contextRef.current);
  }, [currentCompany?.id, currentBranch?.id]);

  async function show(category?: Category) {
    if (category ? !canChange : !canAdd) return;
    setFields({}); setError("");
    if (!category) {
      setEditing(null); setForm({ company: currentCompany?.id || 0, name: "", description: "" }); setOpen(true); return;
    }
    setSaving(true); setOpen(true);
    try {
      const detail = await http.get<Category>(`categories/${category.id}/`);
      setEditing(detail); setForm({ company: detail.company, name: detail.name, description: detail.description || "" });
    } catch (caught) {
      setOpen(false); setError(caught instanceof ApiError ? caught.message : "Não foi possível abrir a categoria.");
    } finally { setSaving(false); }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setFields({});
    try {
      if (editing) await http.patch(`categories/${editing.id}/`, form); else await http.post("categories/", form);
      setOpen(false); setSuccess(editing ? "Categoria atualizada com sucesso." : "Categoria criada com sucesso."); await load();
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields); } else setError("Não foi possível salvar a categoria.");
    } finally { setSaving(false); }
  }

  async function persistOrder(next: Category[]) {
    const previous = items;
    const companyId = currentCompany?.id;
    const context = contextRef.current;
    if (!companyId || !currentBranch || orderState === "saving") return;
    setItems(next); setOrderState("saving");
    try {
      const ordered = await http.post<Category[]>("categories/reorder/", { company: companyId, category_ids: next.map((item) => item.id) });
      if (contextRef.current !== context) return;
      setItems(ordered); setOrderState("");
    } catch (caught) {
      if (contextRef.current !== context) return;
      setItems(previous); setOrderState("error");
      setError(caught instanceof ApiError ? caught.message : "Não foi possível salvar a ordem.");
    }
  }

  function move(from: number, to: number) {
    if (!canChange || orderState === "saving" || from < 0 || to < 0 || from >= items.length || to >= items.length || from === to) return;
    const next = [...items]; const [moved] = next.splice(from, 1); next.splice(to, 0, moved); void persistOrder(next);
  }

  function drop(overId: number) {
    if (dragged.current === null) return;
    const from = items.findIndex((item) => item.id === dragged.current);
    const to = items.findIndex((item) => item.id === overId);
    dragged.current = null; move(from, to);
  }

  async function changeStatus() {
    if (!confirming) return;
    setSaving(true);
    const action = confirming.status === "active" ? "deactivate" : "activate";
    try {
      await http.post(`categories/${confirming.id}/${action}/`); setConfirming(null);
      setSuccess(`Categoria ${action === "activate" ? "ativada" : "inativada"}.`); await load();
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar o status."); }
    finally { setSaving(false); }
  }

  return <>
    <PageHeader title="Categorias" description={`Ordem do catálogo de ${currentCompany?.trade_name || "sua empresa"}.`} action={<Button onClick={() => show()} disabled={!canAdd || !currentBranch}><Plus className="size-4" />Nova categoria</Button>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !open && <Alert message={error} />}{success && <Alert type="success" message={success} />}
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Categorias cadastradas</h2><p className="mt-1 text-[11px] text-slate-500">{orderState === "saving" ? "Salvando nova ordem..." : orderState === "error" ? "A ordem anterior foi restaurada" : canChange ? "Arraste ou use os botões para reordenar" : "Ordem do catálogo"}</p></div><Tags className="size-5 text-slate-300" /></div>
        {loading ? <TableLoading /> : items.length ? <div className="table-wrap"><table className="data-table">
          <thead><tr><th>Ordem</th><th>Nome</th><th>Descrição</th><th>Produtos</th><th>Status</th><th className="text-right">Ações</th></tr></thead>
          <tbody>{items.map((item, index) => <tr key={item.id} draggable={canChange && orderState !== "saving"} onDragStart={() => { dragged.current = item.id; }} onDragOver={(event) => event.preventDefault()} onDrop={() => drop(item.id)} className="transition hover:bg-slate-50">
            <td><div className="flex items-center gap-1"><GripVertical className={`size-4 ${canChange ? "cursor-grab text-slate-400" : "text-slate-200"}`} /><button type="button" className="icon-button" aria-label={`Mover ${item.name} para cima`} title="Mover para cima" disabled={!canChange || orderState === "saving" || index === 0} onClick={() => move(index, index - 1)}><ArrowUp className="size-4" /></button><button type="button" className="icon-button" aria-label={`Mover ${item.name} para baixo`} title="Mover para baixo" disabled={!canChange || orderState === "saving" || index === items.length - 1} onClick={() => move(index, index + 1)}><ArrowDown className="size-4" /></button></div></td>
            <td className="font-semibold">{item.name}</td><td className="max-w-96 truncate text-slate-500">{item.description || "-"}</td><td>{item.product_count}</td><td><StatusBadge active={item.status === "active"} /></td>
            <td><div className="flex justify-end gap-1"><button className="icon-button" disabled={!canChange} onClick={() => void show(item)}><Pencil className="size-4" /></button><button className="icon-button" disabled={!canStatus} onClick={() => setConfirming(item)}><Power className="size-4" /></button></div></td>
          </tr>)}</tbody>
        </table></div> : <EmptyState title="Nenhuma categoria cadastrada" description="Cadastre categorias para organizar o catálogo." />}
      </section>
    </div>
    <Modal open={open} title={editing ? "Editar categoria" : "Nova categoria"} onClose={() => !saving && setOpen(false)} size={editing ? "xl" : undefined}><form onSubmit={submit}>
      <div className="space-y-5 p-5 sm:p-6">{error && <Alert message={error} />}<Field label="Nome" error={fieldError(fields, "name")}><Input required value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /></Field><Field label="Descrição" optional error={fieldError(fields, "description")}><Textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} /></Field>
        {editing && <section className="rounded-lg border border-slate-200"><div className="border-b border-slate-100 px-4 py-3"><h3 className="text-xs font-bold">Produtos relacionados</h3></div>{editing.related_products.length ? <div className="divide-y divide-slate-100">{editing.related_products.map((product) => <button type="button" key={product.id} className="grid w-full gap-1 px-4 py-3 text-left hover:bg-slate-50 sm:grid-cols-[1fr_9rem_8rem_auto] sm:items-center" onClick={() => router.push(`/produtos?edit=${product.id}`)}><strong className="text-xs">{product.name}</strong><span className="text-[11px] text-slate-500">{product.internal_code}</span><span className="text-xs">{formatBRL(product.sale_price)}</span><StatusBadge active={product.status === "active"} /></button>)}</div> : <p className="p-4 text-xs text-slate-400">Nenhum produto nesta categoria.</p>}</section>}
      </div>
      <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4"><Button type="button" variant="secondary" onClick={() => setOpen(false)} disabled={saving}>Cancelar</Button><Button type="submit" loading={saving}>Salvar categoria</Button></div>
    </form></Modal>
    <ConfirmDialog open={!!confirming} title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} categoria`} message={`Confirma a alteração de status de “${confirming?.name || ""}”?`} confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"} danger={confirming?.status === "active"} loading={saving} onClose={() => setConfirming(null)} onConfirm={changeStatus} />
  </>;
}

export default function CategoriesPage() { return <AdminGuard requiredPermissions={[permissions.viewCategory]}><Categories /></AdminGuard>; }
