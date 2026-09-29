import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, ChevronRight, ShieldCheck } from "lucide-react";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";
import { ProductEvidence, VideoTeaser } from "@/components/marketing/product-evidence";

export const metadata: Metadata = {
  title: "CORE PDV | PDV, gestão e pagamentos para sua operação",
  description: "Conecte vendas, caixa, estoque, mesas, compras, pagamentos e gestão em uma única plataforma.",
};

const posItems = ["Venda rápida", "Operadores e atendimento", "Mesas, comandas e pedidos", "Caixa, pagamentos e impressão"];
const backofficeItems = ["Produtos, preços e estoque", "Compras e fornecedores", "Relatórios e financeiro", "Filiais, usuários e permissões"];
const structuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "CORE PDV",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description: "Plataforma para conectar operações de ponto de venda e gestão.",
};

export default function HomePage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <PublicHeader active="home" />
      <main>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
        <section className="border-b border-subtle bg-surface">
          <div className="mx-auto grid max-w-7xl gap-12 px-4 py-18 sm:px-6 sm:py-24 lg:grid-cols-[1fr_0.86fr] lg:items-end lg:px-8">
            <div className="max-w-3xl"><p className="marketing-eyebrow">CORE PDV</p><h1 className="mt-5 text-4xl font-black leading-[1.03] tracking-[-0.055em] text-fg sm:text-6xl">Sua operação inteira. Conectada pelo CORE.</h1><p className="mt-6 max-w-2xl text-base leading-8 text-muted">PDV, pagamentos, mesas, estoque, compras, financeiro e gestão para operações presenciais que precisam seguir em movimento.</p><div className="mt-8 flex flex-col gap-3 sm:flex-row"><Link href="/contato" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-bold text-white transition hover:bg-primary-dark">Solicitar demonstração <ArrowRight className="size-4" /></Link><Link href="#em-acao" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-subtle px-6 text-sm font-bold text-fg transition hover:bg-surface-muted">Ver o CORE em ação <ArrowRight className="size-4" /></Link></div></div>
            <div className="border-l-4 border-primary bg-surface-muted p-6 sm:p-8"><p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Do atendimento à gestão</p><p className="mt-5 text-xl font-bold leading-8 tracking-tight text-fg">CORE POS registra a operação. CORE Backoffice transforma esse contexto em controle.</p><p className="mt-5 text-sm leading-7 text-muted">Os dois ambientes têm papéis diferentes e trabalham sobre a mesma rotina da empresa.</p></div>
          </div>
        </section>

        <section className="border-b border-subtle bg-canvas"><div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8"><p className="text-center text-xs font-bold uppercase tracking-[0.16em] text-muted">O que o CORE conecta</p><div className="mt-7 flex flex-wrap items-center justify-center gap-x-3 gap-y-3 text-sm font-bold text-fg">{["Venda", "Pagamento", "Caixa", "Estoque", "Gestão"].map((item, index) => <span key={item} className="flex items-center gap-3">{index > 0 && <ChevronRight className="size-4 text-primary" aria-hidden="true" />}{item}</span>)}</div></div></section>

        <section id="em-acao" className="scroll-mt-20"><div className="mx-auto max-w-7xl px-4 py-18 sm:px-6 sm:py-24 lg:px-8"><div className="mb-8 max-w-2xl"><p className="marketing-eyebrow">CORE em operação</p><h2 className="mt-4 text-3xl font-black tracking-[-0.045em] text-fg sm:text-4xl">Do atendimento à gestão, sem reconstruir o produto para a apresentação.</h2></div><VideoTeaser /></div></section>

        <section className="border-y border-subtle bg-surface"><div className="mx-auto grid max-w-7xl gap-10 px-4 py-18 sm:px-6 sm:py-24 lg:grid-cols-2 lg:px-8"><div><p className="marketing-eyebrow">CORE POS</p><h2 className="mt-4 text-3xl font-black tracking-[-0.045em] text-fg">A operação acontece aqui.</h2><p className="mt-5 text-sm leading-7 text-muted">O CORE POS reúne os fluxos que acontecem no balcão, no salão e no caixa. A equipe atende, registra e encerra a rotina operacional no próprio ponto de venda.</p><ul className="mt-7 space-y-3 border-t border-subtle pt-6 text-sm font-semibold text-fg">{posItems.map((item) => <li key={item} className="flex gap-3"><span className="text-primary">01</span>{item}</li>)}</ul></div><ProductEvidence title="CORE POS em dispositivo real" description="Slot reservado para o fluxo real de venda e pagamento." asset="/site/screenshots/core-pos-venda.webp" /></div></section>

        <section><div className="mx-auto grid max-w-7xl gap-10 px-4 py-18 sm:px-6 sm:py-24 lg:grid-cols-2 lg:px-8"><ProductEvidence title="CORE Backoffice" description="Slot reservado para a visão real de gestão do CORE." asset="/site/screenshots/backoffice-dashboard.webp" /><div><p className="marketing-eyebrow">CORE Backoffice</p><h2 className="mt-4 text-3xl font-black tracking-[-0.045em] text-fg">A gestão acontece aqui.</h2><p className="mt-5 text-sm leading-7 text-muted">Produtos, estoque, compras, relatórios, financeiro e acessos compõem o ambiente de acompanhamento e controle da empresa.</p><ul className="mt-7 space-y-3 border-t border-subtle pt-6 text-sm font-semibold text-fg">{backofficeItems.map((item) => <li key={item} className="flex gap-3"><span className="text-primary">02</span>{item}</li>)}</ul></div></div></section>

        <section id="integracoes" className="border-y border-subtle bg-surface"><div className="mx-auto grid max-w-7xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_auto] lg:items-center lg:px-8"><div><p className="marketing-eyebrow">Pagamentos e integrações</p><h2 className="mt-4 text-3xl font-black tracking-[-0.045em] text-fg">Pagamento faz parte da venda. Não deveria ser outro processo.</h2><p className="mt-5 max-w-2xl text-sm leading-7 text-muted">O CORE possui arquitetura preparada para múltiplos provedores de pagamento. Cada integração é apresentada comercialmente somente quando seu estágio operacional estiver confirmado.</p></div><Link href="/solucoes#pagamentos" className="inline-flex items-center gap-2 text-sm font-bold text-primary hover:text-primary-dark">Conhecer a arquitetura <ArrowRight className="size-4" /></Link></div></section>

        <section id="segmentos"><div className="mx-auto max-w-7xl px-4 py-18 sm:px-6 sm:py-24 lg:px-8"><div className="grid gap-8 lg:grid-cols-[0.75fr_1.25fr]"><div><p className="marketing-eyebrow">Segmentos</p><h2 className="mt-4 text-3xl font-black tracking-[-0.045em] text-fg">Operações presenciais, cada uma com sua rotina.</h2></div><div className="border-l border-subtle pl-6 text-sm leading-7 text-muted"><p>O CORE se aplica a bares, restaurantes, lounges, casas de eventos, pizzarias, lanchonetes, food service, varejo e outras operações presenciais compatíveis.</p><p className="mt-5 font-semibold text-fg">A conversa comercial parte da operação real, não de uma promessa genérica de segmento.</p></div></div></div></section>

        <section id="seguranca" className="border-y border-subtle bg-surface"><div className="mx-auto grid max-w-7xl gap-8 px-4 py-16 sm:px-6 lg:grid-cols-[auto_1fr] lg:items-start lg:px-8"><ShieldCheck className="size-7 text-primary" aria-hidden="true" /><div><p className="marketing-eyebrow">Segurança e auditoria</p><h2 className="mt-3 text-2xl font-black tracking-[-0.04em] text-fg">Acesso, contexto de filial e ações registradas.</h2><p className="mt-4 max-w-3xl text-sm leading-7 text-muted">O produto possui perfis e permissões, contexto de filial, dispositivos e histórico de auditoria para apoiar o controle da operação. Não apresentamos certificações ou integrações sem comprovação.</p></div></div></section>

        <section id="empresa" className="bg-canvas"><div className="mx-auto grid max-w-7xl gap-8 px-4 py-18 sm:px-6 sm:py-24 lg:grid-cols-[1fr_auto] lg:items-end lg:px-8"><div><p className="marketing-eyebrow">Vamos conversar</p><h2 className="mt-4 max-w-2xl text-3xl font-black tracking-[-0.045em] text-fg sm:text-4xl">Conheça o CORE a partir da sua operação.</h2><p className="mt-5 max-w-xl text-sm leading-7 text-muted">Sem criação automática de conta, checkout ou cartão. A equipe comercial entende o seu cenário antes da próxima etapa.</p></div><Link href="/contato" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-bold text-white transition hover:bg-primary-dark">Solicitar demonstração <ArrowRight className="size-4" /></Link></div></section>
      </main>
      <PublicFooter />
    </div>
  );
}
