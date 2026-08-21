import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  Banknote,
  BarChart3,
  Boxes,
  Building2,
  Check,
  CircleDollarSign,
  FileSearch,
  Gauge,
  LockKeyhole,
  ReceiptText,
  ShieldCheck,
  ShoppingCart,
  Sparkles,
  Users,
  WalletCards,
  Zap,
} from "lucide-react";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";

export const metadata: Metadata = {
  title: "CORE PDV — Controle operacional para bares, restaurantes e lounges",
  description:
    "Conecte vendas, caixa, estoque, comissões, consumação, descontos e relatórios para conferir a operação e conhecer o resultado.",
};

const featureCards = [
  {
    icon: ShoppingCart,
    title: "Consumo registrado no atendimento",
    description:
      "Atendente, formas de pagamento, desconto autorizado, taxa de serviço e consumação ficam no mesmo fluxo da venda.",
  },
  {
    icon: Boxes,
    title: "Estoque com origem e movimentação",
    description:
      "Saldo por filial, produtos compostos e movimentações auditáveis ajudam a rastrear o que saiu e o que ainda deveria estar disponível.",
  },
  {
    icon: Banknote,
    title: "Divergência de caixa explicável",
    description:
      "Abertura, entradas, sangrias, recebimentos, gaveta esperada e fechamento formam um histórico para conferir diferenças.",
  },
  {
    icon: BarChart3,
    title: "Comissão e resultado verificáveis",
    description:
      "Faturamento de vendas, taxa de serviço, recebimentos e comissão seguem a mesma regra no Dashboard e nos relatórios.",
  },
  {
    icon: Users,
    title: "Responsabilidade por pessoa e filial",
    description:
      "Perfis, permissões e bloqueios individuais definem quem pode operar e o que cada pessoa pode fazer em cada filial.",
  },
  {
    icon: FileSearch,
    title: "Descontos e ações sob auditoria",
    description:
      "Ações críticas registram responsável, contexto, antes e depois para que descontos e alterações não fiquem sem conferência.",
  },
];

const audience = ["Bares", "Restaurantes", "Lounges", "Casas de eventos", "Boates", "Operações presenciais"];

