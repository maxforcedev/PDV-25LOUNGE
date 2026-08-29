import { http } from "@/lib/http";
import type { FractionableProductConfig, InventoryCountStatus, InventoryQuantityGroup, InventoryQuantityGroups, InventoryWorkflowStockOption, LossReason, Product, StockTransferStatus, TransferDivergenceStatus, TransferResolutionType } from "@/types";

export const transferStatusLabels: Record<StockTransferStatus, string> = {
  DRAFT: "Rascunho", IN_TRANSIT: "Em trânsito", PARTIALLY_RECEIVED: "Recebida parcialmente",
  RECEIVED: "Recebida", RECEIVED_WITH_DIVERGENCE: "Recebida com divergência", CANCELLED: "Cancelada",
};
export const divergenceStatusLabels: Record<TransferDivergenceStatus, string> = { PENDING: "Pendente", RESOLVED: "Resolvida" };
export const countStatusLabels: Record<InventoryCountStatus, string> = { OPEN: "Aberto", CONFIRMED: "Confirmado" };
export const resolutionTypeLabels: Record<TransferResolutionType, string> = {
  FOUND_RECEIPT: "Item localizado e recebido", RETURN_TO_ORIGIN: "Retorno confirmado à origem",
  LOSS_IN_TRANSIT: "Perda em trânsito", AUTHORIZED_CORRECTION: "Correção autorizada de separação",
};
export const lossReasonLabels: Record<LossReason, string> = {
  BREAKAGE: "Quebra", EXPIRATION: "Vencimento", DAMAGE: "Avaria", INTERNAL_USE: "Consumo interno",
  MISPLACEMENT: "Extravio", OPERATIONAL_ERROR: "Erro operacional", OTHER: "Outro",
};
export function inventoryTone(status: string) {
  if (["RECEIVED", "RESOLVED", "CONFIRMED"].includes(status)) return "bg-success-surface text-success-strong";
  if (["CANCELLED"].includes(status)) return "bg-danger-surface text-danger-strong";
  if (["PARTIALLY_RECEIVED", "RECEIVED_WITH_DIVERGENCE", "PENDING"].includes(status)) return "bg-warning-surface text-warning-strong";
  return "bg-info-surface text-info-strong";
}
export function apiPagePath(path: string) {
  const url = new URL(path, window.location.origin);
  return /^https?:\/\//.test(path) ? url.toString() : `${url.pathname.replace(/^\//, "")}${url.search}`;
}

export const movementDomainOriginLabels: Record<string, string> = {
  LEGACY: "Legado",
  MANUAL: "Movimentação manual",
  PURCHASE: "Recebimento de compra",
  TRANSFER_DISPATCH: "Despacho de transferência",
  TRANSFER_RECEIPT: "Recebimento de transferência",
  TRANSFER_RETURN: "Retorno de transferência",
  TRANSFER_CORRECTION: "Correção de transferência",
  LOSS: "Registro de perda",
  INVENTORY_COUNT: "Contagem de inventário",
  ORDER: "Comanda",
  ORDER_CANCELLATION: "Cancelamento de comanda",
};

export function movementDomainOriginLabel(value: string | undefined) {
  return value ? movementDomainOriginLabels[value] || value : "Não informado";
}

export function isUnitQuantityValid(value: string, unit: string | undefined, allowZero = false) {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,3})?$/.test(normalized)) return false;
  const quantity = Number(normalized);
  if (!Number.isFinite(quantity) || (allowZero ? quantity < 0 : quantity <= 0)) return false;
  return unit?.toLowerCase() !== "un" || Number.isInteger(quantity);
}

export function quantityInputMode(unit: string | undefined) {
  return unit?.toLowerCase() === "un" ? "numeric" : "decimal";
}

export function isExactContentValid(value: string, allowZero = false) {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,9})?$/.test(normalized)) return false;
  const quantity = Number(normalized);
  return Number.isFinite(quantity) && (allowZero ? quantity >= 0 : quantity > 0);
}

export function contentUnitLabel(unit: string | null | undefined) {
  return unit?.toLowerCase() === "ml" ? "mL" : unit?.toLowerCase() === "g" ? "g" : "";
}

