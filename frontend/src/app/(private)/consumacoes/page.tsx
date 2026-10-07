"use client";
import { AdminGuard } from "@/components/admin-guard";
import { SalesList } from "@/components/sales-list";
import { permissions } from "@/lib/permissions";
export default function ConsumptionsPage() { return <AdminGuard requiredPermissions={[permissions.viewConsumption]} requiredFeatures={["consumption"]}><SalesList operation="consumption" /></AdminGuard>; }
