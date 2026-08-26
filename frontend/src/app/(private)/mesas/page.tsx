"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Plus, Pencil, Power, Layers, Users } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Modal, Spinner, TableLoading } from "@/components/ui";
import { fieldError, formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Table } from "@/types";

function TablesPage() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canChange = hasPermission(permissions.openCommand) && !readOnly;
  const [tables, setTables] = useState<Table[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [commandTable, setCommandTable] = useState<Table | null>(null);
  const [commandIdentifier, setCommandIdentifier] = useState("");
  const [editing, setEditing] = useState<Table | null>(null);
  const [form, setForm] = useState({ name: "", seats: "0" });
  const [batchForm, setBatchForm] = useState({ prefix: "", start: "1", end: "20", seats: "0" });
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(token: string) {
    if (!currentBranch) { setTables([]); setLoading(false); return; }
    setLoading(true);
    setError("");
    try {
      const response = await http.get<Table[]>(`tables/operational/?branch=${currentBranch.id}`);
      if (context.current === token) setTables(response);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as mesas.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => { setTables([]); void loadRef.current(String(currentBranch?.id || "")); }, [currentBranch?.id]);

  function openCreate() { setEditing(null); setForm({ name: "", seats: "0" }); setFields({}); setModalOpen(true); }
  function openEdit(table: Table) { setEditing(table); setForm({ name: table.name, seats: String(table.seats) }); setFields({}); setModalOpen(true); }

  async function save() {
    if (!currentBranch) return;
    setSaving(true); setError(""); setFields({});
    const payload = { branch: currentBranch.id, name: form.name.trim(), seats: Number(form.seats) || 0 };
    try {
      if (editing) { await http.patch(`tables/${editing.id}/`, payload); }
      else { await http.post("tables/", payload); }
      setModalOpen(false);
      await load(String(currentBranch.id));
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível salvar a mesa.");
    } finally { setSaving(false); }
  }

  async function batchSave() {
    if (!currentBranch) return;
    setSaving(true); setError(""); setFields({});
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
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível criar as mesas em lote.");
    } finally { setSaving(false); }
  }

  async function toggleStatus(table: Table) {
    if (!canChange || !currentBranch) return;
    const action = table.status === "active" ? "deactivate" : "activate";
    try { await http.post(`tables/${table.id}/${action}/`, {}); await load(String(currentBranch.id)); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar o status."); }
  }

  async function openCommand() {
    if (!commandTable) return;
    setSaving(true); setError(""); setFields({});
    try {
      await http.post("commands/open/", {
        table: commandTable.id,
        identifier: commandIdentifier.trim(),
      });
      setCommandTable(null); setCommandIdentifier("");
      await load(String(currentBranch?.id || ""));
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível abrir a comanda.");
    } finally { setSaving(false); }
  }

  if (!currentBranch) return <div className="p-6"><Alert message="Selecione uma filial." /></div>;

  return (
    <>
      <PageHeader title="Mesas" description="Acompanhe ocupação e abra Comandas rapidamente." action={canChange ? (
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setBatchOpen(true)}><Layers className="size-4" />Gerar lote</Button>
          <Button onClick={openCreate}><Plus className="size-4" />Nova mesa</Button>
        </div>
      ) : undefined} />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {loading ? <TableLoading /> : tables.length ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {tables.map((table) => {
              const occupied = table.operational_status === "occupied";
              return <section key={table.id} className={`card p-4 ${occupied ? "border-primary/40" : ""}`}>
                <div className="flex items-start justify-between gap-3"><div><h2 className="font-bold">{table.name}</h2><p className={`mt-1 text-xs font-semibold ${occupied ? "text-primary" : "text-muted"}`}>{occupied ? "OCUPADA" : "LIVRE"} · {table.open_commands_count || 0} comandas</p></div><div className="flex gap-1">{canChange && <><button className="icon-button" title="Editar mesa" onClick={() => openEdit(table)}><Pencil className="size-4" /></button><button className="icon-button" title={table.status === "active" ? "Inativar" : "Ativar"} onClick={() => void toggleStatus(table)}><Power className="size-4" /></button></>}</div></div>
                <div className="mt-4 flex items-end justify-between"><div><span className="block text-xs text-muted">Total confirmado</span><strong>{occupied ? formatBRL(table.open_commands_total || "0") : "-"}</strong></div><span className="text-xs text-muted">{table.seats ? `${table.seats} lugares` : "Sem capacidade"}</span></div>
                {table.open_commands?.length ? <div className="mt-4 space-y-2 border-t border-subtle pt-3">{table.open_commands.map((command) => <Link key={command.id} href={`/comandas/${command.id}`} className="flex items-center justify-between text-sm text-primary hover:underline"><span>{command.identifier || command.command_number}</span><span>{formatBRL(command.confirmed_total)}</span></Link>)}</div> : null}
                {canChange && table.status === "active" ? <Button className="mt-4 w-full" variant={occupied ? "secondary" : "primary"} onClick={() => { setCommandTable(table); setCommandIdentifier(""); setFields({}); }}><Users className="size-4" />Nova comanda</Button> : null}
              </section>;
            })}
          </div>
        ) : <Alert message="Nenhuma mesa cadastrada nesta filial." />}
      </div>
      <Modal open={modalOpen} title={editing ? "Editar mesa" : "Nova mesa"} onClose={() => setModalOpen(false)}>
        <div className="space-y-4 p-5">
          <Field label="Nome da mesa" error={fieldError(fields, "name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} disabled={saving} placeholder="Ex.: Mesa 1" /></Field>
          <Field label="Lugares" error={fieldError(fields, "seats")}><Input type="number" min="0" value={form.seats} onChange={(e) => setForm({ ...form, seats: e.target.value })} disabled={saving} /></Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setModalOpen(false)}>Cancelar</Button><Button loading={saving} onClick={() => void save()}>{editing ? "Salvar" : "Criar"}</Button></div>
        </div>
      </Modal>
      <Modal open={batchOpen} title="Gerar mesas em lote" onClose={() => setBatchOpen(false)}>
        <div className="space-y-4 p-5">
          <p className="text-xs text-muted">Gera múltiplas mesas numeradas de uma vez. Cada mesa é uma entidade própria.</p>
          <Field label="Prefixo (opcional)" error={fieldError(fields, "prefix")}><Input value={batchForm.prefix} onChange={(e) => setBatchForm({ ...batchForm, prefix: e.target.value })} disabled={saving} placeholder="Ex.: Mesa " /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Número inicial" error={fieldError(fields, "start")}><Input type="number" min="1" value={batchForm.start} onChange={(e) => setBatchForm({ ...batchForm, start: e.target.value })} disabled={saving} /></Field>
            <Field label="Número final" error={fieldError(fields, "end")}><Input type="number" min="1" value={batchForm.end} onChange={(e) => setBatchForm({ ...batchForm, end: e.target.value })} disabled={saving} /></Field>
          </div>
          <Field label="Lugares" error={fieldError(fields, "seats")}><Input type="number" min="0" value={batchForm.seats} onChange={(e) => setBatchForm({ ...batchForm, seats: e.target.value })} disabled={saving} /></Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setBatchOpen(false)}>Cancelar</Button><Button loading={saving} onClick={() => void batchSave()}>Gerar mesas</Button></div>
        </div>
      </Modal>
      <Modal open={!!commandTable} title={`Nova comanda · ${commandTable?.name || ""}`} onClose={() => setCommandTable(null)}>
        <div className="space-y-4 p-5"><p className="text-sm text-muted">Esta mesa pode manter várias Comandas abertas ao mesmo tempo.</p><Field label="Identificação da comanda" error={fieldError(fields, "identifier")}><Input value={commandIdentifier} onChange={(event) => setCommandIdentifier(event.target.value)} disabled={saving} placeholder="Ex.: Junior" /></Field>{error && <Alert message={error} />}<div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setCommandTable(null)}>Cancelar</Button><Button loading={saving} onClick={() => void openCommand()}>Abrir comanda</Button></div></div>
      </Modal>
    </>
  );
}

export default function TablesPageWrapper() {
  return <AdminGuard requiredPermissions={[permissions.viewCommands]} requiredFeatures={["tables"]}><TablesPage /></AdminGuard>;
}
