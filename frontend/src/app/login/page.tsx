"use client";

import { useState } from "react";
import Link from "next/link";
import { Eye, EyeOff, LockKeyhole, ShieldCheck } from "lucide-react";
import { Alert, Button, Field, Input, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/http";
import { useAuth } from "@/providers/auth-provider";
import { useBranding } from "@/providers/branding-provider";

export default function LoginPage() {
  const { login, loading: authLoading, user } = useAuth();
  const branding = useBranding();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email.trim(), password);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível entrar.");
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading || user) return <div className="flex min-h-screen items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Carregando</span></div>;

  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden bg-dark p-14 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute -right-32 -top-28 size-96 rounded-full border-[70px] border-primary/15" />
        <div className="absolute -bottom-40 -left-28 size-96 rounded-full bg-primary/10 blur-2xl" />
        <div className="relative flex items-center gap-3"><div className="flex size-10 items-center justify-center rounded-lg bg-primary"><ShieldCheck className="size-5" /></div><div><strong className="block text-sm tracking-wide">{branding.platform_name}</strong><span className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Administração</span></div></div>
        <div className="relative max-w-xl"><span className="mb-5 block h-1 w-10 rounded bg-primary" /><h1 className="text-4xl font-bold leading-tight tracking-tight">Gestão clara para uma operação conectada.</h1><p className="mt-5 max-w-lg text-sm leading-7 text-slate-300">Centralize empresas, filiais e permissões em um ambiente seguro, direto e preparado para o dia a dia.</p></div>
        <p className="relative text-[11px] text-slate-500">Acesso protegido por sessão e verificação CSRF.</p>
      </section>
      <section className="flex items-center justify-center bg-canvas px-5 py-10 sm:px-10">
        <div className="w-full max-w-md animate-enter">
          <div className="mb-8 flex items-center gap-3 lg:hidden"><div className="flex size-10 items-center justify-center rounded-lg bg-primary text-white"><ShieldCheck className="size-5" /></div><strong className="text-sm text-dark">{branding.platform_name}</strong></div>
          <div className="card p-6 sm:p-8">
            <div className="mb-7"><div className="mb-5 flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary"><LockKeyhole className="size-5" /></div><h2 className="text-2xl font-bold tracking-tight text-dark">Acesse sua conta</h2><p className="mt-2 text-[13px] text-slate-500">Informe suas credenciais para continuar.</p></div>
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && <Alert message={error} />}
              <Field label="E-mail"><Input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="voce@empresa.com.br" disabled={submitting} /></Field>
              <Field label="Senha"><div className="relative"><Input type={showPassword ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Digite sua senha" className="pr-11" disabled={submitting} /><button type="button" className="icon-button absolute right-0.5 top-1/2 -translate-y-1/2" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Ocultar senha" : "Exibir senha"}>{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div></Field>
              <Button type="submit" className="w-full" loading={submitting}>Entrar</Button>
            </form>
          </div>
          <div className="mt-5 flex items-center justify-between gap-4 px-1 text-[11px] font-semibold text-muted">
            <Link href="/" className="transition hover:text-fg">Página inicial</Link>
            <Link href="/ajuda" className="transition hover:text-fg">Central de ajuda</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
