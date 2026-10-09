import type { Metadata } from "next";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";
import { PlansCatalog } from "@/components/marketing/plans-catalog";

export const metadata: Metadata = {
  title: "Planos ",
  description: "Conheça os planos do CORE PDV e fale com nossa equipe sobre a sua operação.",
};

export default function PlansPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <PublicHeader active="plans" />
      <main>
        <section className="marketing-hero border-b border-subtle">
          <div className="mx-auto max-w-7xl px-4 py-16 text-center sm:px-6 sm:py-20 lg:px-8">
            <p className="marketing-eyebrow">Planos CORE</p>
            <h1 className="mx-auto mt-4 max-w-3xl text-4xl font-black tracking-[-0.05em] text-fg sm:text-5xl">Encontre o plano que faz sentido para sua operação.</h1>
            <p className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-muted">Compare os limites e características disponíveis. A contratação é conversada com a equipe comercial.</p>
          </div>
        </section>
        <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-20 lg:px-8"><PlansCatalog /></section>
      </main>
      <PublicFooter />
    </div>
  );
}
