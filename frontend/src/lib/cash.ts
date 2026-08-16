export function normalizeMoney(value: unknown): string | null {
  return typeof value === "string" ? value.trim().replace(",", ".") : null;
}

export function moneyToCents(value: unknown): bigint | null {
  const normalized = normalizeMoney(value);
  if (normalized === null) return null;
  const match = normalized.match(/^(\d+)(?:\.(\d{1,2}))?$/);
  if (!match) return null;
  return BigInt(match[1]) * BigInt(100) + BigInt((match[2] || "").padEnd(2, "0"));
}

export function signedMoneyToCents(value: unknown): bigint | null {
  const normalized = normalizeMoney(value);
  if (normalized === null) return null;
  const negative = normalized.startsWith("-");
  const cents = moneyToCents(negative ? normalized.slice(1) : normalized);
  return cents === null ? null : negative ? -cents : cents;
}

export function centsToDecimal(value: bigint) {
  const negative = value < BigInt(0);
  const absolute = negative ? -value : value;
  return `${negative ? "-" : ""}${absolute / BigInt(100)}.${String(absolute % BigInt(100)).padStart(2, "0")}`;
}

export function canonicalMoney(value: unknown) {
  const cents = moneyToCents(value);
  return cents === null ? null : centsToDecimal(cents);
}

export function subtractMoney(left: unknown, right: unknown) {
  const leftCents = moneyToCents(left);
  const rightCents = moneyToCents(right);
  return leftCents === null || rightCents === null ? null : centsToDecimal(leftCents - rightCents);
}
