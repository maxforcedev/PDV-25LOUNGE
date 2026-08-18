import { redirect } from "next/navigation";
import { ReportsCenter } from "@/components/reports-center";

const legacy: Record<string, string> = {
  sales: "vendas", consumptions: "consumacoes", cash: "caixa",
  withdrawals: "sangrias", "inventory-movements": "consumo-estoque",
  "stock-consumption": "consumo-estoque", "operational-result": "resultado",
};

export default async function ReportsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const report = typeof params.report === "string" ? params.report : "";
  if (report && legacy[report]) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (key !== "report" && typeof value === "string") query.set(key, value);
    });
    redirect(`/relatorios/${legacy[report]}${query.size ? `?${query}` : ""}`);
  }
  return <ReportsCenter />;
}
