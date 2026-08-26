"use client";
import { AdminGuard } from "@/components/admin-guard";
import { SalesPdv } from "@/components/sales-pdv";
import { permissions } from "@/lib/permissions";
export default function PdvPage() { return <AdminGuard requiredPermissions={[]} alternatives={[{ permission: permissions.createSale, features: ["counter", "cash_register"] }, { permission: permissions.createConsumption, features: ["consumption"] }]}><SalesPdv /></AdminGuard>; }