export function packageContentDisplay(content: string | null | undefined, config: FractionableProductConfig | null | undefined) {
  if (!config) return null;
  return exactContentDisplay({ content, packageContent: config.package_content, contentUnit: config.content_unit });
}

type ExactContentDisplay = {
  content?: string | number | null;
  packageContent?: string | number | null;
  contentUnit?: string | null;
  completePackages?: string | number | null;
  residualContent?: string | number | null;
};

function scaledDecimal(value: string | number, places = 9) {
  const normalized = String(value).trim().replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;
  const negative = normalized.startsWith("-");
  const [whole, fraction = ""] = normalized.replace("-", "").split(".");
  const scaled = BigInt(`${whole}${fraction.padEnd(places, "0").slice(0, places)}`);
  return negative ? -scaled : scaled;
}

function displayScaled(value: bigint, places = 9) {
  const zero = BigInt(0);
  const negative = value < zero;
  const absolute = negative ? -value : value;
  const scale = BigInt(10) ** BigInt(places);
  const fraction = String(absolute % scale).padStart(places, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${absolute / scale}${fraction ? `,${fraction}` : ""}`;
}

export function exactContentDisplay({ content, packageContent, contentUnit, completePackages, residualContent }: ExactContentDisplay) {
  const unit = contentUnitLabel(contentUnit);
  if (!unit) return null;
  const total = content == null ? null : scaledDecimal(content);
  const packageSize = packageContent == null ? null : scaledDecimal(packageContent);
  if (total != null && packageSize != null && packageSize > BigInt(0)) {
    const negative = total < BigInt(0);
    const absolute = negative ? -total : total;
    const complete = absolute / packageSize;
    const residual = absolute % packageSize;
    return `${negative ? "-" : ""}${complete} ${complete === BigInt(1) ? "embalagem" : "embalagens"} + ${displayScaled(residual)} ${unit}`;
  }
  if (completePackages != null && residualContent != null) {
    const negative = Number(completePackages) < 0 || Number(residualContent) < 0;
    const complete = negative ? Math.abs(Number(completePackages)) : completePackages;
    const residual = negative ? Math.abs(Number(residualContent)) : residualContent;
    return `${negative ? "-" : ""}${formatPackageCount(complete)} + ${formatContentNumber(residual)} ${unit}`;
  }
  return total == null ? null : `${displayScaled(total)} ${unit}`;
}

function formatPackageCount(value: string | number) {
  const quantity = Number(value);
  return `${Number.isFinite(quantity) ? quantity.toLocaleString("pt-BR", { maximumFractionDigits: 0 }) : value} ${quantity === 1 ? "embalagem" : "embalagens"}`;
}

function formatContentNumber(value: string | number) {
  const scaled = scaledDecimal(value);
  return scaled == null ? String(value) : displayScaled(scaled);
}

export function physicalQuantityDisplay({
  quantity,
  unit,
  content,
  packageContent,
  contentUnit,
  completePackages,
  residualContent,
}: ExactContentDisplay & { quantity?: string | number | null; unit?: string | null }) {
  const exact = exactContentDisplay({ content, packageContent, contentUnit, completePackages, residualContent });
  if (exact) return exact;
  if (quantity == null) return "-";
  const normalizedUnit = String(unit || "").toUpperCase();
  const numeric = Number(quantity);
  const formatted = numeric.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  if (normalizedUnit === "UN" && !Number.isInteger(numeric)) return `${formatted} unidades equivalentes`;
  return `${formatted}${normalizedUnit ? ` ${normalizedUnit}` : ""}`;
}

export async function enrichFractionStockOptions(stocks: InventoryWorkflowStockOption[]) {
  return Promise.all(stocks.map(async (stock) => {
    try {
      const product = await http.get<Product>(`products/${stock.product}/`);
      return { ...stock, fraction_config: product.fraction_config || null };
    } catch {
      return stock;
    }
  }));
}

export function normalizeQuantityGroups(groups: InventoryQuantityGroups | undefined, fallback?: string): InventoryQuantityGroup[] {
  if (Array.isArray(groups)) return groups;
  if (groups) return Object.entries(groups).map(([unit, quantity]) => ({ unit, quantity }));
  return fallback === undefined ? [] : [{ unit: "", quantity: fallback }];
}
