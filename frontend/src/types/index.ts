export type Status = "active" | "inactive";
export interface UserCompany {
  id: number;
  trade_name: string;
  status: Status;
  is_owner: boolean;
  saas_status?: "ACTIVE" | "SUSPENDED_BY_PLAN_LIMIT" | string;
  effective_status: SaaSEffectiveStatus;
  can_operate: boolean;
  access_profile?: { id: number | null; name: string | null } | null;
  permissions: string[];
}

export type BranchFeature =
  | "tables"
  | "commands"
  | "counter"
  | "consumption"
  | "cash_register";

export interface BranchFeatureState {
  enabled: boolean;
  plan_allowed: boolean;
}

export interface FeaturePermissionAlternative {
  permission: string;
  features: readonly BranchFeature[];
}

export interface UserBranch {
  id: number;
  name: string;
  company_id: number;
  status: Status;
  access_profile: { id: number | null; name: string | null } | null;
  permissions: string[];
  features: Record<string, BranchFeatureState>;
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
  profile_photo_url: string | null;
  birth_date: string | null;
  cpf: string;
  zip_code: string;
  street: string;
  address_number: string;
  address_complement: string;
  neighborhood: string;
  city: string;
  state: string;
  last_login: string | null;
  archived_at: string | null;
  membership?: {
    id: number;
    company_id: number;
    is_active: boolean;
    is_owner: boolean;
    saas_status: string;
    access_profile_id: number | null;
    branch_accesses: Array<{ branch_id: number; access_profile_id: number }>;
  } | null;
  companies: UserCompany[];
  branches: UserBranch[];
  permission_scopes: Record<string, "COMPANY" | "BRANCH">;
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
  support_session?: SupportSessionContext | null;
  created_at: string;
  updated_at: string;
}

export type SaaSEffectiveStatus =
  | "PENDING_APPROVAL"
  | "TRIALING"
  | "ACTIVE"
  | "PAST_DUE"
  | "RESTRICTED"
  | "SUSPENDED_FINANCIAL"
  | "SUSPENDED_ADMIN"
  | "TRIAL_EXPIRED"
  | "CANCELLED"
  | "ARCHIVED"
  | "REJECTED"
  | "UNMAPPED"
  | "INVALID_ENTITLEMENTS"
  | "INVALID_SUBSCRIPTION"
  | string;

export interface SupportSessionContext {
  id: number;
  actor?: number;
  actor_email?: string;
  company: number;
  company_name?: string;
  impersonated_user?: number | null;
  impersonated_user_name?: string | null;
  mode: "READ_ONLY" | "READ_WRITE";
  reason: string;
  expires_at: string;
  ended_at?: string | null;
  created_at?: string;
}

export interface PublicBranding {
  platform_name: string;
  logo_url: string;
  compact_logo_url: string;
  favicon_url: string;
  logo_light_url?: string;
  logo_dark_url?: string;
  compact_logo_light_url?: string;
  compact_logo_dark_url?: string;
  primary_color: string;
  support_email: string;
  support_phone: string;
  institutional_links: Record<string, string>;
}

export interface PublicPlan {
  id: number;
  code: string;
  name: string;
  description: string;
  version: number;
  price: string;
  currency: string;
  billing_period_months: number;
  trial_days: number;
  limits: {
    users: { unlimited: boolean; value: number | null };
    branches: { unlimited: boolean; value: number | null };
  };
}

export interface ProvisioningResult {
  id: string;
  detail: string;
}

export type SubscriptionStatus =
  | "TRIALING"
  | "ACTIVE"
  | "PAST_DUE"
  | "RESTRICTED"
  | "SUSPENDED_FINANCIAL"
  | "TRIAL_EXPIRED"
  | "CANCELLED"
  | "SUPERSEDED";

