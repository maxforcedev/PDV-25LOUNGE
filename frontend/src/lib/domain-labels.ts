export const domainLabels: Record<string, string> = {
  finalized: "Finalizada", cancelled: "Cancelada", open: "Aberta", closed: "Fechada",
  sale: "Venda", consumption: "Consumação", sale_cancellation: "Cancelamento de venda",
  consumption_cancellation: "Cancelamento de consumação", manual_entry: "Entrada manual",
  withdrawal: "Sangria", entry: "Entrada", exit: "Saída", adjustment: "Ajuste",
  fixed_amount: "Valor fixo", percentage: "Percentual", normal: "Normal",
  bonus: "Bonificada", return: "Devolução", opening_balance: "Saldo inicial",
  correction: "Correção", transfer: "Transferência", damage: "Avaria", loss: "Perda",
  internal_use: "Uso interno", inventory: "Inventário", regularization: "Regularização",
  balance_correction: "Correção de saldo", other: "Outros", manual_exit: "Saída manual",
  reversal: "Reversão/cancelamento", cash: "Dinheiro", pix: "PIX",
  credit_card: "Crédito", debit_card: "Débito", operating_expense: "Despesa operacional",
  neutral: "Não afeta resultado", unclassified: "Não classificado",
  DRAFT: "Rascunho", IN_TRANSIT: "Em trânsito", PARTIALLY_RECEIVED: "Recebida parcialmente",
  RECEIVED: "Recebida", RECEIVED_WITH_DIVERGENCE: "Recebida com divergência", CANCELLED: "Cancelada",
  PENDING: "Pendente", RESOLVED: "Resolvida", OPEN: "Aberto", CONFIRMED: "Confirmado",
  FOUND_RECEIPT: "Item localizado e recebido", RETURN_TO_ORIGIN: "Retorno confirmado à origem",
  LOSS_IN_TRANSIT: "Perda em trânsito", AUTHORIZED_CORRECTION: "Correção autorizada de separação",
  BREAKAGE: "Quebra", EXPIRATION: "Vencimento", DAMAGE: "Avaria", INTERNAL_USE: "Consumo interno",
  MISPLACEMENT: "Extravio", OPERATIONAL_ERROR: "Erro operacional", OTHER: "Outro",
  LEGACY: "Legado", MANUAL: "Movimentação manual", PURCHASE: "Recebimento de compra",
  TRANSFER_DISPATCH: "Despacho de transferência", TRANSFER_RECEIPT: "Recebimento de transferência",
  TRANSFER_RETURN: "Retorno de transferência", TRANSFER_CORRECTION: "Correção de transferência",
  LOSS: "Registro de perda", INVENTORY_COUNT: "Contagem de inventário",
  direct: "Estoque próprio", none: "Sem estoque", components: "Baixa por componentes",
  counter: "Balcão", table: "Mesa", command: "Comanda", ml: "mL", g: "g",
};

export function domainLabel(value: unknown) {
  const key = String(value ?? "");
  return domainLabels[key] || (key ? "Não identificado" : "-");
}
