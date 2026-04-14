"use client";

import { useParams } from "next/navigation";
import { OpplanTracker } from "@/components/streaming/opplan-tracker";

export default function PlanPage() {
  const params = useParams();
  const id = params.id as string;

  return <OpplanTracker engagementId={id} />;
}
