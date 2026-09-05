"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { CheckCircle2, KeyRound, ShieldCheck } from "lucide-react";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, http } from "@/lib/http";

function tokenError(caught: unknown) {
  if (caught instanceof ApiError) {
    if (caught.code === "pin_reset_token_invalid" || caught.status === 400)
      return "Este link de PIN é inválido, expirou ou já foi utilizado. Solicite um novo link ao administrador.";
    if (caught.status >= 500)
      return "Não foi possível configurar o PIN agora. Tente novamente em alguns instantes.";
    return caught.message;
  }
  return "Não foi possível configurar o PIN. Verifique sua conexão e tente novamente.";
}

export default function PosPinPage() {
  const params = useSearchParams();
  const token = params.get("token") || "";
  const [pin, setPin] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(token ? "" : "Este link de PIN é inválido, expirou ou já foi utilizado.");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!/^\d{6}$/.test(pin)) {
      setError("O PIN deve ter exatamente 6 dígitos numéricos.");
      return;
    }
    if (pin !== confirmation) {
      setError("A confirmação do PIN não corresponde.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await http.postPublic("pos/pin/confirm/", { token, pin });
      setSuccess(true);
      setPin("");
      setConfirmation("");
    } catch (caught) {
      setError(tokenError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-canvas px-5 py-10">
      <div className="absolute inset-x-0 top-0 h-72 bg-[radial-gradient(ellipse_at_top,_rgba(52,84,209,0.18),transparent_70%)]" />
      <section className="relative w-full max-w-md">
        <div className="mb-8 flex justify-center"><BrandWordmark imageClassName="h-10 max-w-52" /></div>
        <div className="rounded-3xl border border-subtle bg-surface p-6 shadow-[0_24px_60px_rgba(40,60,80,0.13)] sm:p-9">
          {success ? (
            <div className="py-5 text-center">
              <CheckCircle2 className="mx-auto size-14 text-success" />
              <h1 className="mt-5 text-2xl font-bold text-dark">PIN configurado</h1>
              <p className="mt-3 text-sm leading-6 text-muted">PIN configurado com sucesso. Você já pode acessar o CORE PDV.</p>
            </div>
          ) : (
            <>
              <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary"><KeyRound className="size-6" /></div>
              <p className="mt-6 text-xs font-bold uppercase tracking-[0.14em] text-primary">Segurança do dispositivo</p>
              <h1 className="mt-2 text-2xl font-bold text-dark">Criar PIN do CORE PDV</h1>
              <p className="mt-3 text-sm leading-6 text-muted">Use um PIN pessoal de seis dígitos para entrar no CORE PDV neste dispositivo.</p>
              <form className="mt-7 space-y-5" onSubmit={submit}>
                {error && <Alert message={error} />}
                <Field label="Novo PIN">
                  <Input type="password" inputMode="numeric" autoComplete="new-password" pattern="[0-9]{6}" maxLength={6} required disabled={submitting || !token} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))} />
                </Field>
                <Field label="Confirmar PIN">
                  <Input type="password" inputMode="numeric" autoComplete="new-password" pattern="[0-9]{6}" maxLength={6} required disabled={submitting || !token} value={confirmation} onChange={(event) => setConfirmation(event.target.value.replace(/\D/g, ""))} />
                </Field>
                <Button type="submit" className="w-full" loading={submitting} disabled={!token}>Salvar PIN</Button>
              </form>
              <div className="mt-6 flex gap-3 rounded-xl border border-subtle bg-surface-muted p-3 text-xs leading-5 text-muted"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />Seu PIN nunca é exibido ao administrador e este link só pode ser usado uma vez.</div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
