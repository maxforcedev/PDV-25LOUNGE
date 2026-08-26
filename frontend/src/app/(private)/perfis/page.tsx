"use client";

import { useEffect, useRef, useState } from "react";
import { Pencil, Plus, Power, ShieldCheck, Users } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, EmptyState, Field, Input, Modal, Pagination, StatusBadge, TableLoading, Textarea } from "@/components/ui";
import { fieldError, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { AccessProfile, FunctionalPermission, Paginated } from "@/types";

type ProfileForm = { company: number; name: string; description: string; receives_commission: boolean; commission_rate: string | null; permission_codes: string[] };

type CrudColumn = "view" | "create" | "change" | "change_status";
const columnLabels: Record<CrudColumn, string> = { view: "Visualizar", create: "Cadastrar", change: "Editar", change_status: "Inativar" };
const moduleLabels: Record<string, string> = { companies: "Empresas e filiais", accounts: "Usuários e perfis", products: "Produtos", suppliers: "Fornecedores", branch_prices: "Preços por filial", inventory: "Estoque", cash_registers: "Caixa", sales: "Vendas", payment_methods: "Formas de pagamento", promotions: "Promoções", reports: "Relatórios", audit_logs: "Auditoria", commissions: "Comissões" };
function permissionSuffix(code: string) { return code.split(".").slice(1).join("."); }
function PermissionMatrix({ catalog, selected, onChange }: { catalog: FunctionalPermission[]; selected: string[]; onChange: (codes: string[]) => void }) {
  const modules = Object.entries(Object.groupBy(catalog, (item) => item.module || "general"));
  function setCodes(codes: string[], checked: boolean) { const next = new Set(selected); codes.forEach((code) => checked ? next.add(code) : next.delete(code)); onChange([...next]); }
  return <div className="space-y-5">{modules.map(([module, itemsValue]) => { const items = itemsValue || []; const byResource = Object.groupBy(items, (item) => item.code.split(".")[0]); const rows = Object.entries(byResource).map(([resource, permissions]) => {
    const suffixes = new Set((permissions || []).map((item) => permissionSuffix(item.code)));
    const crudResource = suffixes.has("view") && (suffixes.has("add") || suffixes.has("create") || suffixes.has("change") || suffixes.has("change_status"));
    const cells: Partial<Record<CrudColumn, FunctionalPermission>> = {};
    const special: FunctionalPermission[] = [];
    (permissions || []).forEach((permission) => { const suffix = permissionSuffix(permission.code); const column: CrudColumn | null = suffix === "view" && crudResource ? "view" : ["add", "create"].includes(suffix) && crudResource ? "create" : suffix === "change" && crudResource ? "change" : suffix === "change_status" ? "change_status" : null; if (column) cells[column] = permission; else special.push(permission); });
    return { resource, label: (permissions || [])[0]?.label.replace(/^(Visualizar|Cadastrar|Editar|Alterar status de|Configurar)\s+/i, "") || resource, cells, special };
  });
  const moduleCodes = items.map((item) => item.code); const allModule = moduleCodes.every((code) => selected.includes(code));
  return <fieldset key={module} className="overflow-hidden rounded-lg border border-slate-200"><legend className="sr-only">{moduleLabels[module] || module}</legend><div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3"><strong className="text-xs text-primary">{moduleLabels[module] || module}</strong><button type="button" className="text-[11px] font-semibold text-primary" onClick={() => setCodes(moduleCodes, !allModule)}>{allModule ? "Desmarcar módulo" : "Selecionar módulo"}</button></div>
    <div className="hidden overflow-x-auto md:block"><table className="w-full min-w-160 text-left text-xs"><thead><tr className="border-b border-slate-100 text-[10px] uppercase text-slate-400"><th className="px-4 py-3">Recurso</th>{(Object.keys(columnLabels) as CrudColumn[]).map((column) => { const codes = rows.map((row) => row.cells[column]?.code).filter(Boolean) as string[]; const checked = !!codes.length && codes.every((code) => selected.includes(code)); return <th key={column} className="px-3 py-3 text-center"><button type="button" disabled={!codes.length} className="font-bold disabled:text-slate-200" onClick={() => setCodes(codes, !checked)}>{columnLabels[column]}</button></th>; })}</tr></thead><tbody>{rows.filter((row) => Object.keys(row.cells).length).map((row) => <tr key={row.resource} className="border-b border-slate-100 last:border-0"><td className="px-4 py-3 font-semibold">{row.label}</td>{(Object.keys(columnLabels) as CrudColumn[]).map((column) => { const permission = row.cells[column]; return <td key={column} className="px-3 py-3 text-center">{permission ? <input aria-label={`${columnLabels[column]} ${row.label}`} type="checkbox" className="size-4 accent-primary" checked={selected.includes(permission.code)} onChange={() => setCodes([permission.code], !selected.includes(permission.code))} /> : <span className="text-slate-200">-</span>}</td>; })}</tr>)}</tbody></table></div>
    <div className="divide-y divide-slate-100 md:hidden">{rows.filter((row) => Object.keys(row.cells).length).map((row) => <div key={row.resource} className="p-4"><strong className="text-xs">{row.label}</strong><div className="mt-3 grid grid-cols-2 gap-2">{(Object.keys(columnLabels) as CrudColumn[]).map((column) => { const permission = row.cells[column]; return permission && <label key={column} className="flex items-center gap-2 text-[11px]"><input type="checkbox" className="size-4 accent-primary" checked={selected.includes(permission.code)} onChange={() => setCodes([permission.code], !selected.includes(permission.code))} />{columnLabels[column]}</label>; })}</div></div>)}</div>
    {rows.some((row) => row.special.length) && <div className="border-t border-slate-200 p-4"><h4 className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">Ações especiais</h4><div className="grid gap-2 sm:grid-cols-2">{rows.flatMap((row) => row.special).map((permission) => <label key={permission.code} className="flex cursor-pointer gap-3 rounded-md p-2 hover:bg-slate-50"><input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={selected.includes(permission.code)} onChange={() => setCodes([permission.code], !selected.includes(permission.code))} /><span><strong className="block text-xs">{permission.label}</strong><small className="text-[10px] leading-4 text-slate-400">{permission.description}</small></span></label>)}</div></div>}
  </fieldset>; })}</div>;
}

function Profiles() {
  const { currentCompany, hasPermission } = useAuth();
  const canAdd = hasPermission(permissions.addAccessProfile);
  const canChange = hasPermission(permissions.changeAccessProfile);
  const canStatus = hasPermission(permissions.changeAccessProfileStatus);
  const canChangeCommission = hasPermission(permissions.changeProfileCommission);
  const [data, setData] = useState<Paginated<AccessProfile> | null>(null);
  const [catalog, setCatalog] = useState<FunctionalPermission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<AccessProfile | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<ProfileForm>({ company: 0, name: "", description: "", receives_commission: true, commission_rate: null, permission_codes: [] });
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<AccessProfile | null>(null);
  const [usersModal, setUsersModal] = useState<{ name: string; users: Array<{ id: number; email: string; first_name: string; last_name: string }> } | null>(null);
  const [usersLoading, setUsersLoading] = useState(false);
  const companyIdRef = useRef(currentCompany?.id);
  companyIdRef.current = currentCompany?.id;

  async function load(path?: string, requestedCompanyId = currentCompany?.id) {
    if (!requestedCompanyId) return;
    setLoading(true); setError("");
    try { const response = await http.get<Paginated<AccessProfile>>(path || `access-profiles/?company=${requestedCompanyId}`); if (companyIdRef.current === requestedCompanyId) setData(response); }
    catch (caught) { if (companyIdRef.current === requestedCompanyId) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os perfis."); }
    finally { if (companyIdRef.current === requestedCompanyId) setLoading(false); }
  }

  useEffect(() => {
    if (!currentCompany) return;
    const companyId = currentCompany.id; let active = true;
    void load(undefined, companyId);
    http.getAll<FunctionalPermission>("functional-permissions/").then((items) => { if (active && companyIdRef.current === companyId) setCatalog(items); }).catch((caught) => { if (active && companyIdRef.current === companyId) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as permissões."); });
    return () => { active = false; };
  }, [currentCompany?.id]);

  function openCreate() {
    if (!currentCompany || !canAdd) return;
    setEditing(null); setForm({ company: currentCompany.id, name: "", description: "", receives_commission: true, commission_rate: null, permission_codes: [] }); setFields({}); setError(""); setOpen(true);
  }

  async function openEdit(profile: AccessProfile) {
    if (!canChange) return;
    const requestedCompanyId = currentCompany?.id;
    setError("");
    try {
      const detail = await http.get<AccessProfile>(`access-profiles/${profile.id}/`);
      if (companyIdRef.current !== requestedCompanyId || detail.company !== requestedCompanyId) return;
      setEditing(detail); setForm({ company: detail.company, name: detail.name, description: detail.description || "", receives_commission: detail.receives_commission ?? true, commission_rate: detail.commission_rate ?? null, permission_codes: detail.permission_codes }); setFields({}); setOpen(true);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o perfil."); }
  }

  function toggle(code: string) {
    setForm((current) => ({ ...current, permission_codes: current.permission_codes.includes(code) ? current.permission_codes.filter((item) => item !== code) : [...current.permission_codes, code] }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setFields({}); setSuccess("");
    try {
      const payload = canChangeCommission ? form : { company: form.company, name: form.name, description: form.description, permission_codes: form.permission_codes };
      if (editing) await http.patch(`access-profiles/${editing.id}/`, payload);
      else await http.post("access-profiles/", payload);
      setOpen(false); setSuccess(editing ? "Perfil atualizado com sucesso." : "Perfil criado com sucesso."); await load();
    } catch (caught) { if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields); } else setError("Não foi possível salvar o perfil."); }
    finally { setSaving(false); }
  }

  async function changeStatus() {
    if (!confirming || !canStatus) return;
    setSaving(true); setError("");
    const action = confirming.status === "active" ? "deactivate" : "activate";
    try { await http.post(`access-profiles/${confirming.id}/${action}/`); setConfirming(null); setSuccess(`Perfil ${action === "activate" ? "ativado" : "inativado"} com sucesso.`); await load(); }
    catch (caught) { setConfirming(null); setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar o status."); }
    finally { setSaving(false); }
  }

  async function viewUsers(profile: AccessProfile) {
    setUsersLoading(true);
    setError("");
    try {
      const users = await http.get<Array<{ id: number; email: string; first_name: string; last_name: string }>>(`access-profiles/${profile.id}/users/`);
      setUsersModal({ name: profile.name, users });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os usuários.");
    } finally { setUsersLoading(false); }
  }

  return <>
    <PageHeader title="Perfis de acesso" description={`Permissões funcionais de ${currentCompany?.trade_name || "sua empresa"}.`} action={<Button onClick={openCreate} disabled={!canAdd}><Plus className="size-4" />Novo perfil</Button>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">{error && !open && <Alert message={error} />}{success && <Alert type="success" message={success} />}<section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Perfis cadastrados</h2>{/* <p className="mt-1 text-[11px] text-slate-500">Acesso definido por empresa, sem papéis fixos</p> */}</div><ShieldCheck className="size-5 text-slate-300" /></div>{loading ? <TableLoading /> : data?.results.length ? <><div className="table-wrap"><table className="data-table"><thead><tr><th>Perfil</th><th>Permissões</th><th>Usuários</th><th>Tipo</th><th>Status</th><th>Atualização</th><th className="text-right">Ações</th></tr></thead><tbody>{data.results.map((profile) => <tr key={profile.id}><td><strong className="block">{profile.name}</strong><span className="text-[11px] text-slate-400">{profile.description || "Sem descrição"}</span></td><td>{profile.permission_codes.length}</td><td><button className="text-xs font-semibold text-primary hover:underline" onClick={() => void viewUsers(profile)} disabled={usersLoading}>{profile.user_count ?? 0}</button></td><td>{profile.is_system ? "Padrão do sistema" : "Personalizado"}</td><td><StatusBadge active={profile.status === "active"} /></td><td>{formatDate(profile.updated_at)}</td><td><div className="flex justify-end gap-1"><button className="icon-button" onClick={() => void viewUsers(profile)} disabled={usersLoading} title="Ver usuários"><Users className="size-4" /></button><button className="icon-button" onClick={() => void openEdit(profile)} disabled={!canChange}><Pencil className="size-4" /></button><button className="icon-button" onClick={() => setConfirming(profile)} disabled={!canStatus}><Power className="size-4" /></button></div></td></tr>)}</tbody></table></div><Pagination count={data.count} next={data.next} previous={data.previous} onPage={load} /></> : <EmptyState title="Nenhum perfil cadastrado" description="Crie um perfil e selecione as permissões funcionais." />}</section></div>
    <Modal open={open} title={editing ? "Editar perfil" : "Novo perfil"} description="Matriz gerada exclusivamente pelo catálogo de permissões da API." onClose={() => !saving && setOpen(false)} size="xl"><form onSubmit={submit}><div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-6"><div className="sm:col-span-2">{error && <Alert message={error} />}</div><Field label="Nome" error={fieldError(fields, "name")}><Input required value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} disabled={saving} /></Field><Field label="Descrição" optional error={fieldError(fields, "description")}><Textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} disabled={saving} /></Field><label className="flex items-center gap-3 rounded-lg border border-slate-200 p-4 text-xs font-semibold"><input type="checkbox" className="size-4 accent-primary" checked={form.receives_commission} onChange={(event) => setForm((current) => ({ ...current, receives_commission: event.target.checked }))} /><span><strong className="block">Recebe comissão</strong><small className="font-normal text-slate-400">Quando desmarcado, vendas deste perfil não geram comissão.</small></span></label><Field label="Comissão do perfil" optional error={fieldError(fields, "commission_rate")}><Input inputMode="decimal" placeholder="Usar padrão da filial" value={form.commission_rate || ""} onChange={(event) => setForm((current) => ({ ...current, commission_rate: event.target.value || null }))} disabled={saving || !form.receives_commission} /></Field><div className="sm:col-span-2"><h3 className="mb-3 text-xs font-bold">Permissões</h3><PermissionMatrix catalog={catalog} selected={form.permission_codes} onChange={(permission_codes) => setForm((current) => ({ ...current, permission_codes }))} />{fieldError(fields, "permission_codes") && <p className="field-error">{fieldError(fields, "permission_codes")}</p>}</div></div><div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4"><Button type="button" variant="secondary" onClick={() => setOpen(false)} disabled={saving}>Cancelar</Button><Button type="submit" loading={saving}>Salvar perfil</Button></div></form></Modal>
    <ConfirmDialog open={!!confirming} title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} perfil`} message={`Confirma a alteração de status de “${confirming?.name || ""}”?`} confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"} danger={confirming?.status === "active"} loading={saving} onClose={() => !saving && setConfirming(null)} onConfirm={changeStatus} />
    <Modal open={!!usersModal} title={`Usuários do perfil "${usersModal?.name || ""}"`} onClose={() => setUsersModal(null)}>
      <div className="p-5">
        {usersModal?.users.length ? (
          <div className="space-y-2">
            {usersModal.users.map((u) => (
              <div key={u.id} className="flex items-center gap-3 rounded-md border border-slate-100 p-3 text-xs">
                <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">{(u.first_name?.[0] || "") + (u.last_name?.[0] || "") || u.email?.[0]?.toUpperCase() || "?"}</span>
                <div><strong className="block">{u.first_name} {u.last_name}</strong><small className="text-slate-400">{u.email}</small></div>
              </div>
            ))}
          </div>
        ) : <EmptyState title="Nenhum usuário vinculado" description="Este perfil não possui usuários ativos no momento." />}
      </div>
    </Modal>
  </>;
}

export default function ProfilesPage() { return <AdminGuard requiredPermissions={[permissions.viewAccessProfile]}><Profiles /></AdminGuard>; }
