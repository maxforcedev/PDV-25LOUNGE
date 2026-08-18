"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ShieldX } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Select, TableLoading, Textarea } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Branch, FunctionalPermission, User, UserPermissionBlock } from "@/types";

export default function PermissionBlocksPage() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [catalog, setCatalog] = useState<FunctionalPermission[]>([]);
  const [blocks, setBlocks] = useState<UserPermissionBlock[]>([]);
  const [userId, setUserId] = useState("");
  const [permissionCode, setPermissionCode] = useState("");
  const [branchId, setBranchId] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const canChange = hasPermission(permissions.changePermissionBlock);

  async function load() {
    if (!currentCompany) return;
    setLoading(true); setError("");
    try {
      const [nextUsers, nextBranches, nextCatalog, nextBlocks] = await Promise.all([
        http.getAll<User>(`users/?company=${currentCompany.id}`),
        http.getAll<Branch>(`branches/?company=${currentCompany.id}`),
        http.getAll<FunctionalPermission>(`functional-permissions/?company=${currentCompany.id}`),
        http.getAll<UserPermissionBlock>(`user-permission-blocks/?company=${currentCompany.id}&active=true`),
      ]);
      setUsers(nextUsers.filter((item) => item.can_login && !item.is_superuser));
      setBranches(nextBranches);
      setCatalog(nextCatalog);
      setBlocks(nextBlocks);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os bloqueios individuais."); }
    finally { setLoading(false); }
  }
  useEffect(() => { setUserId(""); setPermissionCode(""); setBranchId(""); void load(); }, [currentCompany?.id]);
  const selectedUser = users.find((item) => String(item.id) === userId);
  const inheritedCodes = useMemo(() => {
    if (!selectedUser || !currentCompany) return new Set<string>();
    const companyCodes = selectedUser.companies.find((item) => item.id === currentCompany.id)?.permissions || [];
    const branchCodes = selectedUser.branches.filter((item) => item.company_id === currentCompany.id && (!branchId || String(item.id) === branchId)).flatMap((item) => item.permissions);
    return new Set([...companyCodes, ...branchCodes]);
  }, [selectedUser, currentCompany?.id, branchId]);
  const grouped = useMemo(() => Object.entries(catalog.filter((item) => inheritedCodes.has(item.code)).reduce<Record<string, FunctionalPermission[]>>((groups, item) => {
    (groups[item.module] ||= []).push(item);
    return groups;
  }, {})), [catalog, inheritedCodes]);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!currentCompany) return;
    setSaving(true); setError(""); setSuccess("");
    try {
      await http.post("user-permission-blocks/", { company: currentCompany.id, branch: branchId ? Number(branchId) : null, user: Number(userId), permission_code: permissionCode, reason });
      setSuccess("Permissão bloqueada para o usuário no escopo selecionado.");
      setPermissionCode(""); setReason(""); await load();
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível criar o bloqueio."); }
    finally { setSaving(false); }
  }
  async function revoke(block: UserPermissionBlock) {
    setSaving(true); setError(""); setSuccess("");
    try { await http.post(`user-permission-blocks/${block.id}/revoke/`); setSuccess("Bloqueio revogado; a permissão herdada volta a valer."); await load(); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível revogar o bloqueio."); }
    finally { setSaving(false); }
  }
  if (!hasPermission(permissions.viewPermissionBlock)) return <div className="p-6"><Alert message="Seu usuário não possui permissão para visualizar bloqueios individuais." /></div>;
  return <>
    <PageHeader title="Bloqueios individuais" description="Retire permissões herdadas do perfil sem criar perfis paralelos." action={<Link href="/usuarios" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar aos usuários</Link>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}{success && <Alert type="success" message={success} />}
      {canChange && <form className="card grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4" onSubmit={create}>
        <Field label="Usuário"><Select required value={userId} onChange={(event) => { setUserId(event.target.value); setPermissionCode(""); }}><option value="">Selecione</option>{users.map((item) => <option key={item.id} value={item.id}>{item.first_name} {item.last_name}</option>)}</Select></Field>
        <Field label="Permissão herdada"><Select required value={permissionCode} onChange={(event) => setPermissionCode(event.target.value)}><option value="">{userId ? "Selecione entre as permissões herdadas" : "Selecione primeiro o usuário"}</option>{grouped.map(([module, items]) => <optgroup key={module} label={module}>{items.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}</optgroup>)}</Select></Field>
        <Field label="Escopo"><Select value={branchId} onChange={(event) => { setBranchId(event.target.value); setPermissionCode(""); }}><option value="">Toda a empresa</option>{branches.map((item) => <option key={item.id} value={item.id}>{item.name}{item.id === currentBranch?.id ? " (atual)" : ""}</option>)}</Select></Field>
        <Field label="Justificativa"><Textarea required rows={1} value={reason} onChange={(event) => setReason(event.target.value)} /></Field>
        <div className="flex items-center justify-between gap-4 sm:col-span-2 xl:col-span-4"><p className="text-[11px] text-slate-500">{selectedUser ? `${inheritedCodes.size} permissões herdadas ainda ativas neste escopo.` : "O bloqueio só pode retirar uma permissão concedida pelo perfil."}</p><Button type="submit" loading={saving}><ShieldX className="size-4" />Aplicar bloqueio</Button></div>
      </form>}
      <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Bloqueios ativos</h2><p className="mt-1 text-[11px] text-slate-500">A regra mais restritiva prevalece sobre o perfil.</p></div><ShieldX className="size-5 text-slate-300" /></div>{loading ? <TableLoading /> : blocks.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Usuário</th><th>Permissão</th><th>Escopo</th><th>Justificativa</th><th>Desde</th><th></th></tr></thead><tbody>{blocks.map((block) => <tr key={block.id}><td><strong>{block.user_name}</strong></td><td><span className="block font-semibold">{block.permission_label}</span><small className="text-slate-400">{block.permission_code}</small></td><td>{block.branch_name || block.company_name}</td><td>{block.reason}</td><td>{formatDate(block.created_at)}</td><td>{canChange && <Button variant="secondary" disabled={saving} onClick={() => void revoke(block)}>Revogar</Button>}</td></tr>)}</tbody></table></div> : <EmptyState title="Nenhum bloqueio ativo" description="Todos os usuários seguem integralmente seus perfis de acesso." />}</section>
    </div>
  </>;
}
