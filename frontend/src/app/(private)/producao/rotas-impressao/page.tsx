import { AdminGuard } from "@/components/admin-guard";
import { DocumentPrintRoutes } from "@/components/document-print-routes";
import { PageHeader } from "@/components/page-header";
import { permissions } from "@/lib/permissions";

export default function PrintRoutesPage() {
  return <AdminGuard requiredPermissions={[permissions.managePrintRoutes]}>
    <PageHeader title="Rotas de impressao" description="Defina como cada documento da filial ativa sera impresso." />
    <main className="p-4 sm:p-6 lg:p-8"><DocumentPrintRoutes /></main>
  </AdminGuard>;
}
