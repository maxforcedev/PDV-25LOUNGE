import Link from "next/link";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";

export function PublicFooter() {
  return (
    <footer className="border-t border-subtle bg-surface">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1fr_auto] lg:px-8">
        <div>
          <BrandWordmark compact />
          <p className="mt-4 max-w-md text-xs leading-6 text-muted">
            Gestão operacional e ponto de venda para bares, restaurantes, lounges e casas de eventos.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-x-10 gap-y-3 text-xs">
          <Link href="/#recursos" className="font-semibold text-muted hover:text-fg">Recursos</Link>
          <Link href="/ajuda" className="font-semibold text-muted hover:text-fg">Central de ajuda</Link>
          <Link href="/#seguranca" className="font-semibold text-muted hover:text-fg">Segurança</Link>
          <Link href="/login" className="font-semibold text-muted hover:text-fg">Área de clientes</Link>
        </div>
      </div>
      <div className="border-t border-subtle">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-[11px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span>CORE PDV · Operação conectada, do caixa ao relatório.</span>
          <span>Interface em português brasileiro.</span>
        </div>
      </div>
    </footer>
  );
}
