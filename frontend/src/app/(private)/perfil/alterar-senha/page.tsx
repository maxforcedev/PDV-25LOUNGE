"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input } from "@/components/ui";
import { fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";

export default function ChangePasswordPage() {
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (form.new_password !== form.confirm_password) {
      setError("A confirmação de senha não corresponde.");
      return;
    }
    setSaving(true);
    setFields({});
    try {
      await http.post("auth/change-password/", { current_password: form.current_password, new_password: form.new_password });
      setSuccess("Senha alterada com sucesso.");
      setForm({ current_password: "", new_password: "", confirm_password: "" });
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else {
        setError("Não foi possível alterar a senha.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="Alterar senha" description="Mantenha sua senha segura e atualizada." />
      <div className="p-4 sm:p-6 lg:p-8">
        <section className="card max-w-lg self-start">
          <div className="card-header"><div><h2 className="text-sm font-bold">Alteração de senha</h2><p className="mt-1 text-[11px] text-slate-500">Informe sua senha atual e a nova senha</p></div><KeyRound className="size-5 text-slate-300" /></div>
          <form onSubmit={submit}>
            <div className="space-y-5 p-5 sm:p-6">
              {error && <Alert message={error} />}
              {success && <Alert type="success" message={success} />}
              <Field label="Senha atual" error={fieldError(fields, "current_password")}><Input type="password" required value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} disabled={saving} autoComplete="current-password" /></Field>
              <Field label="Nova senha" error={fieldError(fields, "new_password")}><Input type="password" required value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} disabled={saving} autoComplete="new-password" /></Field>
              <Field label="Confirmar nova senha"><Input type="password" required value={form.confirm_password} onChange={(e) => setForm({ ...form, confirm_password: e.target.value })} disabled={saving} autoComplete="new-password" /></Field>
            </div>
            <div className="flex justify-end border-t border-slate-100 px-5 py-4 sm:px-6"><Button type="submit" loading={saving}>Alterar senha</Button></div>
          </form>
        </section>
      </div>
    </>
  );
}
