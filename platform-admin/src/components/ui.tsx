"use client";

import { AlertTriangle, CheckCircle2, LoaderCircle, X } from "lucide-react";
import { useEffect } from "react";
import { ApiError } from "@/lib/api";

export function LoadingBlock({ label = "Carregando dados operacionais" }: { label?: string }) {
  return <div className="panel flex min-h-48 items-center justify-center gap-3 p-8 text-sm text-steel/70"><LoaderCircle className="animate-spin" size={18} />{label}</div>;
}

export function ErrorBlock({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : "Falha inesperada.";
  return <div className="border border-alert/35 bg-red-50 p-4 text-sm text-red-900"><div className="flex gap-2"><AlertTriangle size={18} /><div><strong>Operacao interrompida</strong><p className="mt-1">{message}</p>{retry && <button className="mt-3 text-xs font-bold uppercase underline" onClick={retry}>Tentar novamente</button>}</div></div></div>;
}

export function Notice({ message, error = false }: { message: string; error?: boolean }) {
  return <div className={`flex items-center gap-2 border px-3 py-2 text-sm ${error ? "border-alert/35 bg-red-50 text-red-900" : "border-cyan/30 bg-cyan-50 text-cyan-950"}`}>{error ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}{message}</div>;
}

export function Status({ value, positive }: { value: string; positive?: boolean }) {
  const ok = positive ?? ["ACTIVE", "APPROVED", "TRIALING", "active"].includes(value);
  return <span className={`status ${ok ? "border-cyan/30 bg-cyan-50 text-cyan-900" : value.includes("PENDING") || value === "PAST_DUE" ? "border-amber/35 bg-amber-50 text-amber-900" : "border-line bg-[#e8ebe7] text-steel"}`}><span className={`size-1.5 rounded-full ${ok ? "bg-cyan" : "bg-steel/50"}`} />{value.replaceAll("_", " ")}</span>;
}

export function Modal({ title, description, children, onClose, wide = false }: { title: string; description?: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/70 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><div className={`max-h-[92vh] w-full overflow-y-auto border border-steel bg-paper shadow-2xl ${wide ? "max-w-3xl" : "max-w-lg"}`}><div className="sticky top-0 z-10 flex items-start justify-between border-b border-line bg-paper px-5 py-4"><div><p className="eyebrow">Acao controlada</p><h2 className="mt-1 text-lg font-bold">{title}</h2>{description && <p className="mt-1 text-sm text-steel/70">{description}</p>}</div><button className="p-2 text-steel hover:bg-line/50" onClick={onClose} aria-label="Fechar"><X size={18} /></button></div>{children}</div></div>;
}

export function CriticalFields({ reason, password, onReason, onPassword, error }: { reason: string; password: string; onReason: (value: string) => void; onPassword: (value: string) => void; error?: unknown }) {
  const apiError = error instanceof ApiError ? error : null;
  return <div className="grid gap-4 border-t border-line bg-[#edf0eb] p-5"><div className="field"><label htmlFor="critical-reason">Motivo auditavel</label><textarea id="critical-reason" className="textarea" value={reason} onChange={(event) => onReason(event.target.value)} required placeholder="Registre a justificativa operacional" />{apiError?.fields.reason?.map((item) => <p className="text-xs text-alert" key={item}>{item}</p>)}</div><div className="field"><label htmlFor="critical-password">Confirme sua senha</label><input id="critical-password" className="input" type="password" value={password} onChange={(event) => onPassword(event.target.value)} required autoComplete="current-password" />{apiError?.fields.current_password?.map((item) => <p className="text-xs text-alert" key={item}>{item}</p>)}</div></div>;
}

export function Empty({ title, detail }: { title: string; detail: string }) {
  return <div className="p-10 text-center"><p className="font-bold">{title}</p><p className="mt-1 text-sm text-steel/65">{detail}</p></div>;
}
