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

export function formatQuantity(value: unknown, unit?: string) {
  if (typeof value !== "string") return "-";
  const normalized = value.replace(",", ".");
  const num = parseFloat(normalized);
  if (isNaN(num)) return "-";
  const [integer, decimal = ""] = normalized.split(".");
  const trimmed = decimal.replace(/0+$/, "");
  const formatted = trimmed ? `${integer},${trimmed}` : integer;
  if (!unit) return formatted;
  const u = unit.toUpperCase();
  if (u === "ML") {
    if (num >= 1000 && num % 1000 === 0) return `${num / 1000} L`;
    return `${formatted} mL`;
  }
  if (u === "G") {
    if (num >= 1000 && num % 1000 === 0) return `${num / 1000} kg`;
    return `${formatted} g`;
  }
  if (u === "KG") return `${formatted} kg`;
  if (u === "UN") return formatted && formatted !== "0" ? `${formatted} UN` : formatted;
  if (u === "L") return `${formatted} L`;
  return `${formatted} ${u}`;
}

export function formatBRL(value: unknown) {
  if (typeof value !== "string") return "-";
  const negative = value.startsWith("-");
  const digits = value.replace(/\D/g, "").padStart(3, "0");
  const integer = digits.slice(0, -2).replace(/^0+(?=\d)/, "");
  return `${negative ? "-" : ""}R$ ${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${digits.slice(-2)}`;
}

export function formatDecimalBRL(value: unknown) {
  if (typeof value !== "string" || !/^-?\d+(\.\d+)?$/.test(value)) return "-";
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace("-", "").split(".");
  let cents = BigInt(whole) * BigInt(100) + BigInt((fraction + "00").slice(0, 2));
  if ((fraction[2] || "0") >= "5") cents += BigInt(1);
  return formatBRL(`${negative ? "-" : ""}${cents / BigInt(100)}.${String(cents % BigInt(100)).padStart(2, "0")}`);
}
