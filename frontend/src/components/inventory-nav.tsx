"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";

const links = [
  ["/estoque", "Visão geral", [permissions.viewInventory]],
  ["/estoque/movimentacoes", "Movimentações", [permissions.viewInventoryHistory]],
  ["/estoque/transferencias", "Transferências", [permissions.viewTransfers, permissions.createTransfer, permissions.dispatchTransfer, permissions.receiveTransfer]],
  ["/estoque/divergencias", "Divergências", [permissions.viewTransfers, permissions.resolveTransfer]],
  ["/estoque/perdas", "Perdas", [permissions.viewAdvancedInventory, permissions.recordLoss]],
  ["/estoque/inventarios", "Inventário", [permissions.viewAdvancedInventory, permissions.performInventoryCount]],
] as const;

export function InventoryNav() {
  const pathname = usePathname();
  const { hasAnyPermission } = useAuth();
  return <nav aria-label="Estoque" className="flex gap-2 overflow-x-auto border-b border-subtle bg-surface px-4 py-3 sm:px-6 lg:px-8">
    {links.filter(([, , required]) => hasAnyPermission(required)).map(([href, label]) => {
      const active = pathname === href || (href !== "/estoque" && pathname.startsWith(`${href}/`));
      return <Link key={href} href={href} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${active ? "bg-primary text-white" : "bg-surface-muted text-muted hover:text-fg"}`}>{label}</Link>;
    })}
  </nav>;
}
