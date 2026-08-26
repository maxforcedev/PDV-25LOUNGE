import type { User, UserCompany } from "@/types";

export const permissions = {
  viewCompany: "companies.view", changeCompany: "companies.change",
  viewBranch: "branches.view", addBranch: "branches.add", changeBranch: "branches.change",
  changeBranchSettings: "branches.change_settings",
  viewUser: "users.view", addUser: "users.add", changeUser: "users.change", changeUserStatus: "users.change_status",
  viewPermissionBlock: "user_permission_blocks.view", changePermissionBlock: "user_permission_blocks.change",
  viewAccessProfile: "access_profiles.view", addAccessProfile: "access_profiles.add", changeAccessProfile: "access_profiles.change", changeAccessProfileStatus: "access_profiles.change_status",
  viewProduct: "products.view", addProduct: "products.add", changeProduct: "products.change", changeProductStatus: "products.change_status", configureComposition: "products.configure_composition",
  changeProductCost: "products.change_cost", changeProductPrice: "products.change_price",
  configureProductBranch: "products.configure_branch", configureProductFraction: "products.configure_fraction",
  configureProductDestinations: "products.configure_destinations", duplicateProduct: "products.duplicate",
  viewSupplier: "suppliers.view", changeSupplier: "suppliers.change",
  viewModifiers: "modifiers.view", changeModifiers: "modifiers.change",
  viewPurchase: "purchases.view", createPurchase: "purchases.create", placePurchase: "purchases.place",
  receivePurchase: "purchases.receive", closePurchase: "purchases.close", viewPurchaseCosts: "purchases.view_costs",
  managePurchasePayables: "purchases.manage_payables",
  viewCategory: "categories.view", addCategory: "categories.add", changeCategory: "categories.change", changeCategoryStatus: "categories.change_status",
  viewBranchPrice: "branch_prices.view", changeBranchPrice: "branch_prices.change",
  viewCompanyBranchPrice: "branch_prices.view_company", changeCompanyBranchPrice: "branch_prices.change_company",
  viewInventory: "inventory.view", moveInventory: "inventory.move", changeMinimum: "inventory.change_minimum", viewInventoryHistory: "inventory.view_history",
  inventoryEntry: "inventory.entry", inventoryExit: "inventory.exit", inventoryAdjust: "inventory.adjust", regularizeInventory: "inventory.regularize",
  viewStockKpis: "inventory.view_stock_kpis", viewStockCosts: "inventory.view_stock_costs",
  viewTransfers: "inventory.transfer.view", createTransfer: "inventory.transfer.create",
  dispatchTransfer: "inventory.transfer.dispatch", receiveTransfer: "inventory.transfer.receive",
  resolveTransfer: "inventory.transfer.resolve", recordLoss: "inventory.loss.record",
  performInventoryCount: "inventory.count.perform", viewAdvancedInventory: "inventory.report.view",
  viewCashRegister: "cash_registers.view", openCashRegister: "cash_registers.open", manualCashEntry: "cash_registers.manual_entry", withdrawCash: "cash_registers.withdraw", closeCashRegister: "cash_registers.close",
  addCashRegister: "cash_registers.add", changeCashRegister: "cash_registers.change", changeCashRegisterStatus: "cash_registers.change_status", administerOtherCash: "cash_registers.administer_others",
  createSale: "sales.create", viewSale: "sales.view", cancelSale: "sales.cancel", applyDiscount: "sales.apply_discount", applyItemDiscount: "sales.apply_item_discount", waiveServiceFee: "sales.waive_service_fee",
  createConsumption: "sales.create_consumption", viewConsumption: "sales.view_consumption", cancelConsumption: "sales.cancel_consumption",
  viewCommands: "commands.view", openCommand: "commands.open", addCommandItems: "commands.add_items", cancelCommandItems: "commands.cancel_items", finalizeCommand: "commands.finalize",
  viewPaymentMethod: "payment_methods.view", changePaymentMethod: "payment_methods.change",
  viewSalesReport: "reports.view_sales", viewConsumptionsReport: "reports.view_consumptions", viewCashReport: "reports.view_cash", viewWithdrawalsReport: "reports.view_withdrawals", viewInventoryReport: "reports.view_inventory", viewOperationalResult: "reports.view_operational_result", viewStockConsumptionReport: "reports.view_stock_consumption", exportReports: "reports.export",
  viewPromotion: "promotions.view", changePromotion: "promotions.change",
  viewDashboard: "dashboard.view",
  viewProductsReport: "reports.view_products", viewReceiptsReport: "reports.view_receipts", viewTeamReport: "reports.view_team", viewDiscountsReport: "reports.view_discounts", viewCancellationsReport: "reports.view_cancellations", viewPricesReport: "reports.view_prices",
  viewAuditLog: "audit_logs.view",
  viewCommission: "commissions.view", changeBranchCommission: "commissions.change_branch_default", changeProfileCommission: "commissions.change_profile", changeUserCommission: "commissions.change_user_override",
} as const;

export const reportMenuPermissions = [
  permissions.viewSalesReport,
  permissions.viewConsumptionsReport,
  permissions.viewCashReport,
  permissions.viewWithdrawalsReport,
  permissions.viewInventoryReport,
  permissions.viewOperationalResult,
  permissions.viewStockConsumptionReport,
  permissions.viewProductsReport,
  permissions.viewReceiptsReport,
  permissions.viewTeamReport,
  permissions.viewDiscountsReport,
  permissions.viewCancellationsReport,
  permissions.viewPricesReport,
  permissions.viewCommission,
  permissions.viewAdvancedInventory,
] as const;

export function hasPermission(user: User | null, company: UserCompany | null, permission: string) {
  return !!user && (user.is_superuser || !!company?.permissions.includes(permission));
}

export function hasAnyPermission(user: User | null, company: UserCompany | null, required: readonly string[]) {
  return !!user && (user.is_superuser || required.some((code) => company?.permissions.includes(code)));
}
