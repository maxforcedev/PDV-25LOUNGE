import type { PublicBranding } from "../types/index";

const labels: Record<string, string> = {
  legal_name: "razão social", trade_name: "nome fantasia", cnpj: "CNPJ", address: "endereço", jurisdiction: "cidade/UF",
  commercial_email: "e-mail comercial", legal_email: "e-mail jurídico", privacy_email: "e-mail de privacidade", security_email: "e-mail de segurança",
  dpo_name: "identificação do DPO", dpo_email: "e-mail do DPO", website_url: "site oficial", subprocessors_url: "página de suboperadores",
  effective_date: "data de vigência", support_contact: "canal de suporte", platform_name: "nome da plataforma",
};

export function resolveLegalTemplate(template: string, branding: PublicBranding) {
  const values: Record<string, string> = {
    ...branding.legal_settings,
    platform_name: branding.platform_name,
    support_contact: [branding.support_email, branding.support_phone].filter(Boolean).join(" / "),
  };
  const date = values.effective_date;
  if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    const parsed = new Date(`${date}T12:00:00Z`);
    if (!Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date) {
      values.effective_date = parsed.toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
    }
  }
  const missing = new Set<string>();
  const markdown = template.replace(/\{\{([a-z_]+)\}\}/g, (_, key: string) => {
    const value = values[key]?.trim();
    if (value) return value.replace(/[\r\n]+/g, " ").replace(/\*/g, "");
    missing.add(labels[key] || key);
    return `[${labels[key] || key}: não informado]`;
  });
  return { markdown, missing: [...missing] };
}
