"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Banknote, ExternalLink, Pencil, Plus, Power, Search } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { CashStatus } from "@/components/cash-ui";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, EmptyState, Field, Input, Modal, Pagination, Select, StatusBadge, TableLoading } from "@/components/ui";
import { formatBRL, formatDate, fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { CashRegister, Paginated } from "@/types";

function Registers() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const canAdd = hasPermission(permissions.addCashRegister);
  const canChange = hasPermission(permissions.changeCashRegister);
  const canStatus = hasPermission(permissions.changeCashRegisterStatus);
  const canOpen = hasPermission(permissions.openCashRegister);
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [data, setData] = useState<Paginated<CashRegister> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CashRegister | null>(null);
  const [name, setName] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<CashRegister | null>(null);

  function query() {
    const params = new URLSearchParams();
    if (search.trim()) params.set("search", search.trim());
    if (status) params.set("status", status);
    return `cash-registers/?${params}`;
  }

  async function load(path?: string, context = contextRef.current) {
    if (!currentBranch) { setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const response = await http.get<Paginated<CashRegister>>(path || query());
      if (contextRef.current === context) setData(response);
    } catch (caught) {
      if (contextRef.current === context) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os caixas.");
    } finally { if (contextRef.current === context) setLoading(false); }
  }

  useEffect(() => {
    const context = contextRef.current;
    setSearch(""); setStatus(""); setData(null); setError(""); setSuccess(""); setModalOpen(false); setConfirming(null);
    void load("cash-registers/", context);
  }, [currentCompany?.id, currentBranch?.id]);

  function show(register?: CashRegister) {
    if (register ? !canChange : !canAdd) return;
    setEditing(register || null); setName(register?.name || ""); setFields({}); setError(""); setModalOpen(true);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!(editing ? canChange : canAdd) || !currentBranch) return;
    setSaving(true); setError(""); setFields({});
    try {
      if (editing) await http.patch(`cash-registers/${editing.id}/`, { name });
      else await http.post("cash-registers/", { branch: currentBranch.id, name });
      setModalOpen(false); setSuccess(editing ? "Caixa atualizado com sucesso." : "Caixa criado com sucesso."); await load();
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields); }
      else setError("Não foi possível salvar o caixa.");
    } finally { setSaving(false); }
  }

  async function changeStatus() {
    if (!confirming || !canStatus) return;
    const register = confirming;
    const action = register.status === "active" ? "deactivate" : "activate";
    setSaving(true); setError("");
    try {
      await http.post(`cash-registers/${register.id}/${action}/`);
      setConfirming(null); setSuccess(`Caixa ${action === "activate" ? "ativado" : "inativado"}.`); await load();
    } catch (caught) { setConfirming(null); setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar o status do caixa."); }
    finally { setSaving(false); }
  }

  const actions = (register: CashRegister) => <div className="flex flex-wrap items-center gap-1">
    {register.open_session && <Link className="btn btn-secondary h-9 px-3" href={`/caixas/sessoes/${register.open_session.id}`}><ExternalLink className="size-4" />Operar</Link>}
    {!register.open_session && register.status === "active" && canOpen && <Link className="btn btn-primary h-9 px-3" href={`/caixas/abrir?register=${register.id}`}><Banknote className="size-4" />Abrir</Link>}
    {canChange && <button className="icon-button" aria-label={`Editar ${register.name}`} onClick={() => show(register)}><Pencil className="size-4" /></button>}
    {canStatus && <button className="icon-button" aria-label={`${register.status === "active" ? "Inativar" : "Ativar"} ${register.name}`} onClick={() => setConfirming(register)}><Power className="size-4" /></button>}
  </div>;

  return <>
    <PageHeader title="Caixas" description={`Filial atual: ${currentBranch?.name || "nenhuma filial selecionada"}. Os dados abaixo pertencem somente a este contexto.`} action={canAdd ? <Button onClick={() => show()}><Plus className="size-4" />Novo caixa</Button> : undefined} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !modalOpen && <Alert message={error} />}{success && <Alert type="success" message={success} />}
      <form className="card grid gap-3 p-4 sm:grid-cols-[1fr_12rem_auto]" onSubmit={(event) => { event.preventDefault(); void load(); }}>
        <div className="relative"><Search className="absolute left-3 top-3 size-4 text-slate-400" /><Input className="pl-9" placeholder="Buscar caixa pelo nome" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <Select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Todos os status</option><option value="active">Ativos</option><option value="inactive">Inativos</option></Select>
        <Button type="submit">Filtrar</Button>
      </form>
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Caixas da filial</h2><p className="mt-1 text-[11px] text-slate-500">{currentBranch?.name || "Selecione uma filial"}</p></div><Banknote className="size-5 text-slate-300" /></div>
        {loading ? <TableLoading columns={5} /> : data?.results.length ? <>
          <div className="hidden md:block table-wrap"><table className="data-table"><thead><tr><th>Nome</th><th>Status</th><th>Sessão atual</th><th>Abertura</th><th className="text-right">Ações</th></tr></thead><tbody>{data.results.map((register) => <tr key={register.id}><td><strong>{register.name}</strong><span className="block text-[11px] text-slate-400">{register.branch_name}</span></td><td><StatusBadge active={register.status === "active"} /></td><td>{register.open_session ? <CashStatus status={register.open_session.status} /> : <span className="text-slate-400">Sem sessão aberta</span>}</td><td>{register.open_session ? <><span className="block font-semibold">{formatBRL(register.open_session.opening_amount)}</span><span className="text-[11px] text-slate-400">{formatDate(register.open_session.opened_at)} por {register.open_session.opened_by_name}</span></> : "-"}</td><td><div className="flex justify-end">{actions(register)}</div></td></tr>)}</tbody></table></div>
          <div className="divide-y divide-slate-100 md:hidden">{data.results.map((register) => <article key={register.id} className="space-y-3 p-5"><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-bold">{register.name}</h3><p className="mt-1 text-[11px] text-slate-400">{register.branch_name}</p></div><StatusBadge active={register.status === "active"} /></div>{register.open_session ? <div className="rounded-md bg-slate-50 p-3 text-xs"><div className="flex items-center justify-between"><CashStatus status="open" /><strong>{formatBRL(register.open_session.opening_amount)}</strong></div><p className="mt-2 text-[11px] text-slate-500">Aberta em {formatDate(register.open_session.opened_at)} por {register.open_session.opened_by_name}</p></div> : <p className="text-xs text-slate-400">Sem sessão aberta</p>} {actions(register)}</article>)}</div>
          <Pagination count={data.count} next={data.next} previous={data.previous} onPage={load} />
        </> : <EmptyState title="Nenhum caixa encontrado" description="Cadastre um caixa nesta filial ou ajuste os filtros da busca." />}
      </section>
    </div>
    <Modal open={modalOpen} title={editing ? "Editar caixa" : "Novo caixa"} description={`Configuração vinculada à filial ${currentBranch?.name || "atual"}.`} onClose={() => !saving && setModalOpen(false)} size="md"><form onSubmit={submit}><div className="space-y-4 p-5 sm:p-6">{error && <Alert message={error} />}<Field label="Nome do caixa" error={fieldError(fields, "name")}><Input autoFocus required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex.: Caixa principal" /></Field>{fieldError(fields, "branch") && <p className="field-error">{fieldError(fields, "branch")}</p>}</div><div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4"><Button type="button" variant="secondary" disabled={saving} onClick={() => setModalOpen(false)}>Cancelar</Button><Button type="submit" loading={saving}>Salvar</Button></div></form></Modal>
    <ConfirmDialog open={!!confirming} title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} caixa`} message={`Confirma a alteração de status de “${confirming?.name || ""}”? Um caixa com sessão aberta não pode ser inativado.`} confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"} danger={confirming?.status === "active"} loading={saving} onClose={() => setConfirming(null)} onConfirm={changeStatus} />
  </>;
}

export default function RegistersPage() { return <AdminGuard requiredPermissions={[permissions.viewCashRegister]} requiredFeatures={["cash_register"]}><Registers /></AdminGuard>; }
