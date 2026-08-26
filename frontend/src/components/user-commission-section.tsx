"use client";

import { useEffect, useState } from "react";
import { Percent, Pencil } from "lucide-react";
import { Alert, Button, EmptyState, Field, Input, Modal, Select, TableLoading } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { User } from "@/types";

type CommissionOverride = {
  id: number;
  branch: number;
  user: number;
  receives_commission: boolean;
  commission_rate: string | null;
};

type CommissionMode = "profile" | "none" | "individual";

export function UserCommissionSection({ userId }: { userId?: number } = {}) {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const canChange = hasPermission(permissions.changeUserCommission);
  const canRead = canChange || hasPermission(permissions.viewCommission);
  const [users, setUsers] = useState<User[]>([]);
  const [overrides, setOverrides] = useState<CommissionOverride[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<User | null>(null);
  const [mode, setMode] = useState<CommissionMode>("profile");
  const [rate, setRate] = useState("");
  const [formError, setFormError] = useState("");
  const [rateError, setRateError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const companyId = currentCompany?.id;
    const branchId = currentBranch?.id;
    setEditing(null);
    setSuccess("");
    if (!companyId || !branchId || !canRead) {
      setUsers([]);
      setOverrides([]);
      return;
    }

    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      http.getAll<User>(`users/?company=${companyId}`),
      http.getAll<CommissionOverride>(`user-commission-overrides/?branch=${branchId}`),
    ]).then(([userItems, overrideItems]) => {
      if (!active) return;
      setUsers(userItems.filter((user) => (
        (!userId || user.id === userId)
        &&
        user.is_active
        && user.branches.some((branch) => (
          branch.id === branchId
          && branch.status === "active"
          && !!branch.access_profile
        ))
      )));
      setOverrides(overrideItems);
    }).catch((caught) => {
      if (active) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as comissões individuais.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [currentCompany?.id, currentBranch?.id, canRead, userId]);

  if (!canRead) return null;

  function show(user: User) {
    if (!canChange) return;
    const override = overrides.find((item) => item.user === user.id);
    setEditing(user);
    setMode(
      !override ? "profile"
        : !override.receives_commission ? "none"
          : override.commission_rate !== null ? "individual" : "profile"
    );
    setRate(override?.commission_rate || "");
    setFormError("");
    setRateError("");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!editing || !currentBranch || !canChange) return;
    const existing = overrides.find((item) => item.user === editing.id);
    if (mode === "individual") {
      const percentage = Number(rate);
      if (!rate.trim() || !Number.isFinite(percentage) || percentage < 0 || percentage > 100) {
        setRateError("Informe um percentual entre 0 e 100.");
        return;
      }
    }

    setSaving(true);
    setFormError("");
    setRateError("");
    try {
      if (mode === "profile") {
        if (existing) await http.delete(`user-commission-overrides/${existing.id}/`);
        setOverrides((items) => items.filter((item) => item.user !== editing.id));
      } else {
        const payload = {
          branch: currentBranch.id,
          user: editing.id,
          receives_commission: mode === "individual",
          commission_rate: mode === "individual" ? rate : null,
        };
        const saved = existing
          ? await http.patch<CommissionOverride>(`user-commission-overrides/${existing.id}/`, payload)
          : await http.post<CommissionOverride>("user-commission-overrides/", payload);
        setOverrides((items) => [...items.filter((item) => item.user !== editing.id), saved]);
      }
      setEditing(null);
      setSuccess("Configuração de comissão atualizada.");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setFormError(caught.message);
        setRateError(caught.fields.commission_rate?.[0] || "");
      } else {
        setFormError("Não foi possível atualizar a comissão individual.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="px-4 pb-4 sm:px-6 sm:pb-6 lg:px-8 lg:pb-8">
      {success && <div className="mb-4"><Alert type="success" message={success} /></div>}
      <section className="card overflow-hidden">
        <div className="card-header">
          <div>
            <h2 className="text-sm font-bold">Comissão individual</h2>
            <p className="mt-1 text-[11px] text-slate-500">
              Configuração da filial {currentBranch?.name || "atual"}. Sem override, vale o perfil e depois o padrão da filial.
            </p>
          </div>
          <Percent className="size-5 text-slate-300" />
        </div>
        {error && <div className="m-4"><Alert message={error} /></div>}
        {loading ? <TableLoading /> : users.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Usuário</th><th>Perfil da filial</th><th>Configuração</th>{canChange && <th className="text-right">Ação</th>}</tr></thead>
              <tbody>{users.map((user) => {
                const branchAccess = user.branches.find((branch) => branch.id === currentBranch?.id);
                const override = overrides.find((item) => item.user === user.id);
                const description = !override
                  ? "Usar configuração do perfil"
                  : !override.receives_commission
                    ? "Não recebe comissão"
                    : override.commission_rate === null
                      ? "Usar configuração do perfil"
                      : `${override.commission_rate}% individual`;
                return (
                  <tr key={user.id}>
                    <td><strong>{user.first_name} {user.last_name}</strong><small className="block text-slate-400">{user.email || "Sem e-mail"}</small></td>
                    <td>{branchAccess?.access_profile?.name || "Sem perfil"}</td>
                    <td><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold">{description}</span></td>
                    {canChange && <td className="text-right"><Button type="button" variant="secondary" onClick={() => show(user)}><Pencil className="size-3.5" />Configurar</Button></td>}
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        ) : !error && <EmptyState title="Sem usuários elegíveis" description="Nenhum usuário ativo possui acesso e perfil ativos nesta filial." />}
        {!canChange && <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">Somente leitura. A alteração individual está indisponível ou bloqueada nesta filial.</p>}
      </section>

      <Modal
        open={!!editing}
        title={`Comissão de ${editing?.first_name || ""} ${editing?.last_name || ""}`}
        description={`A escolha vale somente para ${currentBranch?.name || "a filial atual"}.`}
        onClose={() => { if (!saving) setEditing(null); }}
        size="md"
      >
        <form onSubmit={submit}>
          <div className="space-y-4 p-5 sm:p-6">
            {formError && <Alert message={formError} />}
            <Field label="Configuração">
              <Select value={mode} onChange={(event) => setMode(event.target.value as CommissionMode)} disabled={saving}>
                <option value="profile">Usar configuração do perfil</option>
                <option value="none">Não recebe comissão</option>
                <option value="individual">Percentual individual</option>
              </Select>
            </Field>
            {mode === "profile" && <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">Ao salvar, o override existente será excluído. A comissão seguirá o perfil e, se ele não definir percentual, a filial.</p>}
            {mode === "none" && <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">As novas vendas deste usuário não gerarão comissão nesta filial.</p>}
            {mode === "individual" && (
              <Field label="Percentual individual (%)" error={rateError}>
                <Input required type="number" inputMode="decimal" min="0" max="100" step="0.01" value={rate} onChange={(event) => setRate(event.target.value)} disabled={saving} />
              </Field>
            )}
          </div>
          <div className="modal-footer flex justify-end gap-2 border-t px-5 py-4 sm:px-6">
            <Button type="button" variant="secondary" onClick={() => setEditing(null)} disabled={saving}>Cancelar</Button>
            <Button type="submit" loading={saving}>Salvar configuração</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
