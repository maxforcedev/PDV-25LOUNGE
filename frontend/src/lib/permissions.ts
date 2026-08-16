import type { User, UserCompany } from "@/types";

export const permissions = {
  viewCompany: "companies.view", changeCompany: "companies.change",
  viewBranch: "branches.view", addBranch: "branches.add", changeBranch: "branches.change",
  viewUser: "users.view", addUser: "users.add", changeUser: "users.change", changeUserStatus: "users.change_status",
  viewAccessProfile: "access_profiles.view", addAccessProfile: "access_profiles.add", changeAccessProfile: "access_profiles.change", changeAccessProfileStatus: "access_profiles.change_status",
  viewProduct: "products.view", addProduct: "products.add", changeProduct: "products.change", changeProductStatus: "products.change_status", configureComposition: "products.configure_composition",
  viewInventory: "inventory.view", moveInventory: "inventory.move", changeMinimum: "inventory.change_minimum", viewInventoryHistory: "inventory.view_history",
  viewStockKpis: "inventory.view_stock_kpis", viewStockCosts: "inventory.view_stock_costs",
  viewCashRegister: "cash_registers.view", openCashRegister: "cash_registers.open", manualCashEntry: "cash_registers.manual_entry", withdrawCash: "cash_registers.withdraw", closeCashRegister: "cash_registers.close",
  createSale: "sales.create", viewSale: "sales.view", cancelSale: "sales.cancel", applyDiscount: "sales.apply_discount",
  createConsumption: "sales.create_consumption", viewConsumption: "sales.view_consumption", cancelConsumption: "sales.cancel_consumption",
  viewPaymentMethod: "payment_methods.view", changePaymentMethod: "payment_methods.change",
  viewSalesReport: "reports.view_sales", viewConsumptionsReport: "reports.view_consumptions", viewCashReport: "reports.view_cash", viewWithdrawalsReport: "reports.view_withdrawals", viewInventoryReport: "reports.view_inventory", exportReports: "reports.export",
  viewPromotion: "promotions.view", changePromotion: "promotions.change",
} as const;

export function hasPermission(user: User | null, company: UserCompany | null, permission: string) {
  return !!user && (user.is_superuser || !!company?.permissions.includes(permission));
}

export function hasAnyPermission(user: User | null, company: UserCompany | null, required: readonly string[]) {
  return !!user && (user.is_superuser || required.some((code) => company?.permissions.includes(code)));
}
