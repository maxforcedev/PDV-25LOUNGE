import { formatQuantity } from "./format";

export function ticketModifierLabel(value: unknown) {
  if (typeof value === "string") return value;
  const item = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const quantity = formatQuantity(String(item.selected_quantity ?? item.quantity ?? "1"));
  const name = String(item.option_name ?? item.name ?? "");
  return name ? `${quantity}x ${name}` : "";
}
