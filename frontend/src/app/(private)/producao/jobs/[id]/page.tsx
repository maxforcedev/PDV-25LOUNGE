"use client";
import { useParams } from "next/navigation";
import { AdminGuard } from "@/components/admin-guard";
import { PrintJobDetail } from "@/components/production-ui";
import { permissions } from "@/lib/permissions";
export default function PrintJobPage() { const { id } = useParams<{ id: string }>(); return <AdminGuard requiredPermissions={[permissions.viewPrintJobs]}><PrintJobDetail id={id} /></AdminGuard>; }
