"use client";

import { useParams } from "next/navigation";
import { AttackGraphCanvas } from "@/components/graph/attack-graph-canvas";

export default function EngagementGraphPage() {
  const params = useParams();
  const id = params.id as string;

  return <AttackGraphCanvas engagementId={id} />;
}