export interface Subscription {
  id: number;
  company: number;
  plan_version: number;
  plan_name: string;
  plan_version_number: number;
  billing_mode: "PAID" | "FREE" | "INTERNAL";
  status: SubscriptionStatus;
  is_current: boolean;
  current_period_start: string;
  current_period_end: string;
  trial_started_at: string | null;
  trial_ends_at: string | null;
  cancel_at_period_end: boolean;
  cancellation_reason: string;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlanEntitlement {
  id: number;
  plan_version: number;
  capability: number;
  capability_code: string;
  enabled: boolean;
  unlimited: boolean;
  limit_value: number | null;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionUsage {
  capability_code: string;
  period_start: string;
  period_end: string;
  quantity: number;
}

export interface OwnerSubscriptionContext {
  subscription: Subscription;
  effective_status: SaaSEffectiveStatus;
  entitlements: PlanEntitlement[];
  usage: SubscriptionUsage[];
}

export interface BillingRecord {
  id: number;
  subscription: number;
  amount: string;
  paid_at: string;
  payment_method: string;
  note: string;
  competency_start: string;
  competency_end: string;
  actor: number;
  actor_email: string;
  proof_reference: string;
  idempotency_key: string;
  created_at: string;
}

export interface SubscriptionChangeRequest {
  id: number;
  subscription: number;
  request_type: "PLAN_CHANGE" | "CANCELLATION";
  requested_plan_version: number | null;
  reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  requested_by: number;
  resolved_by: number | null;
  resolved_at: string | null;
  created_at: string;
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
  uses_tables: boolean;
  uses_commands: boolean;
  uses_counter: boolean;
  uses_consumption: boolean;
  uses_cash_register: boolean;
  charges_service_fee: boolean;
  default_table_quantity: number;
  table_range_start: number;
  table_range_end: number;
  default_table_seats: number;
  default_table_prefix: string;
  consumption_limit_enabled: boolean;
  command_consumption_limit: string | null;
  table_consumption_limit: string | null;
  feature_flags?: Record<string, boolean>;
  negative_stock_count: number;
  negative_stock_state:
    "clear" | "enabled_with_negatives" | "legacy_inconsistent";
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
  birth_date: string;
  cpf: string;
  zip_code: string;
  street: string;
  address_number: string;
  address_complement: string;
  neighborhood: string;
  city: string;
  state: string;
}

export interface UserPayload {
  email: string | null;
  password?: string | null;
  can_login: boolean;
  user_type: UserType;
  first_name: string;
  last_name: string;
  birth_date: string | null;
  cpf: string;
  zip_code: string;
  street: string;
  address_number: string;
  address_complement: string;
  neighborhood: string;
  city: string;
  state: string;
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
  user_count?: number;
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
  available_counter: boolean;
  available_table: boolean;
  available_command: boolean;
  participates_in_service_fee: boolean;
  participates_in_commission: boolean;
  product_count: number;
  related_products: Array<{
    id: number;
    name: string;
    internal_code: string;
    sale_price: string;
    status: Status;
  }>;
  status: Status;
  deleted_at: string | null;
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

export type ContentUnit = "ml" | "g";
export type SalesChannel = "counter" | "table" | "command";

export interface ProductFractionComponent {
  component_product: number;
  component_name: string;
  component_internal_code: string;
  content_quantity: string;
  content_unit: ContentUnit;
}

export interface FractionableProductConfig {
  id: number;
  product: number;
  package_content: string;
  content_unit: ContentUnit;
  tracking_active: boolean;
  activated_at: string | null;
  activated_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProductBranchConfiguration {
  branch: number;
  is_available: boolean;
  channels: Record<SalesChannel, boolean>;
  sale_price: string;
  participation: {
    participates_in_service_fee: boolean;
    participates_in_commission: boolean;
  };
}

export interface ProductBranchConfig {
  id?: number;
  product: number;
  product_name: string;
  branch: number;
  branch_name: string;
  is_available: boolean;
  available_counter: boolean | null;
  available_table: boolean | null;
  available_command: boolean | null;
  participates_in_service_fee: boolean | null;
  participates_in_commission: boolean | null;
  effective_participation: {
    participates_in_service_fee: boolean;
    participates_in_commission: boolean;
  };
  effective_channels: Record<SalesChannel, boolean>;
  effective_sale_price: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProductBranchStock {
  applicable: boolean;
  semantic: "actual" | "components" | "not_applicable";
  stock_id?: number | null;
  current_quantity?: string;
  minimum_quantity?: string;
  unit?: string;
  unit_cost?: string;
  current_content?: string;
  content_unit?: ContentUnit;
  package_content?: string;
}

export interface ProductionDestination {
  id: number;
  branch: number;
  branch_name: string;
  name: string;
  code: string;
  status: Status;
  created_at: string;
  updated_at: string;
}

export type PrintJobStatus = "pending" | "processing" | "printed" | "failed" | "cancelled";

export interface PrinterDevice {
  id: number;
  branch: number;
  name: string;
  device_type: "manual" | "development";
  connection_type: "network" | "usb" | "bluetooth";
  status: Status;
  destination_ids: number[];
  technical_configuration: Record<string, unknown>;
  connection_summary: string;
  operational_status:
    | "not_tested"
    | "online"
    | "offline"
    | "bridge_unavailable"
    | "failed";
  last_seen_at: string | null;
  last_test_at: string | null;
  last_operational_error: string;
  created_at: string;
  updated_at: string;
}

export interface PrintJob {
  id: number;
  company: number;
  branch: number;
  production_job: number | null;
  is_test: boolean;
  production_event: "new" | "cancel";
  destination: number;
  printer_device: number;
  printer_name: string;
  connection_type: "network" | "usb" | "bluetooth";
  payload_snapshot: Record<string, unknown>;
  status: PrintJobStatus;
  attempts: number;
  last_error: string;
  error_summary: string;
  origin_type: "test" | "command" | "sale" | "system";
  origin_label: string;
  idempotency_key: string;
  processing_at: string | null;
  printed_at: string | null;
  reprint_of: number | null;
  reprint_number: number;
  created_at: string;
  updated_at: string;
}

export type PresentationType =
  | "UN"
  | "CX"
  | "FD"
  | "PK"
  | "PCT"
  | "ENG"
  | "DSP"
  | "BDJ"
  | "SC"
  | "KIT"
  | "OTHER";

export interface PresentationPreset {
  id: number;
  company: number;
  presentation_type: PresentationType;
  code: string;
  description: string;
  conversion_factor: string;
  custom_code?: string;
  custom_name?: string;
  usage_count?: number;
  status: Status;
  created_at: string;
  updated_at: string;
}

export interface EmbeddedProductSupplierUnit {
  id: number;
  purchase_presentation: number | null;
  unit_code: string;
  description: string;
  conversion_factor: string;
  barcode: string;
  is_default: boolean;
  status: Status;
  presentation_preset?: number | null;
  presentation_preset_code?: string;
  presentation_preset_name?: string;
  presentation_type?: PresentationType;
  custom_code?: string;
  custom_name?: string;
}

export interface EmbeddedProductSupplier {
  id: number;
  supplier: number;
  supplier_name: string;
  supplier_code: string;
  is_preferred: boolean;
  is_exclusive: boolean;
  status: Status;
  units: EmbeddedProductSupplierUnit[];
}

export interface Supplier {
  id: number;
  company: number;
  company_name: string;
  branch: number;
  branch_name: string;
  legal_name: string;
  trade_name: string;
  tax_id: string | null;
  phone: string;
  email: string;
  address: Partial<Address>;
  contact_name: string;
  notes: string;
  status: Status;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductSupplierUnit {
  id: number;
  company: number;
  company_name: string;
  product_supplier: number;
  product_name: string;
  supplier_name: string;
  purchase_presentation: number | null;
  unit_code: string;
  description: string;
  conversion_factor: string;
  barcode: string;
  is_default: boolean;
  status: Status;
  presentation_preset?: number | null;
  presentation_preset_code?: string;
  presentation_preset_name?: string;
  presentation_type?: PresentationType;
  custom_code?: string;
  custom_name?: string;
  created_at: string;
  updated_at: string;
}

export interface ProductPurchasePresentation {
  id: number;
  company: number;
  company_name?: string;
  product: number;
  product_name?: string;
  unit_code: string;
  description: string;
  conversion_factor: string;
  status: Status;
  created_at: string;
  updated_at: string;
}

export interface ProductSupplier {
  id: number;
  company: number;
  product: number;
  product_name: string;
  supplier: number;
  supplier_name: string;
  supplier_code: string;
  is_preferred: boolean;
  is_exclusive: boolean;
  status: Status;
  created_at: string;
  updated_at: string;
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
  sku: string | null;
  unit: string;
  cost: string | null;
  sale_price: string;
  is_sellable: boolean;
  is_favorite: boolean;
  available_counter: boolean;
  available_table: boolean;
  available_command: boolean;
  participates_in_service_fee: boolean;
  participates_in_commission: boolean;
  inventory_behavior: InventoryBehavior;
  status: Status;
  archived_at: string | null;
  archived_by: number | null;
  image: string | null;
  components: ProductComponent[];
  fraction_components: ProductFractionComponent[];
  suggested_cost: string | null;
  suggested_sale_price: string | null;
  branch_configuration?: ProductBranchConfiguration | null;
  branch_stock?: ProductBranchStock | null;
  fraction_config?: FractionableProductConfig | null;
  production_destinations?: ProductionDestination[];
  purchase_presentations?: ProductPurchasePresentation[];
  suppliers?: EmbeddedProductSupplier[];
  modifier_groups?: ModifierGroup[];
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
    availability: Record<string, boolean>;
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
  total_cost?: string | null;
  average_unit_cost?: string | null;
  last_unit_cost?: string | null;
  product_status: Status;
  product_deleted: boolean;
  product_deleted_at: string | null;
  inventory_behavior: InventoryBehavior;
  current_quantity: string;
  current_content: string | null;
  package_content?: string | null;
  content_unit?: ContentUnit | null;
  complete_packages?: string | null;
  residual_content?: string | null;
  minimum_quantity: string;
  state: "normal" | "below_minimum" | "zero" | "negative";
  created_at: string;
  updated_at: string;
}

export type PurchaseOrderType = "ORDER" | "DIRECT";
export type PurchaseOrderStatus =
  | "DRAFT"
  | "PLACED"
  | "PARTIALLY_RECEIVED"
  | "RECEIVED"
  | "CANCELLED"
  | "CLOSED_PARTIAL";
export type PayableInstallmentStatus = "PENDING" | "PAID" | "CANCELLED";

export interface PurchaseOrderItem {
  id: number;
  line_number: number;
  product: number;
  product_supplier: number | null;
  product_supplier_unit: number | null;
  ordered_quantity: string;
  received_quantity: string;
  pending_quantity: string;
  product_name: string;
  product_internal_code: string;
  product_stock_unit: string;
  supplier_name: string;
  supplier_tax_id: string;
  supplier_product_code: string;
  presentation_unit_code: string;
  presentation_description: string;
  conversion_factor: string;
  ordered_stock_quantity: string;
  received_stock_quantity: string;
  pending_stock_quantity: string;
  purchase_unit_price?: string;
  gross_subtotal?: string;
  allocated_discount?: string;
  allocated_freight?: string;
  allocated_other_expenses?: string;
  effective_total?: string;
  effective_stock_unit_cost?: string;
  created_at: string;
}

export interface PurchaseReceiptItem {
  id: number;
  purchase_order_item: number;
  ordered_quantity_snapshot: string;
  previously_received_quantity: string;
  received_quantity: string;
  accumulated_quantity: string;
  pending_quantity: string;
  divergence_quantity: string;
  divergence_reason: string;
  conversion_factor_snapshot: string;
  stock_quantity: string;
  ordered_stock_quantity: string;
  previously_received_stock_quantity: string;
  accumulated_stock_quantity: string;
  pending_stock_quantity: string;
  divergence_stock_quantity: string;
  ordered_total?: string;
  received_total?: string;
  difference_total?: string;
  effective_stock_unit_cost_snapshot?: string;
  product_name_snapshot: string;
  supplier_name_snapshot: string;
  presentation_snapshot: string;
  created_at: string;
}

export interface PurchaseReceipt {
  id: string;
  purchase_order: number;
  order_number: string;
  company: number;
  branch: number;
  supplier: number;
  idempotency_key: string;
  notes: string;
  divergence_reason: string;
  confirmed_by: number;
  confirmed_at: string;
  items: PurchaseReceiptItem[];
  created_at: string;
}

export interface PayableInstallment {
  id: number;
  purchase_order: number;
  order_number: string;
  supplier: number;
  supplier_name: string;
  installment_number: number;
  amount: string;
  due_date: string;
  status: PayableInstallmentStatus;
  paid_at: string | null;
  paid_amount: string | null;
  paid_payment_method: string;
  paid_by: number | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  cancellation_reason: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrder {
  id: number;
  company: number;
  company_name: string;
  branch: number;
  branch_name: string;
  supplier: number;
  supplier_name: string;
  order_number: string;
  order_type: PurchaseOrderType;
  status: PurchaseOrderStatus;
  gross_total?: string;
  global_discount?: string;
  freight_total?: string;
  other_expenses_total?: string;
  payable_total?: string;
  document_number: string;
  document_key: string;
  document_series: string;
  document_date: string | null;
  attachment: { name: string; download_url: string } | null;
  attachments: Array<{
    id: number;
    name: string;
    download_url: string;
    status: "active" | "inactive";
  }>;
  notes: string;
  exclusive_supplier_override: boolean;
  created_by: number;
  placed_by: number | null;
  placed_at: string | null;
  closed_by: number | null;
  closed_at: string | null;
  closure_reason: string;
  items: PurchaseOrderItem[];
  installments?: PayableInstallment[];
  receipts: PurchaseReceipt[];
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
  origin?: { kind: string; id: string; label: string } | null;
  nature: string;
  operation_reference: string;
  operation_label: string;
  operation_count: number;
  created_at: string;
  unit_cost_snapshot?: string;
  domain_origin?: string;
  transfer_item?: number | null;
  transfer_resolution?: string | null;
  loss_record?: string | null;
  inventory_count_item?: number | null;
  previous_content?: string | null;
  content_quantity?: string | null;
  final_content?: string | null;
  package_content?: string | null;
  content_unit?: ContentUnit | null;
  previous_complete_packages?: string | null;
  previous_residual_content?: string | null;
  movement_complete_packages?: string | null;
  movement_residual_content?: string | null;
  final_complete_packages?: string | null;
  final_residual_content?: string | null;
}

export type StockTransferStatus = "DRAFT" | "IN_TRANSIT" | "PARTIALLY_RECEIVED" | "RECEIVED" | "RECEIVED_WITH_DIVERGENCE" | "CANCELLED";
export type TransferDivergenceStatus = "PENDING" | "RESOLVED";
export type TransferResolutionType = "FOUND_RECEIPT" | "RETURN_TO_ORIGIN" | "LOSS_IN_TRANSIT" | "AUTHORIZED_CORRECTION";
export type LossReason = "BREAKAGE" | "EXPIRATION" | "DAMAGE" | "INTERNAL_USE" | "MISPLACEMENT" | "OPERATIONAL_ERROR" | "OTHER";
export type InventoryCountStatus = "OPEN" | "CONFIRMED";
export type InventoryCountMode = "FULL" | "PARTIAL";

export interface StockTransferItem {
  id: number; product: number; product_name_snapshot: string; product_internal_code_snapshot: string;
  product_unit_snapshot: string; requested_quantity: string; dispatched_quantity: string | null;
  received_quantity: string; pending_quantity: string | null; origin_unit_cost_snapshot?: string;
  origin_cost_source?: "BRANCH_AVERAGE" | "PRODUCT_FALLBACK"; origin_sale_price_snapshot: string | null;
  movement_ids: number[]; created_at: string;
  package_content_snapshot: string | null; content_unit_snapshot: ContentUnit | null;
}
export interface StockTransferReceiptItem {
  id: number; transfer_item: number; dispatched_quantity_snapshot: string; previously_received_quantity: string;
  received_quantity: string; accumulated_quantity: string; pending_quantity: string; unit_cost_snapshot?: string;
  movement_ids: number[]; created_at: string;
  received_content_snapshot: string | null;
}
export interface StockTransferReceipt {
  id: string; transfer: string; company: number; destination_branch: number; idempotency_key: string;
  finalize: boolean; notes: string; received_by: number; received_at: string;
  items: StockTransferReceiptItem[]; created_at: string;
}
export interface StockTransfer {
  id: string; company: number; origin_branch: number; origin_branch_name: string; destination_branch: number;
  destination_branch_name: string; status: StockTransferStatus; notes: string; created_by: number;
  dispatched_by: number | null; dispatched_at: string | null; cancelled_by: number | null;
  cancelled_at: string | null; cancellation_reason: string; items: StockTransferItem[];
  receipts: StockTransferReceipt[]; created_at: string; updated_at: string;
  dispatch_idempotency_key?: string | null;
}
export interface TransferResolution {
  id: string; divergence: number; idempotency_key: string; resolution_type: TransferResolutionType;
  quantity: string; observation: string; resolved_by: number; resolved_at: string;
  movement_ids: number[]; created_at: string;
}
export interface TransferDivergence {
  id: number; transfer: string; transfer_item: number; product: number; product_name: string;
  dispatched_quantity_snapshot: string; received_quantity_snapshot: string; initial_quantity: string;
  resolved_quantity: string; pending_quantity: string; status: TransferDivergenceStatus;
  unit_cost_snapshot?: string; cost_impact?: string; potential_sale_value: string;
  detected_by: number; detected_at: string; resolutions: TransferResolution[]; created_at: string; updated_at: string;
}
export interface LossRecord {
  id: string; company: number; branch: number; branch_name: string; product: number; product_name: string;
  idempotency_key: string; quantity: string; reason: LossReason; observation: string;
  unit_cost_snapshot?: string; sale_price_snapshot: string; cost_impact?: string; potential_sale_value: string;
  recorded_by: number; recorded_at: string; movement_ids: number[]; created_at: string;
  content_quantity: string | null; content_unit: ContentUnit | null;
  package_content_snapshot?: string | null; complete_packages?: string | null; residual_content?: string | null;
  attachment?: { name: string; download_url: string } | null;
}
export interface InventoryCountItem {
  id: number; product: number; product_name: string; theoretical_quantity: string; counted_quantity: string;
  difference_quantity: string; counted_at: string; unit_cost_snapshot?: string; sale_price_snapshot: string;
  cost_impact?: string; potential_sale_value: string; counted_by: number; observation: string;
  movement_ids: number[]; created_at: string;
  theoretical_content: string | null;
  counted_complete_packages: string | null;
  counted_residual_content: string | null;
  counted_content: string | null;
  difference_content: string | null;
  content_unit: ContentUnit | null;
  package_content_snapshot?: string | null;
  difference_complete_packages?: string | null;
  difference_residual_content?: string | null;
}
export interface InventoryCount {
  id: string; company: number; branch: number; branch_name: string; status: InventoryCountStatus;
  mode: InventoryCountMode;
  observation: string; created_by: number; confirmed_by: number | null; confirmed_at: string | null;
  confirmation_idempotency_key: string | null; items: InventoryCountItem[]; created_at: string; updated_at: string;
}
export interface InventoryQuantityGroup {
  unit: string;
  quantity: string;
  content_quantity?: string | null;
  package_content?: string | null;
  content_unit?: ContentUnit | null;
  complete_packages?: string | null;
  residual_content?: string | null;
}
export type InventoryQuantityGroups = Record<string, string> | InventoryQuantityGroup[];
export interface AdvancedInventoryExactQuantity {
  content_quantity?: string | null;
  package_content?: string | null;
  content_unit?: ContentUnit | null;
  complete_packages?: string | null;
  residual_content?: string | null;
}
export interface AdvancedInventoryProductEventRow extends AdvancedInventoryExactQuantity {
  event_at: string;
  product: number;
  product_name: string;
  unit: string;
  quantity: string;
  movement_ids: number[];
}
export interface AdvancedInventoryDispatchRow extends AdvancedInventoryProductEventRow { transfer: string; transfer_item: number; }
export interface AdvancedInventoryReceiptItemRow extends AdvancedInventoryExactQuantity { transfer_item: number; product: number; product_name: string; unit: string; quantity: string; movement_ids: number[]; }
export interface AdvancedInventoryReceiptRow { receipt: string; transfer: string; event_at: string; received_by: number; finalize: boolean; items: AdvancedInventoryReceiptItemRow[]; movement_ids: number[]; }
export interface AdvancedInventoryResolutionRow extends AdvancedInventoryProductEventRow { resolution: string; divergence: number; transfer: string; transfer_item: number; resolution_type: TransferResolutionType; }
export interface AdvancedInventoryDivergenceRow extends AdvancedInventoryExactQuantity { divergence: number; transfer: string; transfer_item: number; event_at: string; product: number; product_name: string; unit: string; initial_quantity: string; }
export interface AdvancedInventoryLossRow extends AdvancedInventoryProductEventRow { loss: string; reason: LossReason; }
export interface AdvancedInventoryCountRow extends AdvancedInventoryExactQuantity { inventory_count: string; inventory_count_item: number; event_at: string; status: InventoryCountStatus; product: number; product_name: string; unit: string; difference_quantity: string; difference_content?: string | null; movement_ids: number[]; }
export interface AdvancedInventoryTransferStateRow { transfer: string; status: StockTransferStatus; dispatched_at: string; origin_branch: number; destination_branch: number; }
export interface AdvancedInventoryDivergenceStateRow extends AdvancedInventoryExactQuantity { divergence: number; transfer: string; transfer_item: number; status: TransferDivergenceStatus; product: number; unit: string; pending_quantity: string; pending_content?: string | null; }
export interface AdvancedInventoryTransitStateRow extends AdvancedInventoryExactQuantity { transfer: string; transfer_item: number; product: number; unit: string; pending_quantity: string; pending_content?: string | null; }
export interface AdvancedInventoryReport {
  branch: number;
  filters: { start_datetime: string | null; end_datetime: string | null; product: number | null; responsible: number | null; transfer_status: string | null; divergence_status: string | null; inventory_status: string | null; loss_reason: string | null; resolution_type: string | null };
  events: { transfer_dispatches: number; transfer_receipts: number; divergence_resolutions: number; divergences: number; losses: number; inventory_counts: number };
  transfer_statuses: Record<string, number>;
  state_basis: { mode: "current_state" | "as_of_period_end"; as_of: string; event_metrics: "event_time" };
  pending_quantity_basis: "current_state" | "as_of_period_end";
  pending_quantity_as_of: string;
  quantities_by_unit: Record<string, Record<string, string>>;
  financials: { inventory_potential_sale_value: string; loss_potential_sale_value: string; pending_divergence_potential_sale_value: string; in_transit_potential_sale_value: string; inventory_cost_impact?: string; loss_cost_impact?: string; pending_divergence_cost_impact?: string; in_transit_cost_value?: string };
  drill_down: {
    inventory_counts: string; divergences: string; losses: string; transfers: string; movements: string;
    movement_ids: number[];
    resource_ids: { transfers: string[]; receipts: string[]; resolutions: string[]; divergences: string[]; losses: string[]; inventory_counts: string[]; movements: number[] };
    links: { transfers: string[]; divergences: string[]; losses: string[]; inventory_counts: string[]; movements: string[] };
    contract: { event_rows: "filtered_by_each_domain_event_timestamp"; state_rows: "current_state" | "as_of_period_end"; state_as_of: string };
    event_rows: { dispatches: AdvancedInventoryDispatchRow[]; receipts: AdvancedInventoryReceiptRow[]; resolutions: AdvancedInventoryResolutionRow[]; divergences: AdvancedInventoryDivergenceRow[]; losses: AdvancedInventoryLossRow[]; inventory_counts: AdvancedInventoryCountRow[] };
    state_rows: { transfers: AdvancedInventoryTransferStateRow[]; divergences: AdvancedInventoryDivergenceStateRow[]; in_transit: AdvancedInventoryTransitStateRow[] };
  };
}

export interface InventoryWorkflowStockOption {
  stock: number | null;
  product: number;
  product_name: string;
  internal_code: string;
  unit: string;
  category?: number | null;
  category_name?: string;
  current_quantity: string;
  equivalent_quantity: string;
  current_content?: string | null;
  package_content?: string | null;
  content_unit?: ContentUnit | null;
  complete_packages?: string | null;
  residual_content?: string | null;
  fraction_config?: FractionableProductConfig | null;
  unit_cost?: string;
}
export interface InventoryWorkflowBranchOption { id: number; name: string; }
export interface TransferWorkflowOptions {
  origin_branch: InventoryWorkflowBranchOption;
  destination_branches: InventoryWorkflowBranchOption[];
  stocks: InventoryWorkflowStockOption[];
}
export interface TransferReceiveOption {
  transfer_item: number;
  product: number;
  product_name: string;
  internal_code: string;
  unit: string;
  dispatched_quantity: string;
  received_quantity: string;
  pending_quantity: string;
}
export interface TransferReceiveOptions {
  transfer: string;
  origin_branch: number;
  destination_branch: number;
  items: TransferReceiveOption[];
}
export interface InventoryWorkflowOptions {
  branch: InventoryWorkflowBranchOption;
  stocks: InventoryWorkflowStockOption[];
}

export type CashSessionStatus = "open" | "closed" | "cancelled";
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
  cancelled_at?: string | null;
  cancellation_reason?: string;
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
  "dj" | "artist" | "advance" | "promoter" | "supplier" | "other";

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

export interface ModifierOption {
  id: number;
  modifier_group: number;
  name: string;
  option_type: "add" | "remove" | "observation" | "text" | "product_input" | "component_substitution";
  additional_price: string;
  stock_product: number | null;
  stock_product_name: string;
  sort_order: number;
  status: string;
}

export interface ModifierGroup {
  id: number;
  company: number;
  name: string;
  is_required: boolean;
  min_selections: number;
  max_selections: number | null;
  allow_option_quantity: boolean;
  min_total_quantity: string;
  max_total_quantity: string | null;
  required_quantity?: string | null;
  substitution_component: number | null;
  inherit_component_quantity: boolean;
  sort_order: number;
  status: string;
  options?: ModifierOption[];
}

export interface ProductModifierGroup {
  id: number;
  product: number;
  modifier_group: number;
  modifier_group_name?: string;
  sort_order: number;
  status: string;
}

export interface ModifierSelection {
  option: number;
  quantity: string;
}

export interface ModifierSnapshotEntry {
  group_id: number;
  group_name: string;
  option_id: number;
  option_name: string;
  option_type: string;
  additional_price: string;
  selected_quantity: string;
  contribution: string;
  sort_order: number;
}

export interface SaleItem {
  id: number;
  product: number;
  quantity: string;
  product_name: string;
  internal_code: string;
  unit: string;
  unit_cost?: string | null;
  base_unit_price?: string;
  modifier_unit_total?: string;
  modifier_snapshot?: ModifierSnapshotEntry[];
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
  customer: number | null;
  customer_name: string | null;
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
  modifier_snapshot?: ModifierSnapshotEntry[];
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
  sales_revenue: string;
  consumption_charged: string;
  effective_revenue: string;
  service_fee: string;
  total_received: string;
  payment_total: string;
  reconciliation_delta: string;
  // Compatibility aliases still consumed by existing sale detail/report views.
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
  sales_revenue: string;
  consumption_charged: string;
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
  total_received: string;
  payment_total: string;
  reconciliation_delta: string;
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
  sales_revenue: string;
  effective_revenue: string;
  sales_count: number;
  consumption_count: number;
  service_fee: string;
  fee_contained: string;
  sales_received: string;
  commercial_payments: string;
  consumption_charged: string;
  total_received: string;
  payment_total: string;
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
  reversed_sales_revenue: string;
  reversed_consumption_charged: string;
  reversed_effective_revenue: string;
  reversed_service_fee: string;
  reversed_total_received: string;
  reversed_payment_total: string;
  reconciliation_delta: string;
}

export interface ConsumptionReportSummary {
  count: number;
  reference: string;
  charged: string;
  subsidy: string;
  benefit: string;
  quantity: string;
  sales_revenue: string;
  consumption_charged: string;
  effective_revenue: string;
  service_fee: string;
  total_received: string;
  payment_total: string;
  reconciliation_delta: string;
  payment_totals: Array<{
    code: string;
    name: string;
    amount: string;
    payment_total: string;
  }>;
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
  sales_revenue: string;
  effective_revenue: string;
  service_fee: string;
  sales_received: string;
  consumption_charged: string;
  total_received: string;
  payment_total: string;
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
  sales_revenue: string;
  consumption_charged: string;
  effective_revenue: string;
  service_fee: string;
  total_received: string;
  payment_total: string;
  reconciliation_delta: string;
  costs_and_expenses: string;
  historical_sales_cogs?: string;
  historical_consumption_cogs?: string;
  commission?: string;
  operating_expenses?: string;
  fixed_cost?: string;
  estimated_result?: string;
  result?: string;
  margin: string | null;
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
    sales_revenue: string;
    consumption_charged: string;
    effective_revenue: string;
    service_fee: string;
    total_received: string;
    payment_total: string;
    reconciliation_delta: string;
    gross: string;
    commission?: string;
    count: number;
    average: string;
    ticket_average: string;
    account_discount: string;
    item_discount: string;
    manual_discount: string;
    manual_discount_count: number;
    promotion_discount: string;
    total_discount: string;
    cancellations: { count: number; value: string };
    payment_distribution: Array<{
      code: string;
      name: string;
      amount: string;
      payment_total: string;
      percentage: string;
    }>;
    payment_distribution_scope: "operational" | "sales_only";
    hourly_sales: Array<{
      hour: string;
      count: number;
      sales_revenue: string;
      effective_revenue: string;
      service_fee: string;
      total_received: string;
    }>;
    top_products: Array<{
      product_id?: number;
      product_name: string;
      quantity: string;
      sales_revenue: string;
    }>;
    top_categories: Array<{
      category_id?: number;
      category_name: string;
      quantity: string;
      sales_revenue: string;
    }>;
    top_sellers: ReportUserGroup[];
    top_operators: ReportUserGroup[];
    heatmap: Array<{
      weekday: number;
      hour: number;
      count: number;
      sales_revenue: string;
      average: string;
    }>;
    weekly_comparison: {
      current: Array<{
        date: string;
        count: number;
        sales_revenue: string;
      }>;
      previous: Array<{
        date: string;
        count: number;
        sales_revenue: string;
      }>;
    };
    latest_sales: {
      count: number;
      page: number;
      page_size: number;
      total_pages: number;
      next_page: number | null;
      previous_page: number | null;
      ordering: string[];
      results: ReportSale[];
    };
  };
  consumptions?: {
    count: number;
    reference: string;
    charged: string;
    subsidy: string;
    sales_revenue: string;
    consumption_charged: string;
    effective_revenue: string;
    service_fee: string;
    total_received: string;
    payment_total: string;
    reconciliation_delta: string;
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
    sales_revenue: string;
    consumption_charged: string;
    effective_revenue: string;
    service_fee: string;
    total_received: string;
    payment_total: string;
    reconciliation_delta: string;
    costs_and_expenses: string;
    result?: string;
    estimated_result?: string;
    margin?: string | null;
    charged_consumption?: string;
    historical_sales_cogs?: string;
    historical_consumption_cogs?: string;
    commission?: string;
    operating_expenses?: string;
    fixed_cost?: string;
  };
}
export interface ReportUserGroup {
  user: { id: number; name: string } | null;
  count: number;
  gross: string;
  sales_revenue: string;
  consumption_charged: string;
  effective_revenue: string;
  service_fee: string;
  commission?: string;
  commission_rate?: string;
  commission_sale_count?: number;
  customer_total: string;
  total_received: string;
  payment_total: string;
  reconciliation_delta: string;
  payment_reconciliation_delta: string;
  average: string;
  cancellation_count: number;
  cancellation_value: string;
}
export interface ReportResponse<
  T,
  S = Record<string, unknown>,
> extends Paginated<T> {
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

export interface Table {
  id: number;
  branch: number;
  name: string;
  seats: number;
  status: string;
  operational_status?: "free" | "occupied";
  open_commands_count?: number;
  open_commands_total?: string;
  open_commands?: Array<{
    id: number;
    command_number: string;
    identifier: string;
    open_items_count: number;
    confirmed_total: string;
    paid_total: string;
    opened_at: string;
    opened_by_name: string;
  }>;
  created_at: string;
  updated_at: string;
}

export interface Command {
  id: number;
  company: number;
  branch: number;
  table: number | null;
  table_name?: string;
  customer: number | null;
  command_number: string;
  identifier: string;
  status: "open" | "closed";
  opened_by: number;
  closed_at: string | null;
  closed_by: number | null;
  sale: number | null;
  open_items_count?: number;
  confirmed_total?: string;
  created_at: string;
  updated_at: string;
}

export interface Customer {
  id: number;
  company: number;
  name: string;
  phone: string;
  document: string | null;
  email: string;
  birth_date: string | null;
  notes: string;
  status: Status;
  duplicate_warning: { customer_id: number; name: string; message: string } | null;
  created_at: string;
  updated_at: string;
}

export interface CommandPaymentSummary {
  command_id: number;
  command_total: string;
  paid_total: string;
  remaining_total: string;
}

export interface CommandPayment {
  id: number;
  command: number;
  payment_method: number;
  payment_method_name: string;
  payment_method_code: string;
  amount: string;
  received_amount: string | null;
  change_amount: string | null;
  cash_session: number | null;
  operator: number;
  status: "applied" | "reversed";
  idempotency_key: string;
  reversal_of: number | null;
  reversal_reason: string;
  created_at: string;
}

export interface OrderItem {
  id: number;
  order: number;
  product: number;
  quantity: string;
  product_name: string;
  internal_code: string;
  unit: string;
  unit_price: string;
  base_unit_price?: string;
  modifier_unit_total?: string;
  modifier_snapshot?: ModifierSnapshotEntry[];
  unit_cost?: string;
  component_cost_snapshot?: Array<Record<string, unknown>>;
  status: "pending" | "confirmed" | "cancelled";
  confirmed_at: string | null;
  confirmed_by: number | null;
  cancelled_at: string | null;
  cancelled_by: number | null;
  cancellation_reason: string;
  created_at: string;
  updated_at: string;
}