function DashboardPreview() {
  const bars = [46, 72, 58, 86, 68, 94, 78];
  return (
    <div className="relative mx-auto w-full max-w-[720px] lg:max-w-none">
      <div className="absolute -inset-10 -z-10 rounded-[40px] bg-primary/10 blur-3xl" />
      <div className="overflow-hidden rounded-[24px] border border-subtle bg-surface-raised shadow-[0_30px_80px_rgba(15,23,42,0.16)] ring-1 ring-white/30">
        <div className="flex h-12 items-center gap-2 border-b border-subtle bg-surface px-4">
          <span className="size-2.5 rounded-full bg-danger/65" />
          <span className="size-2.5 rounded-full bg-warning/75" />
          <span className="size-2.5 rounded-full bg-success/75" />
          <span className="ml-3 text-[10px] font-semibold text-muted">CORE PDV · Prévia ilustrativa</span>
        </div>
        <div className="grid min-h-[430px] grid-cols-[58px_1fr] sm:grid-cols-[150px_1fr]">
          <aside className="border-r border-white/8 bg-operational-canvas px-2 py-4 sm:px-3">
            <div className="mb-6 flex items-center justify-center gap-2 sm:justify-start sm:px-2">
              <span className="text-[10px] font-black tracking-tight text-white sm:text-xs">CORE</span>
              <span className="hidden rounded bg-primary px-1.5 py-0.5 text-[8px] font-black tracking-wider text-white sm:inline">PDV</span>
            </div>
            <div className="space-y-1.5">
              {[Gauge, ShoppingCart, Boxes, Banknote, ReceiptText, Users].map((Icon, index) => (
                <div
                  key={index}
                  className={`flex h-8 items-center rounded-lg ${index === 0 ? "bg-primary text-white" : "text-operational-muted"} ${index === 0 ? "justify-center sm:justify-start" : "justify-center sm:justify-start"} sm:gap-2 sm:px-2`}
                >
                  <Icon className="size-3.5 shrink-0" />
                  <span className="hidden truncate text-[9px] font-semibold sm:block">
                    {['Visão geral', 'PDV', 'Estoque', 'Caixa', 'Relatórios', 'Equipe'][index]}
                  </span>
                </div>
              ))}
            </div>
          </aside>
          <div className="bg-canvas p-3 sm:p-5">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <p className="text-[9px] font-semibold uppercase tracking-[0.15em] text-muted">Exemplo ilustrativo</p>
                <h3 className="mt-1 text-sm font-bold text-fg sm:text-base">Conferência da operação</h3>
              </div>
              <div className="rounded-lg border border-subtle bg-surface px-2.5 py-1.5 text-[9px] font-semibold text-muted">Cenário exemplo · Matriz</div>
            </div>
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              {[
                ["Faturamento de vendas", "R$ 18.420", "Valor ilustrativo"],
                ["Consumação cobrada", "R$ 380", "Valor ilustrativo"],
                ["Faturamento efetivo", "R$ 18.800", "Vendas + consumação"],
                ["Total recebido", "R$ 20.642", "+ R$ 1.842 de serviço"],
              ].map(([label, value, meta]) => (
                <div key={label} className="rounded-xl border border-subtle bg-surface p-3 shadow-sm">
                  <p className="text-[8px] font-semibold text-muted sm:text-[9px]">{label}</p>
                  <strong className="mt-1.5 block text-[13px] tracking-tight text-fg sm:text-base">{value}</strong>
                  <span className="mt-1 block text-[8px] font-semibold text-success-strong">{meta}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 grid gap-2 xl:grid-cols-[1.35fr_0.65fr]">
              <div className="rounded-xl border border-subtle bg-surface p-3 sm:p-4">
                <div className="flex items-center justify-between">
                  <div><p className="text-[10px] font-bold text-fg">Conferência por período</p><p className="mt-0.5 text-[8px] text-muted">Faturamento efetivo por dia</p></div>
                  <span className="rounded-full bg-info-surface px-2 py-1 text-[8px] font-bold text-info-strong">Exemplo</span>
                </div>
                <div className="mt-5 flex h-28 items-end justify-between gap-2 border-b border-subtle px-1">
                  {bars.map((height, index) => (
                    <div key={index} className="flex h-full flex-1 items-end justify-center gap-[2px]">
                      <span className="w-[38%] rounded-t-sm bg-chart-previous/55" style={{ height: `${Math.max(24, height - 18)}%` }} />
                      <span className="w-[38%] rounded-t-sm bg-chart-1" style={{ height: `${height}%` }} />
                    </div>
                  ))}
                </div>
                <div className="mt-2 grid grid-cols-7 text-center text-[7px] font-semibold text-muted">
                  {['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'].map((day) => <span key={day}>{day}</span>)}
                </div>
              </div>
              <div className="rounded-xl border border-subtle bg-surface p-3 sm:p-4">
                <p className="text-[10px] font-bold text-fg">Recebimentos</p>
                <p className="mt-0.5 text-[8px] text-muted">Distribuição ilustrativa</p>
                <div className="mt-4 space-y-3">
                  {[
                    ['PIX', 40], ['Crédito', 30], ['Dinheiro', 10], ['Débito', 20],
                  ].map(([label, width]) => (
                    <div key={String(label)}>
                      <div className="mb-1 flex justify-between text-[8px]"><span className="font-semibold text-fg">{label}</span><span className="text-muted">{width}%</span></div>
                      <div className="h-1.5 rounded-full bg-surface-muted"><div className="h-full rounded-full bg-chart-1" style={{ width: `${width}%` }} /></div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {[
                ['Estoque', '4 alertas', Boxes], ['Caixa', '2 abertos', WalletCards], ['Equipe', '8 ativos', Users],
              ].map(([label, value, Icon]) => {
                const IconComponent = Icon as typeof Boxes;
                return <div key={String(label)} className="flex items-center gap-2 rounded-xl border border-subtle bg-surface p-2.5"><span className="flex size-7 items-center justify-center rounded-lg bg-info-surface text-info-strong"><IconComponent className="size-3.5" /></span><div className="min-w-0"><p className="truncate text-[8px] text-muted">{label as string}</p><strong className="block truncate text-[9px] text-fg sm:text-[10px]">{value as string}</strong></div></div>;
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <PublicHeader active="home" />

      <main>
        <section className="marketing-hero relative overflow-hidden">
          <div className="marketing-grid absolute inset-0 opacity-60" />
          <div className="absolute left-1/2 top-[-220px] size-[520px] -translate-x-1/2 rounded-full bg-primary/18 blur-[110px]" />
          <div className="relative mx-auto grid max-w-7xl items-center gap-14 px-4 pb-20 pt-16 sm:px-6 sm:pb-24 sm:pt-22 lg:grid-cols-[0.92fr_1.08fr] lg:px-8 lg:pb-28 lg:pt-28">
            <div className="max-w-2xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-info-surface px-3 py-1.5 text-[11px] font-bold text-info-strong shadow-sm">
                <Sparkles className="size-3.5" />
                Controle para operações presenciais
              </div>
              <h1 className="mt-7 max-w-3xl text-[42px] font-black leading-[1.04] tracking-[-0.052em] text-fg sm:text-6xl lg:text-[64px]">
                Pare de fechar a casa<br />
                <span className="text-primary">sem saber o resultado.</span>
              </h1>
              <p className="mt-6 max-w-xl text-[15px] leading-7 text-muted sm:text-base sm:leading-8">
                Caixa divergente, estoque sem rastreabilidade, comissão difícil de conferir, consumo sem controle e descontos sem auditoria escondem o resultado. O CORE PDV conecta esses registros do atendimento ao fechamento.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link href="#recursos" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-bold text-white shadow-[0_14px_35px_rgba(52,84,209,0.28)] transition hover:-translate-y-0.5 hover:bg-primary-dark focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/30">
                  Conhecer o CORE PDV <ArrowRight className="size-4" />
                </Link>
                <Link href="/login" className="inline-flex h-12 items-center justify-center rounded-xl border border-subtle bg-surface/85 px-6 text-sm font-bold text-fg shadow-sm transition hover:border-primary/25 hover:bg-surface">
                  Já sou cliente: acessar
                </Link>
              </div>
              <div className="mt-8 grid max-w-xl grid-cols-1 gap-3 text-xs text-muted sm:grid-cols-3">
                {[
                  [ShieldCheck, "Acessos por filial"],
                  [BadgeCheck, "Ações rastreáveis"],
                  [Zap, "Dados conectados"],
                ].map(([Icon, label]) => {
                  const IconComponent = Icon as typeof ShieldCheck;
                  return <div key={String(label)} className="flex items-center gap-2"><span className="flex size-6 items-center justify-center rounded-full bg-success-surface text-success-strong"><Check className="size-3.5" /></span><span className="font-semibold">{label as string}</span></div>;
                })}
              </div>
            </div>
            <DashboardPreview />
          </div>
        </section>

        <section className="border-y border-subtle bg-surface">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <p className="text-center text-[10px] font-bold uppercase tracking-[0.18em] text-muted">Projetado para operações como</p>
            <div className="mt-4 flex flex-wrap justify-center gap-x-7 gap-y-3">
              {audience.map((item) => <span key={item} className="text-xs font-bold text-fg/80">{item}</span>)}
            </div>
          </div>
        </section>

        <section id="recursos" className="scroll-mt-20">
          <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8">
            <div className="grid gap-8 lg:grid-cols-[0.72fr_1.28fr] lg:items-end">
              <div>
                <p className="marketing-eyebrow">Evidências para conferir</p>
                <h2 className="mt-4 text-3xl font-black tracking-[-0.04em] text-fg sm:text-4xl">Controle não é ter mais telas. É conseguir explicar a operação.</h2>
              </div>
              <p className="max-w-2xl text-sm leading-7 text-muted lg:justify-self-end">No CORE PDV, cada recurso deixa uma evidência: a venda movimenta o estoque, o pagamento compõe o caixa, as regras calculam comissão e resultado, e as ações críticas podem ser auditadas.</p>
            </div>

            <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {featureCards.map(({ icon: Icon, title, description }) => (
                <article key={title} className="group rounded-2xl border border-subtle bg-surface p-6 shadow-[0_8px_30px_rgba(15,23,42,0.035)] transition duration-300 hover:-translate-y-1 hover:border-primary/25 hover:shadow-[0_18px_45px_rgba(15,23,42,0.07)]">
                  <div className="flex size-11 items-center justify-center rounded-xl bg-info-surface text-info-strong transition group-hover:bg-primary group-hover:text-white"><Icon className="size-5" /></div>
                  <h3 className="mt-5 text-base font-extrabold tracking-tight text-fg">{title}</h3>
                  <p className="mt-2 text-[13px] leading-6 text-muted">{description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="operacao" className="scroll-mt-20 border-y border-subtle bg-surface">
          <div className="mx-auto grid max-w-7xl gap-12 px-4 py-20 sm:px-6 sm:py-24 lg:grid-cols-2 lg:items-center lg:px-8">
            <div>
              <p className="marketing-eyebrow">Do registro à decisão</p>
              <h2 className="mt-4 max-w-xl text-3xl font-black tracking-[-0.04em] text-fg sm:text-4xl">Feche a operação com contexto para decidir o próximo passo.</h2>
              <p className="mt-5 max-w-xl text-sm leading-7 text-muted">O CORE PDV organiza o caminho crítico da casa para que a equipe registre a rotina e a gestão confira o que foi vendido, consumido, recebido e movimentado.</p>
              <div className="mt-8 space-y-5">
                {[
                  ["01", "Defina as regras", "Empresa, filial, equipe, acessos, produtos, preços e estoque formam o contexto da operação."],
                  ["02", "Registre o movimento", "Caixa aberto, atendente identificado, pagamento, consumação, desconto e baixa de estoque ficam relacionados."],
                  ["03", "Confira antes de decidir", "Recebimentos, comissão, estoque, auditoria e resultado usam o mesmo contexto operacional."],
                ].map(([number, title, description]) => (
                  <div key={number} className="grid grid-cols-[44px_1fr] gap-4">
                    <span className="flex size-11 items-center justify-center rounded-xl border border-primary/20 bg-info-surface text-[11px] font-black text-info-strong">{number}</span>
                    <div><h3 className="text-sm font-extrabold text-fg">{title}</h3><p className="mt-1 text-[13px] leading-6 text-muted">{description}</p></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-[28px] border border-subtle bg-canvas p-3 shadow-[0_24px_60px_rgba(15,23,42,0.08)] sm:p-6">
              <div className="rounded-2xl border border-subtle bg-surface p-5 sm:p-7">
                <div className="flex items-start justify-between gap-4">
                  <div><span className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Exemplo ilustrativo</span><h3 className="mt-2 text-lg font-black tracking-tight text-fg">Como o total recebido é formado</h3></div>
                  <CircleDollarSign className="size-7 text-primary" />
                </div>
                <div className="mt-7 space-y-3">
                  <div className="flex items-center justify-between border-b border-subtle pb-3 text-sm"><span className="text-muted">Faturamento de vendas</span><strong className="text-fg">R$ 18.420,00</strong></div>
                  <div className="flex items-center justify-between border-b border-subtle pb-3 text-sm"><span className="text-muted">+ Consumação cobrada</span><strong className="text-fg">R$ 380,00</strong></div>
                  <div className="flex items-center justify-between rounded-xl bg-info-surface px-4 py-3.5 text-sm"><span className="font-bold text-info-strong">Faturamento efetivo</span><strong className="text-info-strong">R$ 18.800,00</strong></div>
                  <div className="flex items-center justify-between border-b border-subtle pb-3 pt-2 text-sm"><span className="text-muted">+ Taxa de serviço</span><strong className="text-fg">R$ 1.842,00</strong></div>
                  <div className="flex items-center justify-between rounded-xl bg-success-surface px-4 py-3.5 text-sm"><span className="font-extrabold text-success-strong">Total recebido</span><strong className="text-success-strong">R$ 20.642,00</strong></div>
                </div>
                <p className="mt-5 text-[11px] leading-5 text-muted">Valores apenas ilustrativos: Faturamento de vendas + Consumação cobrada = Faturamento efetivo; + Taxa = Total recebido.</p>
              </div>
            </div>
          </div>
        </section>

        <section id="seguranca" className="scroll-mt-20">
          <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8">
            <div className="overflow-hidden rounded-[30px] bg-operational-canvas text-operational-fg shadow-[0_30px_80px_rgba(15,23,42,0.16)]">
              <div className="grid gap-10 px-6 py-10 sm:px-10 sm:py-12 lg:grid-cols-[1.05fr_0.95fr] lg:px-14 lg:py-16">
                <div>
                  <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-operational-info"><LockKeyhole className="size-3.5" /> Controle de acesso</span>
                  <h2 className="mt-5 max-w-xl text-3xl font-black tracking-[-0.04em] text-white sm:text-4xl">Cada ação parte de uma pessoa, em uma filial, com uma permissão.</h2>
                  <p className="mt-5 max-w-xl text-sm leading-7 text-operational-muted">Perfis e bloqueios individuais participam da autorização no backend. Assim, esconder um botão não é tratado como controle e ações sensíveis respeitam o acesso definido.</p>
                  <Link href="/ajuda" className="mt-8 inline-flex items-center gap-2 text-sm font-bold text-white hover:text-operational-info">Entender acessos e permissões <ArrowRight className="size-4" /></Link>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    [Building2, "Contexto por filial", "Acessos e operação são recalculados ao trocar de unidade."],
                    [ShieldCheck, "Autorização no backend", "As permissões são verificadas além da interface."],
                    [LockKeyhole, "Bloqueios individuais", "Exceções podem ser definidas sem duplicar perfis inteiros."],
                    [FileSearch, "Histórico de auditoria", "Mudanças críticas ficam ligadas ao responsável e ao contexto."],
                  ].map(([Icon, title, desc]) => {
                    const IconComponent = Icon as typeof ShieldCheck;
                    return <div key={String(title)} className="rounded-2xl border border-white/8 bg-white/[0.045] p-5"><IconComponent className="size-5 text-operational-info" /><h3 className="mt-4 text-sm font-extrabold text-white">{title as string}</h3><p className="mt-2 text-[12px] leading-5 text-operational-muted">{desc as string}</p></div>;
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="border-y border-subtle bg-surface">
          <div className="mx-auto grid max-w-7xl gap-10 px-4 py-20 sm:px-6 sm:py-24 lg:grid-cols-[1fr_auto] lg:items-center lg:px-8">
            <div>
              <p className="marketing-eyebrow">Central de ajuda</p>
              <h2 className="mt-4 max-w-2xl text-3xl font-black tracking-[-0.04em] text-fg sm:text-4xl">Consulte o procedimento sem perder o contexto da operação.</h2>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-muted">Encontre orientações sobre caixa, vendas, estoque, cadastros, permissões, relatórios e configurações do CORE PDV.</p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Link href="#recursos" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-sm font-bold text-white transition hover:bg-primary-dark">Conhecer o CORE PDV <ArrowRight className="size-4" /></Link>
              <Link href="/ajuda" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-subtle bg-canvas px-6 text-sm font-bold text-fg transition hover:border-primary/25 hover:bg-info-surface hover:text-info-strong">Abrir Central de Ajuda <ArrowRight className="size-4" /></Link>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
