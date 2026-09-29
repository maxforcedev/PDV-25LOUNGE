import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Boxes,
  Building2,
  LockKeyhole,
  ShoppingCart,
  Users,
  WalletCards,
} from "lucide-react";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";

export const metadata: Metadata = {
  title: "Soluções | CORE PDV",
  description:
    "Conheça as soluções do CORE PDV para vendas, atendimento, pagamentos, estoque, gestão, filiais e controle operacional.",
};

const solutions = [
  {
    icon: ShoppingCart,
    eyebrow: "Venda e atendimento",
    title: "CORE POS para a operação que acontece no balcão e no salão.",
    description:
      "Venda rápida, operadores, produtos, descontos autorizados e fluxo de fechamento conectados ao restante da operação.",
    points: ["Venda rápida e atendimento", "Operadores e permissões", "Caixa e recebimentos"],
  },
  {
    icon: Users,
    eyebrow: "Mesas e comandas",
    title: "Atendimento organizado sem separar o pedido do financeiro.",
    description:
      "Mesas, comandas, itens, responsáveis e fechamento compartilham a mesma base operacional para reduzir retrabalho e divergências.",
    points: ["Mesas e atendimentos", "Pedidos e itens", "Fechamento conectado"],
  },
  {
    icon: WalletCards,
    eyebrow: "Pagamentos",
    title: "Pagamento integrado ao fluxo da venda.",
    description:
      "A arquitetura do CORE está sendo preparada para trabalhar com múltiplos provedores de pagamento sem transformar a maquininha em um processo paralelo.",
    points: ["Múltiplos provedores", "Vínculo com a venda", "Integrações em desenvolvimento e homologação"],
  },
  {
    icon: Boxes,
    eyebrow: "Estoque e compras",
    title: "Saiba de onde veio e para onde foi cada movimentação.",
    description:
      "Compras, entradas, perdas, inventários, transferências e vendas alimentam uma trilha única para acompanhar o estoque por filial.",
    points: ["Compras e fornecedores", "Inventários e perdas", "Transferências entre filiais"],
  },
  {
    icon: BarChart3,
    eyebrow: "Gestão",
    title: "O Backoffice conecta operação, conferência e decisão.",
    description:
      "Dashboards, relatórios, caixa, recebimentos, produtos e performance usam o mesmo contexto para facilitar a conferência da rotina.",
    points: ["Dashboards e relatórios", "Caixa e recebimentos", "Produtos e performance"],
  },
  {
    icon: Building2,
    eyebrow: "Multiempresa e multifilial",
    title: "Uma estrutura preparada para crescer com a operação.",
    description:
      "Empresas, filiais, usuários e dispositivos ficam organizados em uma arquitetura única, com contexto e acesso definidos por unidade.",
    points: ["Empresas e filiais", "Usuários por contexto", "Operação centralizada"],
  },
];

