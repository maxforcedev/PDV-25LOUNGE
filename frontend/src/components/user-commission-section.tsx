"use client";

import { useEffect, useState } from "react";
import { Percent } from "lucide-react";
import { Alert, Button, Field, Input, Select, Spinner } from "@/components/ui";
import { decimalCompare, formatEditableDecimal } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";

type CommissionOverride = { id: number; branch: number; user: number; receives_commission: boolean; commission_rate: string | null };
type CommissionMode = "profile" | "none" | "individual";

export function UserCommissionSection({ userId }: { userId: number }) {
  const { currentBranch, hasPermission } = useAuth();
  const canChange = hasPermission(permissions.changeUserCommission);
  const canRead = canChange || hasPermission(permissions.viewCommission);
  const [override, setOverride] = useState<CommissionOverride | null>(null);
  const [mode, setMode] = useState<CommissionMode>("profile");
  const [rate, setRate] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!currentBranch || !canRead) { setLoading(false); return; }
    setLoading(true); setError("");
    http.getAll<CommissionOverride>(`user-commission-overrides/?branch=${currentBranch.id}&user=${userId}`)
      .then((items) => {
        const item = items[0] || null;
        setOverride(item);
        setMode(!item ? "profile" : !item.receives_commission ? "none" : item.commission_rate !== null ? "individual" : "profile");
         setRate(formatEditableDecimal(item?.commission_rate || ""));
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar a comissão."))
      .finally(() => setLoading(false));
  }, [currentBranch?.id, canRead, userId]);

  if (!canRead) return <div className="p-5 text-xs text-muted">Sem permissão para consultar comissão.</div>;

  async function save() {
    if (!currentBranch || !canChange) return;
    if (mode === "individual" && (!rate.trim() || decimalCompare(rate, "0") === -1 || decimalCompare(rate, "100") === 1)) { setError("Informe um percentual entre 0 e 100."); return; }
    setSaving(true); setError(""); setSuccess("");
    try {
      if (mode === "profile") {
        if (override) await http.delete(`user-commission-overrides/${override.id}/`);
        setOverride(null);
      } else {
        const payload = { branch: currentBranch.id, user: userId, receives_commission: mode === "individual", commission_rate: mode === "individual" ? rate : null };
        const saved = override ? await http.patch<CommissionOverride>(`user-commission-overrides/${override.id}/`, payload) : await http.post<CommissionOverride>("user-commission-overrides/", payload);
         setOverride(saved);
         setRate(formatEditableDecimal(saved.commission_rate || ""));
      }
      setSuccess("Configuração de comissão atualizada.");
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível salvar a comissão."); }
    finally { setSaving(false); }
  }

  return <div className="space-y-5 p-5 sm:p-6">
    <div className="flex items-center gap-3"><span className="rounded-lg bg-primary/10 p-2 text-primary"><Percent className="size-5" /></span><div><h2 className="text-sm font-bold">Configuração de comissão</h2><p className="text-xs text-muted">Regras aplicadas somente à filial {currentBranch?.name || "atual"}.</p></div></div>
    {error && <Alert message={error} />}{success && <Alert type="success" message={success} />}
    {loading ? <div className="flex min-h-32 items-center justify-center"><Spinner className="size-5" /></div> : <div className="grid gap-4 sm:max-w-xl sm:grid-cols-2">
      <Field label="Regra"><Select value={mode} onChange={(event) => setMode(event.target.value as CommissionMode)} disabled={!canChange}><option value="profile">Usar perfil/filial</option><option value="none">Não recebe comissão</option><option value="individual">Percentual individual</option></Select></Field>
      {mode === "individual" && <Field label="Percentual (%)"><Input type="number" min="0" max="100" step="0.01" value={rate} onChange={(event) => setRate(event.target.value)} disabled={!canChange} /></Field>}
    </div>}
    {canChange && !loading && <Button type="button" loading={saving} onClick={() => void save()}>Salvar comissão</Button>}
  </div>;
}
