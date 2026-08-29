"use client";
import { AdminGuard } from "@/components/admin-guard";
import { Printers } from "@/components/production-ui";
import { permissions } from "@/lib/permissions";
export default function PrintersPage() { return <AdminGuard requiredPermissions={[permissions.managePrinters]}><Printers /></AdminGuard>; }
