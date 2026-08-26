import type { Metadata } from "next";
import { OwnerGuard } from "@/components/owner-guard";
import { SubscriptionCenter } from "@/components/subscription-center";

export const metadata: Metadata = {
  title: "Assinatura | CORE PDV",
};

export default function SubscriptionPage() {
  return <OwnerGuard><SubscriptionCenter /></OwnerGuard>;
}
