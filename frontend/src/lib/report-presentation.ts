export type ReportCenterItem = {
  href: string;
  label: string;
  permission: string;
};

export type ReportCenterGroup = {
  title: "Vendas" | "Financeiro" | "Estoque" | "Inventários";
  description: string;
  reports: readonly ReportCenterItem[];
};

export const reportGroups: readonly ReportCenterGroup[] = [
  {
    title: "Vendas",
    description: "Operações, recebimentos, desempenho e cancelamentos.",
    reports: [
      { href: "/relatorios/visao-geral", label: "Visão geral", permission: "reports.view_sales" },
      { href: "/relatorios/vendas", label: "Vendas", permission: "reports.view_sales" },
      { href: "/relatorios/recebimentos", label: "Recebimentos / Formas de pagamento", permission: "reports.view_receipts" },
      { href: "/relatorios/produtos", label: "Produtos e desempenho", permission: "reports.view_products" },
      { href: "/relatorios/atendentes", label: "Atendentes", permission: "reports.view_team" },
      { href: "/relatorios/operadores", label: "Operadores", permission: "reports.view_team" },
      { href: "/relatorios/cancelamentos", label: "Cancelamentos e estornos", permission: "reports.view_cancellations" },
      { href: "/relatorios/consumacoes", label: "Consumação / Cortesias", permission: "reports.view_consumptions" },
    ],
  },
  {
    title: "Financeiro",
    description: "Resultado estimado, comissões e controle de caixa.",
    reports: [
      { href: "/relatorios/resultado", label: "Resultado estimado", permission: "reports.view_operational_result" },
      { href: "/relatorios/comissoes", label: "Comissões", permission: "commissions.view" },
      { href: "/relatorios/descontos", label: "Descontos e autorizações", permission: "reports.view_discounts" },
      { href: "/relatorios/caixa", label: "Caixa", permission: "reports.view_cash" },
      { href: "/relatorios/sangrias", label: "Sangrias", permission: "reports.view_withdrawals" },
    ],
  },
  {
    title: "Estoque",
    description: "Movimentações, consumo, custos e preços por filial.",
    reports: [
      { href: "/relatorios/posicao-estoque", label: "Posição de estoque", permission: "inventory.report.view" },
      { href: "/relatorios/movimentacoes", label: "Movimentações de estoque", permission: "reports.view_inventory" },
      { href: "/relatorios/precos", label: "Preços por filial", permission: "reports.view_prices" },
      { href: "/relatorios/transferencias", label: "Transferências de estoque", permission: "inventory.report.view" },
    ],
  },
  {
    title: "Inventários",
    description: "Contagens físicas, divergências e impacto histórico.",
    reports: [
      { href: "/relatorios/inventarios", label: "Inventários realizados", permission: "inventory.report.view" },
    ],
  },
];

export const phaseOneReportGroups: readonly ReportCenterGroup[] = reportGroups
  .filter((group) => group.title !== "Inventários")
  .map((group) => ({
    ...group,
    reports: group.reports.filter(
      (report) =>
        ![
          "/relatorios/posicao-estoque",
          "/relatorios/transferencias",
        ].includes(report.href),
    ),
  }));

export type BranchPriceState =
  | { kind: "unavailable"; price: null; detail: "Não disponível" }
  | { kind: "specific"; price: string; detail: "Preço da filial" }
  | { kind: "inherited"; price: string; detail: "Preço padrão" };

export function branchPriceState(
  available: boolean,
  specificPrice: string | null | undefined,
  defaultPrice: string,
): BranchPriceState {
  if (!available) return { kind: "unavailable", price: null, detail: "Não disponível" };
  if (specificPrice != null) {
    return { kind: "specific", price: specificPrice, detail: "Preço da filial" };
  }
  return { kind: "inherited", price: defaultPrice, detail: "Preço padrão" };
}
