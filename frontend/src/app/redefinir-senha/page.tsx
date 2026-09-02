"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, http } from "@/lib/http";

export default function ResetPasswordPage() {
  const params = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirmation) {
      setError("A confirmação de senha não corresponde.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await http.post("auth/password-reset/confirm/", {
        uid: params.get("uid") || "",
        token: params.get("token") || "",
        new_password: password,
      });
      setSuccess(true);
      setPassword("");
      setConfirmation("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível redefinir a senha.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-5 py-10">
      <div className="w-full max-w-md">
        <div className="card p-6 sm:p-8">
          <div className="mb-7 flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary"><KeyRound className="size-5" /></div>
          <h1 className="text-2xl font-bold text-dark">Definir nova senha</h1>
          <p className="mt-2 text-sm text-muted">A nova senha será válida em todas as empresas vinculadas à sua identidade CORE.</p>
          <form className="mt-6 space-y-5" onSubmit={submit}>
            {success && <Alert type="success" message="Senha redefinida com sucesso. Entre novamente com a nova senha." />}
            {error && <Alert message={error} />}
            {!success && <>
              <Field label="Nova senha"><Input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} disabled={submitting} /></Field>
              <Field label="Confirmar nova senha"><Input type="password" autoComplete="new-password" minLength={8} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={submitting} /></Field>
              <Button type="submit" className="w-full" loading={submitting}>Redefinir senha</Button>
            </>}
          </form>
          <Link href="/login" className="mt-5 block text-center text-xs font-semibold text-primary hover:underline">Ir para o login</Link>
        </div>
      </div>
    </main>
  );
}
