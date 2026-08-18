"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { FileSearch, RefreshCw } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Field, Input, Modal, Pagination, Select, TableLoading } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { AuditLog, Branch, Paginated, User } from "@/types";

function initialPeriod(): PeriodValue {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return { start: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T00:00`, end: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T23:59` };
}

function jsonPreview(value: Record<string, unknown>) {
  const keys = Object.keys(value || {});
  if (!keys.length) return "-";
  return JSON.stringify(value, null, 0);
}

const actionLabels: Record<string, string> = { create: "Criou", update: "Alterou", activate: "Ativou", deactivate: "Inativou", cancel: "Cancelou", close: "Fechou", open: "Abriu", revoke: "Revogou", withdrawal: "Registrou sangria", grouped_entry: "Registrou entrada agrupada", regularize_negatives: "Regularizou estoque negativo" };
const fieldLabels: Record<string, string> = { name: "Nome", status: "Status", reason: "Motivo", is_active: "Ativo", allow_negative_stock: "Permitir estoque negativo", service_fee_rate: "Taxa de serviço", commission_rate: "Comissão", fixed_daily_cost: "Custo fixo diário", user_id: "Usuário", permission_id: "Permissão", permission_code: "Permissão", quantity: "Quantidade", final_quantity: "Saldo final", nature: "Natureza", address: "Endereço", address_pending: "Endereço pendente" };
function humanAction(value: string) { const parts = value.split("."); const verb = parts.at(-1) || value; const subject = parts.slice(0, -1).join(" ").replaceAll("_", " "); return `${actionLabels[verb] || verb.replaceAll("_", " ")} ${subject}`.trim(); }
function humanValue(value: unknown): string { if (value === null || value === undefined || value === "") return "Não informado"; if (value === true) return "Sim"; if (value === false) return "Não"; if (Array.isArray(value)) return value.map(humanValue).join(", "); if (typeof value === "object") return JSON.stringify(value); return String(value); }
function objectModule(value: string) { const parts = value.split("."); return (parts[0] === "apps" ? parts[1] : parts.at(-2))?.replaceAll("_", " ") || "sistema"; }
function objectHref(log: AuditLog) { const model = log.object_type.split(".").at(-1)?.toLowerCase(); if (model === "sale") return `/vendas/${log.object_id}`; if (model === "cashsession") return `/caixas/sessoes/${log.object_id}`; if (model === "branch") return "/filiais"; if (model === "user") return "/usuarios"; if (model === "accessprofile") return "/perfis"; return null; }

