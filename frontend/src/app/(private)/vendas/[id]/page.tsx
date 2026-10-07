"use client";
import { AdminGuard } from "@/components/admin-guard";
import { SaleDetail } from "@/components/sale-detail";
import { permissions } from "@/lib/permissions";
export default function SaleDetailPage() { return <AdminGuard requiredPermissions={[permissions.viewSale, permissions.cancelSale]} requiredFeatures={["counter"]}><SaleDetail expectedOperation="sale" /></AdminGuard>; }
