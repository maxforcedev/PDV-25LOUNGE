"use client";

import { useEffect, useRef, useState } from "react";
import { Layers, Pencil, Plus, Search, Trash2, Users } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Modal, TableLoading } from "@/components/ui";
import { fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { BranchSettings, Table } from "@/types";

function TablesPage() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canManageTables = hasPermission(permissions.manageTables) && !readOnly;
  const [tables, setTables] = useState<Table[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [editing, setEditing] = useState<Table | null>(null);
  const [form, setForm] = useState({ name: "", seats: "0" });
  const [batchForm, setBatchForm] = useState({ prefix: "", start: "1", end: "20", seats: "0" });
  const [search, setSearch] = useState("");
  const [settings, setSettings] = useState<BranchSettings | null>(null);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<Table | null>(null);
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(token: string) {
    if (!currentBranch) {
      setTables([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await http.getAll<Table>(`tables/?branch=${currentBranch.id}`);
      if (context.current === token) setTables(response);
    } catch (caught) {
      if (context.current === token) {
        setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as mesas.");
      }
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    setTables([]);
    void loadRef.current(String(currentBranch?.id || ""));
    if (currentBranch) {
      void http.get<BranchSettings>(`branches/${currentBranch.id}/settings/`)
        .then(setSettings)
        .catch(() => setSettings(null));
    }
  }, [currentBranch?.id]);

  function openCreate() {
    setEditing(null);
    setForm({ name: "", seats: "0" });
    setFields({});
    setModalOpen(true);
  }

  function openEdit(table: Table) {
    setEditing(table);
    setForm({ name: table.name, seats: String(table.seats) });
    setFields({});
    setModalOpen(true);
  }

  async function save() {
    if (!currentBranch) return;
    setSaving(true);
    setError("");
    setFields({});
    const payload = { branch: currentBranch.id, name: form.name.trim(), seats: Number(form.seats) || 0 };
    try {
      if (editing) await http.patch(`tables/${editing.id}/`, payload);
      else await http.post("tables/", payload);
      setModalOpen(false);
      await load(String(currentBranch.id));
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields || {});
      } else setError("Não foi possível salvar a mesa.");
    } finally {
      setSaving(false);
    }
  }

  async function batchSave() {
    if (!currentBranch) return;
    setSaving(true);
    setError("");
    setFields({});
    try {
      await http.post("tables/batch/", {
        branch: currentBranch.id,
        prefix: batchForm.prefix,
        start: Number(batchForm.start),
        end: Number(batchForm.end),
        seats: Number(batchForm.seats) || 0,
      });
      setBatchOpen(false);
      await load(String(currentBranch.id));
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields || {});
      } else setError("Não foi possível criar as mesas em lote.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteTable(table: Table) {
    if (!canManageTables || !currentBranch) return;
    setSaving(true);
    setError("");
    try {
      await http.delete(`tables/${table.id}/`);
      setDeleting(null);
      await load(String(currentBranch.id));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível excluir a mesa.");
    } finally {
      setSaving(false);
    }
  }

  if (!currentBranch) return <div className="p-6"><Alert message="Selecione uma filial." /></div>;
  const term = search.trim().toLowerCase();
  const visibleTables = tables.filter((table) => !term || table.name.toLowerCase().includes(term));

  return <>
    <PageHeader title="Mesas" action={canManageTables ? <div className="flex gap-2">
      <Button variant="secondary" onClick={() => {
        setBatchForm({ prefix: settings?.default_table_prefix || "", start: String(settings?.table_range_start || 1), end: String(settings?.table_range_end || settings?.default_table_quantity || 20), seats: String(settings?.default_table_seats || 0) });
        setBatchOpen(true);
      }}><Layers className="size-4" />Configurar intervalo</Button>
      <Button onClick={openCreate}><Plus className="size-4" />Nova mesa</Button>
    </div> : undefined} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      <section className="rounded-lg border border-subtle bg-surface p-3">
        <div className="relative w-full lg:max-w-md"><Search className="absolute left-3 top-3 size-4 text-muted" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Pesquisar mesa" /></div>
      </section>
      {loading ? <TableLoading /> : visibleTables.length ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {visibleTables.map((table) => <section key={table.id} className="card min-h-44 p-5">
          <div className="flex items-start justify-between gap-3"><div><h2 className="text-2xl font-black tracking-tight">{table.name}</h2><p className="mt-1 text-xs font-bold text-muted">MESA FÍSICA</p></div>{canManageTables && <div className="flex gap-1"><button className="icon-button" title="Editar mesa" onClick={() => openEdit(table)}><Pencil className="size-4" /></button><button className="icon-button" title="Excluir mesa" onClick={() => setDeleting(table)}><Trash2 className="size-4" /></button></div>}</div>
          <div className="mt-6"><span className="inline-flex items-center gap-1 text-sm text-muted"><Users className="size-4" />{table.seats ? `${table.seats} lugares` : "Sem capacidade"}</span></div>
        </section>)}
      </div> : <Alert message={tables.length ? "Nenhuma mesa corresponde à pesquisa." : "Nenhuma mesa cadastrada nesta filial."} />}
    </div>
    <Modal open={modalOpen} title={editing ? "Editar mesa" : "Nova mesa"} onClose={() => setModalOpen(false)}><div className="space-y-4 p-5"><Field label="Nome da mesa" error={fieldError(fields, "name")}><Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} disabled={saving} placeholder="Ex.: Mesa 1" /></Field><Field label="Lugares" error={fieldError(fields, "seats")}><Input type="number" min="0" value={form.seats} onChange={(event) => setForm({ ...form, seats: event.target.value })} disabled={saving} /></Field>{error && <Alert message={error} />}<div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setModalOpen(false)}>Cancelar</Button><Button loading={saving} onClick={() => void save()}>{editing ? "Salvar" : "Criar"}</Button></div></div></Modal>
    <Modal open={batchOpen} title="Configurar e gerar mesas" onClose={() => setBatchOpen(false)}><div className="space-y-4 p-5"><p className="text-xs text-muted">Preview: {Math.max(0, Number(batchForm.end || 0) - Number(batchForm.start || 0) + 1)} mesas serão disponibilizadas. Mesas existentes ou históricas nunca são removidas.</p><Field label="Prefixo (opcional)" error={fieldError(fields, "prefix")}><Input value={batchForm.prefix} onChange={(event) => setBatchForm({ ...batchForm, prefix: event.target.value })} disabled={saving} placeholder="Ex.: Mesa " /></Field><div className="grid grid-cols-2 gap-4"><Field label="Número inicial" error={fieldError(fields, "start")}><Input type="number" min="1" value={batchForm.start} onChange={(event) => setBatchForm({ ...batchForm, start: event.target.value })} disabled={saving} /></Field><Field label="Número final" error={fieldError(fields, "end")}><Input type="number" min="1" value={batchForm.end} onChange={(event) => setBatchForm({ ...batchForm, end: event.target.value })} disabled={saving} /></Field></div><Field label="Lugares" error={fieldError(fields, "seats")}><Input type="number" min="0" value={batchForm.seats} onChange={(event) => setBatchForm({ ...batchForm, seats: event.target.value })} disabled={saving} /></Field>{error && <Alert message={error} />}<div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setBatchOpen(false)}>Cancelar</Button><Button loading={saving} onClick={() => void batchSave()}>Gerar/atualizar mesas</Button></div></div></Modal>
    <Modal open={!!deleting} title={`Excluir ${deleting?.name || "mesa"}?`} onClose={() => setDeleting(null)}><div className="space-y-4 p-5"><p className="text-sm text-muted">Ela deixará de aparecer no cadastro. O histórico de atendimentos e relatórios será preservado.</p><div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setDeleting(null)} disabled={saving}>Cancelar</Button><Button loading={saving} onClick={() => deleting && void deleteTable(deleting)}>Excluir mesa</Button></div></div></Modal>
  </>;
}

export default function TablesPageWrapper() {
  return <AdminGuard requiredPermissions={[permissions.viewTables]} requiredFeatures={["tables"]}><TablesPage /></AdminGuard>;
}
