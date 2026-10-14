export type AttentionCategory = "inventory" | "financial" | "commands" | "printing";
export type AttentionSeverity = "critical" | "attention" | "informational";

export type OperationalAttentionAlert = {
  identity: string;
  category: AttentionCategory;
  title: string;
  description: string;
  severity: AttentionSeverity;
  state: "active";
  reference: "current" | "period";
  occurred_at: string | null;
  entity: { type: string; id: number | null; name: string; branch_id: number };
  context: { company_id: number; company_name: string; branch_id: number; branch_name: string };
  recommended_action: string;
  route: string | null;
};

export type OperationalAttentionSummary = {
  active_count: number;
  by_severity: Record<AttentionSeverity, number>;
  by_category: Record<AttentionCategory, number>;
};

export type OperationalAttentionResponse = {
  period: { start_datetime: string; end_datetime: string };
  as_of: string;
  filters: { categories: AttentionCategory[]; severities: AttentionSeverity[] };
  available_categories: AttentionCategory[];
  summary: OperationalAttentionSummary;
  count: number;
  next: string | null;
  previous: string | null;
  results: OperationalAttentionAlert[];
};

export function operationalAttentionQuery({
  categories = [],
  severities = [],
  page = 1,
  startDatetime,
  endDatetime,
}: {
  categories?: AttentionCategory[];
  severities?: AttentionSeverity[];
  page?: number;
  startDatetime?: string;
  endDatetime?: string;
}) {
  const query = new URLSearchParams({ page: String(page) });
  if (startDatetime) query.set("start_datetime", startDatetime);
  if (endDatetime) query.set("end_datetime", endDatetime);
  categories.forEach((category) => query.append("category", category));
  severities.forEach((severity) => query.append("severity", severity));
  return query;
}
