"use client";
import { AdminGuard } from "@/components/admin-guard";
import { SaleDetail } from "@/components/sale-detail";
import { permissions } from "@/lib/permissions";
export default function ConsumptionDetailPage() { return <AdminGuard requiredPermissions={[permissions.viewConsumption, permissions.cancelConsumption]}><SaleDetail expectedOperation="consumption" /></AdminGuard>; }
