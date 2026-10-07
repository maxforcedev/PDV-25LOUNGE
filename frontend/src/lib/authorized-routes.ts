import { permissions, reportMenuPermissions } from "@/lib/permissions";
import type { BranchFeature, FeaturePermissionAlternative, User, UserBranch, UserCompany } from "@/types";

const routes: Array<{
  href: string;
  permissions: readonly string[];
  features?: readonly BranchFeature[];
  anyFeature?: boolean;
  alternatives?: readonly FeaturePermissionAlternative[];
}> = [
  { href: "/dashboard", permissions: [permissions.viewDashboard], features: ["reports"] },
  { href: "/pdv", permissions: [], alternatives: [{ permission: permissions.createSale, features: ["counter", "cash_register"] }, { permission: permissions.createConsumption, features: ["consumption"] }] },
  { href: "/mesas", permissions: [permissions.viewTables], features: ["tables"] },
  { href: "/comandas", permissions: [permissions.viewCommands], features: ["commands"] },
  { href: "/caixas", permissions: [permissions.viewCashRegister], features: ["cash_register"] },
  { href: "/producao/fila", permissions: [permissions.viewPrintJobs], features: ["production"] },
  { href: "/producao/rotas-impressao", permissions: [permissions.managePrintRoutes], features: ["production"] },
  { href: "/producao/impressoras", permissions: [permissions.managePrinters], features: ["production"] },
  { href: "/produtos", permissions: [permissions.viewProduct], features: ["products"] },
  { href: "/categorias", permissions: [permissions.viewCategory], features: ["products"] },
  { href: "/modificadores", permissions: [permissions.viewModifiers], features: ["products"] },
  { href: "/fornecedores", permissions: [permissions.viewSupplier], features: ["suppliers"] },
  { href: "/clientes", permissions: [permissions.viewCustomer], features: ["customers"] },
  { href: "/formas-de-pagamento", permissions: [permissions.viewPaymentMethod], features: ["financial"] },
  { href: "/promocoes", permissions: [permissions.viewPromotion, permissions.changePromotion], features: ["promotions"] },
  { href: "/compras", permissions: [permissions.viewPurchase], features: ["purchases"] },
  { href: "/contas-a-pagar", permissions: [permissions.managePurchasePayables], features: ["purchases", "financial"] },
  { href: "/estoque", permissions: [permissions.viewInventory], features: ["inventory"] },
  { href: "/usuarios", permissions: [permissions.viewUser] },
  { href: "/perfis", permissions: [permissions.viewAccessProfile] },
  { href: "/filiais", permissions: [permissions.viewBranch, permissions.addBranch, permissions.changeBranch] },
  { href: "/pos-dispositivos", permissions: [permissions.viewPosDevices, permissions.managePosDevices], features: ["pos"] },
  { href: "/relatorios", permissions: reportMenuPermissions, features: ["reports"] },
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
