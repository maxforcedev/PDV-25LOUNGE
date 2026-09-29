"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { friendlyError, http } from "@/lib/http";

type FormState = {
  name: string;
  company_name: string;
  whatsapp: string;
  email: string;
  segment: string;
  message: string;
  honeypot: string;
};

const initialState: FormState = {
  name: "", company_name: "", whatsapp: "", email: "", segment: "", message: "", honeypot: "",
};

export function ContactForm() {
  const searchParams = useSearchParams();
  const [form, setForm] = useState(initialState);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  const plan = searchParams.get("plano") || "";
  const utm = {
    utm_source: searchParams.get("utm_source") || "",
    utm_medium: searchParams.get("utm_medium") || "",
    utm_campaign: searchParams.get("utm_campaign") || "",
  };

  useEffect(() => {
    setSent(false);
  }, [plan]);

  function update(field: keyof FormState, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSending(true);
    try {
      await http.postPublic("public/leads/", {
        ...form,
        source_path: `${window.location.pathname}${window.location.search}`,
        plan_interest: plan,
        ...utm,
      });
      setSent(true);
      setForm(initialState);
    } catch (caught) {
      setError(friendlyError(caught, "Não foi possível enviar seu contato. Tente novamente.").message);
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return <div className="border border-success/30 bg-success-surface p-6 text-sm leading-6 text-success-strong" role="status">Recebemos seu contato. Nossa equipe falará com você.</div>;
  }

  return (
    <form className="border border-subtle bg-surface p-5 sm:p-7" onSubmit={submit}>
      {plan && <p className="mb-6 border-b border-subtle pb-4 text-xs text-muted">Plano de interesse: <strong className="text-fg">{plan}</strong></p>}
      <div className="grid gap-5 sm:grid-cols-2">
        <label><span className="label">Nome</span><input className="input" required value={form.name} onChange={(event) => update("name", event.target.value)} autoComplete="name" /></label>
        <label><span className="label">Empresa</span><input className="input" required value={form.company_name} onChange={(event) => update("company_name", event.target.value)} autoComplete="organization" /></label>
        <label><span className="label">WhatsApp</span><input className="input" required value={form.whatsapp} onChange={(event) => update("whatsapp", event.target.value)} inputMode="tel" autoComplete="tel" /></label>
        <label><span className="label">E-mail</span><input className="input" required type="email" value={form.email} onChange={(event) => update("email", event.target.value)} autoComplete="email" /></label>
        <label className="sm:col-span-2"><span className="label">Segmento</span><select className="input" required value={form.segment} onChange={(event) => update("segment", event.target.value)}><option value="">Selecione</option><option>Bares e restaurantes</option><option>Lounges e casas noturnas</option><option>Eventos</option><option>Food service</option><option>Varejo</option><option>Outro</option></select></label>
        <label className="sm:col-span-2"><span className="label">Mensagem <span className="font-normal text-muted">(opcional)</span></span><textarea className="textarea" value={form.message} onChange={(event) => update("message", event.target.value)} /></label>
        <label className="sr-only" aria-hidden="true">Não preencha este campo<input tabIndex={-1} autoComplete="off" value={form.honeypot} onChange={(event) => update("honeypot", event.target.value)} /></label>
      </div>
      {error && <p className="field-error mt-5" role="alert">{error}</p>}
      <button className="btn btn-primary mt-6 h-12 w-full rounded-xl sm:w-auto" disabled={sending}>{sending ? "Enviando..." : "Quero conhecer o CORE"}<ArrowRight className="size-4" /></button>
    </form>
  );
}
