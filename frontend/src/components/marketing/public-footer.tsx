"use client";

import Link from "next/link";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { useBranding } from "@/providers/branding-provider";

const groups = [
  { title: "Produto", links: [["Soluções", "/solucoes"], ["CORE POS", "/solucoes#core-pos-vendas"], ["Gestão", "/solucoes#gestao-e-relatorios"], ["Planos", "/planos"], ["Integrações", "/#integracoes"]] },
  { title: "Empresa", links: [["Contato", "/contato"], ["Segurança", "/#seguranca"]] },
  { title: "Suporte", links: [["Ajuda", "/ajuda"], ["Área do cliente", "/login"]] },
] as const;

export function PublicFooter() {
  const branding = useBranding();
  const phoneHref = branding.support_phone.replace(/[^\d+]/g, "");
  function openCookies() { window.dispatchEvent(new Event("core:open-cookie-preferences")); }
  return <footer className="border-t border-subtle bg-surface"><div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.2fr_2fr] lg:px-8"><div><BrandWordmark compact /><p className="mt-5 max-w-sm text-sm leading-6 text-muted">Tecnologia para conectar o ponto de venda, a operação e a gestão em um só fluxo.</p>{(branding.support_email || branding.support_phone) && <p className="mt-6 text-xs leading-6 text-muted">{branding.support_email && <a className="block hover:text-fg" href={`mailto:${branding.support_email}`}>{branding.support_email}</a>}{branding.support_phone && <a className="block hover:text-fg" href={`tel:${phoneHref}`}>{branding.support_phone}</a>}</p>}</div><div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-3">{groups.map((group) => <section key={group.title}><h2 className="text-xs font-black uppercase tracking-[0.12em] text-fg">{group.title}</h2><ul className="mt-4 space-y-3 text-xs">{group.links.map(([label, href]) => <li key={label}><Link href={href} className="font-semibold text-muted hover:text-fg">{label}</Link></li>)}</ul></section>)}<section><h2 className="text-xs font-black uppercase tracking-[0.12em] text-fg">Legal</h2><ul className="mt-4 space-y-3 text-xs">{branding.institutional_links.privacy && <li><a href={branding.institutional_links.privacy} className="font-semibold text-muted hover:text-fg">Privacidade</a></li>}{branding.institutional_links.terms && <li><a href={branding.institutional_links.terms} className="font-semibold text-muted hover:text-fg">Termos</a></li>}{branding.institutional_links.cookies && <li><a href={branding.institutional_links.cookies} className="font-semibold text-muted hover:text-fg">Política de cookies</a></li>}<li><button type="button" className="font-semibold text-muted hover:text-fg" onClick={openCookies}>Preferências de cookies</button></li></ul></section></div></div><div className="border-t border-subtle bg-surface-muted"><div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-[11px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8"><span>Desenvolvido por CAVALINI SOLUÇÕES TECNOLOGICAS</span><span>CNPJ 69.366.055/0001-16</span></div></div></footer>;
}
