"use client";

import Link from "next/link";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { useBranding } from "@/providers/branding-provider";

type FooterLinkItem = [label: string, href: string];

function FooterLink({ label, href }: { label: string; href: string }) {
  const className = "font-semibold text-muted hover:text-fg";
  return href.startsWith("/")
    ? <Link href={href} className={className}>{label}</Link>
    : <a href={href} className={className}>{label}</a>;
}

export function PublicFooter() {
  const branding = useBranding();
  const links = branding.institutional_links;
  const legal = branding.legal_settings || {};
  const companyLinks: FooterLinkItem[] = [
    ["Contato", "/contato"],
    ["Segurança", "/#seguranca"],
  ];
  if (links.website) companyLinks.push(["Site institucional", links.website]);
  const groups: { title: string; links: FooterLinkItem[] }[] = [
    {
      title: "Produto",
      links: [
        ["Soluções", "/solucoes"],
        ["CORE POS", "/solucoes#core-pos-vendas"],
        ["Gestão", "/solucoes#gestao-e-relatorios"],
        ["Planos", "/planos"],
        ["Integrações", "/#integracoes"],
      ],
    },
    { title: "Empresa", links: companyLinks },
    { title: "Suporte", links: [["Ajuda", links.help || "/ajuda"], ["Área do cliente", "/login"]] },
  ];
  const phoneHref = branding.support_phone.replace(/[^\d+]/g, "");
  function openCookies() { window.dispatchEvent(new Event("core:open-cookie-preferences")); }

  return <footer className="border-t border-subtle bg-surface"><div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.2fr_2fr] lg:px-8"><div><BrandWordmark compact /><p className="mt-5 max-w-sm text-sm leading-6 text-muted">Tecnologia para conectar o ponto de venda, a operação e a gestão em um só fluxo.</p>{(branding.support_email || branding.support_phone) && <p className="mt-6 text-xs leading-6 text-muted">{branding.support_email && <a className="block hover:text-fg" href={`mailto:${branding.support_email}`}>{branding.support_email}</a>}{branding.support_phone && <a className="block hover:text-fg" href={`tel:${phoneHref}`}>{branding.support_phone}</a>}</p>}</div><div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-3">{groups.map((group) => <section key={group.title}><h2 className="text-xs font-black uppercase tracking-[0.12em] text-fg">{group.title}</h2><ul className="mt-4 space-y-3 text-xs">{group.links.map(([label, href]) => <li key={label}><FooterLink label={label} href={href} /></li>)}</ul></section>)}<section><h2 className="text-xs font-black uppercase tracking-[0.12em] text-fg">Legal</h2><ul className="mt-4 space-y-3 text-xs"><li><FooterLink label="Termos de Uso" href={links.terms || "/termos-de-uso"} /></li><li><FooterLink label="Política de Privacidade" href={links.privacy || "/privacidade"} /></li><li><FooterLink label="Licença e Assinatura" href="/licenca-e-assinatura" /></li><li><FooterLink label="Tratamento de Dados" href="/tratamento-de-dados" /></li>{links.cookies && <li><FooterLink label="Política de cookies" href={links.cookies} /></li>}<li><button type="button" className="font-semibold text-muted hover:text-fg" onClick={openCookies}>Preferências de cookies</button></li></ul></section></div></div><div className="border-t border-subtle bg-surface-muted"><div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-[11px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">{legal.legal_name && <span>Desenvolvido por {legal.legal_name}</span>}{legal.cnpj && <span>CNPJ {legal.cnpj}</span>}</div></div></footer>;
}
