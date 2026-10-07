import type { BranchFeature } from "@/types";

type HasFeature = (feature: BranchFeature) => boolean;

const routeFeatures: ReadonlyArray<[string, readonly BranchFeature[]]> = [
  ["/relatorios/caixa", ["reports", "cash_register"]],
  ["/relatorios/sangrias", ["reports", "cash_register"]],
  ["/relatorios/compras", ["reports", "purchases"]],
  ["/relatorios/fornecedores", ["reports", "suppliers"]],
  ["/relatorios/contas-a-pagar", ["reports", "purchases", "financial"]],
  ["/relatorios/posicao-estoque", ["reports", "inventory"]],
  ["/relatorios/movimentacoes", ["reports", "inventory"]],
  ["/relatorios/transferencias", ["reports", "inventory"]],
  ["/relatorios/inventarios", ["reports", "inventory"]],
  ["/relatorios/estoque-avancado", ["reports", "inventory"]],
  ["/relatorios/consumo-estoque", ["reports", "inventory"]],
  ["/relatorios/precos", ["reports", "products"]],
  ["/relatorios/produtos", ["reports", "products"]],
  ["/relatorios/modificadores", ["reports", "products"]],
  ["/relatorios/clientes", ["reports", "customers"]],
  ["/relatorios/promocoes", ["reports", "promotions"]],
  ["/relatorios/consumacoes", ["reports", "consumption"]],
  ["/relatorios/mesas-comandas", ["reports", "tables", "commands"]],
  ["/relatorios/tickets", ["reports", "production"]],
  ["/relatorios", ["reports"]],
  ["/producao", ["production"]],
  ["/caixas", ["cash_register"]],
  ["/estoque", ["inventory"]],
  ["/compras", ["purchases"]],
  ["/fornecedores", ["suppliers"]],
  ["/clientes", ["customers"]],
  ["/promocoes", ["promotions"]],
  ["/produtos", ["products"]],
  ["/categorias", ["products"]],
  ["/modificadores", ["products"]],
  ["/formas-de-pagamento", ["financial"]],
  ["/contas-a-pagar", ["purchases", "financial"]],
  ["/pos-dispositivos", ["pos"]],
  ["/auditoria", ["audit"]],
  ["/mesas", ["tables"]],
  ["/comandas", ["commands"]],
  ["/consumacoes", ["consumption"]],
];

export function requiredFeaturesForPath(pathname: string) {
  return routeFeatures.find(([path]) => pathname === path || pathname.startsWith(`${path}/`))?.[1] ?? [];
}

export function isFeaturePathAllowed(pathname: string, hasFeature: HasFeature) {
  return requiredFeaturesForPath(pathname).every(hasFeature);
}

export function isFunctionalPermissionAvailable(code: string, hasFeature: HasFeature) {
  if (code.startsWith("suppliers.")) return hasFeature("suppliers");
  if (code.startsWith("purchases.")) return hasFeature("purchases");
  if (code.startsWith("inventory.")) return hasFeature("inventory");
  if (code.startsWith("cash_registers.")) return hasFeature("cash_register");
  if (code.startsWith("customers.")) return hasFeature("customers");
  if (code.startsWith("promotions.")) return hasFeature("promotions");
  if (code.startsWith("tables.")) return hasFeature("tables");
  if (code.startsWith("commands.")) return hasFeature("commands");
  if (code.startsWith("production.") || code.startsWith("printers.") || code.startsWith("print_routes.") || code.startsWith("print_jobs.") || code.startsWith("tickets.")) return hasFeature("production");
  if (code.startsWith("products.") || code.startsWith("categories.") || code.startsWith("modifiers.") || code.startsWith("branch_prices.")) return hasFeature("products");
  if (code.startsWith("payment_methods.") || code.startsWith("commissions.")) return hasFeature("financial");
  if (code.startsWith("reports.") || code.startsWith("dashboard.")) return hasFeature("reports");
  if (code.startsWith("audit_logs.")) return hasFeature("audit");
  if (code.startsWith("pos_devices.")) return hasFeature("pos");
  if (code === "sales.create") return hasFeature("counter") && hasFeature("cash_register");
  if (code.includes("consumption")) return hasFeature("consumption");
  if (code.startsWith("sales.")) return hasFeature("counter") || hasFeature("consumption");
  return true;
}
