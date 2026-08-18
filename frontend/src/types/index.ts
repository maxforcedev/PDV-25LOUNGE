export type Status = "active" | "inactive";
export interface UserCompany {
  id: number;
  trade_name: string;
  status: Status;
  access_profile: { id: number | null; name: string | null } | null;
  permissions: string[];
}

export interface UserBranch {
  id: number;
  name: string;
  company_id: number;
  status: Status;
  access_profile: { id: number | null; name: string | null } | null;
  permissions: string[];
}

export interface User {
  id: number;
  email: string | null;
  can_login: boolean;
  user_type: UserType;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_superuser: boolean;
  companies: UserCompany[];
  branches: UserBranch[];
  permission_blocks: Array<{
    id: number;
    company: number;
    company_name: string;
    branch: number | null;
    branch_name: string | null;
    permission_code: string;
    permission_label: string;
    reason: string;
  }>;
  created_at: string;
  updated_at: string;
}

export interface Company {
  id: number;
  trade_name: string;
  legal_name: string;
  cnpj: string | null;
  email: string;
  phone: string;
  status: Status;
  branches: Branch[];
  created_at: string;
  updated_at: string;
}

export interface Address {
  zip_code: string;
  street: string;
  number: string;
  complement?: string;
  neighborhood: string;
  city: string;
  state: string;
}

export interface Branch {
  id: number;
  company: number;
  company_name: string;
  name: string;
  cnpj: string | null;
  phone: string;
  email: string;
  address: Address | string | null;
  status: Status;
  is_matrix: boolean;
  address_pending: boolean;
  settings_summary: Omit<
    BranchSettings,
    "id" | "branch" | "created_at" | "updated_at"
  > | null;
  created_at: string;
  updated_at: string;
}

