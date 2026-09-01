import { centsToDecimal, moneyToCents } from "@/lib/cash";

export function quantityToThousandths(value: unknown): bigint | null {
  if (typeof value !== "string") return null;
  const match = value.trim().replace(",", ".").match(/^(\d+)(?:\.(\d{1,3}))?$/);
  if (!match) return null;
  return BigInt(match[1]) * BigInt(1000) + BigInt((match[2] || "").padEnd(3, "0"));
}

export function thousandthsToDecimal(value: bigint) {
  const negative = value < BigInt(0);
  const absolute = negative ? -value : value;
  const fraction = String(absolute % BigInt(1000)).padStart(3, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${absolute / BigInt(1000)}${fraction ? `.${fraction}` : ""}`;
}

export function modifierContributionCents(price: unknown, quantity: unknown) {
  const cents = moneyToCents(price);
  const units = quantityToThousandths(quantity);
  if (cents === null || units === null) return null;
  const raw = cents * units;
  const whole = raw / BigInt(1000);
  return raw % BigInt(1000) >= BigInt(500) ? whole + BigInt(1) : whole;
}

export function provisionalItemTotal(price: unknown, quantity: unknown) {
  const cents = moneyToCents(price);
  const units = quantityToThousandths(quantity);
  if (cents === null || units === null) return null;
  const raw = cents * units;
  const whole = raw / BigInt(1000);
  const remainder = raw % BigInt(1000);
  // Python Decimal uses half-even rounding when the backend quantizes item subtotals.
  return remainder > BigInt(500) || (remainder === BigInt(500) && whole % BigInt(2) !== BigInt(0)) ? whole + BigInt(1) : whole;
}

export function sumMoney(values: unknown[]) {
  let total = BigInt(0);
  for (const value of values) {
    const cents = moneyToCents(value);
    if (cents === null) return null;
    total += cents;
  }
  return total;
}

export function provisionalCartTotal(items: Array<{ sale_price: string; quantity: string }>) {
  let total = BigInt(0);
  for (const item of items) {
    const itemTotal = provisionalItemTotal(item.sale_price, item.quantity);
    if (itemTotal === null) return null;
    total += itemTotal;
  }
  return total;
}

export { centsToDecimal, moneyToCents };