export default function SolutionsPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <PublicHeader active="solutions" />

      <main>
        <section className="border-b border-subtle bg-surface">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-24">
            <div className="max-w-4xl">
              <p className="marketing-eyebrow">Soluções CORE</p>
              <h1 className="mt-5 max-w-4xl text-4xl font-black leading-[1.04] tracking-[-0.05em] text-fg sm:text-5xl lg:text-6xl">
                Uma operação conectada do atendimento à gestão.
              </h1>
              <p className="mt-6 max-w-3xl text-[15px] leading-7 text-muted sm:text-base sm:leading-8">
                O CORE PDV reúne os fluxos que normalmente ficam espalhados entre sistemas, planilhas e processos manuais. A proposta é simples: registrar a operação uma vez e manter venda, caixa, estoque, atendimento e gestão no mesmo contexto.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/cadastro"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-bold text-white shadow-[0_14px_35px_rgba(52,84,209,0.24)] transition hover:bg-primary-dark"
                >
                  Solicitar demonstração <ArrowRight className="size-4" />
                </Link>
                <Link
                  href="/planos"
                  className="inline-flex h-12 items-center justify-center rounded-xl border border-subtle bg-canvas px-6 text-sm font-bold text-fg transition hover:border-primary/25 hover:bg-info-surface"
                >
                  Conhecer planos
                </Link>
              </div>
            </div>
          </div>
        </section>

        <section className="bg-canvas">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
            <div className="grid gap-4 border-y border-subtle py-6 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["CORE POS", "Venda e atendimento"],
                ["Backoffice", "Gestão centralizada"],
                ["Estoque", "Movimentação rastreável"],
                ["Integrações", "Operação conectada"],
              ].map(([title, description]) => (
                <div key={title} className="px-1 py-2">
                  <strong className="block text-sm font-extrabold text-fg">{title}</strong>
                  <span className="mt-1 block text-xs leading-5 text-muted">{description}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-surface">
          <div className="mx-auto max-w-7xl px-4 py-18 sm:px-6 sm:py-24 lg:px-8">
            <div className="max-w-3xl">
              <p className="marketing-eyebrow">Do ponto de venda ao controle</p>
              <h2 className="mt-4 text-3xl font-black tracking-[-0.04em] text-fg sm:text-4xl">
                Soluções que compartilham o mesmo núcleo operacional.
              </h2>
              <p className="mt-4 text-sm leading-7 text-muted">
                Em vez de apresentar dezenas de funcionalidades isoladas, o CORE organiza os principais fluxos da empresa em partes que trabalham juntas.
              </p>
            </div>

            <div className="mt-14 divide-y divide-subtle border-y border-subtle">
              {solutions.map(({ icon: Icon, eyebrow, title, description, points }) => (
                <article key={title} className="grid gap-8 py-10 lg:grid-cols-[0.38fr_0.62fr] lg:items-start lg:py-14">
                  <div>
                    <span className="flex size-11 items-center justify-center rounded-xl border border-primary/15 bg-info-surface text-info-strong">
                      <Icon className="size-5" />
                    </span>
                    <p className="mt-5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-primary">
                      {eyebrow}
                    </p>
                  </div>
                  <div className="max-w-3xl">
                    <h3 className="text-2xl font-black leading-tight tracking-[-0.035em] text-fg sm:text-3xl">
                      {title}
                    </h3>
                    <p className="mt-4 max-w-2xl text-sm leading-7 text-muted">{description}</p>
                    <div className="mt-6 flex flex-wrap gap-x-6 gap-y-3">
                      {points.map((point) => (
                        <span key={point} className="text-xs font-bold text-fg/80">
                          {point}
                        </span>
                      ))}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-operational-canvas text-operational-fg">
          <div className="mx-auto grid max-w-7xl gap-10 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:px-8">
            <div>
              <p className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-operational-info">
                Segurança e controle
              </p>
              <h2 className="mt-4 max-w-xl text-3xl font-black tracking-[-0.04em] text-white sm:text-4xl">
                Acesso, contexto e auditoria fazem parte da operação.
              </h2>
              <p className="mt-5 max-w-xl text-sm leading-7 text-operational-muted">
                Usuários, filiais, permissões e ações sensíveis são tratados como parte do produto, não apenas como elementos visuais da interface.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {[
                [LockKeyhole, "Permissões", "Ações respeitam o acesso efetivo do usuário."],
                [Building2, "Filiais", "O contexto operacional acompanha cada unidade."],
                [Users, "Responsabilidade", "Ações ficam associadas a quem executou."],
              ].map(([Icon, title, description]) => {
                const IconComponent = Icon as typeof LockKeyhole;
                return (
                  <div key={String(title)} className="border-l border-white/10 pl-5">
                    <IconComponent className="size-5 text-operational-info" />
                    <strong className="mt-4 block text-sm text-white">{title as string}</strong>
                    <span className="mt-2 block text-xs leading-5 text-operational-muted">{description as string}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="border-t border-subtle bg-surface">
          <div className="mx-auto grid max-w-7xl gap-8 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[1fr_auto] lg:items-center lg:px-8">
            <div>
              <p className="marketing-eyebrow">Conheça o CORE</p>
              <h2 className="mt-4 max-w-2xl text-3xl font-black tracking-[-0.04em] text-fg sm:text-4xl">
                Vamos entender a sua operação antes de criar qualquer conta.
              </h2>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-muted">
                Nesta fase, a entrada de novos clientes é acompanhada pela equipe CORE. Não há pagamento online nem criação automática de empresa pelo site.
              </p>
            </div>
            <Link
              href="/cadastro"
              className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-bold text-white transition hover:bg-primary-dark"
            >
              Solicitar demonstração <ArrowRight className="size-4" />
            </Link>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
