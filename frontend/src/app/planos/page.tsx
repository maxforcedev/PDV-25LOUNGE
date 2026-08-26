import type { Metadata } from "next";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";
import { PlansCatalog } from "@/components/marketing/plans-catalog";

export const metadata: Metadata = {
  title: "Planos | CORE PDV",
  description: "Conheça os planos públicos do CORE PDV e comece sem cartão.",
};

export default function PlansPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <PublicHeader active="plans" />
      <main>
        <section className="marketing-hero border-b border-subtle">
          <div className="mx-auto max-w-7xl px-4 py-16 text-center sm:px-6 sm:py-20 lg:px-8">
            <p className="marketing-eyebrow">Planos públicos</p>
            <h1 className="mx-auto mt-4 max-w-3xl text-4xl font-black tracking-[-0.05em] text-fg sm:text-5xl">Escolha o espaço certo para sua operação.</h1>
            <p className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-muted">Compare preço, período, usuários e filiais. O cadastro não pede cartão e qualquer trial disponível aparece antes da escolha.</p>
          </div>
        </section>
        <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-20 lg:px-8"><PlansCatalog /></section>
      </main>
      <PublicFooter />
    </div>
  );
}
