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
};

export function domainLabel(value: unknown) {
  const key = String(value ?? "");
  return domainLabels[key] || key || "-";
}