function AuditPageInner() {
  const { currentCompany, currentBranch } = useAuth();
  const contextRef = useRef(currentBranch?.id || 0);
  contextRef.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState(initialPeriod);
  const [search, setSearch] = useState("");
  const [branch, setBranch] = useState("");
  const [actor, setActor] = useState("");
  const [module, setModule] = useState("");
  const [action, setAction] = useState("");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [data, setData] = useState<Paginated<AuditLog> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<AuditLog | null>(null);

  function url(path?: string, selectedPeriod = period, selectedBranch = branch) {
    if (path) return path;
    const params = new URLSearchParams({ start_datetime: selectedPeriod.start, end_datetime: selectedPeriod.end });
    if (search.trim()) params.set("search", search.trim());
    if (selectedBranch) params.set("branch", selectedBranch);
    if (actor) params.set("actor", actor);
    if (module.trim()) params.set("object_type", module.trim());
    if (action.trim()) params.set("action", action.trim());
    return `audit-logs/?${params}`;
  }

  async function load(path?: string, token = contextRef.current, selectedPeriod = period, selectedBranch = branch) {
    if (!currentBranch) return;
    setLoading(true); setError("");
    try {
      const response = await http.get<Paginated<AuditLog>>(url(path, selectedPeriod, selectedBranch));
      if (contextRef.current === token) setData(response);
    } catch (caught) {
      if (contextRef.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar a auditoria.");
    } finally {
      if (contextRef.current === token) setLoading(false);
    }
  }

  useEffect(() => {
    const nextBranch = String(currentBranch?.id || "");
    setBranch(nextBranch); setActor(""); setModule(""); setAction("");
    void load(undefined, contextRef.current, period, nextBranch);
    if (currentCompany) void Promise.all([
      http.getAll<Branch>(`branches/?company=${currentCompany.id}`),
      http.getAll<User>(`users/?company=${currentCompany.id}`),
    ]).then(([branchItems, userItems]) => { setBranches(branchItems); setUsers(userItems); }).catch(() => { setBranches([]); setUsers([]); });
  }, [currentCompany?.id, currentBranch?.id]);

  return <>
    <PageHeader title="Auditoria" description="Consulta append-only das alterações críticas do sistema." action={<Button variant="secondary" onClick={() => void load()}><RefreshCw className="size-4" />Atualizar</Button>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      <section className="card p-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <PeriodFilter value={period} onApply={(value) => { setPeriod(value); void load(undefined, contextRef.current, value); }} />
          <Field label="Branch"><Select value={branch} onChange={(event) => setBranch(event.target.value)}><option value="">Todas autorizadas</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="Ator"><Select value={actor} onChange={(event) => setActor(event.target.value)}><option value="">Todos</option>{users.map((item) => <option key={item.id} value={item.id}>{item.first_name} {item.last_name}</option>)}</Select></Field>
          <Field label="Módulo"><Input value={module} onChange={(event) => setModule(event.target.value)} placeholder="Ex.: cash" /></Field>
          <Field label="Ação"><Input value={action} onChange={(event) => setAction(event.target.value)} placeholder="Ex.: close" /></Field>
          <Field label="Busca"><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Objeto ou ID" /></Field>
          <div className="flex items-end"><Button onClick={() => void load()}><FileSearch className="size-4" />Filtrar</Button></div>
        </div>
      </section>
      <section className="card overflow-hidden">
        <div className="card-header"><h2 className="text-sm font-bold">Logs</h2></div>
        {loading ? <TableLoading /> : data?.results.length ? <><div className="table-wrap"><table className="data-table"><thead><tr><th>Quando</th><th>Ação</th><th>Ator</th><th>Módulo / objeto</th><th>Resumo</th><th></th></tr></thead><tbody>{data.results.map((log) => <tr key={log.id}><td>{formatDate(log.created_at)}</td><td><strong className="capitalize">{humanAction(log.action)}</strong><span className="block text-[11px] text-slate-400">{log.branch_name || log.company_name || "Escopo global"}</span></td><td>{log.actor_name || "Sistema"}</td><td><strong className="block text-[11px] capitalize">{objectModule(log.object_type)}</strong><span className="text-[11px] capitalize">{log.object_type.split(".").at(-1)?.replaceAll("_", " ")} #{log.object_id}</span></td><td className="max-w-md truncate text-[11px]" title={jsonPreview(log.after)}>{Object.entries(log.after || {}).slice(0, 2).map(([key, value]) => `${fieldLabels[key] || key}: ${humanValue(value)}`).join(" · ") || "Sem alteração de campos"}</td><td><Button variant="secondary" onClick={() => setSelected(log)}>Detalhes</Button></td></tr>)}</tbody></table></div><Pagination count={data.count} next={data.next} previous={data.previous} onPage={(path) => void load(path)} /></> : <EmptyState title="Sem logs" description="Nenhuma alteração crítica encontrada para o período." />}
      </section>
    </div>
    <Modal open={!!selected} title="Detalhes da auditoria" description={selected ? `${humanAction(selected.action)} em ${formatDate(selected.created_at)}` : ""} onClose={() => setSelected(null)} size="xl">
      {selected && <div className="space-y-5 p-5"><div className="grid gap-3 rounded-lg bg-slate-50 p-4 text-xs sm:grid-cols-2"><p><strong className="block text-slate-500">Responsável</strong>{selected.actor_name || "Sistema"}</p><p><strong className="block text-slate-500">Escopo</strong>{selected.branch_name || selected.company_name || "Global"}</p><p><strong className="block text-slate-500">Objeto técnico</strong>{selected.object_type} #{selected.object_id}</p><p><strong className="block text-slate-500">Endereço IP</strong>{humanValue(selected.metadata?.ip_address)}</p><p className="break-all sm:col-span-2"><strong className="block text-slate-500">Dispositivo</strong>{humanValue(selected.metadata?.user_agent)}</p>{objectHref(selected) && <p className="sm:col-span-2"><Link className="font-bold text-primary" href={objectHref(selected)!}>Abrir objeto relacionado</Link></p>}</div><div className="table-wrap rounded-lg border border-slate-200"><table className="data-table"><thead><tr><th>Campo</th><th>De</th><th>Para</th></tr></thead><tbody>{Array.from(new Set([...Object.keys(selected.before || {}), ...Object.keys(selected.after || {})])).map((key) => <tr key={key}><td className="font-semibold">{fieldLabels[key] || key.replaceAll("_", " ")}</td><td>{humanValue(selected.before?.[key])}</td><td>{humanValue(selected.after?.[key])}</td></tr>)}</tbody></table></div></div>}
    </Modal>
  </>;
}

export default function AuditPage() {
  return <AdminGuard requiredPermissions={[permissions.viewAuditLog]}><AuditPageInner /></AdminGuard>;
}
