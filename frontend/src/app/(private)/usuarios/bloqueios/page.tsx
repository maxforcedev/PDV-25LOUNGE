"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Search, ShieldX } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Input, Select, TableLoading, Textarea } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { PermissionBlockOptions, UserPermissionBlock } from "@/types";

const moduleLabels: Record<string, string> = {
  accounts: "Usuários e acessos",
  companies: "Empresas e filiais",
  products: "Produtos",
  inventory: "Estoque",
  cash_registers: "Caixa",
  sales: "Vendas e consumações",
  payment_methods: "Formas de pagamento",
  promotions: "Promoções",
  reports: "Dashboard e relatórios",
  audit_logs: "Auditoria",
  commissions: "Comissões",
};

const emptyOptions: PermissionBlockOptions = { users: [], branches: [], permissions: [] };

function PermissionBlocks() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const [options, setOptions] = useState<PermissionBlockOptions>(emptyOptions);
  const [blocks, setBlocks] = useState<UserPermissionBlock[]>([]);
  const [userId, setUserId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [selectedBlockIds, setSelectedBlockIds] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const canChange = hasPermission(permissions.changePermissionBlock);

  async function loadBlocks() {
    if (!currentCompany) return;
    const next = await http.getAll<UserPermissionBlock>(
      `user-permission-blocks/?company=${currentCompany.id}&active=true`,
    );
    setBlocks(next);
    setSelectedBlockIds(new Set());
  }

  async function loadOptions(nextUser = userId, nextBranch = branchId) {
    if (!currentCompany || !canChange) return;
    setLoadingCandidates(true);
    try {
      const params = new URLSearchParams({ company: String(currentCompany.id) });
      if (nextUser) params.set("user", nextUser);
      if (nextBranch) params.set("branch", nextBranch);
      setOptions(await http.get<PermissionBlockOptions>(`user-permission-blocks/options/?${params}`));
    } finally {
      setLoadingCandidates(false);
    }
  }

  useEffect(() => {
    setUserId("");
    setBranchId("");
    setSelectedCodes(new Set());
    setSearch("");
    setReason("");
    setOptions(emptyOptions);
    if (!currentCompany) return;
    setLoading(true);
    setError("");
    Promise.all([loadBlocks(), canChange ? loadOptions("", "") : Promise.resolve()])
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os bloqueios individuais."))
      .finally(() => setLoading(false));
  }, [currentCompany?.id, canChange]);

  const visiblePermissions = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    if (!term) return options.permissions;
    return options.permissions.filter((item) =>
      `${item.label} ${item.code} ${moduleLabels[item.module] || item.module}`.toLocaleLowerCase("pt-BR").includes(term),
    );
  }, [options.permissions, search]);
  const grouped = useMemo(() => Object.entries(
    visiblePermissions.reduce<Record<string, typeof visiblePermissions>>((result, item) => {
      (result[item.module] ||= []).push(item);
      return result;
    }, {}),
  ), [visiblePermissions]);
  const visibleCodes = visiblePermissions.map((item) => item.code);
  const allVisibleSelected = visibleCodes.length > 0 && visibleCodes.every((code) => selectedCodes.has(code));

  function changeUser(next: string) {
    setUserId(next);
    setBranchId("");
    setSelectedCodes(new Set());
    setSearch("");
    setError("");
    void loadOptions(next, "").catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as permissões herdadas."));
  }

  function changeScope(next: string) {
    setBranchId(next);
    setSelectedCodes(new Set());
    setSearch("");
    setError("");
    void loadOptions(userId, next).catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as permissões herdadas."));
  }

  function toggleCode(code: string) {
    setSelectedCodes((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function toggleVisible() {
    setSelectedCodes((current) => {
      const next = new Set(current);
      visibleCodes.forEach((code) => allVisibleSelected ? next.delete(code) : next.add(code));
      return next;
    });
  }

  async function applyBlocks(event: React.FormEvent) {
    event.preventDefault();
    if (!currentCompany || !userId || !selectedCodes.size) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await http.post("user-permission-blocks/batch-apply/", {
        company: currentCompany.id,
        branch: branchId ? Number(branchId) : null,
        user: Number(userId),
        permission_codes: [...selectedCodes],
        reason,
      });
      const count = selectedCodes.size;
      setSelectedCodes(new Set());
      setReason("");
      await Promise.all([loadBlocks(), loadOptions(userId, branchId)]);
      setSuccess(`${count} ${count === 1 ? "bloqueio aplicado" : "bloqueios aplicados"} na mesma operação.`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível aplicar os bloqueios.");
    } finally {
      setSaving(false);
    }
  }

  async function revokeSelected() {
    if (!selectedBlockIds.size) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const count = selectedBlockIds.size;
      await http.post("user-permission-blocks/batch-revoke/", { block_ids: [...selectedBlockIds] });
      await loadBlocks();
      if (userId) await loadOptions(userId, branchId);
      setSuccess(`${count} ${count === 1 ? "bloqueio revogado" : "bloqueios revogados"} na mesma operação.`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível revogar os bloqueios.");
    } finally {
      setSaving(false);
    }
  }

  function toggleBlock(id: number) {
    setSelectedBlockIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return <>
    <PageHeader title="Bloqueios individuais" description="Retire várias permissões herdadas sem alterar o perfil-base." action={<Link href="/usuarios" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar aos usuários</Link>} />
    <div className="space-y-5 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      {success && <Alert type="success" message={success} />}
      {canChange && <form className="card overflow-hidden" onSubmit={applyBlocks}>
        <div className="card-header"><div><h2 className="text-sm font-bold">Aplicar bloqueios</h2><p className="mt-1 text-[11px] text-slate-500">Escolha o usuário e o escopo antes de selecionar as capacidades.</p></div><ShieldX className="size-5 text-primary" /></div>
        <div className="grid gap-4 p-5 lg:grid-cols-2">
          <Field label="1. Usuário"><Select required value={userId} onChange={(event) => changeUser(event.target.value)} disabled={loading || saving}><option value="">Selecione um usuário</option>{options.users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="2. Escopo"><Select value={branchId} onChange={(event) => changeScope(event.target.value)} disabled={!userId || loadingCandidates || saving}><option value="">Toda a empresa</option>{options.branches.map((item) => <option key={item.id} value={item.id}>{item.name}{item.id === currentBranch?.id ? " (atual)" : ""}</option>)}</Select></Field>
        </div>
        <div className="border-t border-slate-100 p-5">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <Field label="3. Permissões herdadas"><div className="relative sm:w-96"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por nome, código ou módulo" disabled={!userId || loadingCandidates} /></div></Field>
            <Button type="button" variant="secondary" onClick={toggleVisible} disabled={!visibleCodes.length || loadingCandidates}>{allVisibleSelected ? "Desmarcar visíveis" : "Selecionar visíveis"}</Button>
          </div>
          {loadingCandidates ? <TableLoading columns={3} /> : !userId ? <EmptyState title="Selecione um usuário" description="As permissões bloqueáveis serão calculadas para o escopo escolhido." /> : grouped.length ? <div className="grid gap-4 xl:grid-cols-2">{grouped.map(([module, items]) => <fieldset key={module} className="rounded-lg border border-slate-200 p-4"><legend className="px-1 text-xs font-bold text-dark">{moduleLabels[module] || module}</legend><div className="mt-1 space-y-1">{items.map((item) => <label key={item.code} className="flex cursor-pointer items-start gap-3 rounded-md px-2 py-2.5 transition hover:bg-slate-50"><input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={selectedCodes.has(item.code)} onChange={() => toggleCode(item.code)} /><span><strong className="block text-xs">{item.label}</strong><small className="mt-0.5 block text-[10px] text-slate-500">{item.code}</small></span></label>)}</div></fieldset>)}</div> : <EmptyState title="Nenhuma permissão bloqueável" description={search ? "Nenhuma permissão corresponde à busca." : "O usuário não possui permissões herdadas ativas neste escopo."} />}
        </div>
        <div className="grid gap-4 border-t border-slate-100 p-5 lg:grid-cols-[1fr_auto] lg:items-end"><Field label="4. Justificativa"><Textarea required rows={2} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explique por que estas permissões serão retiradas" /></Field><Button type="submit" loading={saving} disabled={!userId || !selectedCodes.size}><ShieldX className="size-4" />Aplicar {selectedCodes.size || ""} {selectedCodes.size === 1 ? "bloqueio" : "bloqueios"}</Button></div>
      </form>}
      <section className="card overflow-hidden">
        <div className="card-header"><div><h2 className="text-sm font-bold">Bloqueios ativos</h2><p className="mt-1 text-[11px] text-slate-500">A regra mais restritiva prevalece somente no escopo indicado.</p></div>{canChange && <Button variant="danger" disabled={!selectedBlockIds.size} loading={saving} onClick={() => void revokeSelected()}>Revogar selecionados ({selectedBlockIds.size})</Button>}</div>
        {loading ? <TableLoading columns={7} /> : blocks.length ? <div className="table-wrap"><table className="data-table"><thead><tr>{canChange && <th><input type="checkbox" className="size-4 accent-primary" aria-label="Selecionar todos os bloqueios" checked={selectedBlockIds.size === blocks.length} onChange={() => setSelectedBlockIds(selectedBlockIds.size === blocks.length ? new Set() : new Set(blocks.map((block) => block.id)))} /></th>}<th>Usuário</th><th>Permissão</th><th>Escopo</th><th>Justificativa</th><th>Aplicado por</th><th>Desde</th></tr></thead><tbody>{blocks.map((block) => <tr key={block.id}>{canChange && <td><input type="checkbox" className="size-4 accent-primary" aria-label={`Selecionar bloqueio de ${block.permission_label}`} checked={selectedBlockIds.has(block.id)} onChange={() => toggleBlock(block.id)} /></td>}<td><strong>{block.user_name}</strong></td><td><span className="block font-semibold">{block.permission_label}</span><small className="text-slate-400">{block.permission_code}</small></td><td><span className="block font-semibold">{block.branch_name || "Toda a empresa"}</span><small className="text-slate-400">{block.company_name}</small></td><td>{block.reason || "Sem justificativa"}</td><td>{block.created_by_name || "Sistema"}</td><td>{formatDate(block.created_at)}</td></tr>)}</tbody></table></div> : <EmptyState title="Nenhum bloqueio ativo" description="Todos os usuários seguem integralmente seus perfis de acesso." />}
      </section>
    </div>
  </>;
}

export default function PermissionBlocksPage() {
  return <AdminGuard requiredPermissions={[permissions.viewPermissionBlock]}><PermissionBlocks /></AdminGuard>;
}
