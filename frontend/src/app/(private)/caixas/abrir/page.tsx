"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Banknote, LockKeyhole } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Input, Select, Spinner } from "@/components/ui";
import { moneyToCents, normalizeMoney } from "@/lib/cash";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { CashRegister, CashSession } from "@/types";

function OpenRegister() {
  const { currentCompany, currentBranch } = useAuth();
  const router = useRouter();
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [registers, setRegisters] = useState<CashRegister[]>([]);
  const [registerId, setRegisterId] = useState("");
  const [openingAmount, setOpeningAmount] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const context = contextRef.current;
    setRegisters([]); setRegisterId(""); setOpeningAmount(""); setError("");
    if (!currentBranch) { setLoading(false); return; }
    setLoading(true);
    http.getAll<CashRegister>("cash-registers/?status=active").then((response) => {
      if (contextRef.current !== context) return;
      const available = response.filter((register) => !register.open_session);
      setRegisters(available);
      const requested = new URLSearchParams(window.location.search).get("register") || "";
      setRegisterId(available.some((register) => String(register.id) === requested) ? requested : "");
    }).catch((caught) => {
      if (contextRef.current === context) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os caixas disponíveis.");
    }).finally(() => { if (contextRef.current === context) setLoading(false); });
  }, [currentCompany?.id, currentBranch?.id]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!registerId || moneyToCents(openingAmount) === null) { setError("Selecione um caixa e informe um valor de abertura válido, com no máximo duas casas decimais."); return; }
    const context = contextRef.current;
    setSaving(true); setError("");
    try {
      const session = await http.post<CashSession>("cash-sessions/open/", { cash_register: Number(registerId), opening_amount: normalizeMoney(openingAmount) });
      if (contextRef.current === context) {
        const returnTo = new URLSearchParams(window.location.search).get("return");
        router.push(returnTo && returnTo.startsWith("/") ? returnTo : `/caixas/sessoes/${session.id}`);
      }
    } catch (caught) {
      if (contextRef.current === context) setError(caught instanceof ApiError ? caught.message : "Não foi possível abrir o caixa.");
    } finally { if (contextRef.current === context) setSaving(false); }
  }

  return <>
    <PageHeader title="Abrir caixa" description={`Filial atual: ${currentBranch?.name || "nenhuma filial selecionada"}.`} action={<Link href="/caixas" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar aos caixas</Link>} />
    <div className="mx-auto max-w-3xl p-4 sm:p-6 lg:p-8">
      {error && <div className="mb-4"><Alert message={error} /></div>}
      {loading ? <div className="card flex min-h-64 items-center justify-center text-primary"><Spinner className="size-7" /></div> : !registers.length ? <div className="card"><EmptyState title="Nenhum caixa disponível" description="Todos os caixas ativos desta filial já possuem sessão aberta ou ainda não há caixas ativos cadastrados." /><div className="flex justify-center pb-8"><Link href="/caixas" className="btn btn-secondary">Ver caixas da filial</Link></div></div> :
      <form className="card overflow-hidden" onSubmit={submit}>
        <div className="card-header"><div><h2 className="text-sm font-bold">Dados da abertura</h2><p className="mt-1 text-[11px] text-slate-500">A abertura ficará vinculada ao seu usuário e à filial atual.</p></div><div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Banknote className="size-5" /></div></div>
        <div className="grid gap-5 p-5 sm:p-6">
          <Field label="Caixa"><Select required value={registerId} onChange={(event) => setRegisterId(event.target.value)}><option value="">Selecione um caixa sem sessão aberta</option>{registers.map((register) => <option key={register.id} value={register.id}>{register.name}</option>)}</Select></Field>
          <Field label="Valor inicial"><div className="relative"><span className="absolute left-3 top-2.5 text-sm font-semibold text-slate-400">R$</span><Input className="pl-10" required inputMode="decimal" value={openingAmount} onChange={(event) => setOpeningAmount(event.target.value)} placeholder="0,00" /></div></Field>
          <div className="flex items-start gap-3 rounded-lg border border-primary/15 bg-primary/5 p-4 text-xs leading-5 text-slate-600"><LockKeyhole className="mt-0.5 size-4 shrink-0 text-primary" /><p>O valor é enviado como texto decimal, sem conversão para ponto flutuante. Confirme o numerário físico antes de abrir.</p></div>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4 sm:px-6"><Link href={new URLSearchParams(typeof window !== "undefined" ? window.location.search : "").get("return") || "/caixas"} className="btn btn-secondary">Cancelar</Link><Button type="submit" loading={saving}>Confirmar abertura</Button></div>
      </form>}
    </div>
  </>;
}

export default function OpenRegisterPage() { return <AdminGuard requiredPermissions={[permissions.openCashRegister]} requiredFeatures={["cash_register"]}><OpenRegister /></AdminGuard>; }
