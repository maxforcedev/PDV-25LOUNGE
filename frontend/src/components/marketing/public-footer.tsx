"use client";

import Link from "next/link";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { useBranding } from "@/providers/branding-provider";

export function PublicFooter() {
  const branding = useBranding();
  const phoneHref = branding.support_phone.replace(/[^\d+]/g, "");
  const institutionalLinks = Object.entries(branding.institutional_links).slice(0, 2);
  return (
    <footer className="border-t border-subtle bg-surface">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1fr_auto] lg:px-8">
        <div>
          <BrandWordmark compact />
          <p className="mt-4 max-w-md text-xs leading-6 text-muted">
            Gestão operacional e ponto de venda para bares, restaurantes, lounges e casas de eventos.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-x-10 gap-y-3 text-xs">
          <Link href="/#recursos" className="font-semibold text-muted hover:text-fg">Recursos</Link>
          <Link href="/planos" className="font-semibold text-muted hover:text-fg">Planos</Link>
          <Link href="/cadastro" className="font-semibold text-muted hover:text-fg">Criar conta</Link>
          <Link href="/ajuda" className="font-semibold text-muted hover:text-fg">Central de ajuda</Link>
          <Link href="/#seguranca" className="font-semibold text-muted hover:text-fg">Segurança</Link>
          <Link href="/login" className="font-semibold text-muted hover:text-fg">Área de clientes</Link>
          {branding.support_email && <a href={`mailto:${branding.support_email}`} className="font-semibold text-muted hover:text-fg">{branding.support_email}</a>}
          {branding.support_phone && <a href={`tel:${phoneHref}`} className="font-semibold text-muted hover:text-fg">{branding.support_phone}</a>}
          {institutionalLinks.map(([label, url]) => <a key={label} href={url} target="_blank" rel="noreferrer" className="font-semibold capitalize text-muted hover:text-fg">{label.replaceAll("_", " ")}</a>)}
        </div>
      </div>
      <div className="border-t border-subtle">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-[11px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span>{branding.platform_name} · Operação conectada, do caixa ao relatório.</span>
          <span>Interface em português brasileiro.</span>
        </div>
      </div>
    </footer>
  );
}