export interface BranchSettings {
  id: number;
  branch: number;
  allow_negative_stock: boolean;
  service_fee_rate: string;
  commission_rate?: string;
  fixed_daily_cost: string;
  negative_stock_count: number;
  negative_stock_state:
    | "clear"
    | "enabled_with_negatives"
    | "legacy_inconsistent";
  created_at: string;
  updated_at: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface CompanyPayload {
  trade_name: string;
  legal_name: string;
  cnpj: string | null;
  email: string;
  phone: string;
}

export interface BranchPayload {
  company: number;
  name: string;
  cnpj: string | null;
  phone: string;
  email: string;
  address: Address;
}

export interface UserProfilePayload {
  first_name: string;
  last_name: string;
}

export interface UserPayload {
  email: string | null;
  password?: string | null;
  can_login: boolean;
  user_type: UserType;
  first_name: string;
  last_name: string;
  company_accesses: Array<{
    company_id: number;
    access_profile_id: number | null;
    branch_accesses: Array<{ branch_id: number; access_profile_id: number }>;
  }>;
}

export type UserType = "employee" | "promoter" | "dj" | "artist" | "other";

export interface AccessProfile {
  id: number;
  company: number;
  company_name: string;
  name: string;
  description: string;
  is_system: boolean;
  status: Status;
  receives_commission?: boolean;
  commission_rate?: string | null;
  permission_codes: string[];
  created_at: string;
  updated_at: string;
}

export interface FunctionalPermission {
  code: string;
  module: string;
  label: string;
  description: string;
}

export interface Category {
  id: number;
  company: number;
  company_name: string;
  name: string;
  description: string;
  sort_order: number;
  product_count: number;
  related_products: Array<{
    id: number;
    name: string;
    internal_code: string;
    sale_price: string;
    status: Status;
  }>;
  status: Status;
  created_at: string;
  updated_at: string;
}

export type InventoryBehavior = "direct" | "none" | "components";

export interface ProductComponent {
  component_product: number;
  component_name: string;
  component_internal_code: string;
  quantity: string;
  component_unit: string;
  quantity_display: string;
}

export interface Product {
  id: number;
  company: number;
  company_name: string;
  category: number;
  category_name: string;
  name: string;
  description: string;
  internal_code: string;
  barcode: string;
  unit: string;
  cost: string | null;
  sale_price: string;
  is_sellable: boolean;
  is_favorite: boolean;
  inventory_behavior: InventoryBehavior;
  status: Status;
  image: string | null;
  components: ProductComponent[];
  suggested_cost: string | null;
  suggested_sale_price: string | null;
  created_at: string;
  updated_at: string;
}

export interface BranchProductPrice {
  id: number;
  product: number;
  product_name: string;
  internal_code: string;
  branch: number;
  branch_name: string;
  default_price: string;
  sale_price: string;
  created_at: string;
  updated_at: string;
}

export interface ProductPriceComparison {
  branches: Array<{ id: number; name: string }>;
  products: Array<{
    id: number;
    name: string;
    internal_code: string;
    default_price: string;
    prices: Record<string, string | null>;
  }>;
}

export interface Stock {
  id: number;
  product: number;
  product_name: string;
  internal_code: string;
  branch: number;
  branch_name: string;
  unit: string;
  category: number | null;
  category_name: string;
  unit_cost?: string | null;
  total_cost: string | null;
  product_status: Status;
  inventory_behavior: InventoryBehavior;
  current_quantity: string;
  minimum_quantity: string;
  state: "normal" | "below_minimum" | "zero" | "negative";
  created_at: string;
  updated_at: string;
}

export interface StockMovement {
  id: number;
  product: number;
  product_name: string;
  internal_code: string;
  branch: number;
  branch_name: string;
  unit: string;
  previous_quantity: string;
  movement_quantity: string;
  final_quantity: string;
  type: "entry" | "exit" | "adjustment" | string;
  user_name: string;
  reason: string;
  sale: number | null;
  sale_number: string | null;
  sale_operation_type: SaleOperation | null;
  nature: string;
  operation_reference: string;
  operation_label: string;
  operation_count: number;
  created_at: string;
}

export type CashSessionStatus = "open" | "closed";
export type CashMovementType = "manual_entry" | "withdrawal";

export interface OpenSession {
  id: number;
  status: CashSessionStatus;
  opened_at: string;
  opening_amount: string;
  opened_by_name: string;
}

export interface CashRegister {
  id: number;
  branch: number;
  branch_name: string;
  company: number;
  company_name: string;
  name: string;
  status: Status;
  open_session: OpenSession | null;
  created_at: string;
  updated_at: string;
}

export interface CashSession {
  id: number;
  cash_register: number;
  cash_register_name: string;
  register_name: string;
  branch: number;
  branch_name: string;
  company: number;
  company_name: string;
  opened_by: number;
  opened_by_name: string;
  opened_at: string;
  opening_amount: string;
  status: CashSessionStatus;
  closed_by: number | null;
  closed_by_name: string | null;
  closed_at: string | null;
  closing_expected_amount: string | null;
  closing_amount_informed: string | null;
  closing_difference: string | null;
  expected_amount: string;
  manual_entries: string;
  withdrawals: string;
  created_at: string;
  updated_at: string;
}

export interface CashMovement {
  id: number;
  cash_session: number;
  cash_register: number;
  register_name: string;
  branch: number;
  branch_name: string;
  movement_type: CashMovementType;
  amount: string;
  user: number;
  user_name: string;
  reason: string;
  category: WithdrawalCategory | null;
  category_label: string | null;
  beneficiary: CashBeneficiary | null;
  result_effect: "unclassified" | "operating_expense" | "neutral";
  operation_reference: string;
  created_at: string;
}

export type WithdrawalCategory =
  | "dj"
  | "artist"
  | "advance"
  | "promoter"
  | "supplier"
  | "other";

export interface CashBeneficiary {
  id: number;
  name: string;
  user_type: UserType;
  can_login?: boolean;
}

export interface CashSummary {
  opening_amount: string;
  manual_entries: string;
  withdrawals: string;
  expected_amount: string;
  status: CashSessionStatus;
  sale_cash: string;
  consumption_cash: string;
  cash_reversals: string;
  cash_cancellations: number;
  cash_payments: string;
  closing_amount_informed: string | null;
  closing_difference: string | null;
  sales: {
    count: number;
    gross: string;
    promotion_discount: string;
    item_discount: string;
    account_discount: string;
    manual_discount: string;
    effective_revenue: string;
    service_fee: string;
    commission?: string;
    customer_total: string;
    cancellations: { count: number; value: string };
  };
  consumptions: {
    count: number;
    reference: string;
    charged: string;
    benefit: string;
    cancellations: { count: number; value: string };
  };
  payment_totals: Array<{
    payment_method_code: string;
    payment_method_name: string;
    amount: string;
  }>;
}

export type SessionTimelineKind =
  | "open"
  | "manual_entry"
  | "withdrawal"
  | "cash_sale"
  | "charged_consumption"
  | "cancellation"
  | "close";

export interface SessionTimelineEvent {
  id: string;
  timestamp: string;
  kind: SessionTimelineKind;
  label: string;
  amount: string;
  sale: {
    id: number;
    number: string;
    operation_type: SaleOperation;
    status: SaleStatus;
  } | null;
  details: string;
  reason?: string | null;
  beneficiary_name?: string | null;
  registered_by_name?: string | null;
  category_label?: string | null;
}

export interface SessionTimeline {
  count: number;
  results: SessionTimelineEvent[];
}

export interface PaymentMethod {
  id: number;
  company: number;
  code: string;
  name: string;
  status: Status;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface CheckoutCashSession {
  id: number;
  register_name: string;
  opened_by_name: string;
}

export interface CheckoutPaymentMethod {
  id: number;
  code: string;
  name: string;
  status: Status;
  is_system: boolean;
}

export interface CheckoutOptions {
  payment_methods: CheckoutPaymentMethod[];
  cash_sessions: CheckoutCashSession[];
}

export interface SaleCategory {
  id: number;
  name: string;
}

export type SaleOperation = "sale" | "consumption";
export type SaleStatus = "finalized" | "cancelled";

export interface SaleItem {
  id: number;
  product: number;
  quantity: string;
  product_name: string;
  internal_code: string;
  unit: string;
  unit_cost?: string | null;
  unit_price: string;
  subtotal: string;
  promotion: number | null;
  promotion_name: string | null;
  promotion_discount_type: "percentage" | "fixed_amount" | null;
  promotion_discount_value: string | null;
  promotion_benefit: string;
  manual_discount: string;
  discount_approved_by: number | null;
  discount_approved_by_name: string | null;
  component_cost_snapshot?: Array<{
    product: number;
    product_name: string;
    internal_code: string;
    unit: string;
    quantity_per_unit: string;
    consumed_quantity: string;
    unit_cost: string;
    unit_cost_contribution: string;
  }>;
  net_subtotal: string;
  created_at: string;
}

export interface Payment {
  id: number;
  payment_method: number;
  payment_method_name: string;
  payment_method_code: string;
  amount: string;
  received_amount: string | null;
  change_amount: string | null;
  created_at: string;
}

export interface Sale {
  id: number;
  company: number;
  company_name: string;
  branch: number;
  branch_name: string;
  cash_session: number | null;
  cash_session_status: CashSessionStatus | null;
  sale_number: string;
  idempotency_key: string | null;
  operation_type: SaleOperation;
  status: SaleStatus;
  created_by: number;
  created_by_name: string;
  seller_user: number | null;
  seller_user_name: string | null;
  discount_approved_by: number | null;
  discount_approved_by_name: string | null;
  beneficiary_user: number | null;
  beneficiary_user_name: string | null;
  subtotal: string;
  promotion_discount_total: string;
  item_discount_total: string;
  discount: string;
  service_fee_rate: string;
  service_fee_amount: string;
  service_fee_waived: boolean;
  service_fee_waived_by: number | null;
  service_fee_waived_by_name: string | null;
  commission_rate?: string;
  commission_amount?: string;
  charged_amount: string | null;
  total: string;
  cancelled_at: string | null;
  cancelled_by: number | null;
  cancelled_by_name: string | null;
  cancellation_reason: string | null;
  items: SaleItem[];
  payments: Payment[];
  created_at: string;
  updated_at: string;
}

export interface SaleBeneficiary {
  id: number;
  name: string;
  user_type: UserType;
  can_login: boolean;
}

export interface SaleUserOption {
  id: number;
  name: string;
  email: string | null;
}

export interface SalePreviewItem {
  product: number;
  quantity: string;
  product_name: string;
  internal_code: string;
  unit: string;
  unit_cost: string | null;
  unit_price: string;
  subtotal: string;
  promotion: number | null;
  promotion_name: string | null;
  promotion_discount_type: "percentage" | "fixed_amount" | null;
  promotion_discount_value: string | null;
  promotion_benefit: string;
  manual_discount: string;
  net_subtotal: string;
}

export interface SalePreview {
  operation_type: SaleOperation;
  items: SalePreviewItem[];
  subtotal: string;
  promotion_discount_total: string;
  item_discount_total: string;
  discount: string;
  service_fee_rate: string;
  service_fee_amount: string;
  service_fee_waived: boolean;
  commission_rate?: string;
  commission_amount?: string;
  charged_amount: string | null;
  reference_total: string;
  total: string;
}

export interface PromotionSchedule {
  id?: number;
  weekday: number;
  start_time: string;
  end_time: string;
}

export interface Promotion {
  id: number;
  name: string;
  branch: number | null;
  branch_name: string;
  broker_all_branches: boolean;
  discount_type: "percentage" | "fixed_amount";
  discount_value: string;
  starts_at: string;
  ends_at: string | null;
  schedules: PromotionSchedule[];
  status: Status;
  product_ids: number[];
  category_ids: number[];
  product_names: string[];
  category_names: string[];
  product_count: number;
  category_count: number;
  created_at: string;
  updated_at: string;
}

export interface ReportPeriod {
  start_datetime: string;
  end_datetime: string;
}
export interface ReportSale {
  id: number;
  sale_number: string;
  operation_type: SaleOperation;
  status: SaleStatus;
  operator: { id: number; name: string };
  seller: { id: number; name: string } | null;
  discount_approved_by: { id: number; name: string } | null;
  beneficiary: { id: number; name: string; user_type: UserType } | null;
  subtotal: string;
  promotion_discount_total: string;
  item_discount_total: string;
  discount: string;
  service_fee_rate: string;
  service_fee_amount: string;
  commission_rate?: string;
  commission_amount?: string;
  total: string;
  effective_revenue: string;
  total_received_sales: string;
  customer_total: string;
  payment_reconciliation_delta: string;
  created_at: string;
  cancelled_at: string | null;
  items: Array<Record<string, unknown>>;
  payments: Array<Record<string, unknown>>;
}
export interface CashReportRow {
  id: number;
  opened_at: string;
  closed_at: string | null;
  status: string;
  register: { id: number; name: string };
  operator: { id: number; name: string };
  opening: string;
  manual_entries: string;
  sale_cash: string;
  consumption_cash: string;
  cash_reversals: string;
  cash_cancellations: number;
  cash_payments: string;
  withdrawals: string;
  expected: string;
  informed: string | null;
  difference: string | null;
  operational_summary: CashSummary;
}

export interface PaymentSourceTotal {
  code: string;
  name: string;
  commercial_received: string;
  consumption_received: string;
  gross_received: string;
  reversals: string;
  net_received: string;
}

export interface CommercialReportSummary {
  gross: string;
  effective_revenue: string;
  count: number;
  average: string;
  ticket_average: string;
  account_discount: string;
  item_discount: string;
  manual_discount: string;
  promotion_discount: string;
  total_discount: string;
  service_fee: string;
  commission?: string;
  customer_total: string;
  total_received_sales: string;
  payment_reconciliation_delta: string;
  discount_reconstruction_delta: string;
  received_reconstruction_delta: string;
  commission_sale_count: number;
  commission_attendant_count: number;
  cancellations: CancellationReportSummary;
}

export interface ReceiptsReportSummary {
  effective_revenue: string;
  sales_count: number;
  consumption_count: number;
  service_fee: string;
  fee_contained: string;
  sales_received: string;
  commercial_payments: string;
  consumption_charged: string;
  charged_consumption_payments: string;
  consumption_received: string;
  gross_received: string;
  reversals: string;
  total_operational_received: string;
  semantic_operational_received: string;
  reconciliation_delta: string;
  payment_totals: PaymentSourceTotal[];
  filtered_payment_method?: {
    code: string;
    name: string;
    subtotal: string;
    is_integral_revenue: false;
  };
}

export interface CancellationReportSummary {
  count: number;
  value: string;
  reversed_effective_revenue: string;
  reversed_service_fee: string;
  reversed_total_received: string;
  reconciliation_delta: string;
}

export interface ConsumptionReportSummary {
  count: number;
  reference: string;
  charged: string;
  subsidy: string;
  benefit: string;
  quantity: string;
  payment_totals: Array<{ code: string; name: string; amount: string }>;
  payment_reconciliation_delta: string;
  historical_cost?: string;
  historical_consumption_cogs?: string;
}

export interface CashReportSummary {
  count: number;
  session_rows_scope: "complete_session";
  top_summary_scope: "requested_period_events";
  complete_session_totals: {
    opening: string;
    manual_entries: string;
    sale_cash: string;
    consumption_cash: string;
    cash_reversals: string;
    cash_payments: string;
    withdrawals: string;
    expected: string;
    informed: string;
    difference: string;
  };
  sales_count: number;
  consumption_count: number;
  effective_revenue: string;
  service_fee: string;
  sales_received: string;
  consumption_charged: string;
  operational_received: string;
  reversals: string;
  reconciliation_delta: string;
  manual_entries: string;
  withdrawals: string;
  opening: string;
  expected: string;
  informed: string;
  difference: string;
  payment_totals: PaymentSourceTotal[];
  commission?: string;
}

export interface OperationalResultReportSummary {
  gross: string;
  promotion_discount: string;
  item_discount: string;
  account_discount: string;
  manual_discount: string;
  discounts: string;
  effective_revenue: string;
  service_fee: string;
  customer_total: string;
  total_received_sales: string;
  payment_reconciliation_delta: string;
  charged_consumption: string;
  operational_received: string;
  historical_sales_cogs: string;
  historical_consumption_cogs: string;
  commission?: string;
  operating_expenses: string;
  fixed_cost: string;
  estimated_result: string;
  result: string;
  margin: string;
  operational_reconciliation_delta: string;
  unclassified_withdrawals: { count: number; amount: string };
  cash_session: number | null;
  notice: string;
}
export interface DashboardData {
  period: ReportPeriod;
  filters?: {
    category: number | null;
    categories: Array<{ id: number; name: string }>;
  };
  sales?: {
    revenue: string;
    gross: string;
    effective_revenue: string;
    customer_total: string;
    total_received_sales: string;
    payment_reconciliation_delta: string;
    total_received_operational?: string;
    operational_reconciliation_delta?: string;
    service_fee: string;
    commission?: string;
    count: number;
    average: string;
    account_discount: string;
    item_discount: string;
    manual_discount: string;
    manual_discount_count: number;
    promotion_discount: string;
    total_discount: string;
    cancellations: { count: number; value: string };
    payment_distribution: Array<{ code: string; name: string; amount: string }>;
    payment_distribution_scope: "operational" | "sales_only";
    hourly_sales: Array<{
      hour: string;
      count: number;
      effective_revenue: string;
      service_fee: string;
      customer_total: string;
    }>;
    top_products: Array<{
      product_id?: number;
      product_name: string;
      quantity: string;
      revenue: string;
    }>;
    top_categories: Array<{
      category_id?: number;
      category_name: string;
      quantity: string;
      revenue: string;
    }>;
    top_sellers: ReportUserGroup[];
    top_operators: ReportUserGroup[];
    heatmap: Array<{
      weekday: number;
      hour: number;
      count: number;
      revenue: string;
      average: string;
    }>;
    weekly_comparison: {
      current: Array<{ date: string; count: number; revenue: string }>;
      previous: Array<{ date: string; count: number; revenue: string }>;
    };
    latest_sales: ReportSale[];
  };
  consumptions?: {
    count: number;
    reference: string;
    charged: string;
    subsidy: string;
  };
  withdrawals?: { count: number; amount: string };
  current_cash?: CashReportRow[];
  inventory?: {
    zero_count: number;
    negative_count: number;
    below_minimum_count: number;
    physical_products: number;
    inventory_value?: string;
  };
  operational_result?: {
    result: string;
    estimated_result: string;
    margin: string;
    operational_received: string;
    charged_consumption: string;
    historical_sales_cogs: string;
    historical_consumption_cogs: string;
    commission?: string;
    operating_expenses: string;
    fixed_cost: string;
    operational_reconciliation_delta: string;
  };
}
export interface ReportUserGroup {
  user: { id: number; name: string };
  count: number;
  gross: string;
  effective_revenue: string;
  service_fee: string;
  commission?: string;
  commission_sale_count?: number;
  customer_total: string;
  total_received: string;
  payment_reconciliation_delta: string;
  average: string;
  cancellation_count: number;
  cancellation_value: string;
}
export interface ReportResponse<T, S = Record<string, unknown>> extends Paginated<T> {
  period: ReportPeriod;
  summary: S;
}
export interface ReportsOptions {
  operators: Array<{ id: number; name: string }>;
  sellers: Array<{ id: number; name: string }>;
  beneficiaries: Array<{ id: number; name: string; user_type: UserType }>;
  products: Array<{
    id: number;
    name: string;
    internal_code: string;
    status: Status;
  }>;
  categories: Array<{ id: number; name: string; status: Status }>;
  payment_methods: Array<{
    id: number;
    name: string;
    code: string;
    status: Status;
  }>;
  cash_registers: Array<{ id: number; name: string; status: Status }>;
  cash_sessions: Array<{
    id: number;
    name: string;
    status: string;
    opened_at: string;
    closed_at: string | null;
  }>;
  movement_types: Array<{ value: string; label: string }>;
  withdrawal_categories: Array<{ value: string; label: string }>;
  user_types: Array<{ value: string; label: string }>;
  sale_statuses: Array<{ value: string; label: string }>;
}

export interface AuditLog {
  id: number;
  company: number | null;
  company_name: string | null;
  branch: number | null;
  branch_name: string | null;
  actor: number | null;
  actor_name: string | null;
  action: string;
  action_label: string;
  module_label: string;
  object_label: string;
  object_type: string;
  object_id: string;
  changes: Array<{
    field: string;
    field_label: string;
    before_label: string;
    after_label: string;
  }>;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditOptions {
  modules: Array<{ value: string; label: string }>;
  actions: Array<{ value: string; label: string }>;
}

export interface UserPermissionBlock {
  id: number;
  company: number;
  company_name: string;
  branch: number | null;
  branch_name: string | null;
  user: number;
  user_name: string;
  permission_code: string;
  permission_label: string;
  reason: string;
  is_active: boolean;
  created_by: number | null;
  created_by_name: string | null;
  revoked_by: number | null;
  revoked_by_name: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PermissionBlockOptions {
  users: Array<{ id: number; name: string; email: string | null }>;
  branches: Array<{ id: number; name: string }>;
  permissions: FunctionalPermission[];
}

export interface UserCommissionOverride {
  id: number;
  branch: number;
  branch_name: string;
  user: number;
  user_name: string;
  receives_commission: boolean;
  commission_rate: string | null;
  created_at: string;
  updated_at: string;
}
