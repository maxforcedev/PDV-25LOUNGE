"use client";
import { AdminGuard } from "@/components/admin-guard";
import { PrintQueue } from "@/components/production-ui";
import { permissions } from "@/lib/permissions";
export default function ProductionQueuePage() { return <AdminGuard requiredPermissions={[permissions.viewPrintJobs]}><PrintQueue /></AdminGuard>; }
