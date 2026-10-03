import type { Metadata } from "next";
import { Suspense } from "react";
import { ContactForm } from "@/components/marketing/contact-form";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";

export const metadata: Metadata = { title: "Solicitar demonstração | CORE PDV", description: "Converse com a equipe CORE sobre sua operação." };

export default function ContactPage() {
  return <div className="min-h-screen bg-canvas text-fg"><PublicHeader active="contact" /><main className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[0.8fr_1.2fr] lg:px-8"><section><p className="marketing-eyebrow">Solicitar demonstração</p><h1 className="mt-4 text-4xl font-black tracking-[-0.05em] text-fg">Vamos entender sua operação.</h1><p className="mt-5 max-w-md text-sm leading-7 text-muted">Conte o essencial. Seu contato será salvo para que a equipe CORE retorne com uma conversa comercial adequada ao seu cenário.</p><p className="mt-8 border-l-2 border-primary pl-4 text-xs leading-6 text-muted">SEM PRECISAR DO CARTÃO</p></section><Suspense fallback={<div className="min-h-96 border border-subtle bg-surface" />}><ContactForm /></Suspense></main><PublicFooter /></div>;
}
