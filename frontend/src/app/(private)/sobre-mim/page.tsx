"use client";

import { useEffect, useState } from "react";
import { Building2, GitBranch, ShieldCheck, UserRound } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Field, Input } from "@/components/ui";
import { fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { useAuth } from "@/providers/auth-provider";
import type { UserProfilePayload } from "@/types";

export default function AboutMePage() {
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState<UserProfilePayload>({ first_name: "", last_name: "" });
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (user) setForm({ first_name: user.first_name, last_name: user.last_name });
  }, [user]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFields({});
    setError("");
    setSuccess("");
    try {
      await http.patch("auth/me/", form);
      await refreshUser();
      setSuccess("Seus dados foram atualizados com sucesso.");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else {
        setError("Não foi possível atualizar seus dados.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="Sobre mim" description="Consulte seus acessos e mantenha seus dados pessoais atualizados." />
      <div className="grid gap-6 p-4 sm:p-6 lg:grid-cols-[0.8fr_1.2fr] lg:p-8">
        <section className="card self-start">
          <div className="card-header"><div><h2 className="text-sm font-bold">Dados pessoais</h2><p className="mt-1 text-[11px] text-slate-500">Informações da sua conta</p></div><UserRound className="size-5 text-slate-300" /></div>
          <form onSubmit={submit}>
            <div className="space-y-5 p-5 sm:p-6">
              {error && <Alert message={error} />}
              {success && <Alert type="success" message={success} />}
              <Field label="E-mail"><Input type="email" value={user?.email || ""} readOnly aria-readonly="true" className="bg-slate-50 text-slate-500" /></Field>
              <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                <Field label="Nome" error={fieldError(fields, "first_name")}><Input required value={form.first_name} onChange={(event) => setForm((current) => ({ ...current, first_name: event.target.value }))} disabled={saving} /></Field>
                <Field label="Sobrenome" error={fieldError(fields, "last_name")}><Input required value={form.last_name} onChange={(event) => setForm((current) => ({ ...current, last_name: event.target.value }))} disabled={saving} /></Field>
              </div>
            </div>
            <div className="flex justify-end border-t border-slate-100 px-5 py-4 sm:px-6"><Button type="submit" loading={saving}>Salvar alterações</Button></div>
          </form>
        </section>

        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Empresas e filiais</h2><p className="mt-1 text-[11px] text-slate-500">Resumo somente leitura dos seus vínculos</p></div><Building2 className="size-5 text-slate-300" /></div>
          {user?.companies.length ? (
            <div className="divide-y divide-slate-100">
              {user.companies.map((company) => {
                const branches = user.branches.filter((branch) => branch.company_id === company.id);
                return (
                  <article key={company.id} className="p-5 sm:p-6">
                     <div className="flex flex-wrap items-start justify-between gap-3">
                       <div><h3 className="text-sm font-bold text-dark">{company.trade_name}</h3><p className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500"><ShieldCheck className="size-3.5 text-primary" />Perfil administrativo: <strong className="text-slate-700">{user.is_superuser ? "Superusuário" : company.access_profile?.name || "Sem perfil"}</strong></p></div>
                      <span className="rounded-full bg-primary/8 px-2.5 py-1 text-[11px] font-semibold text-primary">{branches.length} {branches.length === 1 ? "filial" : "filiais"}</span>
                    </div>
                     {branches.length ? <div className="mt-4 grid gap-2 sm:grid-cols-2">{branches.map((branch) => <div key={branch.id} className="flex items-center gap-2.5 rounded-md border border-slate-100 bg-slate-50/70 px-3 py-2.5 text-xs text-slate-600"><GitBranch className="size-3.5 shrink-0 text-primary" /><span><strong className="block font-medium">{branch.name}</strong><small className="text-[10px] text-slate-400">Perfil operacional: {user.is_superuser ? "Superusuário" : branch.access_profile?.name || "Sem perfil"}</small></span></div>)}</div> : <p className="mt-4 rounded-md border border-dashed border-slate-200 p-3 text-center text-[11px] text-slate-400">Nenhuma filial vinculada nesta empresa.</p>}
                  </article>
                );
              })}
            </div>
          ) : <EmptyState title="Nenhuma empresa vinculada" description="Sua conta ainda não possui empresas ou filiais associadas." />}
        </section>
      </div>
    </>
  );
}
