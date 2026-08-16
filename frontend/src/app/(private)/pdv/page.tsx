"use client";
import { AdminGuard } from "@/components/admin-guard";
import { SalesPdv } from "@/components/sales-pdv";
import { permissions } from "@/lib/permissions";
export default function PdvPage() { return <AdminGuard requiredPermissions={[permissions.createSale, permissions.createConsumption]}><SalesPdv /></AdminGuard>; }
