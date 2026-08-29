import type {
  PayableInstallmentStatus,
  PurchaseOrderStatus,
  PurchaseOrderType,
} from "@/types";

export const purchaseTypeLabels: Record<PurchaseOrderType, string> = {
  ORDER: "Pedido de compra",
  DIRECT: "Entrada direta",
};

export const purchaseStatusLabels: Record<PurchaseOrderStatus, string> = {
  DRAFT: "Rascunho",
  PLACED: "Realizado",
  PARTIALLY_RECEIVED: "Recebido parcialmente",
  RECEIVED: "Recebido",
  CANCELLED: "Cancelado",
  CLOSED_PARTIAL: "Parcial encerrado",
};

export const payableStatusLabels: Record<PayableInstallmentStatus, string> = {
  PENDING: "Pendente",
  PAID: "Paga",
  CANCELLED: "Cancelada",
};

export function decimalToScaled(value: string, places: number): bigint {
  const normalized = value.trim().replace(",", ".");
  if (!/^-?\d*(\.\d*)?$/.test(normalized)) return BigInt(0);
  const negative = normalized.startsWith("-");
  const [whole = "0", fraction = ""] = normalized.replace("-", "").split(".");
  const scaled =
    BigInt(whole || "0") * BigInt(10) ** BigInt(places) +
    BigInt((fraction + "0".repeat(places)).slice(0, places));
  return negative ? -scaled : scaled;
}

export function lineTotalCents(quantity: string, price: string): bigint {
  const product = decimalToScaled(quantity, 6) * decimalToScaled(price, 6);
  return (product + BigInt(5_000_000_000)) / BigInt(10_000_000_000);
}

