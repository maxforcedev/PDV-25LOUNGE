"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  KeyRound,
  Pencil,
  Plus,
  Power,
  Search,
  ShieldX,
  SlidersHorizontal,
  Trash2,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AdminGuard } from "@/components/admin-guard";
import { UserCommissionSection } from "@/components/user-commission-section";
import { UserAvatar } from "@/components/user-avatar";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  Pagination,
  Select,
  StatusBadge,
  TableLoading,
} from "@/components/ui";
import { fieldError, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { archivedRecordConflict } from "@/lib/archived-errors";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type {
  Paginated,
  AuditLog,
  User,
  UserPayload,
  UserType,
} from "@/types";

interface UserManagementBranch {
  id: number;
  company: number;
  name: string;
  status: "active" | "inactive";
}

interface UserManagementProfile {
  id: number;
  company: number;
  name: string;
  company_assignable: boolean;
  assignable_branch_ids: number[];
}

const userTypes: Array<[UserType, string]> = [
  ["employee", "Funcionário"],
  ["promoter", "Promoter"],
  ["dj", "DJ"],
  ["artist", "Artista"],
  ["other", "Outro"],
];
const blank = (): UserPayload => ({
  email: null,
  password: null,
  can_login: false,
  user_type: "employee",
  first_name: "",
  last_name: "",
  birth_date: null,
  cpf: "",
  zip_code: "",
  street: "",
  address_number: "",
  address_complement: "",
  neighborhood: "",
  city: "",
  state: "",
  company_accesses: [],
});
const typeLabel = (value: UserType) =>
  userTypes.find(([key]) => key === value)?.[1] || value;
const editorTabs = [
  ["personal", "Dados pessoais"],
  ["access", "Acesso e permissões"],
  ["commission", "Comissão"],
  ["security", "Segurança"],
  ["history", "Histórico"],
] as const;
type EditorTab = (typeof editorTabs)[number][0];
interface UserFilters {
  search: string;
  status: string;
  canLogin: string;
  userType: string;
  accessProfile: string;
  branch: string;
}
interface ArchivedUserConflict {
  userId: number;
  name: string;
  email: string | null;
  archivedAt: string;
}
const emptyFilters = (branchId?: number): UserFilters => ({
  search: "",
  status: "active",
  canLogin: "",
  userType: "",
  accessProfile: "",
  branch: branchId ? String(branchId) : "",
});

function UserEditorFrame({ open, page, title, description, onClose, children }: { open: boolean; page: boolean; title: string; description: string; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null;
  if (!page) return <Modal open title={title} description={description} onClose={onClose} size="xl">{children}</Modal>;
  return <><PageHeader title={title} description={description} /><main className="space-y-4 p-4 sm:p-6 lg:p-8"><section className="card overflow-hidden">{children}</section></main></>;
}

function UsersAdministration() {
  const { user: actor, currentCompany, currentBranch, hasPermission } = useAuth();
  const router = useRouter();
  const { id } = useParams<{ id?: string }>();
  const isDetail = Boolean(id);
  const isNew = id === "novo";
  const canAdd = hasPermission(permissions.addUser);
  const canChange = hasPermission(permissions.changeUser);
  const canStatus = hasPermission(permissions.changeUserStatus);
  const contextRef = useRef(`${currentCompany?.id || ""}:${currentBranch?.id || ""}`);
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [data, setData] = useState<Paginated<User> | null>(null);
  const [branches, setBranches] = useState<UserManagementBranch[]>([]);
  const [profiles, setProfiles] = useState<
    Record<number, UserManagementProfile[]>
  >({});
  const [loading, setLoading] = useState(true);
  const [dependenciesLoading, setDependenciesLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState<UserPayload>(blank());
  const [accessesDirty, setAccessesDirty] = useState(false);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<User | null>(null);
  const [archiving, setArchiving] = useState<User | null>(null);
  const [editorTab, setEditorTab] = useState<EditorTab>("personal");
  const [history, setHistory] = useState<AuditLog[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetFields, setResetFields] = useState<Record<string, string[]>>({});
  const [resetSaving, setResetSaving] = useState(false);
  const [restoreConflict, setRestoreConflict] =
    useState<ArchivedUserConflict | null>(null);
  const [draftFilters, setDraftFilters] = useState<UserFilters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<UserFilters>(emptyFilters);

  useEffect(() => {
    const saved = new URLSearchParams(window.location.search).get("saved");
    if (saved) setSuccess(saved === "created" ? "Usuário criado com sucesso." : saved === "archived" ? "Usuário arquivado. O histórico foi preservado." : saved === "restored" ? "Usuário restaurado com sucesso." : "Usuário atualizado com sucesso.");
  }, []);

  function listPath(companyId: number, selected: UserFilters) {
    const params = new URLSearchParams({ company: String(companyId) });
    if (selected.search.trim()) params.set("search", selected.search.trim());
    if (selected.status) params.set("status", selected.status);
    if (selected.canLogin) params.set("can_login", selected.canLogin);
    if (selected.userType) params.set("user_type", selected.userType);
    if (selected.accessProfile)
      params.set("access_profile", selected.accessProfile);
    if (selected.branch) params.set("branch", selected.branch);
    return `users/?${params}`;
  }

  async function load(
    path?: string,
    companyId = currentCompany?.id,
    selected = appliedFilters,
  ) {
    if (!companyId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await http.get<Paginated<User>>(
        path || listPath(companyId, selected),
      );
      if (contextRef.current === `${companyId}:${currentBranch?.id || ""}`)
        setData(response);
    } catch (caught) {
      if (contextRef.current === `${companyId}:${currentBranch?.id || ""}`)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar os usuários.",
        );
    } finally {
      if (contextRef.current === `${companyId}:${currentBranch?.id || ""}`)
        setLoading(false);
    }
  }
  useEffect(() => {
    const companyId = currentCompany?.id;
    if (!companyId) return;
    let active = true;
    const cleared = emptyFilters(currentBranch?.id);
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    setData(null);
    void load(undefined, companyId, cleared);
    setDependenciesLoading(true);
    http
      .get<{
        branches: Array<{
          id: number;
          company_id: number;
          name: string;
          status: "active" | "inactive";
        }>;
        profiles: Array<{
          id: number;
          company_id: number;
          name: string;
          company_assignable: boolean;
          assignable_branch_ids: number[];
        }>;
      }>(`users/management-options/?company=${currentCompany.id}`)
      .then((options) => {
        if (
          active &&
          contextRef.current === `${companyId}:${currentBranch?.id || ""}`
        ) {
          setBranches(
            options.branches.map(({ company_id, ...branch }) => ({
              ...branch,
              company: company_id,
            })),
          );
          setProfiles(
            options.profiles.reduce<Record<number, UserManagementProfile[]>>(
              (grouped, { company_id, ...profile }) => {
                (grouped[company_id] ||= []).push({
                  ...profile,
                  company: company_id,
                });
                return grouped;
              },
              {},
            ),
          );
        }
      })
      .catch(
        (caught) =>
          active &&
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Não foi possível carregar perfis e filiais.",
          ),
      )
      .finally(() => active && setDependenciesLoading(false));
    return () => {
      active = false;
    };
  }, [currentCompany?.id, currentBranch?.id]);

  useEffect(() => {
    if (!isDetail || !currentCompany) return;
    if (isNew) {
      show();
      return;
    }
    const userId = Number(id);
    if (!Number.isInteger(userId) || userId <= 0) {
      setError("Usuário inválido.");
      return;
    }
    const companyId = currentCompany.id;
    const contextKey = `${companyId}:${currentBranch?.id || ""}`;
    let active = true;
    http.get<User>(`users/${userId}/?company=${companyId}`).then((target) => {
      if (!active || contextRef.current !== contextKey) return;
      if (target.membership?.company_id !== companyId) throw new ApiError("Usuário não encontrado.", 404);
      show(target);
    }).catch((caught) => {
      if (active && contextRef.current === contextKey)
        setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o usuário.");
    });
    return () => { active = false; };
  }, [id, isDetail, isNew, currentCompany?.id, currentBranch?.id]);

  useEffect(() => {
    if (editorTab !== "history" || !editing || !currentCompany) return;
    setHistoryLoading(true);
    http.get<Paginated<AuditLog>>(`audit-logs/?company=${currentCompany.id}&object_type=User&search=${editing.id}`)
      .then((result) => setHistory(result.results.filter((log) => log.object_id === String(editing.id))))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [editorTab, editing?.id, currentCompany?.id]);

  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    setAppliedFilters(draftFilters);
    void load(undefined, currentCompany?.id, draftFilters);
  }

  function clearFilters() {
    const cleared = emptyFilters(currentBranch?.id);
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    void load(undefined, currentCompany?.id, cleared);
  }

  function show(target?: User) {
    if (!target && !canAdd) return;
    const accesses = target?.membership ? [{
      company_id: target.membership.company_id,
      access_profile_id: target.membership.access_profile_id,
      branch_accesses: target.membership.branch_accesses,
    }] : [];
    setEditing(target || null);
    setEditorTab("personal");
    setAccessesDirty(false);
    setForm(
      target
        ? {
            email: target.email,
            password: null,
            can_login: Boolean(target.can_login && target.membership?.is_active),
            user_type: target.user_type,
             first_name: target.first_name,
             last_name: target.last_name,
             birth_date: target.birth_date,
             cpf: target.cpf,
             zip_code: target.zip_code,
             street: target.street,
             address_number: target.address_number,
             address_complement: target.address_complement,
             neighborhood: target.neighborhood,
             city: target.city,
             state: target.state,
            company_accesses: accesses,
          }
        : {
            ...blank(),
            company_accesses: currentCompany
              ? [
                  {
                    company_id: currentCompany.id,
                    access_profile_id: null,
                    branch_accesses: [],
                  },
                ]
              : [],
          },
    );
    setFields({});
    setError("");
    setRestoreConflict(null);
    setOpen(true);
  }
  function update<K extends keyof UserPayload>(key: K, value: UserPayload[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  function updateAccess(
    companyId: number,
    value: Partial<UserPayload["company_accesses"][number]>,
  ) {
    setAccessesDirty(true);
    setForm((current) => ({
      ...current,
      company_accesses: current.company_accesses.map((item) =>
        item.company_id === companyId ? { ...item, ...value } : item,
      ),
    }));
  }
  function toggleBranch(companyId: number, branchId: number) {
    const access = form.company_accesses.find(
      (item) => item.company_id === companyId,
    );
    if (!access) return;
    const existing = access.branch_accesses.some(
      (item) => item.branch_id === branchId,
    );
    const assignableProfile = profiles[companyId]?.find((profile) =>
      profile.assignable_branch_ids.includes(branchId),
    );
    if (!existing && !assignableProfile) {
      setError("Nenhum perfil atribuível está disponível para esta filial.");
      return;
    }
    updateAccess(companyId, {
      branch_accesses: existing
        ? access.branch_accesses.filter((item) => item.branch_id !== branchId)
        : [
            ...access.branch_accesses,
            {
              branch_id: branchId,
              access_profile_id: assignableProfile!.id,
            },
          ],
    });
  }
  function updateBranchProfile(
    companyId: number,
    branchId: number,
    profileId: number,
  ) {
    const access = form.company_accesses.find(
      (item) => item.company_id === companyId,
    );
    if (access)
      updateAccess(companyId, {
        branch_accesses: access.branch_accesses.map((item) =>
          item.branch_id === branchId
            ? { ...item, access_profile_id: profileId }
            : item,
        ),
      });
  }
  function setCanLogin(value: boolean) {
    setAccessesDirty(true);
    setForm((current) => ({
      ...current,
      can_login: value,
      email: current.email,
      password: value ? current.password : null,
      company_accesses: value
        ? current.company_accesses
        : current.company_accesses.map((item) => ({
            ...item,
            access_profile_id: null,
            branch_accesses: [],
          })),
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (
      form.can_login &&
      form.company_accesses.some(
        (access) =>
          !access.branch_accesses.length ||
          access.branch_accesses.some((branch) => !branch.access_profile_id),
      )
    ) {
      setError(
        "Com login, selecione ao menos uma filial com perfil operacional.",
      );
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      const normalizedPayload = {
        ...form,
        email: form.email?.trim() || null,
        password: form.password?.trim() || undefined,
      };
      const payload = { ...normalizedPayload } as Partial<UserPayload>;
      if (editing && !accessesDirty) delete payload.company_accesses;
      if (editing) await http.patch(`users/${editing.id}/?company=${currentCompany?.id}`, payload);
      else await http.post<User>(`users/?company=${currentCompany?.id}`, payload);
      if (isDetail) {
        router.push(`/usuarios?saved=${editing ? "updated" : "created"}`);
        return;
      }
      setOpen(false);
      setSuccess(editing ? "Usuário atualizado com sucesso." : "Usuário criado com sucesso.");
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        const conflict = archivedRecordConflict(
          caught,
          "archived_user_exists",
          "user_id",
        );
        if (!editing && conflict) {
          setRestoreConflict({
            userId: conflict.id,
            name: conflict.name,
            email:
              typeof caught.details.email === "string"
                ? caught.details.email
                : null,
            archivedAt: conflict.archivedAt,
          });
          return;
        }
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível salvar o usuário.");
    } finally {
      setSaving(false);
    }
  }

  async function restoreUser() {
    if (!restoreConflict || !currentCompany) return;
    setSaving(true);
    setError("");
    setFields({});
    try {
      const payload = {
        ...form,
        email: form.email?.trim() || null,
        password: form.password?.trim() || undefined,
      };
      await http.post<User>(
        `users/${restoreConflict.userId}/restore/?company=${currentCompany.id}`,
        payload,
      );
      setRestoreConflict(null);
      if (isDetail) {
        router.push("/usuarios?saved=restored");
        return;
      }
      setOpen(false);
      setSuccess("Usuário restaurado com sucesso.");
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else {
        setError("Não foi possível restaurar o usuário.");
      }
    } finally {
      setSaving(false);
    }
  }
  async function changeStatus() {
    if (!confirming) return;
    setSaving(true);
    const action = confirming.membership?.is_active ? "deactivate" : "activate";
    try {
      const updated = await http.post<User>(`users/${confirming.id}/${action}/?company=${currentCompany?.id}`);
      setConfirming(null);
      setSuccess(`Usuário ${action === "activate" ? "ativado" : "inativado"}.`);
      if (isDetail) setEditing(updated);
      else await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível alterar o status.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function archiveUser() {
    if (!archiving) return;
    setSaving(true); setError("");
    try {
       await http.post(`users/${archiving.id}/archive/?company=${currentCompany?.id}`);
      setArchiving(null);
      if (isDetail) { router.push("/usuarios?saved=archived"); return; }
      setSuccess("Usuário arquivado. O histórico foi preservado.");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível arquivar o usuário.");
    } finally { setSaving(false); }
  }

  async function doResetPassword() {
    if (!resetTarget || !resetPassword.trim()) return;
    setResetSaving(true);
    setResetFields({});
    setError("");
    try {
      await http.post(`users/${resetTarget.id}/reset-password/?company=${currentCompany?.id}`, {
        new_password: resetPassword,
      });
      setResetTarget(null);
      setResetPassword("");
      setSuccess("Senha redefinida com sucesso.");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setResetFields(caught.fields);
      } else {
        setError("Não foi possível redefinir a senha.");
      }
    } finally {
      setResetSaving(false);
    }
  }

  return (
    <>
      {!isDetail && <PageHeader
        title="Usuários"
        description="Cadastre pessoas com ou sem acesso ao sistema."
        action={
          <Button
            onClick={() => show()}
            disabled={!canAdd || dependenciesLoading}
          >
            <Plus className="size-4" />
            Novo usuário
          </Button>
        }
      />}
      {!isDetail && <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !open && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        <form className="card space-y-3 p-4" onSubmit={applyFilters}>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-slate-400" />
              <Input
                className="pl-9"
                placeholder="Nome ou e-mail"
                value={draftFilters.search}
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    search: event.target.value,
                  }))
                }
              />
            </div>
            <Select
              aria-label="Status do usuário"
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  status: event.target.value,
                }))
              }
            >
                <option value="active">Ativos</option>
                <option value="inactive">Inativos</option>
                <option value="all">Todos</option>
            </Select>
            <Select
              aria-label="Acesso ao sistema"
              value={draftFilters.canLogin}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  canLogin: event.target.value,
                }))
              }
            >
              <option value="">Com e sem login</option>
              <option value="true">Pode fazer login</option>
              <option value="false">Sem login</option>
            </Select>
            <Select
              aria-label="Tipo de usuário"
              value={draftFilters.userType}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  userType: event.target.value,
                }))
              }
            >
              <option value="">Todos os tipos</option>
              {userTypes.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Select
              aria-label={
                draftFilters.branch
                  ? "Perfil na filial"
                  : "Perfil administrativo"
              }
              value={draftFilters.accessProfile}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  accessProfile: event.target.value,
                }))
              }
            >
              <option value="">
                {draftFilters.branch
                  ? "Todos os perfis na filial"
                  : "Todos os perfis administrativos"}
              </option>
              {(profiles[currentCompany?.id || 0] || []).map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Filial com acesso ativo"
              value={draftFilters.branch}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  branch: event.target.value,
                  accessProfile: "",
                }))
              }
            >
              <option value="">Todas as filiais</option>
              {branches
                .filter(
                  (branch) =>
                    branch.company === currentCompany?.id &&
                    branch.status === "active",
                )
                .map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
            </Select>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="secondary" onClick={clearFilters}>
              Limpar
            </Button>
            <Button type="submit">
              <SlidersHorizontal className="size-4" />
              Aplicar
            </Button>
          </div>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Usuários cadastrados</h2>
              {/* <p className="mt-1 text-[11px] text-slate-500">
                Pessoas operacionais também podem existir sem login
              </p> */}
            </div>
            <Users className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Usuário</th>
                       <th>Cargo</th>
                      <th>Login</th>
                      <th>Status</th>
                       <th>Último acesso</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <div className="flex items-center gap-3">
                              <UserAvatar user={item} textClassName="text-[11px]" />
                              <div>
                                <strong className="block">
                                  {item.first_name} {item.last_name}
                                </strong>
                                <span className="text-[11px] text-slate-400">
                                  {item.email || "Sem e-mail"}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold">
                              {typeLabel(item.user_type)}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.can_login ? "bg-primary/10 text-primary" : "bg-slate-100 text-slate-500"}`}
                            >
                              {item.can_login ? "Permitido" : "Sem login"}
                            </span>
                          </td>
                          <td>
                              <StatusBadge active={!!item.membership?.is_active && item.is_active} />
                           </td>
                           <td>{item.last_login ? formatDate(item.last_login) : "Nunca acessou"}</td>
                          <td>
                            <div className="flex justify-end gap-1">
                                <Link className="icon-button" aria-label="Ver usuário" href={`/usuarios/${item.id}`}><Pencil className="size-4" /></Link>
                               <button
                                className="icon-button"
                                aria-label="Redefinir senha"
                                disabled={!canChange || !!item.is_superuser}
                                onClick={() => { setResetTarget(item); setResetPassword(""); setResetFields({}); }}
                              >
                                <KeyRound className="size-4" />
                              </button>
                              <Link
                                className="icon-button"
                                aria-label="Bloqueios de acesso"
                                href={`/usuarios/bloqueios?user=${item.id}`}
                              >
                                <ShieldX className="size-4" />
                              </Link>
                              <button
                                className="icon-button"
                                aria-label="Alterar status"
                                disabled={!canStatus || item.id === actor?.id}
                                onClick={() => setConfirming(item)}
                              >
                                 <Power className="size-4" />
                               </button>
                               <button
                                 className="icon-button hover:bg-danger/10 hover:text-danger"
                                 aria-label="Arquivar usuário"
                                  disabled={!canStatus || item.id === actor?.id}
                                 onClick={() => setArchiving(item)}
                               >
                                 <Trash2 className="size-4" />
                               </button>
                            </div>
                          </td>
                        </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={load}
              />
            </>
          ) : (
            <EmptyState
              title={
                Object.values(appliedFilters).some(Boolean)
                  ? "Nenhum usuário encontrado"
                  : "Nenhum usuário cadastrado"
              }
              description={
                Object.values(appliedFilters).some(Boolean)
                  ? "Nenhum usuário corresponde aos filtros aplicados."
                  : "Cadastre a primeira pessoa desta empresa."
              }
            />
          )}
        </section>
      </div>}
      <UserEditorFrame
        open={open}
        page={isDetail}
        title={editing ? `${editing.first_name} ${editing.last_name}` : "Novo usuário"}
        description={editing ? `${typeLabel(editing.user_type)} · ${editing.membership?.is_active ? "Ativo" : "Inativo"}` : "Cadastre os dados principais da pessoa."}
        onClose={() => !saving && (isDetail ? router.push("/usuarios") : setOpen(false))}
      >
        {isDetail && editing && <>
          <div className="flex flex-wrap gap-2 border-b border-subtle p-4 sm:px-6">
            <Button type="button" variant="secondary" onClick={() => router.push("/usuarios")}><ArrowLeft className="size-4" />Voltar</Button>
            {canChange && <Button type="submit" form="user-editor-form" loading={saving}>Salvar usuário</Button>}
            {canStatus && editing.id !== actor?.id && <Button type="button" variant="secondary" onClick={() => setConfirming(editing)}>{editing.membership?.is_active ? "Inativar" : "Ativar"}</Button>}
          </div>
          <div role="tablist" aria-label="Seções do usuário" className="flex overflow-x-auto border-b border-subtle px-4 sm:px-6">
            {editorTabs.map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={editorTab === value} onClick={() => setEditorTab(value)} className={`shrink-0 border-b-2 px-4 py-3 text-xs font-semibold transition ${editorTab === value ? "border-primary text-primary" : "border-transparent text-muted hover:text-fg"}`}>{label}</button>)}
          </div>
        </>}
        <form id="user-editor-form" onSubmit={submit}>
          <fieldset disabled={!!editing && !canChange} className="p-5 disabled:opacity-75 sm:p-6">
            {error && <div className="mb-5"><Alert message={error} /></div>}
            {!editing ? <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Nome" error={fieldError(fields, "first_name")}><Input required value={form.first_name} onChange={(event) => update("first_name", event.target.value)} /></Field>
              <Field label="Sobrenome" error={fieldError(fields, "last_name")}><Input required value={form.last_name} onChange={(event) => update("last_name", event.target.value)} /></Field>
              <Field label="Tipo/Cargo"><Select value={form.user_type} onChange={(event) => update("user_type", event.target.value as UserType)}>{userTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
              <label className="flex items-center gap-3 rounded-lg border border-subtle p-4 text-xs font-semibold"><input type="checkbox" className="size-4 accent-primary" checked={form.can_login} onChange={(event) => setCanLogin(event.target.checked)} /><span><strong className="block">Pode acessar o sistema?</strong><small className="font-normal text-muted">Ative para configurar credenciais e filiais.</small></span></label>
              {form.can_login && <><Field label="E-mail" error={fieldError(fields, "email")}><Input type="email" required value={form.email || ""} onChange={(event) => update("email", event.target.value || null)} /></Field><Field label="Senha inicial" error={fieldError(fields, "password")}><Input type="password" minLength={8} required value={form.password || ""} onChange={(event) => update("password", event.target.value || null)} /></Field>
                <div className="space-y-3 sm:col-span-2"><h3 className="text-sm font-bold">Perfil e filiais autorizadas</h3>{branches.filter((branch) => branch.company === currentCompany?.id).map((branch) => { const access = form.company_accesses[0]; const branchAccess = access?.branch_accesses.find((item) => item.branch_id === branch.id); return <div key={branch.id} className="grid gap-2 rounded-lg border border-subtle p-3 sm:grid-cols-[1fr_14rem]"><label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={!!branchAccess} onChange={() => currentCompany && toggleBranch(currentCompany.id, branch.id)} /><span><strong className="block text-sm">{branch.name}</strong><small className="block text-[11px] font-normal text-muted">{currentCompany?.trade_name}</small></span></label>{branchAccess && <Select required value={branchAccess.access_profile_id || ""} onChange={(event) => currentCompany && updateBranchProfile(currentCompany.id, branch.id, Number(event.target.value))}><option value="">Selecione o perfil</option>{(profiles[currentCompany?.id || 0] || []).filter((profile) => profile.assignable_branch_ids.includes(branch.id)).map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</Select>}</div>; })}{fieldError(fields, "company_accesses") && <p className="field-error">{fieldError(fields, "company_accesses")}</p>}</div>
              </>}
            </div> : <>
              {editorTab === "personal" && <div className="grid gap-5 sm:grid-cols-2"><div className="flex items-center gap-4 sm:col-span-2"><UserAvatar user={editing} className="size-16" textClassName="text-lg" /><div><h2 className="text-sm font-bold">Dados pessoais</h2><p className="text-xs text-muted">Identificação e endereço global do usuário.</p></div></div><Field label="Nome"><Input required value={form.first_name} onChange={(event) => update("first_name", event.target.value)} /></Field><Field label="Sobrenome"><Input required value={form.last_name} onChange={(event) => update("last_name", event.target.value)} /></Field><Field label="CPF" optional><Input value={form.cpf} onChange={(event) => update("cpf", event.target.value)} /></Field><Field label="Aniversário" optional><Input type="date" value={form.birth_date || ""} onChange={(event) => update("birth_date", event.target.value || null)} /></Field><Field label="CEP" optional><Input value={form.zip_code} onChange={(event) => update("zip_code", event.target.value)} /></Field><Field label="Logradouro" optional><Input value={form.street} onChange={(event) => update("street", event.target.value)} /></Field><Field label="Número" optional><Input value={form.address_number} onChange={(event) => update("address_number", event.target.value)} /></Field><Field label="Complemento" optional><Input value={form.address_complement} onChange={(event) => update("address_complement", event.target.value)} /></Field><Field label="Bairro" optional><Input value={form.neighborhood} onChange={(event) => update("neighborhood", event.target.value)} /></Field><Field label="Cidade" optional><Input value={form.city} onChange={(event) => update("city", event.target.value)} /></Field><Field label="Estado" optional><Input maxLength={2} value={form.state} onChange={(event) => update("state", event.target.value.toUpperCase())} /></Field></div>}
              {editorTab === "access" && <div className="space-y-5"><label className="flex items-center gap-3 rounded-lg border border-subtle p-4 text-xs font-semibold"><input type="checkbox" className="size-4 accent-primary" checked={form.can_login} onChange={(event) => setCanLogin(event.target.checked)} /><span><strong className="block">Pode acessar o sistema?</strong><small className="font-normal text-muted">Desativar remove somente o acesso desta empresa.</small></span></label><div className="grid gap-5 sm:grid-cols-2"><Field label="Cargo/Função"><Select value={form.user_type} onChange={(event) => update("user_type", event.target.value as UserType)}>{userTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field><Field label="E-mail" error={fieldError(fields, "email")}><Input type="email" required={form.can_login} value={form.email || ""} onChange={(event) => update("email", event.target.value || null)} /></Field>{form.can_login && !editing.can_login && <Field label="Senha inicial" error={fieldError(fields, "password")}><Input type="password" minLength={8} required value={form.password || ""} onChange={(event) => update("password", event.target.value || null)} /></Field>}</div><div className="flex items-center justify-between rounded-lg border border-subtle p-4"><div><strong className="text-xs">Estado do acesso nesta empresa</strong><p className="mt-1 text-xs text-muted">A credencial global permanece preservada em outras empresas.</p></div><StatusBadge active={form.can_login} /></div>{form.can_login && <div><h2 className="text-sm font-bold">Filiais e perfis autorizados</h2><div className="mt-3 space-y-2">{branches.filter((branch) => branch.company === currentCompany?.id).map((branch) => { const access = form.company_accesses[0]; const branchAccess = access?.branch_accesses.find((item) => item.branch_id === branch.id); return <div key={branch.id} className="grid gap-2 rounded-lg border border-subtle p-3 sm:grid-cols-[1fr_14rem]"><label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-primary" checked={!!branchAccess} onChange={() => currentCompany && toggleBranch(currentCompany.id, branch.id)} /><span><strong className="block text-sm">{branch.name}</strong><small className="block text-[11px] font-normal text-muted">{currentCompany?.trade_name}</small></span></label>{branchAccess && <Select value={branchAccess.access_profile_id} onChange={(event) => currentCompany && updateBranchProfile(currentCompany.id, branch.id, Number(event.target.value))}>{(profiles[currentCompany?.id || 0] || []).filter((profile) => profile.assignable_branch_ids.includes(branch.id) || profile.id === branchAccess.access_profile_id).map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</Select>}</div>; })}</div></div>}</div>}
              {editorTab === "security" && <div className="space-y-4"><h2 className="text-sm font-bold">Segurança</h2>{success && <Alert type="success" message={success} />}<div className="flex flex-wrap gap-2">{canChange && <Button type="button" variant="secondary" onClick={() => { setResetTarget(editing); setResetPassword(""); setResetFields({}); }}><KeyRound className="size-4" />Redefinir senha</Button>}<Link className="btn btn-secondary" href={`/usuarios/bloqueios?user=${editing.id}`}><ShieldX className="size-4" />Bloqueios de acesso</Link></div></div>}
              {editorTab === "history" && <div><h2 className="text-sm font-bold">Histórico</h2><p className="mt-1 text-xs text-muted">Eventos auditáveis deste usuário na empresa atual.</p>{historyLoading ? <TableLoading columns={3} /> : history.length ? <div className="mt-4 divide-y divide-subtle rounded-lg border border-subtle">{history.map((log) => <article key={log.id} className="flex flex-col gap-1 p-3 text-xs sm:flex-row sm:items-center sm:justify-between"><div><strong>{log.action_label}</strong><span className="block text-muted">{log.actor_name || "Sistema"}</span></div><span className="text-muted">{formatDate(log.created_at)}</span></article>)}</div> : <EmptyState title="Sem histórico disponível" description="Nenhum evento específico foi encontrado neste contexto." />}</div>}
            </>}
          </fieldset>
          {!editing && <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancelar</Button><Button type="submit" loading={saving}>Criar usuário</Button></div>}
        </form>
        {editing && editorTab === "commission" && <UserCommissionSection userId={editing.id} />}
        {editing && <div className="flex items-center justify-between border-t border-subtle p-4 sm:px-6"><Button type="button" variant="secondary" disabled={editorTab === editorTabs[0][0]} onClick={() => { const index = editorTabs.findIndex(([value]) => value === editorTab); if (index > 0) setEditorTab(editorTabs[index - 1][0]); }}><ArrowLeft className="size-4" />Anterior</Button><Button type="button" variant="secondary" disabled={editorTab === editorTabs[editorTabs.length - 1][0]} onClick={() => { const index = editorTabs.findIndex(([value]) => value === editorTab); if (index < editorTabs.length - 1) setEditorTab(editorTabs[index + 1][0]); }}>Próximo<ArrowRight className="size-4" /></Button></div>}
       </UserEditorFrame>
      <ConfirmDialog
        open={!!confirming}
        title={`${confirming?.membership?.is_active ? "Inativar" : "Ativar"} usuário`}
        message={`Confirma a alteração de status de “${confirming?.first_name || ""} ${confirming?.last_name || ""}”?`}
        confirmLabel={confirming?.membership?.is_active ? "Inativar" : "Ativar"}
        danger={confirming?.membership?.is_active}
        loading={saving}
        onClose={() => setConfirming(null)}
        onConfirm={changeStatus}
      />
      <ConfirmDialog
        open={!!archiving}
        title="Arquivar usuário"
        message={`Arquivar “${archiving?.first_name || ""} ${archiving?.last_name || ""}”? O acesso será removido da operação, mas vendas, caixa, estoque, auditoria e comissões permanecerão preservados.`}
        confirmLabel="Arquivar"
        danger
        loading={saving}
        onClose={() => setArchiving(null)}
        onConfirm={archiveUser}
      />
      <Modal open={!!resetTarget} title="Redefinir senha" onClose={() => setResetTarget(null)}>
        <div className="space-y-4 p-5">
          <p className="text-sm text-muted">Defina uma nova senha para {resetTarget?.first_name} {resetTarget?.last_name} ({resetTarget?.email}).</p>
          <Field label="Nova senha" error={fieldError(resetFields, "new_password")}>
            <Input type="password" required value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} disabled={resetSaving} autoComplete="new-password" />
          </Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4">
            <Button variant="secondary" onClick={() => setResetTarget(null)}>Cancelar</Button>
            <Button loading={resetSaving} onClick={() => void doResetPassword()}>Redefinir senha</Button>
          </div>
        </div>
      </Modal>
      <Modal
        open={!!restoreConflict}
        title="Restaurar usuário"
        description="Esta identidade já existiu na empresa atual."
        onClose={() => !saving && setRestoreConflict(null)}
      >
        <div className="space-y-4 p-5">
          <div className="rounded-lg border border-subtle bg-surface-soft p-4 text-sm">
            <strong className="block text-fg">{restoreConflict?.name}</strong>
            <span className="mt-1 block text-muted">
              E-mail: {restoreConflict?.email || "Não informado"}
            </span>
            <span className="block text-muted">
              Excluído em: {restoreConflict ? formatDate(restoreConflict.archivedAt) : ""}
            </span>
          </div>
          <p className="text-sm text-muted">
            O mesmo ID e o histórico serão preservados. Somente o vínculo desta
            empresa será restaurado com a configuração de Backoffice selecionada
            no formulário.
          </p>
          <div className="flex justify-end gap-2 border-t border-subtle pt-4">
            <Button
              type="button"
              variant="secondary"
              disabled={saving}
              onClick={() => setRestoreConflict(null)}
            >
              Cancelar
            </Button>
            <Button type="button" loading={saving} onClick={() => void restoreUser()}>
              Restaurar usuário
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

export default function UsersPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewUser]}>
      <>
        <UsersAdministration />
      </>
    </AdminGuard>
  );
}
