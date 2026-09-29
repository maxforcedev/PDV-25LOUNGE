"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useBranding } from "@/providers/branding-provider";

const COOKIE_NAME = "core_cookie_consent_v1";
const STORAGE_KEY = "core.cookie-consent.v1";
type Preference = { version: 1; analytics: boolean; marketing: boolean };

function readPreference(): Preference | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY) || document.cookie.split("; ").find((item) => item.startsWith(`${COOKIE_NAME}=`))?.split("=").slice(1).join("=");
    if (!stored) return null;
    const value = JSON.parse(stored.startsWith("%") ? decodeURIComponent(stored) : stored) as Preference;
    return value.version === 1 ? value : null;
  } catch { return null; }
}

function persist(preference: Preference) {
  const serialized = JSON.stringify(preference);
  window.localStorage.setItem(STORAGE_KEY, serialized);
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(serialized)}; Max-Age=31536000; Path=/; SameSite=Lax`;
  window.dispatchEvent(new CustomEvent("core:cookie-consent", { detail: preference }));
}

export function CookieConsent() {
  const branding = useBranding();
  const pathname = usePathname();
  const [preference, setPreference] = useState<Preference | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const [marketing, setMarketing] = useState(false);

  useEffect(() => {
    const current = readPreference();
    setPreference(current);
    setAnalytics(current?.analytics || false);
    setMarketing(current?.marketing || false);
    setLoaded(true);
    const open = () => setPreferencesOpen(true);
    window.addEventListener("core:open-cookie-preferences", open);
    return () => window.removeEventListener("core:open-cookie-preferences", open);
  }, []);

  function save(value: Preference) {
    persist(value);
    setPreference(value);
    setPreferencesOpen(false);
  }

  const isPublicPage = ["/", "/ajuda", "/planos", "/contato", "/solucoes", "/login"].some((path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)));
  if (!loaded || !isPublicPage) return null;
  if (!preference && !preferencesOpen) {
    return <aside className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-xl border border-subtle bg-surface p-5 shadow-xl sm:bottom-6" aria-label="Preferências de cookies"><p className="text-sm font-bold text-fg">Sua privacidade no CORE</p><p className="mt-2 text-xs leading-5 text-muted">Usamos recursos necessários para segurança e funcionamento. Analytics e marketing permanecem desativados até a sua escolha.{" "}{branding.institutional_links.cookies && <>Consulte a <a className="font-semibold text-primary hover:underline" href={branding.institutional_links.cookies}>política de cookies</a>.</>}</p><div className="mt-4 flex flex-col gap-2 sm:flex-row"><button className="btn btn-primary" onClick={() => save({ version: 1, analytics: true, marketing: true })}>Aceitar</button><button className="btn btn-secondary" onClick={() => save({ version: 1, analytics: false, marketing: false })}>Recusar</button><button className="btn text-primary" onClick={() => setPreferencesOpen(true)}>Preferências</button></div></aside>;
  }
  if (!preferencesOpen) return null;
  return <div className="fixed inset-0 z-50 flex items-end bg-black/35 p-4 sm:items-center sm:justify-center" role="presentation"><section className="w-full max-w-lg border border-subtle bg-surface p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="cookie-title"><h2 id="cookie-title" className="text-lg font-black text-fg">Preferências de cookies</h2><p className="mt-2 text-xs leading-5 text-muted">Você pode alterar esta escolha a qualquer momento no rodapé.</p><div className="mt-6 space-y-4 border-y border-subtle py-5"><Preference label="Necessários" description="Mantêm segurança, sessão e funcionamento básico." checked disabled onChange={() => undefined} /><Preference label="Analytics" description="Ajuda a entender o uso do site quando essa medição estiver disponível." checked={analytics} onChange={setAnalytics} /><Preference label="Marketing" description="Permite comunicações e campanhas futuras, se forem implementadas." checked={marketing} onChange={setMarketing} /></div><div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end"><button className="btn btn-secondary" onClick={() => setPreferencesOpen(false)}>Cancelar</button><button className="btn btn-primary" onClick={() => save({ version: 1, analytics, marketing })}>Salvar preferências</button></div></section></div>;
}

function Preference({ label, description, checked, disabled = false, onChange }: { label: string; description: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void }) {
  return <label className="flex items-start justify-between gap-5"><span><strong className="text-sm text-fg">{label}</strong><span className="mt-1 block text-xs leading-5 text-muted">{description}</span></span><input className="mt-1 size-4 accent-primary" type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} /></label>;
}
