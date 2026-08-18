import { permissions, reportMenuPermissions } from "@/lib/permissions";
import type { User, UserBranch, UserCompany } from "@/types";

const OPERATING_MODULES = new Set([
  "products", "categories", "branch_prices", "inventory", "cash_registers",
  "sales", "payment_methods", "reports", "dashboard", "promotions", "audit_logs",
]);

const OPERATING_PERMISSIONS = new Set<string>([
  permissions.viewCommission,
  permissions.changeBranchCommission,
  permissions.changeUserCommission,
]);

const routes = [
  ["/dashboard", [permissions.viewDashboard]],
  ["/empresas", [permissions.viewCompany, permissions.changeCompany]],
  ["/filiais", [permissions.viewBranch, permissions.addBranch, permissions.changeBranch]],
  ["/perfis", [permissions.viewAccessProfile]],
  ["/usuarios", [permissions.viewUser]],
  ["/usuarios/bloqueios", [permissions.viewPermissionBlock]],
  ["/categorias", [permissions.viewCategory]],
  ["/produtos", [permissions.viewProduct]],
  ["/estoque", [permissions.viewInventory]],
  ["/estoque/movimentacoes", [permissions.viewInventoryHistory]],
  ["/caixas", [permissions.viewCashRegister]],
  ["/pdv", [permissions.createSale, permissions.createConsumption]],
  ["/vendas", [permissions.viewSale]],
  ["/consumacoes", [permissions.viewConsumption]],
  ["/formas-de-pagamento", [permissions.viewPaymentMethod]],
  ["/promocoes", [permissions.viewPromotion, permissions.changePromotion]],
  ["/relatorios", reportMenuPermissions],
  ["/auditoria", [permissions.viewAuditLog]],
] as const;

export function isOperatingPermission(permission: string) {
  return OPERATING_MODULES.has(permission.split(".")[0]) || OPERATING_PERMISSIONS.has(permission);
}

export function firstAuthorizedRoute(
  user: User,
  company: UserCompany | null,
  branch: UserBranch | null,
) {
  if (user.is_superuser) return branch ? "/dashboard" : "/sobre-mim";
  for (const [href, required] of routes) {
    if (required.some((permission) => {
      const source = isOperatingPermission(permission) ? branch : company;
      return source?.permissions.includes(permission);
    })) return href;
  }
  return "/sobre-mim";
}
