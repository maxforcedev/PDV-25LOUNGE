export function formatDate(value: string) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(value));
}

export function initials(firstName: string, lastName: string) {
  return `${firstName?.[0] || ""}${lastName?.[0] || ""}`.toUpperCase() || "U";
}

export function fieldError(fields: Record<string, string[]>, name: string) {
  return fields[name]?.join(" ");
}

function normalizeDecimal(value: unknown) {
  const raw =
    typeof value === "string"
      ? value.trim()
      : typeof value === "number" && Number.isFinite(value)
        ? String(value)
        : "";
  const normalized = raw.replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;

  const negative = normalized.startsWith("-");
  const [whole, fraction = ""] = normalized.replace("-", "").split(".");
  const integer = whole.replace(/^0+(?=\d)/, "");
  const decimal = fraction.replace(/0+$/, "");
  const isZero = integer === "0" && !decimal;
  return `${negative && !isZero ? "-" : ""}${integer}${decimal ? `.${decimal}` : ""}`;
}

export function decimalIsZero(value: unknown) {
  return normalizeDecimal(value) === "0";
}

export function decimalIsOne(value: unknown) {
  return normalizeDecimal(value) === "1";
}

export function decimalEquals(a: unknown, b: unknown) {
  const left = normalizeDecimal(a);
  const right = normalizeDecimal(b);
  return left !== null && left === right;
}

export function decimalCompare(a: unknown, b: unknown) {
  const left = normalizeDecimal(a);
  const right = normalizeDecimal(b);
  if (left === null || right === null) return null;
  if (left === right) return 0;
  const leftNegative = left.startsWith("-");
  const rightNegative = right.startsWith("-");
  if (leftNegative !== rightNegative) return leftNegative ? -1 : 1;
  const [leftWhole, leftFraction = ""] = left.replace("-", "").split(".");
  const [rightWhole, rightFraction = ""] = right.replace("-", "").split(".");
  const fractionLength = Math.max(leftFraction.length, rightFraction.length);
  const leftMagnitude = `${leftWhole}${leftFraction.padEnd(fractionLength, "0")}`;
  const rightMagnitude = `${rightWhole}${rightFraction.padEnd(fractionLength, "0")}`;
  const magnitude = leftWhole.length !== rightWhole.length
    ? leftWhole.length < rightWhole.length ? -1 : 1
    : leftMagnitude < rightMagnitude ? -1 : 1;
  return leftNegative ? -magnitude : magnitude;
}

export function formatQuantity(value: unknown, unit?: string) {
  const normalized = normalizeDecimal(value);
  if (normalized === null) return "-";
  const formatted = normalized.replace(".", ",");
  if (!unit) return formatted;
  const u = unit.toUpperCase();
  const [integer, decimal = ""] = normalized.replace("-", "").split(".");
  const scale = BigInt(10) ** BigInt(decimal.length);
  const scaled = BigInt(`${integer}${decimal}`);
  const thousand = BigInt(1000) * scale;
  const isExactThousandMultiple =
    !normalized.startsWith("-") && scaled >= thousand && scaled % thousand === BigInt(0);
  if (u === "ML") {
    if (isExactThousandMultiple) return `${scaled / thousand} L`;
    return `${formatted} mL`;
  }
  if (u === "G") {
    if (isExactThousandMultiple) return `${scaled / thousand} kg`;
    return `${formatted} g`;
  }
  if (u === "KG") return `${formatted} kg`;
  if (u === "UN") return !decimalIsZero(normalized) ? `${formatted} UN` : formatted;
  if (u === "L") return `${formatted} L`;
  return `${formatted} ${u}`;
}

export function formatEditableDecimal(value: unknown) {
  return normalizeDecimal(value) || "";
}

export function formatPercent(value: unknown) {
  const normalized = normalizeDecimal(value);
  return normalized === null ? "-" : `${normalized.replace(".", ",")}%`;
}

export function formatBRL(value: unknown) {
  if (typeof value !== "string") return "-";
  const negative = value.startsWith("-");
  const digits = value.replace(/\D/g, "").padStart(3, "0");
  const integer = digits.slice(0, -2).replace(/^0+(?=\d)/, "");
  return `${negative ? "-" : ""}R$ ${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${digits.slice(-2)}`;
}

export function formatDecimalBRL(value: unknown) {
  const normalized = normalizeDecimal(value);
  if (normalized === null) return "-";
  const negative = normalized.startsWith("-");
  const [whole, fraction = ""] = normalized.replace("-", "").split(".");
  let cents = BigInt(whole) * BigInt(100) + BigInt((fraction + "00").slice(0, 2));
  if ((fraction[2] || "0") >= "5") cents += BigInt(1);
  return formatBRL(`${negative ? "-" : ""}${cents}`);
}
