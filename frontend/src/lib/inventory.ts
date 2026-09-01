import { formatQuantity } from "@/lib/format";
import type { FractionableProductConfig, InventoryCountStatus, InventoryQuantityGroup, InventoryQuantityGroups, LossReason, StockTransferStatus, TransferDivergenceStatus, TransferResolutionType } from "@/types";

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
  const quantity = inventoryDecimalToScaled(normalized, 3);
  if (quantity === null || (allowZero ? quantity < BigInt(0) : quantity <= BigInt(0))) return false;
  return unit?.toLowerCase() !== "un" || quantity % BigInt(1000) === BigInt(0);
}

export function quantityInputMode(unit: string | undefined) {
  return unit?.toLowerCase() === "un" ? "numeric" : "decimal";
}

export function isExactContentValid(value: string, allowZero = false) {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,9})?$/.test(normalized)) return false;
  const quantity = inventoryDecimalToScaled(normalized);
  return quantity !== null && (allowZero ? quantity >= BigInt(0) : quantity > BigInt(0));
}

export function contentUnitLabel(unit: string | null | undefined) {
  return unit?.toLowerCase() === "ml" ? "mL" : unit?.toLowerCase() === "g" ? "g" : "";
}

export function packageContentDisplay(
  content: string | null | undefined,
  config: Pick<FractionableProductConfig, "package_content" | "content_unit"> | null | undefined,
) {
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

export function inventoryDecimalToScaled(value: unknown, places = 9) {
  const normalized = typeof value === "string"
    ? value.trim().replace(",", ".")
    : typeof value === "number" && Number.isFinite(value)
      ? String(value)
      : "";
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;
  const negative = normalized.startsWith("-");
  const [rawWhole, rawFraction = ""] = normalized.replace("-", "").split(".");
  const fraction = rawFraction.replace(/0+$/, "");
  if (fraction.length > places) return null;
  const whole = rawWhole.replace(/^0+(?=\d)/, "");
  const scaled = BigInt(`${whole}${fraction.padEnd(places, "0")}`);
  return negative ? -scaled : scaled;
}

export function inventoryScaledToDecimal(value: bigint, places = 9) {
  const zero = BigInt(0);
  const negative = value < zero;
  const absolute = negative ? -value : value;
  const scale = BigInt(10) ** BigInt(places);
  const fraction = String(absolute % scale).padStart(places, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${absolute / scale}${fraction ? `.${fraction}` : ""}`;
}

export function inventoryDecimalSign(value: unknown, places = 9) {
  const scaled = inventoryDecimalToScaled(value, places);
  return scaled === null ? null : scaled < BigInt(0) ? -1 : scaled > BigInt(0) ? 1 : 0;
}

export function compareInventoryDecimals(left: unknown, right: unknown, places = 9) {
  const leftScaled = inventoryDecimalToScaled(left, places);
  const rightScaled = inventoryDecimalToScaled(right, places);
  if (leftScaled === null || rightScaled === null) return null;
  return leftScaled < rightScaled ? -1 : leftScaled > rightScaled ? 1 : 0;
}

export function sumInventoryDecimals(values: unknown[], places = 9) {
  let total = BigInt(0);
  for (const value of values) {
    const scaled = inventoryDecimalToScaled(value, places);
    if (scaled === null) return null;
    total += scaled;
  }
  return inventoryScaledToDecimal(total, places);
}

export function subtractInventoryDecimals(left: unknown, right: unknown, places = 9) {
  const leftScaled = inventoryDecimalToScaled(left, places);
  const rightScaled = inventoryDecimalToScaled(right, places);
  return leftScaled === null || rightScaled === null
    ? null
    : inventoryScaledToDecimal(leftScaled - rightScaled, places);
}

export function divideInventoryDecimals(left: unknown, right: unknown, places = 9) {
  const leftScaled = inventoryDecimalToScaled(left, places);
  const rightScaled = inventoryDecimalToScaled(right, places);
  if (leftScaled === null || rightScaled === null || rightScaled === BigInt(0)) return null;
  const scale = BigInt(10) ** BigInt(places);
  return inventoryScaledToDecimal((leftScaled * scale) / rightScaled, places);
}

function displayScaled(value: bigint, places = 9) {
  return inventoryScaledToDecimal(value, places).replace(".", ",");
}

export function exactContentDisplay({ content, packageContent, contentUnit, completePackages, residualContent }: ExactContentDisplay) {
  const unit = contentUnitLabel(contentUnit);
  if (!unit) return null;
  const total = content == null ? null : inventoryDecimalToScaled(content);
  const packageSize = packageContent == null ? null : inventoryDecimalToScaled(packageContent);
  if (total != null && packageSize != null && packageSize > BigInt(0)) {
    const negative = total < BigInt(0);
    const absolute = negative ? -total : total;
    const complete = absolute / packageSize;
    const residual = absolute % packageSize;
    return `${negative ? "-" : ""}${complete} ${complete === BigInt(1) ? "embalagem" : "embalagens"} + ${displayScaled(residual)} ${unit}`;
  }
  if (completePackages != null && residualContent != null) {
    const complete = inventoryDecimalToScaled(completePackages);
    const residual = inventoryDecimalToScaled(residualContent);
    if (complete !== null && residual !== null) {
      const negative = complete < BigInt(0) || residual < BigInt(0);
      return `${negative ? "-" : ""}${formatPackageCount(complete < BigInt(0) ? -complete : complete)} + ${displayScaled(residual < BigInt(0) ? -residual : residual)} ${unit}`;
    }
  }
  return total == null ? null : `${displayScaled(total)} ${unit}`;
}

function formatPackageCount(value: bigint) {
  const scale = BigInt(10) ** BigInt(9);
  const quantity = value / scale;
  return `${quantity.toLocaleString("pt-BR")} ${quantity === BigInt(1) ? "embalagem" : "embalagens"}`;
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
  const formatted = formatQuantity(quantity);
  const scaled = inventoryDecimalToScaled(quantity);
  const scale = BigInt(10) ** BigInt(9);
  if (normalizedUnit === "UN" && scaled !== null && scaled % scale !== BigInt(0)) return `${formatted} unidades equivalentes`;
  return `${formatted}${normalizedUnit ? ` ${normalizedUnit}` : ""}`;
}

export function normalizeQuantityGroups(groups: InventoryQuantityGroups | undefined, fallback?: string): InventoryQuantityGroup[] {
  if (Array.isArray(groups)) return groups;
  if (groups) return Object.entries(groups).map(([unit, quantity]) => ({ unit, quantity }));
  return fallback === undefined ? [] : [{ unit: "", quantity: fallback }];
}
