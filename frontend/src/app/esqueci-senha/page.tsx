"use client";

import Link from "next/link";
import { useState } from "react";
import { KeyRound } from "lucide-react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, http } from "@/lib/http";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await http.post<{ detail: string }>(
        "auth/password-reset/",
        { email: email.trim() },
      );
      setMessage(response.detail);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível solicitar a redefinição.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-5 py-10">
      <div className="w-full max-w-md">
        <div className="card p-6 sm:p-8">
          <div className="mb-7 flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <KeyRound className="size-5" />
          </div>
          <h1 className="text-2xl font-bold text-dark">Recuperar senha</h1>
          <p className="mt-2 text-sm text-muted">Enviaremos as instruções para o e-mail da sua identidade CORE.</p>
          <form className="mt-6 space-y-5" onSubmit={submit}>
            {message && <Alert type="success" message={message} />}
            {error && <Alert message={error} />}
            <Field label="E-mail">
              <Input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} disabled={submitting || !!message} />
            </Field>
            <Button type="submit" className="w-full" loading={submitting} disabled={!!message}>Enviar instruções</Button>
          </form>
          <Link href="/login" className="mt-5 block text-center text-xs font-semibold text-primary hover:underline">Voltar ao login</Link>
        </div>
      </div>
    </main>
  );
}
