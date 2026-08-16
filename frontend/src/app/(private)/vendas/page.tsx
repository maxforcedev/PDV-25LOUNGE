"use client";
import { AdminGuard } from "@/components/admin-guard";
import { SalesList } from "@/components/sales-list";
import { permissions } from "@/lib/permissions";
export default function SalesPage() { return <AdminGuard requiredPermissions={[permissions.viewSale]}><SalesList operation="sale" /></AdminGuard>; }
