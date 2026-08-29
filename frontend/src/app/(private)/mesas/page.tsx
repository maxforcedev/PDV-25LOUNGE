"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Clock3, CreditCard, Layers, Pencil, Plus, Power, Search, Users } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { CustomerQuickPicker } from "@/components/customer-quick-picker";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Modal, Spinner, TableLoading } from "@/components/ui";
import { fieldError, formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { BranchSettings, Customer, Table } from "@/types";

function openedFor(value: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

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
  const [commandCustomer, setCommandCustomer] = useState<Customer | null>(null);
  const [editing, setEditing] = useState<Table | null>(null);
  const [form, setForm] = useState({ name: "", seats: "0" });
  const [batchForm, setBatchForm] = useState({ prefix: "", start: "1", end: "20", seats: "0" });
  const [filter, setFilter] = useState<"all" | "free" | "occupied" | "partial">("all");
  const [search, setSearch] = useState("");
  const [, setClock] = useState(0);
  const [settings, setSettings] = useState<BranchSettings | null>(null);
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
  useEffect(() => { setTables([]); void loadRef.current(String(currentBranch?.id || "")); if (currentBranch) void http.get<BranchSettings>(`branches/${currentBranch.id}/settings/`).then(setSettings).catch(() => setSettings(null)); }, [currentBranch?.id]);
  useEffect(() => {
    const interval = window.setInterval(() => setClock((value) => value + 1), 60000);
    return () => window.clearInterval(interval);
  }, []);

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
        customer: commandCustomer?.id || null,
      });
      setCommandTable(null); setCommandIdentifier(""); setCommandCustomer(null);
      await load(String(currentBranch?.id || ""));
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível abrir a comanda.");
    } finally { setSaving(false); }
  }

  if (!currentBranch) return <div className="p-6"><Alert message="Selecione uma filial." /></div>;
  const visibleTables = tables.filter((table) => {
    const commands = table.open_commands || [];
    const partial = commands.some((command) => Number(command.paid_total) > 0 && Number(command.paid_total) < Number(command.confirmed_total));
    if (filter === "free" && table.operational_status !== "free") return false;
    if (filter === "occupied" && table.operational_status !== "occupied") return false;
    if (filter === "partial" && !partial) return false;
    const term = search.trim().toLowerCase();
    return !term || table.name.toLowerCase().includes(term) || commands.some((command) => `${command.identifier} ${command.command_number} ${command.opened_by_name}`.toLowerCase().includes(term));
  });

  return (
    <>
      <PageHeader title="Mesas" description="Acompanhe ocupação e abra Comandas rapidamente." action={canChange ? (
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => { setBatchForm({ prefix: settings?.default_table_prefix || "", start: String(settings?.table_range_start || 1), end: String(settings?.table_range_end || settings?.default_table_quantity || 20), seats: String(settings?.default_table_seats || 0) }); setBatchOpen(true); }}><Layers className="size-4" />Configurar intervalo</Button>
          <Button onClick={openCreate}><Plus className="size-4" />Nova mesa</Button>
        </div>
      ) : undefined} />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        <section className="flex flex-col gap-3 rounded-lg border border-subtle bg-surface p-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">{(["all", "free", "occupied", "partial"] as const).map((value) => <Button key={value} variant={filter === value ? "primary" : "secondary"} className="min-h-10" onClick={() => setFilter(value)}>{({ all: "Todas", free: "Livres", occupied: "Ocupadas", partial: "Pagamento parcial" })[value]}</Button>)}</div>
          <div className="relative w-full lg:max-w-md"><Search className="absolute left-3 top-3 size-4 text-muted" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Mesa, responsável ou atendente" /></div>
        </section>
        {loading ? <TableLoading /> : visibleTables.length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {visibleTables.map((table) => {
              const occupied = table.operational_status === "occupied";
              const partial = table.open_commands?.some((command) => Number(command.paid_total) > 0 && Number(command.paid_total) < Number(command.confirmed_total));
              return <section key={table.id} className={`card min-h-60 p-5 ${occupied ? "border-primary/40 bg-primary/5" : "border-success/30"}`}>
                <div className="flex items-start justify-between gap-3"><div><h2 className="text-2xl font-black tracking-tight">{table.name}</h2><p className={`mt-1 text-xs font-bold ${occupied ? "text-primary" : "text-success"}`}>{occupied ? "OCUPADA" : "LIVRE"}{partial ? " · PAGAMENTO PARCIAL" : ""}</p></div><div className="flex gap-1">{canChange && <><button className="icon-button" title="Editar mesa" onClick={() => openEdit(table)}><Pencil className="size-4" /></button><button className="icon-button" title={table.status === "active" ? "Inativar" : "Ativar"} onClick={() => void toggleStatus(table)}><Power className="size-4" /></button></>}</div></div>
                <div className="mt-6 flex items-end justify-between"><div><span className="block text-xs text-muted">Total atual</span><strong className="text-xl">{occupied ? formatBRL(table.open_commands_total || "0") : formatBRL("0")}</strong></div><span className="inline-flex items-center gap-1 text-xs text-muted"><Users className="size-3" />{table.seats ? `${table.seats} lugares` : "Sem capacidade"}</span></div>
                {table.open_commands?.length ? <div className="mt-4 space-y-2 border-t border-subtle pt-3">{table.open_commands.map((command) => <Link key={command.id} href={`/comandas/${command.id}`} className="block rounded-md bg-surface-muted p-2 text-sm hover:bg-primary/10"><div className="flex justify-between gap-2 font-bold"><span>{command.identifier || command.command_number}</span><span>{formatBRL(command.confirmed_total)}</span></div><div className="mt-1 flex justify-between text-[11px] text-muted"><span>{command.opened_by_name || "Atendente não informado"}</span><span className="inline-flex items-center gap-1"><Clock3 className="size-3" />{openedFor(command.opened_at)}</span></div>{Number(command.paid_total) > 0 && <div className="mt-1 flex items-center gap-1 text-[11px] text-warning-strong"><CreditCard className="size-3" />Pago {formatBRL(command.paid_total)}</div>}</Link>)}</div> : null}
                {canChange && table.status === "active" ? <Button className="mt-4 w-full min-h-11" variant={occupied ? "secondary" : "primary"} onClick={() => { setCommandTable(table); setCommandIdentifier(""); setCommandCustomer(null); setFields({}); }}><Users className="size-4" />{occupied ? "Adicionar comanda" : "Abrir mesa"}</Button> : null}
              </section>;
            })}
          </div>
        ) : <Alert message={tables.length ? "Nenhuma mesa corresponde aos filtros." : "Nenhuma mesa cadastrada nesta filial."} />}
      </div>
      <Modal open={modalOpen} title={editing ? "Editar mesa" : "Nova mesa"} onClose={() => setModalOpen(false)}>
        <div className="space-y-4 p-5">
          <Field label="Nome da mesa" error={fieldError(fields, "name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} disabled={saving} placeholder="Ex.: Mesa 1" /></Field>
          <Field label="Lugares" error={fieldError(fields, "seats")}><Input type="number" min="0" value={form.seats} onChange={(e) => setForm({ ...form, seats: e.target.value })} disabled={saving} /></Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setModalOpen(false)}>Cancelar</Button><Button loading={saving} onClick={() => void save()}>{editing ? "Salvar" : "Criar"}</Button></div>
        </div>
      </Modal>
      <Modal open={batchOpen} title="Configurar e gerar mesas" onClose={() => setBatchOpen(false)}>
        <div className="space-y-4 p-5">
          <p className="text-xs text-muted">Preview: {Math.max(0, Number(batchForm.end || 0) - Number(batchForm.start || 0) + 1)} mesas serão disponibilizadas. Mesas existentes ou históricas nunca são removidas.</p>
          <Field label="Prefixo (opcional)" error={fieldError(fields, "prefix")}><Input value={batchForm.prefix} onChange={(e) => setBatchForm({ ...batchForm, prefix: e.target.value })} disabled={saving} placeholder="Ex.: Mesa " /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Número inicial" error={fieldError(fields, "start")}><Input type="number" min="1" value={batchForm.start} onChange={(e) => setBatchForm({ ...batchForm, start: e.target.value })} disabled={saving} /></Field>
            <Field label="Número final" error={fieldError(fields, "end")}><Input type="number" min="1" value={batchForm.end} onChange={(e) => setBatchForm({ ...batchForm, end: e.target.value })} disabled={saving} /></Field>
          </div>
          <Field label="Lugares" error={fieldError(fields, "seats")}><Input type="number" min="0" value={batchForm.seats} onChange={(e) => setBatchForm({ ...batchForm, seats: e.target.value })} disabled={saving} /></Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setBatchOpen(false)}>Cancelar</Button><Button loading={saving} onClick={() => void batchSave()}>Gerar/atualizar mesas</Button></div>
        </div>
      </Modal>
      <Modal open={!!commandTable} title={`Nova comanda · ${commandTable?.name || ""}`} onClose={() => setCommandTable(null)}>
        <div className="space-y-4 p-5"><p className="text-sm text-muted">Informe somente o necessário para iniciar o atendimento.</p><Field label="Responsável" optional error={fieldError(fields, "identifier")}><Input value={commandIdentifier} onChange={(event) => setCommandIdentifier(event.target.value)} disabled={saving} placeholder="Ex.: João" /></Field><CustomerQuickPicker value={commandCustomer} onChange={setCommandCustomer} disabled={saving} />{error && <Alert message={error} />}<div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setCommandTable(null)}>Cancelar</Button><Button loading={saving} onClick={() => void openCommand()}>Abrir operação</Button></div></div>
      </Modal>
    </>
  );
}

export default function TablesPageWrapper() {
  return <AdminGuard requiredPermissions={[permissions.viewCommands]} requiredFeatures={["tables"]}><TablesPage /></AdminGuard>;
}