function scaledText(value: bigint, places: number, decimalSeparator = ".") {
  const negative = value < BigInt(0);
  const absolute = negative ? -value : value;
  const divisor = BigInt(10) ** BigInt(places);
  const whole = absolute / divisor;
  const fraction = String(absolute % divisor)
    .padStart(places, "0")
    .replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole}${fraction ? `${decimalSeparator}${fraction}` : ""}`;
}

export function purchaseBaseUnitPrice(
  presentationPrice: string,
  conversionFactor: string,
) {
  const factor = decimalToScaled(conversionFactor, 6);
  if (factor <= BigInt(0)) return "";
  const numerator = decimalToScaled(presentationPrice, 6) * BigInt(1_000_000);
  return scaledText((numerator + factor / BigInt(2)) / factor, 6);
}

export function purchasePresentationPrice(
  basePrice: string,
  conversionFactor: string,
) {
  return scaledText(
    (decimalToScaled(basePrice, 6) * decimalToScaled(conversionFactor, 6)) /
      BigInt(1_000_000),
    6,
  );
}

export function purchasePresentationLabel(code: string, description: string) {
  const text = description.trim().toLocaleLowerCase("pt-BR");
  return `${code} — ${text ? `${text[0].toLocaleUpperCase("pt-BR")}${text.slice(1)}` : "Apresentação"}`;
}

function baseUnitLabel(unit: string, quantity: bigint) {
  if (unit.toUpperCase() === "UN")
    return quantity === BigInt(1) ? "unidade" : "unidades";
  return unit;
}

export function purchaseBaseEquivalent(
  quantity: string,
  conversionFactor: string,
  presentationDescription: string,
  stockUnit: string,
) {
  const amount = decimalToScaled(quantity, 6);
  const factor = decimalToScaled(conversionFactor, 6);
  if (amount < BigInt(0) || factor <= BigInt(0)) return "";
  const packages = amount / factor;
  const remainder = amount % factor;
  const factorText = scaledText(factor, 6, ",");
  const packageWord = (
    presentationDescription
      .trim()
      .toLocaleLowerCase("pt-BR")
      .match(/^([^\s]+)(?:\s+com\s+\d+(?:[,.]\d+)?\s+unidades?)?/)?.[1] || "apresentação"
  );
  const packageText = `${packages} ${packageWord}${packages === BigInt(1) ? "" : "s"} de ${factorText}`;
  const remainderText = `${scaledText(remainder, 6, ",")} ${baseUnitLabel(stockUnit, remainder)}`;
  if (!packages) return remainderText;
  if (!remainder) return packageText;
  return `${packageText} + ${remainderText}`;
}

export function moneyCents(value: string): bigint {
  return decimalToScaled(value, 2);
}

export function centsText(value: bigint): string {
  return `${value / BigInt(100)}.${String(value % BigInt(100)).padStart(2, "0")}`;
}

export function compareDecimal(left: string, right: string, places = 6) {
  const a = decimalToScaled(left, places);
  const b = decimalToScaled(right, places);
  return a === b ? 0 : a > b ? 1 : -1;
}

export function inDatePeriod(value: string, start: string, end: string) {
  const timestamp = new Date(value).getTime();
  return (
    (!start || timestamp >= new Date(start).getTime()) &&
    (!end || timestamp <= new Date(end).getTime())
  );
}

export type ReceiptKeyState = "ready" | "pending" | "ambiguous";
export interface ReceiptKeyRecord {
  fingerprint: string;
  idempotencyKey: string;
  state: ReceiptKeyState;
}

function receiptKeyStorageKey(purchaseId: number) {
  return `pdv.purchase_receipt_keys.${purchaseId}`;
}

export function receiptPayloadFingerprint(payload: {
  items: Array<{
    purchase_order_item: number;
    received_quantity?: string;
    received_stock_quantity?: string;
    divergence_reason: string;
  }>;
  notes: string;
  divergence_reason: string;
}) {
  return JSON.stringify({
    items: [...payload.items].sort(
      (left, right) => left.purchase_order_item - right.purchase_order_item,
    ),
    notes: payload.notes.trim(),
    divergence_reason: payload.divergence_reason.trim(),
  });
}

export function readReceiptKeys(purchaseId: number): ReceiptKeyRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(
      sessionStorage.getItem(receiptKeyStorageKey(purchaseId)) || "[]",
    );
    if (!Array.isArray(value)) return [];
    return value.filter(
      (item): item is ReceiptKeyRecord =>
        !!item &&
        typeof item.fingerprint === "string" &&
        typeof item.idempotencyKey === "string" &&
        ["ready", "pending", "ambiguous"].includes(item.state),
    );
  } catch {
    return [];
  }
}

function writeReceiptKeys(purchaseId: number, records: ReceiptKeyRecord[]) {
  if (typeof window === "undefined") return;
  try {
    if (records.length)
      sessionStorage.setItem(
        receiptKeyStorageKey(purchaseId),
        JSON.stringify(records),
      );
    else sessionStorage.removeItem(receiptKeyStorageKey(purchaseId));
  } catch {
    // Receipt submission still works when browser storage is unavailable.
  }
}

export function ensureReceiptKey(
  purchaseId: number,
  fingerprint: string,
  state: ReceiptKeyState,
) {
  const records = readReceiptKeys(purchaseId);
  const existing = records.find((item) => item.fingerprint === fingerprint);
  if (existing) {
    if (state !== "ready" || existing.state === "ready") existing.state = state;
    writeReceiptKeys(purchaseId, records);
    return existing.idempotencyKey;
  }
  const record = { fingerprint, idempotencyKey: crypto.randomUUID(), state };
  writeReceiptKeys(purchaseId, [...records, record]);
  return record.idempotencyKey;
}

export function updateReceiptKeyState(
  purchaseId: number,
  fingerprint: string,
  state: ReceiptKeyState,
) {
  const records = readReceiptKeys(purchaseId);
  const record = records.find((item) => item.fingerprint === fingerprint);
  if (!record) return;
  record.state = state;
  writeReceiptKeys(purchaseId, records);
}

export function removeReceiptKey(purchaseId: number, fingerprint: string) {
  writeReceiptKeys(
    purchaseId,
    readReceiptKeys(purchaseId).filter(
      (item) => item.fingerprint !== fingerprint,
    ),
  );
}

export function reconcileReceiptKeys(
  purchaseId: number,
  committedKeys: string[],
) {
  const committed = new Set(committedKeys);
  const records = readReceiptKeys(purchaseId);
  const matched = records.filter((item) => committed.has(item.idempotencyKey));
  const remaining = records
    .filter((item) => !committed.has(item.idempotencyKey))
    .map((item) => ({ ...item, state: "ready" as const }));
  writeReceiptKeys(purchaseId, remaining);
  return matched;
}

const attachmentTypes: Record<string, { mime: string; signature: number[] }> = {
  pdf: { mime: "application/pdf", signature: [0x25, 0x50, 0x44, 0x46, 0x2d] },
  png: {
    mime: "image/png",
    signature: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
  },
  jpg: { mime: "image/jpeg", signature: [0xff, 0xd8, 0xff] },
  jpeg: { mime: "image/jpeg", signature: [0xff, 0xd8, 0xff] },
};

export async function validatePurchaseAttachmentFile(file: File) {
  if (!file.size || file.size > 10 * 1024 * 1024)
    return "O anexo deve ter entre 1 byte e 10 MB.";
  if (file.name.length > 120 || /[\x00-\x1f\\/]/.test(file.name))
    return "Use um nome de arquivo seguro com até 120 caracteres.";
  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  const expected = attachmentTypes[extension];
  if (!expected) return "Selecione um arquivo PDF, JPG ou PNG.";
  if (file.type && file.type !== expected.mime)
    return "O tipo declarado do arquivo não corresponde à extensão.";
  const header = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  if (!expected.signature.every((value, index) => header[index] === value))
    return "O conteúdo do arquivo não corresponde ao tipo informado.";
  return "";
}
