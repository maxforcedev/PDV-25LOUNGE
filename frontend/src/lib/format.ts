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

export function formatQuantity(value: unknown) {
  if (typeof value !== "string") return "-";
  const normalized = value.replace(",", ".");
  const [integer, decimal = ""] = normalized.split(".");
  const trimmed = decimal.replace(/0+$/, "");
  return trimmed ? `${integer},${trimmed}` : integer;
}

export function formatBRL(value: unknown) {
  if (typeof value !== "string") return "-";
  const negative = value.startsWith("-");
  const digits = value.replace(/\D/g, "").padStart(3, "0");
  const integer = digits.slice(0, -2).replace(/^0+(?=\d)/, "");
  return `${negative ? "-" : ""}R$ ${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${digits.slice(-2)}`;
}
