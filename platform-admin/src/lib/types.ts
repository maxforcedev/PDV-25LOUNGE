export interface PlatformUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  permissions: string[];
}

export interface DashboardMetrics {
  active_tenants: number;
  paying_customers: number;
  free: number;
  internal: number;
  active_trials: number;
  expired_trials: number;
  past_due: number;
  contracted_mrr: string;
  new_tenants: number;
  scheduled_cancellations: number;
}

export interface Entitlement {
  id: number;
  plan_version: number;
  capability: number;
  capability_code: string;
  enabled: boolean;
  unlimited: boolean;
  limit_value: number | null;
}

export interface PlanVersion {
  id: number;
  plan: number;
  plan_name: string;
  version: number;
  price: string;
  currency: string;
  billing_period_months: number;
  trial_days: number;
  is_public: boolean;
  is_active: boolean;
  is_used: boolean;
  entitlements: Entitlement[];
  created_at: string;
}

export interface Plan {
  id: number;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  versions: PlanVersion[];
}

export interface Capability {
  id: number;
  code: string;
  name: string;
  value_type: "BOOLEAN" | "INTEGER";
  is_active: boolean;
}

export interface Subscription {
  id: number;
  company: number;
  plan_version: number;
  plan_name: string;
  plan_version_number: number;
  billing_mode: "PAID" | "FREE" | "INTERNAL";
  status: string;
  is_current: boolean;
  current_period_start: string;
  current_period_end: string;
  trial_started_at: string | null;
  trial_ends_at: string | null;
  cancel_at_period_end: boolean;
  cancellation_reason: string;
  cancelled_at: string | null;
}

export interface Payment {
  id: number;
  subscription: number;
  amount: string;
  paid_at: string;
  payment_method: string;
  note: string;
  competency_start: string;
  competency_end: string;
  actor_email: string;
  proof_reference: string;
  idempotency_key: string;
  created_at: string;
}

export interface SupportSession {
  id: number;
  actor: number;
  actor_email: string;
  company: number;
  impersonated_user: number | null;
  mode: "READ_ONLY" | "READ_WRITE";
  reason: string;
  expires_at: string;
  ended_at: string | null;
  created_at: string;
}

export interface SubscriptionRequest {
  id: number;
  subscription: number;
  request_type: "PLAN_CHANGE" | "CANCELLATION";
  requested_plan_version: number | null;
  reason: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  requested_by: number;
  resolved_at: string | null;
  created_at: string;
}

export interface TenantSummary {
  id: number;
  trade_name: string;
  operational_status: string;
  effective_status: string;
  can_operate: boolean;
}

export interface TenantDetail extends TenantSummary {
  legal_name: string;
  cnpj: string | null;
  email: string;
  phone: string;
  owner: { user_id: number; email: string } | null;
  subscription: Subscription | null;
  saas_state: {
    approval_status: string;
    approval_reason: string;
    is_admin_suspended: boolean;
    admin_suspension_reason: string;
    archive_reason: string;
  } | null;
  branches: { id: number; name: string; status: string; is_matrix: boolean }[];
  users: { user_id: number; user__email: string; is_active: boolean; is_owner: boolean; saas_status: string }[];
  payments: Payment[];
  support_sessions: SupportSession[];
}

export interface GlobalSettings {
  id: number;
  auto_approve_signups: boolean;
  past_due_days: number;
  restricted_after_days: number;
  support_session_minutes: number;
  public_signup_billing_mode: "PAID" | "FREE";
  enforcement_enabled: boolean;
  enforcement_enabled_at: string | null;
  platform_name: string;
  logo_url: string;
  compact_logo_url: string;
  favicon_url: string;
  primary_color: string;
  support_email: string;
  support_phone: string;
  institutional_links: Record<string, string>;
}
