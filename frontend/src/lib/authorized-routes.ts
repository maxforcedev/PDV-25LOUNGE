import { permissions, reportMenuPermissions } from "@/lib/permissions";
import type { BranchFeature, FeaturePermissionAlternative, User, UserBranch, UserCompany } from "@/types";

const routes: Array<{
  href: string;
  permissions: readonly string[];
  features?: readonly BranchFeature[];
  anyFeature?: boolean;
  alternatives?: readonly FeaturePermissionAlternative[];
}> = [
  { href: "/dashboard", permissions: [permissions.viewDashboard] },
  { href: "/pdv", permissions: [], alternatives: [{ permission: permissions.createSale, features: ["counter", "cash_register"] }, { permission: permissions.createConsumption, features: ["consumption"] }] },
  { href: "/mesas", permissions: [permissions.viewCommands], features: ["tables"] },
  { href: "/comandas", permissions: [permissions.viewCommands], features: ["commands"] },
  { href: "/caixas", permissions: [permissions.viewCashRegister], features: ["cash_register"] },
  { href: "/produtos", permissions: [permissions.viewProduct] },
  { href: "/categorias", permissions: [permissions.viewCategory] },
  { href: "/modificadores", permissions: [permissions.viewModifiers] },
  { href: "/fornecedores", permissions: [permissions.viewSupplier] },
  { href: "/formas-de-pagamento", permissions: [permissions.viewPaymentMethod] },
  { href: "/promocoes", permissions: [permissions.viewPromotion, permissions.changePromotion] },
  { href: "/compras", permissions: [permissions.viewPurchase] },
  { href: "/contas-a-pagar", permissions: [permissions.managePurchasePayables] },
  { href: "/estoque", permissions: [permissions.viewInventory] },
  { href: "/usuarios", permissions: [permissions.viewUser] },
  { href: "/perfis", permissions: [permissions.viewAccessProfile] },
  { href: "/filiais", permissions: [permissions.viewBranch, permissions.addBranch, permissions.changeBranch] },
  { href: "/relatorios", permissions: reportMenuPermissions },
];

export function isOperatingPermission(
  permission: string,
  permissionScopes: Record<string, "COMPANY" | "BRANCH">,
) {
  return permissionScopes[permission] === "BRANCH";
}

export function firstAuthorizedRoute(
  user: User,
  company: UserCompany | null,
  branch: UserBranch | null,
) {
  if (company?.is_owner && !company.can_operate) return "/assinatura";
  if (user.is_superuser) return branch ? "/dashboard" : "/perfil";
  for (const route of routes) {
    const permitted = route.permissions.some((permission) => {
      const source = isOperatingPermission(permission, user.permission_scopes) ? branch : company;
      return source?.permissions.includes(permission);
    });
    const featureAllowed = !route.features || (
      route.anyFeature
        ? route.features.some((feature) => branch?.features?.[feature]?.enabled)
        : route.features.every((feature) => branch?.features?.[feature]?.enabled)
    );
    const alternativeAllowed = route.alternatives?.some(({ permission, features }) =>
      branch?.permissions.includes(permission) && features.every((feature) => branch.features?.[feature]?.enabled)
    );
    if (route.alternatives ? alternativeAllowed : permitted && featureAllowed) return route.href;
  }
  return company?.is_owner ? "/assinatura" : "/perfil";
}
