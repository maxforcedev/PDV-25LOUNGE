"use client";

import Link from "next/link";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { useBranding } from "@/providers/branding-provider";

export function PublicFooter() {
  const branding = useBranding();
  const phoneHref = branding.support_phone.replace(/[^\d+]/g, "");
  const links = [
    ["Soluções", "/solucoes"], ["Integrações", "/#integracoes"], ["Segmentos", "/#segmentos"],
    ["Planos", "/planos"], ["Segurança", "/#seguranca"], ["Empresa", "/#empresa"],
    ["Ajuda", "/ajuda"], ["Contato", "/contato"], ["Área do cliente", "/login"],
  ];
  return (
    <footer className="border-t border-subtle bg-surface">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1fr_1.1fr] lg:px-8">
        <div><BrandWordmark compact /><p className="mt-4 max-w-sm text-xs leading-6 text-muted">CORE conecta a operação no ponto de venda ao controle de gestão, sem separar o que acontece na casa do que precisa ser acompanhado depois.</p></div>
        <nav className="grid grid-cols-2 gap-x-8 gap-y-3 text-xs sm:grid-cols-3" aria-label="Links institucionais">{links.map(([label, href]) => <Link key={label} href={href} className="font-semibold text-muted hover:text-fg">{label}</Link>)}{branding.institutional_links.privacy && <a href={branding.institutional_links.privacy} className="font-semibold text-muted hover:text-fg">Privacidade</a>}{branding.institutional_links.terms && <a href={branding.institutional_links.terms} className="font-semibold text-muted hover:text-fg">Termos</a>}</nav>
      </div>
      <div className="border-t border-subtle"><div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-[11px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8"><span>{branding.platform_name}</span><span>{branding.support_email && <a className="hover:text-fg" href={`mailto:${branding.support_email}`}>{branding.support_email}</a>}{branding.support_email && branding.support_phone && " · "}{branding.support_phone && <a className="hover:text-fg" href={`tel:${phoneHref}`}>{branding.support_phone}</a>}</span></div></div>
    </footer>
  );
}
